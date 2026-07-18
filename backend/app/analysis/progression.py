"""Multi-signal progression analysis.

est-1RM is only one lens, and it fits the ~14% of this user's sets that are heavy. Most
of their training is 6+ reps, so we judge progress across THREE axes together: top-end
load (est-1RM), reps/best-set, and volume-load (tonnage = sum weight*reps). A lift that's
adding reps or volume is progressing even if its estimated 1RM is flat.

Unlike the 1RM-oriented helpers in trends.py, this module counts ALL weighted working sets
(any rep range), so high-rep isolation work (lateral raises, etc.) is analyzed too."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Optional

from sqlmodel import Session, select

from app.analysis.trends import WORKING_SET_TYPES, estimated_1rm
from app.models import ExerciseTemplate, WorkoutSet

# Rep-range bins follow the load-rep continuum (Schoenfeld/Grgic et al., "Loading
# Recommendations for Muscle Strength, Hypertrophy, and Local Endurance: A Re-examination of the
# Repetition Continuum", Sports 2021, + supporting hypertrophy meta-analyses). Growth is similar
# across ~6-20 reps when sets are taken near failure, so hypertrophy runs to 20, not 15 -- a
# 20-rep set is a growth stimulus, not endurance. These are coarse bins over a continuum;
# proximity to failure matters more than the exact rep count.
STRENGTH_MAX = 5       # 1-5 reps  (~>=85% 1RM)  -> strength / neural
HYPERTROPHY_MAX = 20   # 6-20 reps (~60-85% 1RM) -> hypertrophy; 21+ (light) -> endurance


def _lift_sets(session: Session, exercise: str) -> list[WorkoutSet]:
    template = session.get(ExerciseTemplate, exercise)
    stmt = select(WorkoutSet)
    if template:
        stmt = stmt.where(WorkoutSet.exercise_template_id == exercise)
    else:
        stmt = stmt.where(WorkoutSet.exercise_title == exercise)
    return [
        r
        for r in session.exec(stmt).all()
        if r.set_type in WORKING_SET_TYPES and r.weight_kg and r.reps and r.workout_start_time
    ]


def rep_mix(sets: list[WorkoutSet]) -> dict:
    total = len(sets)
    if not total:
        return {"strength": 0, "hypertrophy": 0, "endurance": 0, "total_sets": 0}
    s = sum(1 for r in sets if r.reps <= STRENGTH_MAX)
    h = sum(1 for r in sets if STRENGTH_MAX < r.reps <= HYPERTROPHY_MAX)
    e = sum(1 for r in sets if r.reps > HYPERTROPHY_MAX)
    return {
        "strength": round(100 * s / total),
        "hypertrophy": round(100 * h / total),
        "endurance": round(100 * e / total),
        "total_sets": total,
    }


def _session_aggregates(sets: list[WorkoutSet]) -> list[dict]:
    """One row per workout for a lift: best est-1RM, total volume-load, and best set."""
    by_workout: dict[str, dict] = {}
    for r in sets:
        w = by_workout.setdefault(r.workout_id, {"date": r.workout_start_time, "sets": []})
        w["sets"].append(r)
    out = []
    for w in by_workout.values():
        ss = w["sets"]
        e1rms = [e for e in (estimated_1rm(s.weight_kg, s.reps) for s in ss) if e]
        best = max(ss, key=lambda s: (s.weight_kg, s.reps))
        out.append(
            {
                "date": w["date"],
                "e1rm": max(e1rms) if e1rms else None,
                "volume": sum(s.weight_kg * s.reps for s in ss),
                "best_weight": best.weight_kg,
                "best_reps": best.reps,
            }
        )
    out.sort(key=lambda x: x["date"])
    return out


def lift_progression(session: Session, exercise: str, lookback: int = 4) -> dict:
    """Progression verdict across load / reps / volume for one lift."""
    sets = _lift_sets(session, exercise)
    agg = _session_aggregates(sets)
    all_e1rms = [a["e1rm"] for a in agg if a["e1rm"]]
    result: dict = {
        "exercise": exercise,
        "sessions": len(agg),
        "rep_mix": rep_mix(sets),
        "best_est_1rm": max(all_e1rms) if all_e1rms else None,
        "last_session_date": agg[-1]["date"].isoformat() if agg else None,
    }
    if len(agg) < lookback + 1:
        result.update({"verdict": "new", "reason": "not enough sessions yet"})
        return result

    recent, prior = agg[-lookback:], agg[:-lookback]

    e_recent = max([a["e1rm"] for a in recent if a["e1rm"]], default=None)
    e_prior = max([a["e1rm"] for a in prior if a["e1rm"]], default=None)
    load_up = bool(e_recent and e_prior and e_recent > e_prior * 1.005)

    v_recent = sum(a["volume"] for a in recent) / len(recent)
    v_prior = sum(a["volume"] for a in prior) / len(prior)
    vol_change = (v_recent - v_prior) / v_prior if v_prior else 0.0
    vol_up, vol_down = vol_change > 0.05, vol_change < -0.15

    prior_best = max(((a["best_weight"], a["best_reps"]) for a in prior), default=(0, 0))
    new_best = any(
        a["best_weight"] > prior_best[0]
        or (a["best_weight"] == prior_best[0] and a["best_reps"] > prior_best[1])
        for a in recent
    )

    if load_up or new_best or vol_up:
        verdict = "progressing"
    elif vol_down and not load_up and not new_best:
        verdict = "regressing"
    else:
        verdict = "holding"

    if new_best and not load_up:
        reason = "new top set (more weight or reps than before)"
    elif load_up:
        reason = "estimated 1RM climbing"
    elif vol_up:
        reason = f"volume up {round(vol_change * 100)}%"
    elif vol_down:
        reason = f"volume down {round(abs(vol_change) * 100)}%"
    else:
        reason = "flat on load, reps, and volume"

    result.update(
        {
            "verdict": verdict,
            "reason": reason,
            "volume_change_pct": round(vol_change * 100),
            "recent_best_set": {"weight_kg": recent[-1]["best_weight"], "reps": recent[-1]["best_reps"]},
        }
    )
    return result


def tracked_lifts(session: Session, min_sessions: int) -> list[dict]:
    """Lifts with enough weighted sessions, counting ALL rep ranges (not 1RM-biased)."""
    sessions_by_ex: dict[str, set] = defaultdict(set)
    template_by_ex: dict[str, Optional[str]] = {}
    for r in session.exec(select(WorkoutSet)).all():
        if r.set_type in WORKING_SET_TYPES and r.weight_kg and r.reps:
            sessions_by_ex[r.exercise_title].add(r.workout_id)
            template_by_ex.setdefault(r.exercise_title, r.exercise_template_id)
    return [
        {"exercise": t, "template_id": template_by_ex.get(t), "sessions": len(ids)}
        for t, ids in sessions_by_ex.items()
        if len(ids) >= min_sessions
    ]


_VERDICT_ORDER = {"regressing": 0, "holding": 1, "progressing": 2, "new": 3}


def progression_overview(
    session: Session, lookback: int = 4, recency_days: int = 28
) -> list[dict]:
    """Per-lift verdicts for lifts currently in the rotation. Attention-first ordering
    (regressing, then holding, then progressing)."""
    all_dates = [
        r.workout_start_time
        for r in session.exec(select(WorkoutSet)).all()
        if r.workout_start_time
    ]
    if not all_dates:
        return []
    latest = max(all_dates)

    out = []
    for ex in tracked_lifts(session, min_sessions=lookback + 1):
        prog = lift_progression(session, ex["template_id"] or ex["exercise"], lookback)
        prog["template_id"] = ex["template_id"]
        prog["exercise"] = ex["exercise"]
        last = prog.get("last_session_date")
        if not last or (latest - datetime.fromisoformat(last)) > timedelta(days=recency_days):
            continue
        out.append(prog)
    return sorted(
        out,
        key=lambda d: (_VERDICT_ORDER.get(d["verdict"], 4), -abs(d.get("volume_change_pct", 0))),
    )


def training_mix(session: Session) -> dict:
    """Overall rep-range distribution across all weighted working sets."""
    sets = [
        r
        for r in session.exec(select(WorkoutSet)).all()
        if r.set_type in WORKING_SET_TYPES and r.weight_kg and r.reps
    ]
    return rep_mix(sets)


def volume_load_series(session: Session, exercise: str) -> list[dict]:
    """Weekly volume-load (kg tonnage) for one lift, oldest -> newest."""
    agg: dict[str, float] = defaultdict(float)
    for r in _lift_sets(session, exercise):
        iso = r.workout_start_time.isocalendar()
        agg[f"{iso[0]}-W{iso[1]:02d}"] += r.weight_kg * r.reps
    return [{"week": w, "volume_kg": round(v, 1)} for w, v in sorted(agg.items())]
