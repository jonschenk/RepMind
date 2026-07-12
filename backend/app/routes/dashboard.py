from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.analysis import trends
from app.analysis.summary import generate_summary
from app.config import get_settings
from app.db import get_session

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("")
def dashboard_overview(session: Session = Depends(get_session)):
    """Everything the dashboard needs on first load."""
    settings = get_settings()
    return {
        "exercises": trends.list_tracked_exercises(session),
        "stalled_lifts": trends.stalled_lifts(session, settings.stall_lookback_sessions),
        "weekly_volume": trends.weekly_volume_by_muscle(session),
    }


@router.get("/trend")
def exercise_trend(
    exercise: str = Query(...),
    formula: str = Query("epley"),
    session: Session = Depends(get_session),
):
    formula = "brzycki" if formula == "brzycki" else "epley"
    return {
        "exercise": exercise,
        "formula": formula,
        "series": trends.exercise_trend(session, exercise, formula),
    }


@router.get("/summary")
async def summary(session: Session = Depends(get_session)):
    return await generate_summary(session)
