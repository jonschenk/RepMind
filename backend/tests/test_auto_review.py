"""Weekly-review auto-trigger: fire when the active split is fully covered, with a ceiling
stall-guard. cycle_reason is the pure decision (no LLM/Hevy side effects)."""

from datetime import datetime, timedelta

import pytest
from sqlmodel import Session, SQLModel, create_engine

from app.coach.auto_review import cycle_reason
from app.models import Workout

NOW = datetime(2026, 7, 12, 12, 0)
SINCE = NOW - timedelta(days=3)  # last review 3 days ago

# A PPL split: 3 routines in folder 1. (A second folder to prove we isolate the active split.)
ROUTINES = [
    {"id": "push", "folder_id": 1},
    {"id": "pull", "folder_id": 1},
    {"id": "legs", "folder_id": 1},
    {"id": "arnold-day", "folder_id": 2},
]


@pytest.fixture()
def session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _log(s, routine_id, days_ago, wid):
    s.add(Workout(id=wid, routine_id=routine_id, start_time=NOW - timedelta(days=days_ago)))


def test_fires_when_all_split_days_done(session):
    _log(session, "push", 2, "w1")
    _log(session, "pull", 1, "w2")
    _log(session, "legs", 0, "w3")  # most recent -> active folder = 1
    session.commit()
    assert cycle_reason(session, ROUTINES, SINCE, NOW) == "cycle-complete"


def test_not_yet_when_a_day_is_missing(session):
    _log(session, "push", 2, "w1")
    _log(session, "pull", 0, "w2")  # legs not done yet
    session.commit()
    assert cycle_reason(session, ROUTINES, SINCE, NOW) is None


def test_other_folder_workouts_dont_count(session):
    # Did all of folder 2's... but active split is folder 1 (most recent), only partly done.
    _log(session, "push", 2, "w1")
    _log(session, "arnold-day", 0, "w2")  # most recent is folder 2, fully covered (1 routine)
    session.commit()
    # active folder becomes 2 (single routine, done) -> fires for that split
    assert cycle_reason(session, ROUTINES, SINCE, NOW) == "cycle-complete"


def test_no_workouts_since_returns_none(session):
    _log(session, "push", 10, "old")  # before `since`
    session.commit()
    assert cycle_reason(session, ROUTINES, SINCE, NOW) is None


def test_ceiling_fires_even_without_full_coverage(session):
    old_since = NOW - timedelta(days=12)  # 12 > CEILING (9)
    _log(session, "push", 1, "w1")  # only one day, but stalled too long
    session.commit()
    assert cycle_reason(session, ROUTINES, old_since, NOW) == "ceiling"


def test_freestyle_workout_no_routine_waits(session):
    _log(session, None, 0, "w1")  # no routine_id -> can't determine split
    session.commit()
    assert cycle_reason(session, ROUTINES, SINCE, NOW) is None
