from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session

from app.db import get_session
from app.state import get_preferences, set_preferences

router = APIRouter(prefix="/api/settings", tags=["settings"])


class SettingsUpdate(BaseModel):
    weight_unit: str  # "lb" | "kg"


@router.get("")
def read_settings(session: Session = Depends(get_session)):
    return get_preferences(session)


@router.put("")
def write_settings(body: SettingsUpdate, session: Session = Depends(get_session)):
    return set_preferences(session, {"weight_unit": body.weight_unit})
