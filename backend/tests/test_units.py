"""Weight-unit conversion is on the live-write path (a wrong number gets pushed to Hevy),
so it's worth locking down."""

from app.units import KG_TO_LB, routine_weights_to_kg, to_display, to_kg


def test_lb_roundtrips_to_the_same_round_number():
    # The whole reason we convert in the coach's unit: 135 lb must come back as 135, not 134.9.
    for lb in [45, 95, 135, 185, 225, 315]:
        kg = to_kg(lb, "lb")
        assert to_display(kg, "lb") == float(lb)


def test_kg_is_identity():
    assert to_kg(100, "kg") == 100.0
    assert to_display(100, "kg") == 100.0


def test_none_stays_none():
    assert to_kg(None, "lb") is None
    assert to_display(None, "lb") is None


def test_kg_to_lb_constant_matches_frontend():
    assert KG_TO_LB == 2.2046


def test_routine_weights_to_kg_converts_and_drops_display_field():
    routine = {
        "title": "Push",
        "folder": "PPL",
        "exercises": [
            {
                "name": "Bench",
                "sets": [
                    {"type": "normal", "weight": 225, "reps": 3},
                    {"type": "normal", "reps": 8},  # bodyweight / no weight -> stays absent
                ],
            }
        ],
    }
    out = routine_weights_to_kg(routine, "lb")
    sets = out["exercises"][0]["sets"]
    assert "weight" not in sets[0]
    assert sets[0]["weight_kg"] == to_kg(225, "lb")
    assert "weight_kg" not in sets[1]  # no weight given -> no weight_kg invented
    assert out["folder"] == "PPL"  # unrelated keys preserved
