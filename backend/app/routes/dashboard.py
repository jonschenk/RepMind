from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.analysis import body, progression, trends
from app.analysis.summary import get_cached_summary
from app.config import get_settings
from app.db import get_session

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("")
def dashboard_overview(session: Session = Depends(get_session)):
    """Everything the dashboard needs on first load."""
    settings = get_settings()
    lifts = sorted(
        progression.tracked_lifts(session, min_sessions=2),
        key=lambda d: d["sessions"],
        reverse=True,
    )
    return {
        "exercises": lifts,
        "progression": progression.progression_overview(session, settings.stall_lookback_sessions),
        "training_mix": progression.training_mix(session),
        "weekly_volume": trends.weekly_volume_by_muscle(session),
    }


@router.get("/trend")
def exercise_trend(
    exercise: str = Query(...),
    session: Session = Depends(get_session),
):
    """Three metrics for the trend chart: estimated 1RM and top-set weight (per session),
    and volume-load (per week). Weights are kg; the frontend converts to the display unit."""
    series = trends.exercise_trend(session, exercise)
    est = [{"label": (p["date"] or "")[:10], "value": p["est_1rm"]} for p in series]
    top = [
        {"label": (p["date"] or "")[:10], "value": p["top_weight_kg"], "reps": p["top_reps"]}
        for p in series
    ]
    vol = [
        {"label": v["week"], "value": v["volume_kg"]}
        for v in progression.volume_load_series(session, exercise)
    ]
    return {"exercise": exercise, "est_1rm": est, "top_set": top, "volume": vol}


@router.get("/summary")
async def summary(session: Session = Depends(get_session)):
    # Cached; never regenerates on a page load (see get_cached_summary).
    return await get_cached_summary(session)


@router.get("/body")
def body_stats(session: Session = Depends(get_session)):
    return body.body_stats(session)
