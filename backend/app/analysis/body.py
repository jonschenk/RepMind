"""Bodyweight + body-composition stats from the synced Hevy body measurements, plus
relative strength (estimated 1RM per bodyweight) for the main lifts."""

from __future__ import annotations

from datetime import date
from typing import Optional

from sqlmodel import Session, select

from app.analysis import progression
from app.models import BodyMeasurement

# Bodyweight target band (lb), from the coach context.
TARGET_LB = (180, 185)
STALE_DAYS = 21
_BIG_LIFTS = [
    "Bench Press (Barbell)",
    "Squat (Barbell)",
    "Deadlift (Barbell)",
    "Overhead Press (Barbell)",
]


def relative_strength(session: Session, bodyweight_kg: Optional[float]) -> list[dict]:
    if not bodyweight_kg:
        return []
    out = []
    for name in _BIG_LIFTS:
        e = progression.lift_progression(session, name).get("best_est_1rm")
        if e:
            out.append({"exercise": name, "est_1rm_kg": e, "ratio": round(e / bodyweight_kg, 2)})
    return out


def body_stats(session: Session) -> dict:
    rows = [
        r
        for r in session.exec(select(BodyMeasurement)).all()
        if r.weight_kg and r.date
    ]
    rows.sort(key=lambda r: r.date)
    if not rows:
        return {"has_data": False, "target_lb": list(TARGET_LB)}

    latest = rows[-1]
    try:
        days_since = (date.today() - date.fromisoformat(latest.date)).days
    except ValueError:
        days_since = None

    return {
        "has_data": True,
        "latest": {
            "date": latest.date,
            "weight_kg": latest.weight_kg,
            "fat_percent": latest.fat_percent,
        },
        "days_since": days_since,
        "stale": days_since is not None and days_since > STALE_DAYS,
        "target_lb": list(TARGET_LB),
        "trend": [
            {"date": r.date, "weight_kg": r.weight_kg, "fat_percent": r.fat_percent}
            for r in rows
        ],
        "relative_strength": relative_strength(session, latest.weight_kg),
    }
