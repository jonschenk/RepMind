"""Weight-unit conversion shared by the chat and weekly-review proposal paths.

Everything is stored and sent to Hevy in KILOGRAMS. The coach proposes weights in the
user's DISPLAY unit (lb or kg) so the numbers stay round in their own unit, and we convert
here. KG_TO_LB matches the frontend constant exactly, so a round display weight round-trips
back to the same round number on the preview card (135 lb -> 61.235 kg -> 135.0 lb) instead
of a converted-looking fraction."""

from __future__ import annotations

from typing import Optional

KG_TO_LB = 2.2046


def to_kg(weight: Optional[float], unit: str) -> Optional[float]:
    """Display-unit weight -> canonical kilograms (None stays None)."""
    if weight is None:
        return None
    return float(weight) if unit == "kg" else round(float(weight) / KG_TO_LB, 4)


def to_display(kg: Optional[float], unit: str) -> Optional[float]:
    """Canonical kilograms -> display unit, rounded the way the card shows it."""
    if kg is None:
        return None
    return round(float(kg), 4) if unit == "kg" else round(float(kg) * KG_TO_LB, 1)


def routine_weights_to_kg(routine: dict, unit: str) -> dict:
    """Copy of a proposed routine dict with each set's display-unit `weight` converted to
    canonical `weight_kg`, so the rest of the pipeline (card, edit, push) stays kg-native."""
    out = dict(routine)
    exercises = []
    for ex in routine.get("exercises", []) or []:
        ex2 = dict(ex)
        sets2 = []
        for s in ex.get("sets", []) or []:
            s2 = {k: v for k, v in s.items() if k != "weight"}
            if s.get("weight") is not None:
                s2["weight_kg"] = to_kg(s["weight"], unit)
            sets2.append(s2)
        ex2["sets"] = sets2
        exercises.append(ex2)
    out["exercises"] = exercises
    return out
