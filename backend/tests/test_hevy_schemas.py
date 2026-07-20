

def test_rep_max_is_never_sent_to_hevy():
    """rep_max is repMind-only: a Hevy routine set takes a single rep number, and an unknown
    field 400s the push. The builder must whitelist it out while keeping reps (range bottom)."""
    from app.hevy.schemas import ResolvedExercise, ResolvedRoutine, ResolvedSet, build_routine_body

    routine = ResolvedRoutine(
        title="Push",
        exercises=[
            ResolvedExercise(
                exercise_template_id="ABC123",
                sets=[ResolvedSet(type="normal", weight_kg=100.0, reps=10, rep_max=12)],
            )
        ],
    )
    body = build_routine_body(routine, is_update=True)
    sent_set = body["routine"]["exercises"][0]["sets"][0]
    assert "rep_max" not in sent_set, "rep_max must not reach the Hevy API"
    assert sent_set["reps"] == 10, "Hevy gets the bottom of the range"
