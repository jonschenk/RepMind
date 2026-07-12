"""Seed a demo repmind.db with synthetic history + one pending routine proposal so the
UI and approval flow can be exercised without a live Hevy/Anthropic connection.

Run from backend/:  DATABASE_URL=sqlite:///./repmind.db python seed_demo.py
"""
from datetime import datetime, timedelta

from sqlmodel import Session, select

from app.db import engine, init_db
from app.models import ExerciseTemplate, RoutineProposal, SyncState, Workout, WorkoutSet

init_db()
BASE = datetime(2025, 3, 3)  # a Monday


def add_workout(s, wid, week, entries):
    start = BASE + timedelta(weeks=week)
    s.add(Workout(id=wid, title=entries[0][3], start_time=start, description=entries[0][4]))
    for exi, (title, tid, notes, _wtitle, _wnote, sets) in enumerate(entries):
        for si, (w, r) in enumerate(sets):
            s.add(WorkoutSet(
                workout_id=wid, workout_start_time=start, exercise_index=exi,
                exercise_title=title, exercise_template_id=tid, exercise_notes=notes,
                set_index=si, set_type="normal", weight_kg=w, reps=r))


with Session(engine) as s:
    # Wipe prior demo rows for idempotency.
    for w in s.exec(select(Workout)).all():
        s.delete(w)
    for st in s.exec(select(WorkoutSet)).all():
        s.delete(st)
    s.commit()

    templates = [
        ("t-bench", "Bench Press (Barbell)", "Chest"),
        ("t-squat", "Squat (Barbell)", "Quadriceps"),
        ("t-dead", "Deadlift (Barbell)", "Back"),
        ("t-ohp", "Overhead Press (Barbell)", "Shoulders"),
        ("t-lat", "Lateral Raise (Cable)", "Shoulders"),
        ("t-face", "Face Pull", "Shoulders"),
        ("t-curl", "Hammer Curl (Cross Body)", "Biceps"),
    ]
    for tid, title, mg in templates:
        if not s.get(ExerciseTemplate, tid):
            s.add(ExerciseTemplate(id=tid, title=title, primary_muscle_group=mg))

    bench = [128, 130, 132.5, 133, 132.5, 134, 135, 137]  # improving
    squat = [160, 158, 157, 156, 157, 158, 157, 158]      # stalled: PR wk0, never beaten
    for wk in range(8):
        add_workout(s, f"push-{wk}", wk, [
            ("Bench Press (Barbell)", "t-bench", "felt fast" if wk >= 6 else None, f"Push {wk}", "solid session", [(bench[wk], 3), (bench[wk] - 15, 6), (bench[wk] - 25, 9)]),
            ("Overhead Press (Barbell)", "t-ohp", None, "", "", [(60, 6), (57.5, 8)]),
            ("Lateral Raise (Cable)", "t-lat", None, "", "", [(12.5, 18), (12.5, 16), (10, 20)]),
            ("Face Pull", "t-face", None, "", "", [(25, 20), (25, 18)]),
        ])
        add_workout(s, f"legs-{wk}", wk, [
            ("Squat (Barbell)", "t-squat", "grindy, burnt out from AMRAP" if wk == 4 else None, f"Legs {wk}", "", [(squat[wk], 3), (squat[wk] - 20, 6)]),
            ("Deadlift (Barbell)", "t-dead", "straps once grip went" if wk == 5 else None, "", "", [(180 + wk, 3)]),
        ])
    s.commit()

    state = s.get(SyncState, 1) or SyncState(id=1)
    state.full_sync_done = True
    state.last_synced_at = datetime.utcnow()
    state.workout_count = len(s.exec(select(Workout)).all())
    s.add(state)

    # A pending proposal to exercise the approve->push (DRY_RUN) flow via the UI/API.
    if not s.exec(select(RoutineProposal)).first():
        s.add(RoutineProposal(
            status="pending",
            title="Push A — delt priority",
            payload={
                "title": "Push A — delt priority",
                "notes": "Lateral + rear delt focus. Bench heavy triple then back off.",
                "exercises": [
                    {"name": "Bench Press (Barbell)", "rest_seconds": 210, "sets": [
                        {"type": "warmup", "reps": 5},
                        {"type": "normal", "weight_kg": 137, "reps": 3},
                        {"type": "normal", "weight_kg": 120, "reps": 6},
                    ]},
                    {"name": "Lateral Raise (Cable)", "rest_seconds": 60, "notes": "high rep, controlled", "sets": [
                        {"type": "normal", "reps": 18}, {"type": "normal", "reps": 18},
                        {"type": "normal", "reps": 16}, {"type": "normal", "reps": 15},
                    ]},
                    {"name": "Face Pull", "sets": [{"type": "normal", "reps": 20}, {"type": "normal", "reps": 20}]},
                ],
            },
        ))
    s.commit()
    print(f"Seeded {state.workout_count} workouts + 1 pending proposal.")
