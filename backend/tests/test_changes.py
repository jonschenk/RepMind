"""The shared change log: only approved (pushed) changes, newest first, with a summary."""

from datetime import datetime

import pytest
from sqlmodel import Session, SQLModel, create_engine

from app.analysis.changes import recent_changes
from app.models import RoutineProposal


@pytest.fixture()
def session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _add(s, **kw):
    s.add(RoutineProposal(**kw))


def test_recent_changes_filters_and_orders(session):
    _add(session, status="pushed", source="chat", kind="update", title="Push A",
         diff={"changes_summary": "cut OHP"}, pushed_at=datetime(2026, 7, 12, 10))
    _add(session, status="pushed", source="weekly", kind="create", title="Legs",
         pushed_at=datetime(2026, 7, 10, 10))
    _add(session, status="pending", source="chat", kind="create", title="Pending Day")
    _add(session, status="dismissed", source="weekly", kind="update", title="Denied Day",
         pushed_at=datetime(2026, 7, 11, 10))
    session.commit()

    out = recent_changes(session)
    # only the two pushed ones, newest first
    assert [c["routine"] for c in out] == ["Push A", "Legs"]
    assert out[0]["source"] == "chat" and out[0]["kind"] == "update"
    assert out[0]["summary"] == "cut OHP"
    # missing diff falls back to a generated summary
    assert out[1]["summary"] == "Created routine 'Legs'."


def test_since_filter(session):
    _add(session, status="pushed", source="chat", kind="update", title="Recent",
         pushed_at=datetime(2026, 7, 12, 10))
    _add(session, status="pushed", source="chat", kind="update", title="Old",
         pushed_at=datetime(2026, 7, 1, 10))
    session.commit()

    out = recent_changes(session, since=datetime(2026, 7, 5))
    assert [c["routine"] for c in out] == ["Recent"]


def test_empty(session):
    assert recent_changes(session) == []
