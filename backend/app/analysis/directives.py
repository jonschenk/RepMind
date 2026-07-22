"""Coach memory: durable user directives / standing preferences.

The routine-change log tells the coaches what was edited recently. Directives are different:
they are permanent instructions the user gave ("keep my deadlift heavy singles", "no rear
delts on heavy push days"), injected in FULL into both the chat and weekly-review system
context so a preference stated once is honored everywhere, not forgotten after a week or
scoped to one routine. The user can see and delete them, so it never becomes a black box."""

from __future__ import annotations

from sqlmodel import Session, select

from app.hevy.schemas import strip_dashes
from app.models import CoachDirective


def list_active(session: Session) -> list[CoachDirective]:
    return list(
        session.exec(
            select(CoachDirective)
            .where(CoachDirective.active == True)  # noqa: E712 (SQLModel needs ==)
            .order_by(CoachDirective.created_at)
        ).all()
    )


def add_directive(session: Session, text: str, scope: str | None = None, source: str = "chat") -> CoachDirective:
    text = strip_dashes((text or "").strip())
    scope = strip_dashes(scope.strip()) if scope and scope.strip() else None
    # De-dupe on identical text (case-insensitive) so the coach re-saving the same rule is a
    # no-op rather than a pile of duplicates.
    for d in list_active(session):
        if d.text.lower() == text.lower():
            return d
    row = CoachDirective(text=text, scope=scope, source=source)
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def deactivate(session: Session, directive_id: int) -> bool:
    row = session.get(CoachDirective, directive_id)
    if not row or not row.active:
        return False
    row.active = False
    session.add(row)
    session.commit()
    return True


def directives_block(session: Session) -> str:
    """A system-prompt block of the active directives. Empty string when there are none, so it
    can be concatenated unconditionally."""
    rows = list_active(session)
    if not rows:
        return ""
    lines = [
        "## Standing preferences (the user's durable directives - ALWAYS honor these)",
        "These are permanent instructions the user gave you. Follow them in every routine you "
        "build or edit, without being reminded. Never propose something a directive forbids. If "
        "a directive genuinely conflicts with what the data suggests, do the directive's way and "
        "briefly note the tradeoff rather than overriding it silently.",
    ]
    for d in rows:
        scope = f" [{d.scope}]" if d.scope else ""
        lines.append(f"- {d.text}{scope}")
    return "\n".join(lines)
