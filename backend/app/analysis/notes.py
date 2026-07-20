"""Notes intelligence: mine the user's free-text workout notes for signal a generic
tracker can't see (pain/tweaks, fatigue, technique flags), each tied to a lift and date.

Uses one structured-output Claude call so the result is machine-usable by the weekly
review. Falls back to the raw notes list if Anthropic isn't configured."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from sqlmodel import Session, select

from app.chat.prompt import NO_DASH_RULE
from app.config import get_settings
from app.hevy.schemas import strip_dashes
from app.llm import get_async_anthropic
from app.models import Workout, WorkoutSet
from app.usage import record_usage

_THEME_SCHEMA = {
    "type": "object",
    "properties": {
        "themes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "category": {"type": "string", "enum": ["pain", "fatigue", "technique", "other"]},
                    "exercise": {"type": ["string", "null"]},
                    "date": {"type": ["string", "null"]},
                    "quote": {"type": "string", "description": "the user's own words"},
                    "insight": {"type": "string", "description": "brief interpretation"},
                },
                "required": ["category", "exercise", "date", "quote", "insight"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["themes"],
    "additionalProperties": False,
}


def collect_notes(session: Session, start: datetime, end: datetime) -> list[dict]:
    """Distinct notes in the window: per-exercise notes + workout-level descriptions."""
    notes: list[dict] = []
    seen: set = set()
    for r in session.exec(select(WorkoutSet)).all():
        if not r.exercise_notes or not r.workout_start_time:
            continue
        if not (start <= r.workout_start_time <= end):
            continue
        key = (r.workout_id, r.exercise_title, r.exercise_notes)
        if key in seen:
            continue
        seen.add(key)
        notes.append(
            {
                "date": r.workout_start_time.date().isoformat(),
                "exercise": r.exercise_title,
                "text": r.exercise_notes,
            }
        )
    for w in session.exec(select(Workout)).all():
        if w.description and w.start_time and start <= w.start_time <= end:
            notes.append(
                {"date": w.start_time.date().isoformat(), "exercise": None, "text": w.description}
            )
    return notes


async def extract_note_themes(session: Session, start: datetime, end: datetime) -> dict:
    raw = collect_notes(session, start, end)
    settings = get_settings()
    if not raw or not settings.anthropic_configured:
        return {"themes": [], "raw_notes": raw}

    client = get_async_anthropic()
    user_msg = (
        "These are the user's workout notes from the past week (their own words). Extract the "
        "meaningful themes: pain/tweaks, fatigue/recovery signals, and technique/execution "
        "flags. Ignore neutral logging chatter. Tie each to the exercise and date when present, "
        "quote their words, and add a one-line interpretation.\n\n"
        f"NOTES:\n{json.dumps(raw, indent=2)}"
    )
    # Stream with a generous cap: adaptive thinking can spend the whole budget reasoning
    # before emitting the JSON, so at max_tokens=1500 the turn hit the cap with truncated
    # output and note themes came back empty. Streaming keeps a high cap safe.
    async with client.messages.stream(
        model=settings.anthropic_model,
        max_tokens=8000,
        thinking={"type": "adaptive"},
        output_config={"format": {"type": "json_schema", "schema": _THEME_SCHEMA}},
        system=f"You extract signal from a lifter's training notes. {NO_DASH_RULE}",
        messages=[{"role": "user", "content": user_msg}],
    ) as stream:
        resp = await stream.get_final_message()
    if resp.usage:
        record_usage("notes", settings.anthropic_model, resp.usage.input_tokens or 0, resp.usage.output_tokens or 0)
    text = next((b.text for b in resp.content if b.type == "text"), "{}")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {"themes": [], "raw_notes": raw}

    for t in data.get("themes", []):
        t["quote"] = strip_dashes(t.get("quote"))
        t["insight"] = strip_dashes(t.get("insight"))
    data["raw_notes"] = raw
    return data
