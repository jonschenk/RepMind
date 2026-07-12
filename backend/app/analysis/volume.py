"""Volume analysis by hard-set count (not tonnage) vs weekly landmarks.

Set counts map to hypertrophy stimulus better than tonnage, and let us judge whether a
muscle is under-stimulated. Special-cased: a side/rear-delt counter, since that's the
user's stated priority weak point and can't be read off the "shoulders" group alone
(which is dominated by pressing)."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Optional

from sqlmodel import Session, select

from app.analysis.trends import WORKING_SET_TYPES
from app.models import ExerciseTemplate, WorkoutSet

# Rough weekly hard-set landmarks (MEV, MAV) per primary muscle group. Heuristic starting
# points (RP-style), keyed by Hevy's lowercase muscle names. Tune in one place.
LANDMARKS: dict[str, tuple[int, int]] = {
    "chest": (10, 22),
    "back": (10, 22),
    "lats": (10, 22),
    "upper_back": (8, 18),
    "shoulders": (8, 20),
    "biceps": (8, 20),
    "triceps": (8, 18),
    "quadriceps": (8, 18),
    "hamstrings": (6, 16),
    "glutes": (4, 12),
    "calves": (8, 16),
    "abdominals": (6, 16),
    "forearms": (4, 12),
}

# Side/rear-delt work is identified by exercise name (the "shoulders" group can't
# distinguish lateral/rear from front-delt pressing).
_LATERAL_REAR_KEYWORDS = (
    "lateral",
    "lat raise",
    "face pull",
    "rear delt",
    "reverse fly",
    "reverse pec",
    "rear-delt",
)
SIDE_REAR_DELT_TARGET = (12, 20)  # weekly hard sets; high-frequency priority


def _in_window(dt: Optional[datetime], start: Optional[datetime], end: Optional[datetime]) -> bool:
    if dt is None:
        return False
    if start and dt < start:
        return False
    if end and dt > end:
        return False
    return True


def _is_hard_set(r: WorkoutSet) -> bool:
    return r.set_type in WORKING_SET_TYPES and r.reps is not None and r.reps > 0


def _is_side_rear_delt(title: str) -> bool:
    t = (title or "").lower()
    return any(k in t for k in _LATERAL_REAR_KEYWORDS)


def hard_sets_by_muscle(
    session: Session, start: Optional[datetime] = None, end: Optional[datetime] = None
) -> dict[str, int]:
    templates = {t.id: t for t in session.exec(select(ExerciseTemplate)).all()}
    counts: dict[str, int] = defaultdict(int)
    for r in session.exec(select(WorkoutSet)).all():
        if not _is_hard_set(r) or not _in_window(r.workout_start_time, start, end):
            continue
        tmpl = templates.get(r.exercise_template_id or "")
        muscle = (tmpl.primary_muscle_group if tmpl else None) or "other"
        counts[muscle.lower()] += 1
    return dict(counts)


def side_rear_delt_sets(
    session: Session, start: Optional[datetime] = None, end: Optional[datetime] = None
) -> int:
    return sum(
        1
        for r in session.exec(select(WorkoutSet)).all()
        if _is_hard_set(r)
        and _in_window(r.workout_start_time, start, end)
        and _is_side_rear_delt(r.exercise_title)
    )


def _status(sets: int, mev: int, mav: int) -> str:
    if sets < mev:
        return "under"
    if sets > mav:
        return "over"
    return "in_range"


def muscle_volume_report(
    session: Session, start: Optional[datetime] = None, end: Optional[datetime] = None
) -> list[dict]:
    """Per-muscle hard-set counts vs landmarks for a window, plus a side/rear-delt row."""
    counts = hard_sets_by_muscle(session, start, end)
    report: list[dict] = []
    for muscle, sets in sorted(counts.items(), key=lambda kv: kv[1], reverse=True):
        mev, mav = LANDMARKS.get(muscle, (0, 0))
        report.append(
            {
                "muscle": muscle,
                "sets": sets,
                "mev": mev,
                "mav": mav,
                "status": _status(sets, mev, mav) if mav else "no_landmark",
            }
        )

    delt = side_rear_delt_sets(session, start, end)
    lo, hi = SIDE_REAR_DELT_TARGET
    report.insert(
        0,
        {
            "muscle": "side/rear delts (priority)",
            "sets": delt,
            "mev": lo,
            "mav": hi,
            "status": _status(delt, lo, hi),
            "priority": True,
        },
    )
    return report


def weekly_hard_sets_by_muscle(session: Session) -> list[dict]:
    """All-time weekly hard-set counts per muscle (for a trend chart)."""
    templates = {t.id: t for t in session.exec(select(ExerciseTemplate)).all()}
    agg: dict[tuple[str, str], int] = defaultdict(int)
    for r in session.exec(select(WorkoutSet)).all():
        if not _is_hard_set(r) or not r.workout_start_time:
            continue
        tmpl = templates.get(r.exercise_template_id or "")
        muscle = ((tmpl.primary_muscle_group if tmpl else None) or "other").lower()
        iso = r.workout_start_time.isocalendar()
        agg[(f"{iso[0]}-W{iso[1]:02d}", muscle)] += 1
    return sorted(
        ({"week": w, "muscle": m, "sets": c} for (w, m), c in agg.items()),
        key=lambda d: (d["week"], d["muscle"]),
    )
