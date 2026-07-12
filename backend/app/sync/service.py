"""Sync Hevy workout history + exercise templates into the local SQLite cache.

Full sync on first run (count -> paginate all workouts). Delta sync thereafter via
GET /v1/workouts/events, which reports updated/deleted workouts since a date.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Session, delete, select

from app.hevy import HevyClient
from app.models import ExerciseTemplate, SyncState, Workout, WorkoutSet

logger = logging.getLogger("repmind.sync")


def parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _get_sync_state(session: Session) -> SyncState:
    state = session.get(SyncState, 1)
    if state is None:
        state = SyncState(id=1)
        session.add(state)
        session.commit()
        session.refresh(state)
    return state


def _upsert_workout(session: Session, w: dict) -> None:
    """Insert/replace a workout and its flattened sets."""
    workout_id = w["id"]
    start = parse_dt(w.get("start_time"))

    existing = session.get(Workout, workout_id)
    if existing:
        existing.title = w.get("title")
        existing.description = w.get("description")
        existing.routine_id = w.get("routine_id")
        existing.start_time = start
        existing.end_time = parse_dt(w.get("end_time"))
        existing.created_at = parse_dt(w.get("created_at"))
        existing.updated_at = parse_dt(w.get("updated_at"))
        session.add(existing)
    else:
        session.add(
            Workout(
                id=workout_id,
                title=w.get("title"),
                description=w.get("description"),
                routine_id=w.get("routine_id"),
                start_time=start,
                end_time=parse_dt(w.get("end_time")),
                created_at=parse_dt(w.get("created_at")),
                updated_at=parse_dt(w.get("updated_at")),
            )
        )

    # Replace sets wholesale (simplest correct upsert).
    session.exec(delete(WorkoutSet).where(WorkoutSet.workout_id == workout_id))
    for ex in w.get("exercises", []):
        for s in ex.get("sets", []):
            session.add(
                WorkoutSet(
                    workout_id=workout_id,
                    workout_start_time=start,
                    exercise_index=ex.get("index", 0),
                    exercise_title=ex.get("title", ""),
                    exercise_template_id=ex.get("exercise_template_id"),
                    exercise_notes=ex.get("notes"),
                    set_index=s.get("index", 0),
                    set_type=s.get("type"),
                    weight_kg=s.get("weight_kg"),
                    reps=s.get("reps"),
                    distance_meters=s.get("distance_meters"),
                    duration_seconds=s.get("duration_seconds"),
                    rpe=s.get("rpe"),
                )
            )


def _delete_workout(session: Session, workout_id: str) -> None:
    session.exec(delete(WorkoutSet).where(WorkoutSet.workout_id == workout_id))
    existing = session.get(Workout, workout_id)
    if existing:
        session.delete(existing)


async def sync_templates(session: Session, client: HevyClient) -> int:
    count = 0
    async for t in client.iter_exercise_templates():
        tid = t["id"]
        existing = session.get(ExerciseTemplate, tid)
        fields = dict(
            title=t.get("title", ""),
            type=t.get("type"),
            primary_muscle_group=t.get("primary_muscle_group"),
            secondary_muscle_groups=t.get("secondary_muscle_groups") or [],
            is_custom=bool(t.get("is_custom", False)),
        )
        if existing:
            for k, v in fields.items():
                setattr(existing, k, v)
            session.add(existing)
        else:
            session.add(ExerciseTemplate(id=tid, **fields))
        count += 1
    session.commit()
    return count


async def run_sync(session: Session, client: HevyClient) -> dict:
    """Full sync on first run, delta sync afterward. Returns a summary."""
    state = _get_sync_state(session)

    # Always refresh templates (needed for name->UUID resolution + muscle analysis).
    templates = await sync_templates(session, client)

    if not state.full_sync_done:
        result = await _full_sync(session, client, state)
    else:
        result = await _delta_sync(session, client, state)

    result["templates"] = templates
    return result


async def _full_sync(session: Session, client: HevyClient, state: SyncState) -> dict:
    total = await client.get_workout_count()
    synced = 0
    async for w in client.iter_workouts():
        _upsert_workout(session, w)
        synced += 1
        if synced % 50 == 0:
            session.commit()
            logger.info("Full sync progress: %d/%d workouts", synced, total)
    session.commit()

    state.full_sync_done = True
    state.workout_count = session.exec(select(Workout)).all().__len__()
    state.last_synced_at = datetime.utcnow()
    session.add(state)
    session.commit()
    logger.info("Full sync complete: %d workouts", synced)
    return {"mode": "full", "workouts_synced": synced, "total_reported": total}


async def _delta_sync(session: Session, client: HevyClient, state: SyncState) -> dict:
    since = (state.last_synced_at or datetime.utcnow()).isoformat()
    updated = 0
    deleted = 0
    async for event in client.iter_workout_events(since):
        etype = event.get("type")
        if etype == "updated" and event.get("workout"):
            _upsert_workout(session, event["workout"])
            updated += 1
        elif etype == "deleted":
            wid = event.get("id") or (event.get("workout") or {}).get("id")
            if wid:
                _delete_workout(session, wid)
                deleted += 1
    session.commit()

    state.workout_count = session.exec(select(Workout)).all().__len__()
    state.last_synced_at = datetime.utcnow()
    session.add(state)
    session.commit()
    logger.info("Delta sync complete: %d updated, %d deleted", updated, deleted)
    return {"mode": "delta", "updated": updated, "deleted": deleted}
