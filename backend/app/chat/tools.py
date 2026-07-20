"""Tool definitions + read-tool executors for the chat agent.

Read tools run against the local SQLite cache (fast, deterministic, free). `list_routines`
reads live from Hevy. `propose_routine` is intentionally NOT executed here — the agent
loop captures it and turns it into an approval-gated preview (see agent.py)."""

from __future__ import annotations

import json
from typing import Any

from sqlmodel import Session, select

from app.analysis import progression, trends
from app.analysis import training_state as ts
from app.config import get_settings
from app.hevy import HevyClient
from app.hevy.resolve import search_templates
from app.models import Workout, WorkoutSet
from app.state import get_preferences
from app.units import to_display

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
        "name": "get_training_state",
        "description": (
            "The long-horizon picture the per-lift verdict misses: which lifts are STAGNATING "
            "(no new best for many of their own sessions, with weeks_stuck and whether they're a "
            "swap_candidate), plus systemic DELOAD readiness (how many lifts are regressing, "
            "weeks since a clearly lighter week, and a recommend_deload flag with reasons). Use "
            "this for questions about plateaus, whether it's time to deload, or when to swap a lift."
        ),
        "input_schema": {"type": "object", "properties": {}},
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
        "description": (
            "The user's whole program (live from Hevy): every routine with its folder (the "
            "split it belongs to) and its list of exercises. Use this to see the FULL context "
            "before changing any single day, so you don't duplicate a movement another day "
            "already covers."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_routine",
        "description": (
            "Full current contents of one routine (exercises, sets, reps, weights in the "
            "user's display unit, notes). Call this before editing a routine so your update "
            "reflects what is actually in it, not a guess."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "routine_id": {"type": "string", "description": "Routine id from list_routines (preferred)."},
                "name": {"type": "string", "description": "Or match by routine name."},
            },
        },
    },
]

# NOT strict: notes/rest are optional. `weight` is in the user's DISPLAY unit (lb or kg,
# stated in the system prompt) and converted to kg server-side, so the numbers stay round
# in the user's own unit. Every working set should carry a concrete weight and reps.
PROPOSE_ROUTINE_TOOL: dict = {
    "name": "propose_routine",
    "description": (
        "Propose a Hevy routine for the user to review. This does NOT push anything to Hevy - "
        "it renders a preview card the user must explicitly approve. Use the user's real exercise "
        "names (confirm with search_exercises if unsure). The `weight` field is in the user's "
        "DISPLAY unit stated in the system prompt (pounds unless told otherwise), NOT kilograms - "
        "the app converts it. Give every working set (normal/failure/dropset) a concrete, round "
        "weight and rep count grounded in the user's recent logged weights; never leave weight "
        "blank, and for a 'work up to a top set' day fill in the actual target number to hit. "
        "To EDIT an existing routine in place (e.g. the user says 'fix my push day'), set "
        "`target_routine_id` to that routine's id from list_routines and send the COMPLETE "
        "routine as it should look after the change (the update overwrites the whole routine); "
        "also set `change_summary`. Omit `target_routine_id` to create a brand-new routine."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "notes": {"type": "string"},
            "target_routine_id": {
                "type": "string",
                "description": "Set to an existing routine's id (from list_routines) to UPDATE it in place instead of creating a new one. The routine keeps its Hevy folder. Omit to create new.",
            },
            "change_summary": {
                "type": "string",
                "description": "When updating, a one-line 'what changed and why' (e.g. 'cut incline volume 4->3 sets, dropped OHP to 95 lb, weights were unrealistic'). Recorded in the shared change log the weekly review reads.",
            },
            "folder": {
                "type": "string",
                "description": "Folder to group a NEW routine under in Hevy. For a multi-day split, use the SAME short folder name (e.g. 'PPL') on every day. Ignored for updates (a routine keeps its folder). Omit for a standalone one-off.",
            },
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
                                    "weight": {
                                        "type": "number",
                                        "description": "Target weight in the user's display unit (lb unless stated otherwise). Round to real gym numbers.",
                                    },
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


def _get_training_state(session: Session, inp: dict) -> Any:
    prog = progression.progression_overview(session, get_settings().stall_lookback_sessions)
    # Chat path has no cheap access to mined note themes, so deload leans on the objective
    # signals (regressing lifts, volume drops, weeks since a lighter week).
    return {"stalled_lifts": ts.stalled_lifts(session), "deload": ts.deload_readiness(session, prog, [])}


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
    """Program overview: every routine with its folder and its exercise list, so the coach
    can see the WHOLE split (e.g. which day already trains a movement) before changing one."""
    routines = await client.get_routines()
    folders = {f.get("id"): f.get("title") for f in await client.get_routine_folders()}
    return [
        {
            "id": r.get("id"),
            "title": r.get("title"),
            "folder": folders.get(r.get("folder_id")),
            "exercises": [ex.get("title") for ex in r.get("exercises", [])],
        }
        for r in routines
    ]


async def _get_routine(client: HevyClient, session: Session, inp: dict) -> Any:
    """Full current contents of one routine (by id or name), weights in the user's display
    unit. Use before editing so the update reflects the real routine, not a guess."""
    unit = get_preferences(session)["weight_unit"]
    routines = await client.get_routines()
    rid = (inp.get("routine_id") or "").strip()
    name = (inp.get("name") or "").strip().lower()
    match = None
    for r in routines:
        if rid and r.get("id") == rid:
            match = r
            break
        if name and name in (r.get("title", "") or "").lower():
            match = r  # keep looking for an exact id match, else last name match wins
    if not match:
        return {"error": "routine not found; call list_routines for exact names/ids"}
    return {
        "id": match.get("id"),
        "title": match.get("title"),
        "exercises": [
            {
                "name": ex.get("title"),
                "rest_seconds": ex.get("rest_seconds"),
                "notes": ex.get("notes"),
                "sets": [
                    {"type": s.get("type"), "weight": to_display(s.get("weight_kg"), unit), "reps": s.get("reps")}
                    for s in ex.get("sets", [])
                ],
            }
            for ex in match.get("exercises", [])
        ],
    }


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
        elif name == "get_training_state":
            result = _get_training_state(session, inp)
        elif name == "search_exercises":
            result = _search_exercises(session, inp)
        elif name == "list_routines":
            result = await _list_routines(client)
        elif name == "get_routine":
            result = await _get_routine(client, session, inp)
        else:
            return json.dumps({"error": f"unknown tool {name}"})
        return json.dumps(result, default=str)
    except Exception as exc:  # surface tool errors to the model, don't crash the stream
        return json.dumps({"error": str(exc)})
