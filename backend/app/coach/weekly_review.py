"""Weekly Review generation.

Assembles the week's signals (variation-aware volume, PRs, heavy-lane stalls, mined notes,
adherence) plus the user's current routines, then makes one structured Claude call that
writes a coach-voiced narrative AND proposes routine changes. Proposed changes are stored
as approval-gated RoutineProposal rows (kind=update -> PUT overwrite of an existing routine,
kind=create -> POST new). Nothing is pushed to Hevy here."""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from collections.abc import AsyncIterator
from datetime import datetime, timedelta
from typing import Optional

from sqlmodel import Session, select

from app.analysis import body, progression, prs, volume
from app.analysis.changes import recent_changes
from app.analysis.notes import extract_note_themes
from app.analysis.training_state import training_state
from app.analysis.trends import WORKING_SET_TYPES
from app.chat.prompt import NO_DASH_RULE, load_coach_context
from app.config import get_settings
from app.hevy import HevyClient
from app.hevy.schemas import strip_dashes
from app.llm import get_async_anthropic
from app.state import get_preferences
from app.models import RoutineProposal, WeeklyReview, Workout, WorkoutSet
from app.units import routine_weights_to_kg, to_display
from app.usage import record_usage

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

`recent_performance` is your GROUND TRUTH: for each exercise in the program it lists the ACTUAL
sets (weight x reps, sometimes rpe and a note) the user logged in their most recent session(s).
Every weight and rep you prescribe MUST come from what they actually did here, progressed
sensibly - NOT copied from the current routine. Read their per-set note too (it often explains
a weight they changed mid-session).

`training_state` is the LONG VIEW that per-lift verdicts miss. `stalled_lifts` are lifts that
have set no new best on any axis for many of their own sessions (`sessions_stuck`,
`weeks_stuck`); a `swap_candidate` has been stuck long enough that another small nudge won't
help. `deload` aggregates systemic fatigue (`regressing_lifts`, `fatigue_notes`,
`weeks_since_lighter_week`) into a `recommend_deload` flag with `reasons`. Act on it:
- Name genuinely STAGNATING lifts in the narrative. For a normal stall, change the STIMULUS
  (new rep scheme, an intensity technique like a drop set or double, add a hard set), not just
  the weight. For a `swap_candidate`, propose swapping the movement for a close variation
  (kind=update that replaces it) and say why (stale stimulus for N weeks, not what they were
  doing wrong).
- If `deload.recommend_deload` is true, or the indicators clearly pile up, say so plainly and,
  if warranted, propose a lighter deload week (cut working sets ~40-50% or top loads ~10%),
  citing the `reasons`. Never recommend a deload with no basis.
- JUDGMENT: a lift the user is holding on purpose (a note or `routine_changes` shows they
  approve the current scheme, e.g. a heavy top single they signed off on) is "stalled" by the
  numbers but is NOT a problem - respect it, do not force a swap or a change on it.

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

   Reason across the WHOLE split, not one day in isolation. Look at every current routine
   together: if a muscle is trained redundantly on adjacent days (e.g. rear delts on both
   push and pull) and its weekly volume in `muscle_volume` is at or over target, propose
   TRIMMING the redundant work (consolidate to fewer days), do not add more. Read the current
   routines' exercise `notes` and the user's logged workout `notes` for the week: if they flag
   a muscle as fried / already-hit or a movement as redundant, act on it. Do not program the
   same movement on back-to-back days without a clear reason. Aim for the most optimal weekly
   distribution, not just a locally-sensible single day.

   GROUND EVERY NUMBER, EXPLAIN IT, AND GIVE A PROGRESSION TRIGGER. This is the whole point -
   the user wants a coach who makes informed decisions and a clear path forward, not one who
   copies last week's numbers into a perpetual stuck point. For each exercise you propose, set
   its `weight` and `reps` from `recent_performance` (what they actually hit), and its `notes`
   MUST do BOTH of these:
   1. Explain the current loading from their real data: if you HOLD a weight, say why (they
      ground the last set, missed reps, a per-set note flagged it too heavy, or they just topped
      the rep range); if you PROGRESS, cite what they hit ("you got 10/10/9, chase 11s"); if you
      BACK OFF, tie it to their data or a note.
   2. State the concrete PROGRESSION TRIGGER: the specific, checkable condition that earns the
      NEXT increase, AND the exact next weight. Use double progression. Examples: "hit 10/10/10
      clean at 225 and it's 230 next"; "all three sets of 335x3 with fast bar speed earns 345";
      "once every set reaches 12 reps at 155, go 165". EVERY working lift gets this, including
      ones you are holding or not otherwise changing - the user must always know exactly what
      unlocks more weight, so NO lift ever reads as permanently stuck. Never write a vague
      trigger like "progress when ready"; name the number and the condition.

   When you cite the user's own notes, quote them VERBATIM - never embellish, add adjectives, or
   infer detail they didn't write (if they wrote "solid", do not upgrade it to "moved clean").

   Each set's `weight` is in the user's DISPLAY unit (stated below), NOT kilograms - the app
   converts it. The current routines below are already shown in that unit, so keep the same
   unit. Use real, round gym numbers (in pounds use multiples of 5 like 135, 185, 225; in
   kilograms multiples of 2.5). Give every working set (normal/failure/dropset) a concrete
   `weight` AND `reps`; use `weight: null` only for genuinely bodyweight movements. Never emit
   converted-looking fractions like 132.3.
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
    # Stream with a generous cap. Adaptive thinking over the full week of signals + every
    # current routine spends a lot of output budget reasoning BEFORE it emits any JSON. At
    # max_tokens=8000 the think phase alone exhausted the budget, so the turn ended on
    # stop_reason="max_tokens" with truncated/empty JSON, json.loads failed, and the review
    # came back blank. Streaming makes a high cap safe (no request timeout) and we only pay
    # for tokens produced. Mirrors the chat agent's fix.
    async with client.messages.stream(
        model=settings.anthropic_model,
        max_tokens=24000,
        thinking={"type": "adaptive"},
        output_config={"format": {"type": "json_schema", "schema": _REVIEW_SCHEMA}},
        system=f"{load_coach_context()}\n\n{NO_DASH_RULE}",
        messages=[{"role": "user", "content": user_msg}],
    ) as stream:
        resp = await stream.get_final_message()
    if resp.usage:
        record_usage("weekly", settings.anthropic_model, resp.usage.input_tokens or 0, resp.usage.output_tokens or 0)
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


def _recent_performance(
    session: Session, routines_raw: list[dict], unit: str, sessions_back: int = 2
) -> list[dict]:
    """For each exercise in the current program, the ACTUAL working sets the user logged in
    their most recent session(s) - what they really hit, not what was prescribed. This is the
    ground truth the coach prescribes from, so a proposed weight is a decision about real
    performance rather than a copy of the routine. Weights in the user's display unit."""
    wanted_tids = {
        ex.get("exercise_template_id")
        for r in routines_raw
        for ex in r.get("exercises", [])
        if ex.get("exercise_template_id")
    }
    wanted_titles = {
        (ex.get("title") or "").lower() for r in routines_raw for ex in r.get("exercises", [])
    }

    by_ex: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    title_for: dict[str, str] = {}
    for s in session.exec(select(WorkoutSet)).all():
        if s.set_type not in WORKING_SET_TYPES or not s.reps or s.weight_kg is None:
            continue
        if s.exercise_template_id not in wanted_tids and s.exercise_title.lower() not in wanted_titles:
            continue
        key = s.exercise_template_id or s.exercise_title
        by_ex[key][s.workout_id].append(s)
        title_for.setdefault(key, s.exercise_title)

    out = []
    for key, workouts in by_ex.items():
        recent_sessions = sorted(
            workouts.values(),
            key=lambda ss: ss[0].workout_start_time or datetime.min,
            reverse=True,
        )[:sessions_back]
        history = []
        for ss in recent_sessions:
            ordered = sorted(ss, key=lambda x: x.set_index)
            history.append(
                {
                    "date": ordered[0].workout_start_time.date().isoformat()
                    if ordered[0].workout_start_time
                    else None,
                    "sets": [
                        {"weight": to_display(x.weight_kg, unit), "reps": x.reps, **({"rpe": x.rpe} if x.rpe else {})}
                        for x in ordered
                    ],
                    "note": next((x.exercise_notes for x in ordered if x.exercise_notes), None),
                }
            )
        out.append({"exercise": title_for[key], "recent": history})
    return out


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
                        "notes": ex.get("notes"),
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


# Rotating messages shown during the single long LLM call, so a ~2 minute generation gives
# continuous feedback instead of a frozen spinner.
_DRAFT_HEARTBEATS = (
    "Weighing progression across your lifts",
    "Balancing weekly volume by muscle",
    "Writing it up in plain language",
    "Finalizing proposed routine changes",
)


async def stream_weekly_review(session: Session, client: HevyClient) -> AsyncIterator[dict]:
    """Generate the weekly review, yielding progress events as it goes:
    {"type": "step", "message": ...} for each phase, then {"type": "done", "review": {...}}.
    The heavy LLM call emits heartbeat steps while it runs so the UI keeps moving."""
    settings = get_settings()
    end = datetime.utcnow()
    start = end - timedelta(days=settings.weekly_review_days)

    weight_unit = get_preferences(session)["weight_unit"]

    yield {"type": "step", "message": "Reading your training week"}
    training_days = len(
        {
            w.start_time.date()
            for w in session.exec(select(Workout)).all()
            if w.start_time and start <= w.start_time <= end
        }
    )

    yield {"type": "step", "message": "Mining your workout notes"}
    notes = await extract_note_themes(session, start, end)

    yield {"type": "step", "message": "Crunching volume, progression, and PRs"}
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
    # Long-horizon judgments: which lifts are truly stagnating / swap candidates, and whether
    # the systemic picture warrants a deload. Derived from the per-lift verdicts + notes above.
    signals["training_state"] = training_state(session, signals["progression"], signals["notes"])

    yield {"type": "step", "message": "Pulling your current routines and recent sessions"}
    routines_raw = await client.get_routines()
    routines = _current_routines(routines_raw, weight_unit)
    # Ground truth for prescribing: what the user ACTUALLY lifted recently, per program lift.
    signals["recent_performance"] = _recent_performance(session, routines_raw, weight_unit)

    yield {"type": "step", "message": "Drafting your review and proposing updates"}
    if settings.anthropic_configured:
        llm_task = asyncio.create_task(_generate_llm(settings, signals, routines, weight_unit))
        for hb in _DRAFT_HEARTBEATS:
            done, _ = await asyncio.wait({llm_task}, timeout=12)
            if done:
                break
            yield {"type": "step", "message": hb}
        review = await llm_task
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

    yield {
        "type": "done",
        "review": {
            "id": wr.id,
            "generated_at": wr.generated_at.isoformat(),
            "period": signals["period"],
            "narrative": narrative,
            "signals": signals,
            "proposals": proposals,
        },
    }


async def generate_weekly_review(session: Session, client: HevyClient) -> dict:
    """Non-streaming path (auto-review / cron): drain the generator, return the final review."""
    result: dict = {}
    async for ev in stream_weekly_review(session, client):
        if ev.get("type") == "done":
            result = ev["review"]
    return result
