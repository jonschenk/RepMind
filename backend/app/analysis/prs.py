"""Estimated-1RM PR detection within a time window.

A PR = a session in the window whose best estimated 1RM beat everything logged before the
window for that lift. est-1RM captures both "heavier" and "more reps at the same load", so
it's a single clean signal. Also powers a future standalone PR feed."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlmodel import Session

from app.analysis.trends import Formula, exercise_trend, list_tracked_exercises


def prs_in_period(
    session: Session, start: datetime, end: datetime, formula: Formula = "epley"
) -> list[dict]:
    events: list[dict] = []
    for ex in list_tracked_exercises(session, min_sessions=1):
        series = exercise_trend(session, ex["template_id"] or ex["exercise"], formula)
        prior: list[float] = []
        in_window: list[dict] = []
        for p in series:
            if not p["date"]:
                continue
            dt = datetime.fromisoformat(p["date"])
            if dt < start:
                prior.append(p["est_1rm"])
            elif dt <= end:
                in_window.append(p)

        if not prior or not in_window:
            continue  # need prior history to call it a PR (skip brand-new lifts)
        best_in = max(in_window, key=lambda p: p["est_1rm"])
        prior_best = max(prior)
        if best_in["est_1rm"] > prior_best:
            events.append(
                {
                    "exercise": ex["exercise"],
                    "template_id": ex["template_id"],
                    "type": "est_1rm",
                    "est_1rm": best_in["est_1rm"],
                    "prev_best": prior_best,
                    "gain": round(best_in["est_1rm"] - prior_best, 1),
                    "weight_kg": best_in["top_weight_kg"],
                    "reps": best_in["top_reps"],
                    "date": best_in["date"],
                }
            )
    return sorted(events, key=lambda e: e["gain"], reverse=True)
