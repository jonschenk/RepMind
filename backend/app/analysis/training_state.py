"""Higher-order training judgments the per-lift verdict can't make on its own.

`progression` judges each lift over a short recent window. This module looks across the WHOLE
history and the whole body to answer the questions a coach actually asks:
- Which lifts are genuinely STAGNATING (no new best on any axis for many sessions), and which
  have been stuck long enough to warrant a variation SWAP rather than another nudge?
- Is the lifter systemically fried and due a DELOAD (several lifts regressing at once, a pile
  of fatigue notes, a long stretch with no lighter week)?

These are signals for the coach to weigh, not verdicts: a lift held at maintenance on purpose
is "stalled" by the numbers but not a problem, so the narrative still applies judgment.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

from sqlmodel import Session, select

from app.analysis.progression import (
    _lift_sets,
    _session_aggregates,
    tracked_lifts,
)
from app.analysis.trends import WORKING_SET_TYPES
from app.models import WorkoutSet

# A lift with no new best on ANY axis (est-1RM, volume-load, or best set) for this many of its
# own sessions is stagnating. Trained ~1-2x/week, 6 sessions is roughly 3-6 weeks.
STALL_MIN_SESSIONS = 6
# Stuck this long is past "add a rep" territory - the stimulus is stale, consider a swap.
SWAP_MIN_SESSIONS = 9
# Weeks of accumulation with no clearly lighter week before a deload is worth flagging.
DELOAD_WEEKS_THRESHOLD = 7


def _sessions_since_progress(agg: list[dict]) -> tuple[int, object]:
    """Given a lift's per-session aggregates (oldest->newest), how many sessions since it last
    set a new running-best on ANY axis, and the date of that last real improvement."""
    best_e = best_v = 0.0
    best_wt = best_reps = 0
    last_idx = 0
    for i, a in enumerate(agg):
        improved = False
        if a["e1rm"] and a["e1rm"] > best_e * 1.005:
            best_e = a["e1rm"]
            improved = True
        if a["volume"] > best_v * 1.02:
            best_v = a["volume"]
            improved = True
        if a["best_weight"] > best_wt or (a["best_weight"] == best_wt and a["best_reps"] > best_reps):
            best_wt, best_reps = a["best_weight"], a["best_reps"]
            improved = True
        if improved:
            last_idx = i
    return len(agg) - 1 - last_idx, agg[last_idx]["date"]


def stalled_lifts(session: Session, recency_days: int = 28) -> list[dict]:
    """Lifts still in rotation that haven't set a new best in STALL_MIN_SESSIONS+ sessions,
    with how long they've been stuck and whether they're swap candidates. Most-stuck first."""
    all_dates = [r.workout_start_time for r in session.exec(select(WorkoutSet)).all() if r.workout_start_time]
    if not all_dates:
        return []
    latest = max(all_dates)

    out = []
    for ex in tracked_lifts(session, min_sessions=STALL_MIN_SESSIONS):
        agg = _session_aggregates(_lift_sets(session, ex["template_id"] or ex["exercise"]))
        if len(agg) < STALL_MIN_SESSIONS or (latest - agg[-1]["date"]) > timedelta(days=recency_days):
            continue
        since, last_progress = _sessions_since_progress(agg)
        if since < STALL_MIN_SESSIONS:
            continue
        out.append(
            {
                "exercise": ex["exercise"],
                "sessions_stuck": since,
                "weeks_stuck": max(0, (agg[-1]["date"] - last_progress).days // 7),
                "last_progress": last_progress.date().isoformat(),
                "swap_candidate": since >= SWAP_MIN_SESSIONS,
            }
        )
    return sorted(out, key=lambda d: -d["sessions_stuck"])


def _weeks_since_lighter_week(session: Session) -> int | None:
    """Weeks since the most recent clearly lighter week (a total-volume trough vs the two weeks
    before it) - a proxy for the last deload. None if no clear lighter week / not enough data."""
    weekly: dict[tuple, float] = defaultdict(float)
    for r in session.exec(select(WorkoutSet)).all():
        if r.set_type in WORKING_SET_TYPES and r.weight_kg and r.reps and r.workout_start_time:
            iso = r.workout_start_time.isocalendar()
            weekly[(iso[0], iso[1])] += r.weight_kg * r.reps
    vols = [v for _, v in sorted(weekly.items())]
    if len(vols) < 4:
        return None
    last_light = None
    for i in range(2, len(vols) - 1):  # exclude the current (possibly partial) week
        prior_peak = max(vols[i - 2], vols[i - 1])
        if prior_peak > 0 and vols[i] < 0.8 * prior_peak:
            last_light = i
    return None if last_light is None else (len(vols) - 1) - last_light


def deload_readiness(
    session: Session, progression_list: list[dict], notes_themes: list[dict]
) -> dict:
    """Systemic fatigue indicators + a soft deload recommendation. The coach makes the call."""
    regressing = [p for p in progression_list if p.get("verdict") == "regressing"]
    dropped = [p for p in progression_list if (p.get("volume_change_pct") or 0) <= -10]
    fatigue = [n for n in notes_themes if n.get("category") == "fatigue"]
    weeks_since = _weeks_since_lighter_week(session)

    reasons = []
    if len(regressing) >= 3:
        reasons.append(f"{len(regressing)} lifts regressing at once")
    if len(fatigue) >= 3:
        reasons.append(f"{len(fatigue)} fatigue/grind notes this week")
    if len(dropped) >= 5:
        reasons.append(f"volume down on {len(dropped)} lifts")
    if weeks_since is not None and weeks_since >= DELOAD_WEEKS_THRESHOLD:
        reasons.append(f"{weeks_since} weeks since a clearly lighter week")

    return {
        "regressing_lifts": len(regressing),
        "volume_dropped_lifts": len(dropped),
        "fatigue_notes": len(fatigue),
        "weeks_since_lighter_week": weeks_since,
        "recommend_deload": len(reasons) >= 2,
        "reasons": reasons,
    }


def training_state(
    session: Session, progression_list: list[dict], notes_themes: list[dict]
) -> dict:
    """Combined stagnation + deload picture for the coach."""
    return {
        "stalled_lifts": stalled_lifts(session),
        "deload": deload_readiness(session, progression_list, notes_themes),
    }
