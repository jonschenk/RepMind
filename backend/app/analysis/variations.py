"""Variation-aware analysis.

A single Hevy exercise name (e.g. "Squat (Barbell)") is often logged as both heavy
low-rep work and higher-rep hypertrophy work. Trending them together makes a heavy lift
look like it's "stalling" whenever recent sessions happened to be hypertrophy days. We
split each lift's sessions into a heavy lane (top set <= threshold reps) and a hypertrophy
lane, and judge strength progression off the heavy lane only.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from sqlmodel import Session, select

from app.analysis.trends import Formula, exercise_trend, list_tracked_exercises
from app.models import WorkoutSet


def lane_for_reps(top_reps: Optional[int], threshold: int) -> str:
    return "heavy" if top_reps is not None and top_reps <= threshold else "hypertrophy"


def lane_trends(
    session: Session, exercise: str, threshold: int, formula: Formula = "epley"
) -> dict[str, list[dict]]:
    """Split a lift's per-session best-effort points into heavy vs hypertrophy lanes."""
    series = exercise_trend(session, exercise, formula)
    lanes: dict[str, list[dict]] = {"heavy": [], "hypertrophy": []}
    for p in series:
        lanes[lane_for_reps(p.get("top_reps"), threshold)].append(p)
    return lanes


def _rolling_stall(ests: list[float], lookback: int) -> Optional[dict]:
    """No new PR within the last `lookback` sessions (rolling best vs prior best)."""
    if len(ests) < lookback + 1:
        return None
    best = max(ests)
    pr_index = max(i for i, e in enumerate(ests) if e == best)
    recent_best = max(ests[-lookback:])
    prior_best = max(ests[:-lookback])
    return {
        "stalled": recent_best < prior_best,
        "best_est_1rm": best,
        "recent_best_est_1rm": recent_best,
        "current_est_1rm": ests[-1],
        "sessions_since_pr": len(ests) - 1 - pr_index,
    }


def lift_summary(
    session: Session, exercise: str, lookback: int, threshold: int, formula: Formula = "epley"
) -> dict:
    """Per-lift snapshot used by the weekly review: latest heavy/hypertrophy efforts and the
    heavy-lane stall status (the true strength signal)."""
    lanes = lane_trends(session, exercise, threshold, formula)
    heavy = lanes["heavy"]
    hyp = lanes["hypertrophy"]
    heavy_ests = [p["est_1rm"] for p in heavy]
    return {
        "exercise": exercise,
        "heavy_sessions": len(heavy),
        "hypertrophy_sessions": len(hyp),
        "heavy_latest": heavy[-1] if heavy else None,
        "hypertrophy_latest": hyp[-1] if hyp else None,
        "heavy_stall": _rolling_stall(heavy_ests, lookback),
    }


def variation_aware_stalled(
    session: Session,
    lookback: int,
    threshold: int,
    formula: Formula = "epley",
    recency_days: int = 28,
) -> list[dict]:
    """Stalled lifts judged on the HEAVY lane only, for lifts still being trained. Skips
    lifts without enough heavy-lane history (can't judge a strength stall from light days)."""
    all_dates = [
        r.workout_start_time
        for r in session.exec(select(WorkoutSet)).all()
        if r.workout_start_time
    ]
    if not all_dates:
        return []
    latest = max(all_dates)

    out: list[dict] = []
    for ex in list_tracked_exercises(session, min_sessions=lookback + 1):
        heavy = lane_trends(session, ex["template_id"] or ex["exercise"], threshold, formula)["heavy"]
        if len(heavy) < lookback + 1:
            continue
        last_date_s = heavy[-1]["date"]
        last_dt = datetime.fromisoformat(last_date_s) if last_date_s else None
        if last_dt is None or (latest - last_dt) > timedelta(days=recency_days):
            continue
        st = _rolling_stall([p["est_1rm"] for p in heavy], lookback)
        if st and st["stalled"]:
            out.append(
                {
                    "exercise": ex["exercise"],
                    "template_id": ex["template_id"],
                    "lane": "heavy",
                    "last_session_date": last_date_s,
                    **st,
                }
            )
    return sorted(out, key=lambda d: d["best_est_1rm"] - d["recent_best_est_1rm"], reverse=True)
