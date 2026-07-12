"""The dashboard "what to improve this week" card.

Rule-based signals (deterministic) are computed locally, then handed to one Claude call
that writes the card in the coach's voice. If Anthropic isn't configured, a plain
rule-based fallback is returned so the dashboard still works."""

from __future__ import annotations

from datetime import datetime

from sqlmodel import Session

from app.analysis.trends import (
    exercise_trend,
    list_tracked_exercises,
    stalled_lifts,
    weekly_volume_by_muscle,
)
from app.chat.prompt import NO_DASH_RULE, load_coach_context
from app.config import get_settings
from app.hevy.schemas import strip_dashes
from app.llm import get_async_anthropic

_LATERAL_REAR_KEYWORDS = ("lateral", "lat raise", "face pull", "rear delt", "reverse fly", "reverse pec")


def _improving_lifts(session: Session, lookback: int) -> list[dict]:
    out = []
    for ex in list_tracked_exercises(session, min_sessions=lookback + 1):
        series = exercise_trend(session, ex["template_id"] or ex["exercise"])
        if len(series) < lookback + 1:
            continue
        ests = [s["est_1rm"] for s in series]
        if max(ests[-lookback:]) > max(ests[:-lookback]):
            out.append(
                {
                    "exercise": ex["exercise"],
                    "best_est_1rm": max(ests),
                    "prev_best": round(max(ests[:-lookback]), 1),
                }
            )
    return sorted(out, key=lambda d: d["best_est_1rm"] - d["prev_best"], reverse=True)[:5]


def compute_signals(session: Session) -> dict:
    settings = get_settings()
    lookback = settings.stall_lookback_sessions

    volume = weekly_volume_by_muscle(session)
    recent_weeks = sorted({v["week"] for v in volume})[-2:]
    recent_volume = [v for v in volume if v["week"] in recent_weeks]

    # Side/rear-delt accessory frequency in recent weeks (the user's stated weak point).
    lateral_rear_sessions = 0
    seen = set()
    for ex in list_tracked_exercises(session, min_sessions=1):
        title = ex["exercise"].lower()
        if any(k in title for k in _LATERAL_REAR_KEYWORDS):
            series = exercise_trend(session, ex["template_id"] or ex["exercise"])
            for s in series:
                if s["date"] and s["date"][:10] not in seen:
                    seen.add(s["date"][:10])
    lateral_rear_sessions = len(seen)

    return {
        "stalled_lifts": stalled_lifts(session, lookback)[:5],
        "improving_lifts": _improving_lifts(session, lookback),
        "recent_volume_by_muscle": recent_volume,
        "lateral_rear_delt_sessions_logged": lateral_rear_sessions,
        "lookback_sessions": lookback,
    }


def _fallback_summary(signals: dict) -> str:
    parts = ["**This week's focus**"]
    if signals["stalled_lifts"]:
        names = ", ".join(s["exercise"] for s in signals["stalled_lifts"][:3])
        parts.append(f"- Stalled: {names}. Change a variable (rep range, intensity, or volume).")
    if signals["improving_lifts"]:
        names = ", ".join(s["exercise"] for s in signals["improving_lifts"][:3])
        parts.append(f"- Trending up: {names}. Keep pushing.")
    if signals["lateral_rear_delt_sessions_logged"] == 0:
        parts.append("- No lateral/rear-delt work logged recently — that's the priority weak point. Add cable lateral raises and face pulls, high rep.")
    return "\n".join(parts)


async def generate_summary(session: Session) -> dict:
    signals = compute_signals(session)
    settings = get_settings()
    generated_at = datetime.utcnow().isoformat()

    if not settings.anthropic_configured:
        return {"generated_at": generated_at, "summary": _fallback_summary(signals), "signals": signals}

    import json

    client = get_async_anthropic()
    user_msg = (
        "Here are deterministic signals computed from the user's last few weeks of Hevy "
        "data (weights in kg). Write a short, direct 'what to improve this week' card "
        "(~120-160 words, markdown, coach voice). Prioritize the user's stated weak point "
        "(side/rear delts) and address any stalled lifts specifically. Don't restate every "
        "number — give judgment.\n\n"
        f"SIGNALS:\n{json.dumps(signals, indent=2, default=str)}"
    )
    resp = await client.messages.create(
        model=settings.anthropic_model,
        max_tokens=1200,
        thinking={"type": "adaptive"},
        output_config={"effort": "medium"},
        system=f"{load_coach_context()}\n\n{NO_DASH_RULE}",
        messages=[{"role": "user", "content": user_msg}],
    )
    text = next((b.text for b in resp.content if b.type == "text"), "")
    # Backstop the no-em-dash rule in case the model slips.
    return {"generated_at": generated_at, "summary": strip_dashes(text.strip()), "signals": signals}
