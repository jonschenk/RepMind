"""Cost estimation math."""

from app.usage import PRICING, estimate_cost


def test_estimate_cost_uses_model_pricing():
    # sonnet-5 intro: $2/1M in, $10/1M out
    assert estimate_cost("claude-sonnet-5", 1_000_000, 0) == 2.0
    assert estimate_cost("claude-sonnet-5", 0, 1_000_000) == 10.0
    assert estimate_cost("claude-opus-4-8", 1_000_000, 1_000_000) == 30.0


def test_unknown_model_defaults_to_opus_tier():
    assert estimate_cost("some-future-model", 1_000_000, 0) == 5.0


def test_zero_tokens_is_free():
    assert estimate_cost("claude-opus-4-8", 0, 0) == 0.0


def test_known_models_present():
    for m in ["claude-opus-4-8", "claude-sonnet-5", "claude-haiku-4-5"]:
        assert m in PRICING
