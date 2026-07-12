"""Exercise name <-> template-UUID resolution against the locally cached templates.

Hevy exercise IDs are UUIDs; you must resolve a name to a real template id before
creating a routine (never guess an id). Resolution reads the ExerciseTemplate cache
seeded by the sync service.
"""

from typing import Optional

from sqlmodel import Session, select

from app.models import ExerciseTemplate


def search_templates(session: Session, query: str, limit: int = 10) -> list[ExerciseTemplate]:
    q = (query or "").strip().lower()
    if not q:
        return []
    stmt = select(ExerciseTemplate)
    rows = session.exec(stmt).all()
    # Rank: exact title, then startswith, then contains. Small table (~hundreds), so an
    # in-memory rank is simpler and plenty fast for one user.
    exact = [t for t in rows if t.title.lower() == q]
    starts = [t for t in rows if t.title.lower().startswith(q) and t not in exact]
    contains = [
        t for t in rows if q in t.title.lower() and t not in exact and t not in starts
    ]
    return (exact + starts + contains)[:limit]


def resolve_template_id(session: Session, name_or_id: str) -> Optional[str]:
    """Return a real template UUID for a name or id, or None if no confident match."""
    if not name_or_id:
        return None
    # Already a valid id?
    existing = session.get(ExerciseTemplate, name_or_id)
    if existing:
        return existing.id
    matches = search_templates(session, name_or_id, limit=1)
    return matches[0].id if matches else None
