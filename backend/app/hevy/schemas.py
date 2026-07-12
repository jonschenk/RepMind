"""Types + builders for routines we send TO Hevy.

Keeping the outgoing-payload construction here (alongside the client) means every Hevy
write quirk lives in the `hevy` package: the `{"routine": {...}}` wrapper, the `@`-in-notes
guard, and the "omit empty weight/rest rather than invent a placeholder" rule.
"""

from typing import Optional

from pydantic import BaseModel


def strip_dashes(text: Optional[str]) -> Optional[str]:
    """Replace em/en dashes with a plain hyphen. Hard user preference: never em dashes."""
    if text is None:
        return None
    return text.replace("—", "-").replace("–", "-")


def sanitize_notes(notes: Optional[str]) -> Optional[str]:
    """Hevy silently 400s on any `@` in a notes field. Also enforce the no-em-dash rule."""
    if notes is None:
        return None
    return strip_dashes(notes).replace("@", "")


class ResolvedSet(BaseModel):
    type: str = "normal"  # normal | warmup | failure | dropset
    weight_kg: Optional[float] = None
    reps: Optional[int] = None
    custom_metric: Optional[float] = None


class ResolvedExercise(BaseModel):
    exercise_template_id: str  # must be a real UUID; never guessed
    superset_id: Optional[int] = None
    rest_seconds: Optional[int] = None
    notes: Optional[str] = None
    sets: list[ResolvedSet] = []


class ResolvedRoutine(BaseModel):
    title: str
    folder_id: Optional[int] = None
    notes: Optional[str] = None
    exercises: list[ResolvedExercise] = []


def build_routine_body(routine: ResolvedRoutine, is_update: bool = False) -> dict:
    """Produce the exact JSON body for POST/PUT /v1/routines.

    - Wraps in {"routine": {...}} (bare object silently fails).
    - Sanitizes all notes fields (@ guard).
    - Omits weight_kg / rest_seconds when unset instead of writing a placeholder
      (Hevy defaults rest to 90s when omitted).
    - folder_id handling differs by verb: POST (create) REQUIRES it present (null when
      unset, else Hevy 400s reading `undefined`); PUT (update) FORBIDS it (Hevy 400s with
      "routine.folder_id is not allowed"), and a routine keeps its folder across updates
      anyway, so it is omitted when `is_update`.
    """
    exercises = []
    for ex in routine.exercises:
        sets = []
        for s in ex.sets:
            set_body: dict = {"type": s.type}
            if s.weight_kg is not None:
                set_body["weight_kg"] = s.weight_kg
            if s.reps is not None:
                set_body["reps"] = s.reps
            if s.custom_metric is not None:
                set_body["custom_metric"] = s.custom_metric
            sets.append(set_body)

        ex_body: dict = {"exercise_template_id": ex.exercise_template_id, "sets": sets}
        if ex.superset_id is not None:
            ex_body["superset_id"] = ex.superset_id
        if ex.rest_seconds is not None:
            ex_body["rest_seconds"] = ex.rest_seconds
        notes = sanitize_notes(ex.notes)
        if notes:
            ex_body["notes"] = notes
        exercises.append(ex_body)

    inner: dict = {"title": strip_dashes(routine.title), "exercises": exercises}
    # On create, folder_id must be PRESENT (null when unset). On update it must be ABSENT.
    if not is_update:
        inner["folder_id"] = routine.folder_id
    notes = sanitize_notes(routine.notes)
    if notes:
        inner["notes"] = notes

    return {"routine": inner}
