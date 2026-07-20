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

from sqlmodel import Session, select

from app.analysis.progression import (
    _lift_sets,
    _session_aggregates,
    tracked_lifts,
)
from app.analysis.trends import WORKING_SET_TYPES
from app.models import WorkoutSet

# A lift with no volume-or-best-set improvement for this many of its own sessions is stalling.
# Trained ~1-2x/week, 6 sessions is roughly 3-6 weeks.
STALL_MIN_SESSIONS = 6
# Stuck this long is past "add a rep" territory - the stimulus is stale, consider a swap.
SWAP_MIN_SESSIONS = 9
# "Improvement" is measured against the best of the previous STALL_WINDOW sessions (recent-
# relative, not all-time), long enough to see through session-to-session noise.
STALL_WINDOW = 8
# Weeks of accumulation with no clearly lighter week before a deload is worth flagging.
DELOAD_WEEKS_THRESHOLD = 7


def _sessions_since_progress(agg: list[dict], window: int = STALL_WINDOW) -> tuple[int, object]:
    """Given a lift's per-session aggregates (oldest->newest), how many sessions since it last
    improved, and the date of that improvement.

    Progress is RECENT-RELATIVE, not all-time: a session counts as an improvement if it beats
    the best of the previous `window` sessions on volume-load OR best set (more weight, or same
    weight for more reps). This is deliberate - an all-time measure treats a lift that's still
    climbing in its current rep range as "stuck" just because it set a higher estimated 1RM
    during an old strength phase. est-1RM is intentionally ignored here for the same reason."""
    last_idx = 0
    for i in range(1, len(agg)):
        prior = agg[max(0, i - window):i]
        pv = max((a["volume"] for a in prior), default=0.0)
        pbw = max((a["best_weight"] for a in prior), default=0.0)
        pbr = max((a["best_reps"] for a in prior if a["best_weight"] == pbw), default=0)
        a = agg[i]
        improved = (
            a["volume"] > pv * 1.02
            or a["best_weight"] > pbw
            or (a["best_weight"] == pbw and a["best_reps"] > pbr)
        )
        if improved:
            last_idx = i
    return len(agg) - 1 - last_idx, agg[last_idx]["date"]


def stalled_lifts(session: Session, progression_list: list[dict]) -> list[dict]:
    """Lifts that are genuinely stagnating: the recent verdict already says holding/regressing
    AND they haven't improved (volume or best set, recent-relative) in STALL_MIN_SESSIONS+ of
    their own sessions. Gating on the verdict guarantees a lift that is actually progressing in
    its current rep range is never called stalled. Most-stuck first."""
    verdict_by = {p.get("exercise"): p for p in progression_list}
    out = []
    for ex in tracked_lifts(session, min_sessions=STALL_MIN_SESSIONS):
        p = verdict_by.get(ex["exercise"])
        if not p or p.get("verdict") not in ("holding", "regressing"):
            continue  # progressing / not currently in rotation -> not a stagnation candidate
        agg = _session_aggregates(_lift_sets(session, ex["template_id"] or ex["exercise"]))
        since, last_progress = _sessions_since_progress(agg)
        if since < STALL_MIN_SESSIONS:
            continue
        out.append(
            {
                "exercise": ex["exercise"],
                "verdict": p.get("verdict"),
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
        "stalled_lifts": stalled_lifts(session, progression_list),
        "deload": deload_readiness(session, progression_list, notes_themes),
    }
