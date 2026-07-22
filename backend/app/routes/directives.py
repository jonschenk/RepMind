from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session

from app.analysis import directives
from app.db import get_session

router = APIRouter(prefix="/api/directives", tags=["directives"])


class NewDirective(BaseModel):
    text: str
    scope: str | None = None


def _view(d) -> dict:
    return {"id": d.id, "text": d.text, "scope": d.scope, "source": d.source, "created_at": d.created_at.isoformat()}


@router.get("")
def list_directives(session: Session = Depends(get_session)):
    """Everything the coach durably remembers, so it's never a black box."""
    return [_view(d) for d in directives.list_active(session)]


@router.post("")
def add_directive(body: NewDirective, session: Session = Depends(get_session)):
    d = directives.add_directive(session, body.text, scope=body.scope, source="manual")
    return _view(d)


@router.delete("/{directive_id}")
def remove_directive(directive_id: int, session: Session = Depends(get_session)):
    return {"removed": directives.deactivate(session, directive_id)}
