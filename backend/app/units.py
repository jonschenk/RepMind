"""Weight-unit conversion shared by the chat and weekly-review proposal paths.

Everything is stored and sent to Hevy in KILOGRAMS. The coach proposes weights in the
user's DISPLAY unit (lb or kg) so the numbers stay round in their own unit, and we convert
here. KG_TO_LB matches the frontend constant exactly, so a round display weight round-trips
back to the same round number on the preview card (135 lb -> 61.235 kg -> 135.0 lb) instead
of a converted-looking fraction."""

from __future__ import annotations

import json

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


def _as_list(value, what: str) -> list:
    """Coerce a proposal list field into a real list.

    The model sometimes double-encodes an array as a JSON *string*
    (`"exercises": "[{...}]"`). Iterating that yields characters, which produced the
    infamous "dictionary update sequence element #0 has length 1" crash. Parsing it here
    turns a wasted retry round-trip into a silent success; anything genuinely malformed
    still raises a message that names the field."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError(f"'{what}' must be a list, got an unparseable string: {exc}") from exc
        if not isinstance(parsed, list):
            raise ValueError(f"'{what}' must be a list, got {type(parsed).__name__}")
        return parsed
    raise ValueError(f"'{what}' must be a list, got {type(value).__name__}: {value!r}")


def routine_weights_to_kg(routine: dict, unit: str) -> dict:
    """Copy of a proposed routine dict with each set's display-unit `weight` converted to
    canonical `weight_kg`, so the rest of the pipeline (card, edit, push) stays kg-native."""
    out = dict(routine)
    exercises = []
    for i, ex in enumerate(_as_list(routine.get("exercises"), "exercises")):
        # The model occasionally emits an exercise as a bare string. dict("Bench Press") then
        # raises the useless "dictionary update sequence element #0 has length 1; 2 is
        # required". Fail with something the model can actually act on instead.
        if not isinstance(ex, dict):
            raise ValueError(
                f"exercise #{i + 1} must be an object with 'name' and 'sets', got "
                f"{type(ex).__name__}: {ex!r}"
            )
        ex2 = dict(ex)
        sets2 = []
        for j, s in enumerate(_as_list(ex.get("sets"), f"sets of '{ex.get('name', '?')}'")):
            if not isinstance(s, dict):
                raise ValueError(
                    f"set #{j + 1} of '{ex.get('name', '?')}' must be an object with "
                    f"type/weight/reps, got {type(s).__name__}: {s!r}"
                )
            s2 = {k: v for k, v in s.items() if k != "weight"}
            if s.get("weight") is not None:
                s2["weight_kg"] = to_kg(s["weight"], unit)
            sets2.append(s2)
        ex2["sets"] = sets2
        exercises.append(ex2)
    out["exercises"] = exercises
    return out
