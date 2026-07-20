"""Stagnation detection: sessions since a lift last set a new best on any axis."""

from datetime import datetime, timedelta

from app.analysis.training_state import _sessions_since_progress


def _agg(rows):
    # rows: list of (e1rm, volume, best_weight, best_reps), oldest -> newest
    base = datetime(2026, 1, 1)
    return [
        {"date": base + timedelta(days=i * 3), "e1rm": e, "volume": v, "best_weight": w, "best_reps": r}
        for i, (e, v, w, r) in enumerate(rows)
    ]


def test_plateau_counts_sessions_since_last_pr():
    agg = _agg([
        (100, 1000, 100, 5),  # i0 baseline
        (102, 1050, 102, 5),  # i1 new best
        (102, 1050, 102, 5),  # i2 flat
        (102, 1050, 102, 5),  # i3 flat
        (102, 1050, 102, 5),  # i4 flat
    ])
    since, last = _sessions_since_progress(agg)
    assert since == 3  # last real improvement was i1, three sessions ago
    assert last == agg[1]["date"]


def test_still_progressing_is_zero():
    agg = _agg([(100, 1000, 100, 5), (102, 1050, 102, 5), (104, 1100, 104, 6)])
    since, _ = _sessions_since_progress(agg)
    assert since == 0


def test_a_rep_pr_at_same_weight_counts_as_progress():
    agg = _agg([
        (100, 1000, 225, 8),
        (100, 1000, 225, 8),
        (100, 1010, 225, 9),  # same weight, one more rep -> progress
    ])
    since, _ = _sessions_since_progress(agg)
    assert since == 0
