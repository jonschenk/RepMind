from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.analysis.changes import recent_changes
from app.db import get_session

router = APIRouter(prefix="/api/changes", tags=["changes"])


@router.get("")
def list_changes(session: Session = Depends(get_session)):
    """The shared routine-change log (approved edits from chat + weekly), newest first."""
    return {"changes": recent_changes(session, limit=40)}
