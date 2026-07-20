

def _one_set_body(**set_kwargs):
    from app.hevy.schemas import ResolvedExercise, ResolvedRoutine, ResolvedSet, build_routine_body

    routine = ResolvedRoutine(
        title="Push",
        exercises=[
            ResolvedExercise(exercise_template_id="ABC123", sets=[ResolvedSet(**set_kwargs)])
        ],
    )
    return build_routine_body(routine, is_update=True)["routine"]["exercises"][0]["sets"][0]


def test_rep_range_uses_hevys_native_shape():
    """Hevy stores a range as rep_range {start,end} with reps omitted. Our repMind-side
    rep_max must be translated, never sent as a raw field (unknown fields 400 the push)."""
    s = _one_set_body(type="normal", weight_kg=100.0, reps=10, rep_max=12)
    assert s["rep_range"] == {"start": 10, "end": 12}
    assert "rep_max" not in s, "rep_max is not a Hevy field"
    assert "reps" not in s, "Hevy expects reps omitted when a rep_range is set"


def test_single_target_still_sends_plain_reps():
    s = _one_set_body(type="normal", weight_kg=100.0, reps=3)
    assert s["reps"] == 3
    assert "rep_range" not in s


def test_degenerate_range_falls_back_to_single_reps():
    """rep_max equal to (or below) reps isn't a range - send a plain rep target."""
    s = _one_set_body(type="normal", weight_kg=100.0, reps=8, rep_max=8)
    assert s["reps"] == 8
    assert "rep_range" not in s
