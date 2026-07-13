"""Shared routine-change log.

Both the chat coach and the weekly review read this so they stay in sync: when a routine
is edited via chat (or approved from the weekly review), the other surface can see WHAT
changed, WHEN, from WHICH surface, and WHY. This is what stops the weekly review from
misreading a deliberate mid-week routine adjustment as the user going off-program."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from sqlmodel import Session, select

from app.models import RoutineProposal


def recent_changes(
    session: Session, since: Optional[datetime] = None, limit: int = 25
) -> list[dict]:
    """Approved routine changes (chat + weekly), newest first. `since` filters by when the
    change landed; None returns the most recent `limit` changes regardless of age."""
    rows = session.exec(
        select(RoutineProposal).where(RoutineProposal.status == "pushed")
    ).all()

    out = []
    for r in rows:
        when = r.pushed_at or r.created_at
        if since is not None and when is not None and when < since:
            continue
        diff = r.diff or {}
        summary = diff.get("changes_summary") or diff.get("rationale")
        if not summary:
            summary = f"{'Updated' if r.kind == 'update' else 'Created'} routine '{r.title}'."
        out.append(
            {
                "when": when.isoformat() if when else None,
                "source": r.source,  # chat | weekly
                "kind": r.kind,  # create | update
                "routine": r.title,
                "hevy_routine_id": r.hevy_routine_id,
                "summary": summary,
            }
        )
    out.sort(key=lambda c: c["when"] or "", reverse=True)
    return out[:limit]


def changes_context_block(session: Session, days: int = 21, limit: int = 12) -> str:
    """A short human-readable block of recent changes for a system prompt. Empty string when
    there are none, so it can be concatenated unconditionally."""
    since = datetime.utcnow() - timedelta(days=days)
    changes = recent_changes(session, since=since, limit=limit)
    if not changes:
        return ""
    lines = [
        "## Recent routine changes (shared log)",
        "These routine edits were already approved and pushed. Treat them as intentional. If "
        "a logged session differs from a routine and a change below is dated around then, that "
        "is the user deliberately adjusting the plan, not going off-program. Do not re-flag or "
        "undo something already handled here.",
    ]
    for c in changes:
        when = (c["when"] or "")[:10]
        verb = "updated" if c["kind"] == "update" else "created"
        lines.append(f"- {when} [{c['source']}] {verb} '{c['routine']}': {c['summary']}")
    return "\n".join(lines)
