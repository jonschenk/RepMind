"""Small persistent key/value store on top of the AppState table: cached generated
content and user preferences."""

from datetime import datetime
from typing import Any, Optional

from sqlmodel import Session

from app.models import AppState

WEIGHT_UNIT_DEFAULT = "lb"


def get_state(session: Session, key: str, default: Optional[Any] = None) -> Any:
    row = session.get(AppState, key)
    return row.value if row else default


def set_state(session: Session, key: str, value: dict) -> None:
    row = session.get(AppState, key)
    if row:
        row.value = value
        row.updated_at = datetime.utcnow()
    else:
        row = AppState(key=key, value=value)
    session.add(row)
    session.commit()


def get_preferences(session: Session) -> dict:
    prefs = get_state(session, "preferences", {}) or {}
    return {"weight_unit": prefs.get("weight_unit", WEIGHT_UNIT_DEFAULT)}


def set_preferences(session: Session, prefs: dict) -> dict:
    current = get_preferences(session)
    unit = prefs.get("weight_unit", current["weight_unit"])
    if unit not in ("lb", "kg"):
        unit = WEIGHT_UNIT_DEFAULT
    current["weight_unit"] = unit
    set_state(session, "preferences", current)
    return current
