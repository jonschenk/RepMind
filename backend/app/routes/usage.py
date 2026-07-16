from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.db import get_session
from app.usage import usage_summary

router = APIRouter(prefix="/api/usage", tags=["usage"])


@router.get("")
def get_usage(session: Session = Depends(get_session)):
    """Estimated Claude spend this month + per-surface breakdown."""
    return usage_summary(session)
