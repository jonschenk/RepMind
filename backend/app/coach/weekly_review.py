"""Weekly Review generation.

Assembles the week's signals (variation-aware volume, PRs, heavy-lane stalls, mined notes,
adherence) plus the user's current routines, then makes one structured Claude call that
writes a coach-voiced narrative AND proposes routine changes. Proposed changes are stored
as approval-gated RoutineProposal rows (kind=update -> PUT overwrite of an existing routine,
kind=create -> POST new). Nothing is pushed to Hevy here."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Optional

from sqlmodel import Session, select

from app.analysis import body, progression, prs, volume
from app.analysis.changes import recent_changes
from app.analysis.notes import extract_note_themes
from app.chat.prompt import NO_DASH_RULE, load_coach_context
from app.config import get_settings
from app.hevy import HevyClient
from app.hevy.schemas import strip_dashes
from app.llm import get_async_anthropic
from app.state import get_preferences
from app.models import RoutineProposal, WeeklyReview, Workout
from app.units import routine_weights_to_kg, to_display

# One structured response: narrative + a few complete, approvable routine changes.
_SET = {
    "type": "object",
    "properties": {
        "type": {"type": "string", "enum": ["normal", "warmup", "failure", "dropset"]},
        # In the user's DISPLAY unit (see instructions), converted to kg server-side. null
        # only for genuinely bodyweight movements.
        "weight": {"type": ["number", "null"]},
        "reps": {"type": ["integer", "null"]},
    },
    "required": ["type", "weight", "reps"],
    "additionalProperties": False,
}
_EXERCISE = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "rest_seconds": {"type": ["integer", "null"]},
        "notes": {"type": ["string", "null"]},
        "sets": {"type": "array", "items": _SET},
    },
    "required": ["name", "rest_seconds", "notes", "sets"],
    "additionalProperties": False,
}
_CHANGE = {
    "type": "object",
    "properties": {
        "kind": {"type": "string", "enum": ["update", "create"]},
        "target_routine_id": {"type": ["string", "null"], "description": "required for kind=update"},
        "title": {"type": "string"},
        "rationale": {"type": "string"},
        "changes_summary": {"type": "string", "description": "short human diff for the card"},
        "routine": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "notes": {"type": ["string", "null"]},
                # Folder for a kind=create routine; null for an update (it keeps its folder).
                "folder": {"type": ["string", "null"]},
                "exercises": {"type": "array", "items": _EXERCISE},
            },
            "required": ["title", "notes", "folder", "exercises"],
            "additionalProperties": False,
        },
    },
    "required": ["kind", "target_routine_id", "title", "rationale", "changes_summary", "routine"],
    "additionalProperties": False,
}
_REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "narrative": {"type": "string"},
        "proposed_changes": {"type": "array", "items": _CHANGE},
    },
    "required": ["narrative", "proposed_changes"],
    "additionalProperties": False,
}

_INSTRUCTIONS = """
You are writing this user's weekly training review. Use the signals and their current
routines below. (Analysis signals are in kilograms; the current routines are shown in the
user's display unit - see the unit note.)

How to read the data (important): this user trains mostly hypertrophy - only ~14% of their
sets are heavy (see `training_mix`), so DO NOT judge progress by estimated 1RM alone. The
`progression` list is the primary signal: each lift has a verdict (progressing / holding /
regressing) judged across load, reps, AND volume-load, with a reason. A lift adding reps or
volume is progressing even with a flat 1RM - do not call it stalled. Treat a lift as a
problem only if it is `regressing`, or `holding` while it matters. `est_1rm_prs` is a
nice-to-have, not the headline. Effort/RPE is not logged, so infer effort from notes.

Write:
1. `narrative`: a direct, coach-voiced markdown review of the past week. Lead with what's
   genuinely progressing vs regressing (from `progression`, citing the reason - volume, reps,
   or load), how volume sits vs targets (especially side/rear delts, their priority weak
   point), whether the rep-range mix fits their goals, and anything their notes flag (pain,
   fatigue, technique). Be specific and concise.
2. `proposed_changes`: 2 to 4 concrete, high-value routine changes. Prefer `update` to an
   existing routine (give its `target_routine_id`); use `create` only for a genuinely new
   routine. For an `update`, `routine` must be the COMPLETE routine as it should look after
   your change (all exercises and sets), because the push overwrites the whole routine. Use
   the user's real exercise names. Drive progressive overload the way they actually train
   (more reps or more volume, not just heavier); prioritize the `regressing` lifts; add
   lateral/rear-delt volume only if under target; do NOT add pressing volume to fix delts.
   `changes_summary` is a one-line diff.

   Each set's `weight` is in the user's DISPLAY unit (stated below), NOT kilograms - the app
   converts it. The current routines below are already shown in that unit, so keep the same
   unit. Use real, round gym numbers (in pounds use multiples of 5 like 135, 185, 225; in
   kilograms multiples of 2.5), grounded in the weights they actually lift. Give every
   working set (normal/failure/dropset) a concrete `weight` AND `reps`; use `weight: null`
   only for genuinely bodyweight movements. Never emit converted-looking fractions like 132.3.
   Set `routine.folder` to null for an `update` (it keeps its existing folder). For a `create`
   that belongs with a split, set `folder` to that split's short folder name.

`routine_changes` lists routine edits the user already made this week (via chat or a prior
review), each with a date, source, and what/why. Honor them: if a logged session differs
from the current routine and a change is dated around then, that is the user deliberately
adjusting the plan (e.g. dialing back unrealistic volume or weight), NOT going off-program -
do not scold it or propose undoing it. Build on those changes rather than reverting them.

If `bodyweight.stale` is true, that reading is their last known weight (as of `as_of`), not
current, so say so rather than treating it as today's weight. Use relative strength (est-1RM
per bodyweight) when it adds insight.

Respect the user's training style and never use em dashes.
""".strip()


def _fallback(signals: dict) -> dict:
    delt = next((v for v in signals["volume"] if v.get("priority")), None)
    lines = ["## This week", f"- Trained {signals['training_days']} days."]
    if signals["prs"]:
        lines.append("- PRs: " + ", ".join(p["exercise"] for p in signals["prs"][:3]))
    if signals["heavy_lane_stalls"]:
        lines.append("- Stalling (heavy): " + ", ".join(s["exercise"] for s in signals["heavy_lane_stalls"][:3]))
    if delt:
        lines.append(f"- Side/rear delts: {delt['sets']} sets (target {delt['mev']}-{delt['mav']}, {delt['status']}).")
    return {"narrative": "\n".join(lines), "proposed_changes": []}


async def _generate_llm(settings, signals: dict, routines: list[dict], unit: str) -> dict:
    client = get_async_anthropic()
    unit_note = (
        f"The user's display unit is {unit}. Write the `narrative` with weights in {unit}. "
        f"The analysis SIGNALS below are in kilograms (1 kg = 2.2046 lb), but the CURRENT "
        f"ROUTINES and every routine `weight` you propose are in {unit} - do not switch to kg."
    )
    user_msg = (
        f"{_INSTRUCTIONS}\n\n{unit_note}\n\nSIGNALS:\n{json.dumps(signals, indent=2, default=str)}"
        f"\n\nCURRENT ROUTINES:\n{json.dumps(routines, indent=2, default=str)}"
    )
    resp = await client.messages.create(
        model=settings.anthropic_model,
        max_tokens=8000,
        thinking={"type": "adaptive"},
        output_config={"format": {"type": "json_schema", "schema": _REVIEW_SCHEMA}},
        system=f"{load_coach_context()}\n\n{NO_DASH_RULE}",
        messages=[{"role": "user", "content": user_msg}],
    )
    text = next((b.text for b in resp.content if b.type == "text"), "{}")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"narrative": "", "proposed_changes": []}


def _bodyweight_signal(session: Session) -> Optional[dict]:
    """Latest bodyweight/fat% + relative strength from the synced measurements, with a
    stale flag so the coach knows when the reading is old."""
    bs = body.body_stats(session)
    if not bs.get("has_data"):
        return None
    latest = bs["latest"]
    return {
        "latest_kg": latest["weight_kg"],
        "latest_lb": round(latest["weight_kg"] * 2.2046, 1),
        "fat_percent": latest["fat_percent"],
        "as_of": latest["date"],
        "days_since": bs["days_since"],
        "stale": bs["stale"],
        "relative_strength": bs["relative_strength"],
    }


def _current_routines(routines_raw: list[dict], unit: str) -> list[dict]:
    """Current Hevy routines with set weights converted to the user's display unit, so the
    model reasons and proposes in one consistent unit."""
    out = []
    for r in routines_raw:
        out.append(
            {
                "id": r.get("id"),
                "title": r.get("title"),
                "exercises": [
                    {
                        "title": ex.get("title"),
                        "exercise_template_id": ex.get("exercise_template_id"),
                        "sets": [
                            {"type": s.get("type"), "weight": to_display(s.get("weight_kg"), unit), "reps": s.get("reps")}
                            for s in ex.get("sets", [])
                        ],
                    }
                    for ex in r.get("exercises", [])
                ],
            }
        )
    return out


async def generate_weekly_review(session: Session, client: HevyClient) -> dict:
    settings = get_settings()
    end = datetime.utcnow()
    start = end - timedelta(days=settings.weekly_review_days)

    training_days = len(
        {
            w.start_time.date()
            for w in session.exec(select(Workout)).all()
            if w.start_time and start <= w.start_time <= end
        }
    )
    notes = await extract_note_themes(session, start, end)
    signals = {
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "training_days": training_days,
        "training_mix": progression.training_mix(session),
        "muscle_volume": volume.muscle_volume_report(session, start, end),
        # Primary progress signal: verdict across load + reps + volume per lift.
        "progression": progression.progression_overview(session, settings.stall_lookback_sessions),
        "est_1rm_prs": prs.prs_in_period(session, start, end),
        "notes": notes.get("themes", []),
        "bodyweight": _bodyweight_signal(session),
        # Routine edits (chat + weekly) so a deliberate mid-week adjustment isn't misread as
        # the user going off-program.
        "routine_changes": recent_changes(session, since=start),
    }

    weight_unit = get_preferences(session)["weight_unit"]
    routines = _current_routines(await client.get_routines(), weight_unit)

    if settings.anthropic_configured:
        review = await _generate_llm(settings, signals, routines, weight_unit)
    else:
        review = _fallback(signals)

    narrative = strip_dashes(review.get("narrative", "")).strip()

    proposals: list[dict] = []
    for ch in review.get("proposed_changes", []):
        # Model proposes `weight` in the display unit; store canonical `weight_kg`.
        routine_payload = routine_weights_to_kg(ch.get("routine", {}), weight_unit)
        row = RoutineProposal(
            status="pending",
            kind=ch.get("kind", "update"),
            target_routine_id=ch.get("target_routine_id"),
            source="weekly",
            title=ch.get("title", "Routine update"),
            payload=routine_payload,
            diff={
                "rationale": strip_dashes(ch.get("rationale")),
                "changes_summary": strip_dashes(ch.get("changes_summary")),
            },
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        proposals.append(
            {
                "id": row.id,
                "kind": row.kind,
                "target_routine_id": row.target_routine_id,
                "title": row.title,
                "diff": row.diff,
                "payload": row.payload,
                "status": row.status,
            }
        )

    wr = WeeklyReview(
        period_start=start,
        period_end=end,
        payload={"narrative": narrative, "signals": signals, "proposal_ids": [p["id"] for p in proposals]},
    )
    session.add(wr)
    session.commit()
    session.refresh(wr)

    return {
        "id": wr.id,
        "generated_at": wr.generated_at.isoformat(),
        "period": signals["period"],
        "narrative": narrative,
        "signals": signals,
        "proposals": proposals,
    }
