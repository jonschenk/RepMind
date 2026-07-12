"""Tool definitions + read-tool executors for the chat agent.

Read tools run against the local SQLite cache (fast, deterministic, free). `list_routines`
reads live from Hevy. `propose_routine` is intentionally NOT executed here — the agent
loop captures it and turns it into an approval-gated preview (see agent.py)."""

from __future__ import annotations

import json
from typing import Any

from sqlmodel import Session, select

from app.analysis import progression, trends
from app.config import get_settings
from app.hevy import HevyClient
from app.hevy.resolve import search_templates
from app.models import Workout, WorkoutSet

# --- Tool schemas sent to Claude --------------------------------------------------

READ_TOOLS: list[dict] = [
    {
        "name": "get_progression",
        "description": (
            "Per-lift progression verdicts (progressing / holding / regressing) for lifts "
            "currently in rotation, judged across load, reps, AND volume-load together, each "
            "with a reason and the lift's rep-range mix. Prefer this over estimated 1RM for "
            "judging progress - this user trains mostly hypertrophy, so a flat 1RM does not "
            "mean stalled."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_lift_progression",
        "description": (
            "Detailed progression for ONE lift: rep-range mix, best set, best estimated 1RM, "
            "the volume-vs-load-vs-reps verdict and its reason."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"exercise": {"type": "string"}},
            "required": ["exercise"],
        },
    },
    {
        "name": "get_exercise_trend",
        "description": (
            "Estimated-1RM trend over time for one exercise (best working set per session). "
            "This is only the top-end strength lens; use get_lift_progression for the fuller "
            "picture. Weights in kg."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "exercise": {
                    "type": "string",
                    "description": "Exercise name as it appears in the user's history (e.g. 'Bench Press (Barbell)').",
                },
                "formula": {"type": "string", "enum": ["epley", "brzycki"]},
            },
            "required": ["exercise"],
        },
    },
    {
        "name": "get_workout_history",
        "description": (
            "Get the user's recent workouts with per-exercise sets (weight_kg, reps, rpe) "
            "and any notes the user logged (e.g. 'felt sloppy'). Optionally filter to one exercise."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "exercise": {"type": "string", "description": "Optional: only include this exercise."},
                "limit": {"type": "integer", "description": "How many recent workouts (default 8)."},
            },
        },
    },
    {
        "name": "search_exercises",
        "description": (
            "Search the user's Hevy exercise library by name. Returns matching titles and "
            "their template ids. Use to confirm the exact exercise name before proposing a routine."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
    {
        "name": "list_routines",
        "description": "List the user's existing Hevy routines (live from Hevy).",
        "input_schema": {"type": "object", "properties": {}},
    },
]

# NOT strict: weight/rest are intentionally optional (omit rather than invent a placeholder),
# and notes are optional. Validated server-side at approval time.
PROPOSE_ROUTINE_TOOL: dict = {
    "name": "propose_routine",
    "description": (
        "Propose a Hevy routine for the user to review. This does NOT push anything to Hevy — "
        "it renders a preview card the user must explicitly approve. Use the user's real exercise "
        "names (confirm with search_exercises if unsure). Weights are in kilograms; omit weight or "
        "rest entirely when you don't want to prescribe one rather than inventing a placeholder."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "notes": {"type": "string"},
            "exercises": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Exercise name as in Hevy."},
                        "rest_seconds": {"type": "integer"},
                        "notes": {"type": "string"},
                        "sets": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "type": {"type": "string", "enum": ["normal", "warmup", "failure", "dropset"]},
                                    "weight_kg": {"type": "number"},
                                    "reps": {"type": "integer"},
                                },
                                "required": ["type"],
                            },
                        },
                    },
                    "required": ["name", "sets"],
                },
            },
        },
        "required": ["title", "exercises"],
    },
}

ALL_TOOLS: list[dict] = READ_TOOLS + [PROPOSE_ROUTINE_TOOL]
READ_TOOL_NAMES = {t["name"] for t in READ_TOOLS}


# --- Executors --------------------------------------------------------------------

def _get_exercise_trend(session: Session, inp: dict) -> Any:
    return trends.exercise_trend(session, inp["exercise"], inp.get("formula", "epley"))


def _get_progression(session: Session, inp: dict) -> Any:
    return progression.progression_overview(session, get_settings().stall_lookback_sessions)


def _get_lift_progression(session: Session, inp: dict) -> Any:
    return progression.lift_progression(session, inp["exercise"])


def _search_exercises(session: Session, inp: dict) -> Any:
    matches = search_templates(session, inp["query"], limit=int(inp.get("limit", 10)))
    return [
        {"title": m.title, "template_id": m.id, "primary_muscle_group": m.primary_muscle_group}
        for m in matches
    ]


def _get_workout_history(session: Session, inp: dict) -> Any:
    limit = int(inp.get("limit", 8))
    ex_filter = (inp.get("exercise") or "").strip().lower()
    workouts = session.exec(
        select(Workout).order_by(Workout.start_time.desc()).limit(limit)
    ).all()
    out = []
    for w in workouts:
        sets = session.exec(select(WorkoutSet).where(WorkoutSet.workout_id == w.id)).all()
        by_ex: dict[str, dict] = {}
        for s in sets:
            if ex_filter and ex_filter not in s.exercise_title.lower():
                continue
            entry = by_ex.setdefault(
                s.exercise_title,
                {"exercise": s.exercise_title, "notes": s.exercise_notes, "sets": []},
            )
            entry["sets"].append(
                {"type": s.set_type, "weight_kg": s.weight_kg, "reps": s.reps, "rpe": s.rpe}
            )
        if ex_filter and not by_ex:
            continue
        out.append(
            {
                "date": w.start_time.isoformat() if w.start_time else None,
                "title": w.title,
                "workout_notes": w.description,
                "exercises": list(by_ex.values()),
            }
        )
    return out


async def _list_routines(client: HevyClient) -> Any:
    routines = await client.get_routines()
    # Trim to the useful fields.
    return [
        {"id": r.get("id"), "title": r.get("title"), "folder_id": r.get("folder_id")}
        for r in routines
    ]


async def execute_read_tool(
    name: str, inp: dict, session: Session, client: HevyClient
) -> str:
    """Run a read tool and return a JSON string for the tool_result block."""
    try:
        if name == "get_exercise_trend":
            result = _get_exercise_trend(session, inp)
        elif name == "get_workout_history":
            result = _get_workout_history(session, inp)
        elif name == "get_progression":
            result = _get_progression(session, inp)
        elif name == "get_lift_progression":
            result = _get_lift_progression(session, inp)
        elif name == "search_exercises":
            result = _search_exercises(session, inp)
        elif name == "list_routines":
            result = await _list_routines(client)
        else:
            return json.dumps({"error": f"unknown tool {name}"})
        return json.dumps(result, default=str)
    except Exception as exc:  # surface tool errors to the model, don't crash the stream
        return json.dumps({"error": str(exc)})
