"""Hevy routine-body construction encodes several hard-won quirks (folder_id present on
create / forbidden on update, @-in-notes 400, em-dash ban, omit-empty). These guard them."""

from app.hevy.schemas import (
    ResolvedExercise,
    ResolvedRoutine,
    ResolvedSet,
    build_routine_body,
    sanitize_notes,
    strip_dashes,
)


def _routine(**kw):
    return ResolvedRoutine(
        title=kw.get("title", "Push"),
        folder_id=kw.get("folder_id"),
        notes=kw.get("notes"),
        exercises=kw.get(
            "exercises",
            [ResolvedExercise(exercise_template_id="ABC", sets=[ResolvedSet(type="normal", weight_kg=60.0, reps=5)])],
        ),
    )


def test_body_is_wrapped():
    body = build_routine_body(_routine())
    assert "routine" in body and "title" in body["routine"]


def test_create_includes_folder_id_update_omits_it():
    # POST 400s on an absent folder_id; PUT 400s if folder_id is present at all.
    create = build_routine_body(_routine(folder_id=42), is_update=False)["routine"]
    assert create["folder_id"] == 42

    create_none = build_routine_body(_routine(folder_id=None), is_update=False)["routine"]
    assert "folder_id" in create_none and create_none["folder_id"] is None

    update = build_routine_body(_routine(folder_id=42), is_update=True)["routine"]
    assert "folder_id" not in update


def test_notes_strip_at_sign_and_dashes():
    assert sanitize_notes("email me @ 3 sets - heavy") == "email me  3 sets - heavy"
    assert strip_dashes("a — b – c") == "a - b - c"


def test_empty_weight_and_rest_are_omitted():
    r = _routine(exercises=[ResolvedExercise(exercise_template_id="X", sets=[ResolvedSet(type="normal", reps=8)])])
    ex = build_routine_body(r)["routine"]["exercises"][0]
    assert "rest_seconds" not in ex
    assert "weight_kg" not in ex["sets"][0]
    assert ex["sets"][0]["reps"] == 8
