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

from app.analysis import prs, variations, volume
from app.analysis.notes import extract_note_themes
from app.chat.prompt import NO_DASH_RULE, load_coach_context
from app.config import get_settings
from app.hevy import HevyClient
from app.hevy.schemas import strip_dashes
from app.llm import get_async_anthropic
from app.state import get_preferences
from app.models import RoutineProposal, WeeklyReview, Workout

# One structured response: narrative + a few complete, approvable routine changes.
_SET = {
    "type": "object",
    "properties": {
        "type": {"type": "string", "enum": ["normal", "warmup", "failure", "dropset"]},
        "weight_kg": {"type": ["number", "null"]},
        "reps": {"type": ["integer", "null"]},
    },
    "required": ["type", "weight_kg", "reps"],
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
                "exercises": {"type": "array", "items": _EXERCISE},
            },
            "required": ["title", "notes", "exercises"],
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
routines below (weights in kg).

Write:
1. `narrative`: a direct, coach-voiced markdown review of the past week. Cover what
   progressed (PRs), what's stalling (heavy-lane only - ignore hypertrophy-day dips), how
   their volume sits vs targets (especially side/rear delts, their priority weak point),
   and anything their notes flag (pain, fatigue, technique). Be specific and concise.
2. `proposed_changes`: 2 to 4 concrete, high-value routine changes. Prefer `update` to an
   existing routine (give its `target_routine_id`); use `create` only for a genuinely new
   routine. For an `update`, `routine` must be the COMPLETE routine as it should look after
   your change (all exercises and sets), because the push overwrites the whole routine. Use
   the user's real exercise names. Apply progressive overload where they beat targets at low
   RPE; add lateral/rear-delt volume only if under target; do NOT add pressing volume to fix
   delts; address any stalled or grindy lift explicitly. `changes_summary` is a one-line diff.

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
        f"Write the `narrative` with weights in {unit} (signals are in kg; 1 kg = 2.2046 lb). "
        "The routine `weight_kg` fields must stay in KILOGRAMS (they are sent to Hevy)."
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


async def _bodyweight_signal(client: HevyClient) -> Optional[dict]:
    """Latest bodyweight + recent trend (kg and lb), for context vs the user's target."""
    try:
        measurements = await client.get_body_measurements(max_pages=6)
    except Exception:
        return None
    points = sorted(
        ({"date": m["date"], "weight_kg": m["weight_kg"]} for m in measurements if m.get("weight_kg")),
        key=lambda p: p["date"],
    )
    if not points:
        return None
    latest = points[-1]
    return {
        "latest_kg": latest["weight_kg"],
        "latest_lb": round(latest["weight_kg"] * 2.2046, 1),
        "latest_date": latest["date"],
        "trend": points[-10:],
    }


def _current_routines(routines_raw: list[dict]) -> list[dict]:
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
                            {"type": s.get("type"), "weight_kg": s.get("weight_kg"), "reps": s.get("reps")}
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
        "volume": volume.muscle_volume_report(session, start, end),
        "prs": prs.prs_in_period(session, start, end),
        "heavy_lane_stalls": variations.variation_aware_stalled(
            session, settings.stall_lookback_sessions, settings.heavy_rep_threshold
        ),
        "notes": notes.get("themes", []),
        "bodyweight": await _bodyweight_signal(client),
    }

    routines = _current_routines(await client.get_routines())

    if settings.anthropic_configured:
        review = await _generate_llm(settings, signals, routines, get_preferences(session)["weight_unit"])
    else:
        review = _fallback(signals)

    narrative = strip_dashes(review.get("narrative", "")).strip()

    proposals: list[dict] = []
    for ch in review.get("proposed_changes", []):
        row = RoutineProposal(
            status="pending",
            kind=ch.get("kind", "update"),
            target_routine_id=ch.get("target_routine_id"),
            source="weekly",
            title=ch.get("title", "Routine update"),
            payload=ch.get("routine", {}),
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
