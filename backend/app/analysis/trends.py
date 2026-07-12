"""Rule-based training analysis over the local set cache. Deterministic and free — no
LLM calls here. Estimated 1RM, per-lift trend series, weekly volume per muscle group,
and stalled-lift detection."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Literal, Optional

from sqlmodel import Session, select

from app.models import ExerciseTemplate, WorkoutSet

Formula = Literal["epley", "brzycki"]
WORKING_SET_TYPES = {"normal", "failure", "dropset", None}  # exclude warmup
# 1RM estimation formulas are only reliable at low reps; above this they wildly
# overestimate (a 30-rep leg extension is not a ~550kg single). Sets above this cap are
# excluded from 1RM analysis — high-rep isolation work is judged by volume instead.
MAX_REPS_FOR_1RM = 12


def estimated_1rm(weight: float, reps: int, formula: Formula = "epley") -> Optional[float]:
    if weight is None or reps is None or weight <= 0 or reps <= 0:
        return None
    if reps > MAX_REPS_FOR_1RM:
        return None
    if reps == 1:
        return round(weight, 1)
    if formula == "brzycki":
        if reps >= 37:
            return None
        return round(weight * 36 / (37 - reps), 1)
    return round(weight * (1 + reps / 30), 1)  # Epley


def _working_sets_for(session: Session, exercise: str) -> list[WorkoutSet]:
    """Match by exercise_template_id if `exercise` is a known id, else by title."""
    template = session.get(ExerciseTemplate, exercise)
    stmt = select(WorkoutSet)
    if template:
        stmt = stmt.where(WorkoutSet.exercise_template_id == exercise)
    else:
        stmt = stmt.where(WorkoutSet.exercise_title == exercise)
    rows = session.exec(stmt).all()
    return [
        r
        for r in rows
        if r.set_type in WORKING_SET_TYPES and r.weight_kg and r.reps and r.workout_start_time
    ]


def exercise_trend(
    session: Session, exercise: str, formula: Formula = "epley"
) -> list[dict]:
    """Per-session best estimated 1RM for one exercise, oldest -> newest."""
    rows = _working_sets_for(session, exercise)
    by_session: dict[str, dict] = {}
    for r in rows:
        est = estimated_1rm(r.weight_kg, r.reps, formula)
        if est is None:
            continue
        key = r.workout_id
        cur = by_session.get(key)
        if cur is None or est > cur["est_1rm"]:
            by_session[key] = {
                "date": r.workout_start_time.isoformat() if r.workout_start_time else None,
                "start_time": r.workout_start_time,
                "est_1rm": est,
                "top_weight_kg": r.weight_kg,
                "top_reps": r.reps,
            }
    series = sorted(by_session.values(), key=lambda d: d["start_time"] or datetime.min)
    for s in series:
        s.pop("start_time", None)
    return series


def list_tracked_exercises(session: Session, min_sessions: int = 2) -> list[dict]:
    """Distinct exercises with a weight logged, plus their session counts — powers the
    dashboard exercise picker."""
    rows = session.exec(select(WorkoutSet)).all()
    sessions_by_ex: dict[str, set] = defaultdict(set)
    template_by_ex: dict[str, Optional[str]] = {}
    for r in rows:
        if (
            r.set_type in WORKING_SET_TYPES
            and r.weight_kg
            and r.reps
            and r.reps <= MAX_REPS_FOR_1RM
        ):
            sessions_by_ex[r.exercise_title].add(r.workout_id)
            template_by_ex.setdefault(r.exercise_title, r.exercise_template_id)
    out = [
        {
            "exercise": title,
            "template_id": template_by_ex.get(title),
            "sessions": len(ids),
        }
        for title, ids in sessions_by_ex.items()
        if len(ids) >= min_sessions
    ]
    return sorted(out, key=lambda d: d["sessions"], reverse=True)


def weekly_volume_by_muscle(session: Session) -> list[dict]:
    """Total working-set volume (weight_kg * reps) per ISO week per primary muscle group.
    Shape is friendly to a stacked area/bar chart."""
    templates = {t.id: t for t in session.exec(select(ExerciseTemplate)).all()}
    rows = session.exec(select(WorkoutSet)).all()
    agg: dict[tuple[str, str], float] = defaultdict(float)
    for r in rows:
        if r.set_type not in WORKING_SET_TYPES or not r.weight_kg or not r.reps:
            continue
        if not r.workout_start_time:
            continue
        tmpl = templates.get(r.exercise_template_id or "")
        muscle = (tmpl.primary_muscle_group if tmpl else None) or "other"
        iso = r.workout_start_time.isocalendar()
        week = f"{iso[0]}-W{iso[1]:02d}"
        agg[(week, muscle)] += r.weight_kg * r.reps
    out = [
        {"week": week, "muscle": muscle, "volume_kg": round(vol, 1)}
        for (week, muscle), vol in agg.items()
    ]
    return sorted(out, key=lambda d: (d["week"], d["muscle"]))


def stalled_lifts(
    session: Session,
    lookback_sessions: int,
    formula: Formula = "epley",
    recency_days: int = 28,
) -> list[dict]:
    """Flag lifts the user is CURRENTLY training whose best recent effort hasn't beaten
    their best earlier effort.

    Uses a rolling-window comparison (best estimated-1RM in the last `lookback_sessions`
    sessions vs the best of all earlier sessions), which is robust to alternating
    heavy/hypertrophy days logged under one exercise name — a single heavy day in the
    window still counts. Lifts not trained within `recency_days` of the latest logged
    workout are treated as dropped, not stalled, and excluded.
    """
    all_dates = [
        r.workout_start_time
        for r in session.exec(select(WorkoutSet)).all()
        if r.workout_start_time
    ]
    if not all_dates:
        return []
    latest = max(all_dates)

    exercises = list_tracked_exercises(session, min_sessions=lookback_sessions + 1)
    stalled: list[dict] = []
    for ex in exercises:
        series = exercise_trend(session, ex["template_id"] or ex["exercise"], formula)
        if len(series) < lookback_sessions + 1:
            continue

        last_date_s = series[-1]["date"]
        last_dt = datetime.fromisoformat(last_date_s) if last_date_s else None
        if last_dt is None or (latest - last_dt) > timedelta(days=recency_days):
            continue  # not currently training this lift

        ests = [s["est_1rm"] for s in series]
        recent_best = max(ests[-lookback_sessions:])
        prior_best = max(ests[:-lookback_sessions])
        if recent_best < prior_best:  # no PR in the recent window
            best_all = max(ests)
            pr_index = max(i for i, e in enumerate(ests) if e == best_all)
            stalled.append(
                {
                    "exercise": ex["exercise"],
                    "template_id": ex["template_id"],
                    "best_est_1rm": best_all,
                    "recent_best_est_1rm": recent_best,
                    "current_est_1rm": ests[-1],
                    "sessions_since_pr": len(series) - 1 - pr_index,
                    "last_pr_date": series[pr_index]["date"],
                    "last_session_date": last_date_s,
                }
            )
    # Surface the biggest plateaus first (largest gap between prior best and recent best).
    return sorted(stalled, key=lambda d: d["best_est_1rm"] - d["recent_best_est_1rm"], reverse=True)
