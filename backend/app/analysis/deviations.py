"""Diff a LOGGED session against the routine it was supposed to be.

The chat coach kept tunneling: asked to review a session it fixed the first problem it saw
(the pull-ups) and skimmed the rest, missing that half the day (face pulls, hammer curls) was
skipped entirely. Handing it raw workout history left the reconciliation as manual work it did
badly. This lays out the WHOLE deviation picture in one structured view - what was skipped,
subbed/added, and changed - so it can't miss the back half of a session."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlmodel import Session, select

from app.analysis.trends import WORKING_SET_TYPES
from app.hevy import HevyClient
from app.models import Workout, WorkoutSet
from app.units import to_display


def _fmt_logged(sets: list[WorkoutSet], unit: str) -> str:
    return ", ".join(
        f"{to_display(s.weight_kg, unit)}{unit}x{s.reps}" if s.weight_kg else f"BWx{s.reps}"
        for s in sets
        if s.reps
    ) or "no working sets"


def _fmt_prescribed(ex: dict, unit: str) -> str:
    parts = []
    for s in ex.get("sets", []):
        rr = s.get("rep_range") or {}
        reps = f"{rr.get('start')}-{rr.get('end')}" if rr.get("start") is not None else s.get("reps")
        w = to_display(s.get("weight_kg"), unit)
        parts.append(f"{w}{unit}x{reps}" if w else f"x{reps}")
    return ", ".join(parts) or "no sets"


async def session_vs_routine(
    session: Session, client: HevyClient, unit: str, title: Optional[str] = None
) -> dict:
    """Compare the most recent logged workout (optionally filtered by title substring) against
    the routine it was based on, exercise by exercise."""
    q = select(Workout).where(Workout.start_time.is_not(None)).order_by(Workout.start_time.desc())
    workouts = session.exec(q).all()
    if title:
        t = title.lower()
        workouts = [w for w in workouts if t in (w.title or "").lower()]
    if not workouts:
        return {"error": "no matching workout found"}
    w = workouts[0]

    # Logged exercises for this workout, grouped, working sets only.
    logged: dict[str, dict] = {}
    for s in session.exec(select(WorkoutSet).where(WorkoutSet.workout_id == w.id)).all():
        if s.set_type not in WORKING_SET_TYPES or not s.reps:
            continue
        key = (s.exercise_template_id or s.exercise_title, s.exercise_title)
        entry = logged.setdefault(key, {"title": s.exercise_title, "sets": [], "note": None})
        entry["sets"].append(s)
        if s.exercise_notes and not entry["note"]:
            entry["note"] = s.exercise_notes

    # Prescribed exercises from the routine this workout was based on (live from Hevy).
    prescribed: dict = {}
    routine_title = None
    if w.routine_id:
        try:
            routine = next((r for r in await client.get_routines() if r.get("id") == w.routine_id), None)
        except Exception:  # noqa: BLE001 - fall back to a routine-less diff
            routine = None
        if routine:
            routine_title = routine.get("title")
            for ex in routine.get("exercises", []):
                key = ex.get("exercise_template_id") or ex.get("title")
                prescribed[key] = ex

    logged_by_id = {k[0]: v for k, v in logged.items()}
    exercises = []
    skipped, added, modified = [], [], []

    # Prescribed exercises: done, modified, or skipped?
    for key, ex in prescribed.items():
        got = logged_by_id.get(key)
        p_summary = _fmt_prescribed(ex, unit)
        if not got:
            skipped.append(ex.get("title"))
            exercises.append({"exercise": ex.get("title"), "status": "SKIPPED", "prescribed": p_summary, "logged": None, "note": None})
            continue
        l_summary = _fmt_logged(got["sets"], unit)
        prescribed_n = len(ex.get("sets", []))
        status = "as_prescribed" if len(got["sets"]) == prescribed_n and not got["note"] else "modified"
        if status == "modified":
            modified.append(ex.get("title"))
        exercises.append({"exercise": ex.get("title"), "status": status, "prescribed": p_summary, "logged": l_summary, "note": got["note"]})

    # Logged exercises that were NOT prescribed = added / substituted in.
    for key, entry in logged.items():
        if key[0] in prescribed:
            continue
        added.append(entry["title"])
        exercises.append({"exercise": entry["title"], "status": "ADDED/SUBBED", "prescribed": None, "logged": _fmt_logged(entry["sets"], unit), "note": entry["note"]})

    return {
        "workout": w.title,
        "date": w.start_time.date().isoformat() if w.start_time else None,
        "based_on_routine": routine_title,
        "summary": {
            "prescribed_exercises": len(prescribed),
            "logged_exercises": len(logged),
            "skipped": skipped,
            "added_or_subbed": added,
            "modified": modified,
        },
        "exercises": exercises,
        "read_this": (
            "Address EVERY item above, not just the first problem. A SKIPPED exercise (especially "
            "a weak-point or accessory that fell off the end) usually means the day is overstuffed "
            "or misordered, not that the exercise is bad. Read each note."
        ),
    }
