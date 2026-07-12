"""The dashboard "what to improve this week" card.

Rule-based signals (deterministic) are computed locally, then handed to one Claude call
that writes the card in the coach's voice. If Anthropic isn't configured, a plain
rule-based fallback is returned so the dashboard still works."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlmodel import Session

from app.analysis import progression
from app.analysis import volume as volume_mod
from app.chat.prompt import NO_DASH_RULE, load_coach_context
from app.config import get_settings
from app.hevy.schemas import strip_dashes
from app.llm import get_async_anthropic
from app.state import get_preferences, get_state, set_state

SUMMARY_KEY = "dashboard_summary"


def compute_signals(session: Session) -> dict:
    settings = get_settings()
    lookback = settings.stall_lookback_sessions
    end = datetime.utcnow()
    start = end - timedelta(days=14)

    overview = progression.progression_overview(session, lookback)
    return {
        "training_mix": progression.training_mix(session),
        "regressing": [p for p in overview if p["verdict"] == "regressing"][:6],
        "progressing": [p for p in overview if p["verdict"] == "progressing"][:6],
        "muscle_volume_2wk": volume_mod.muscle_volume_report(session, start, end),
        "lookback_sessions": lookback,
    }


def _fallback_summary(signals: dict) -> str:
    parts = ["**This week's focus**"]
    if signals["regressing"]:
        names = ", ".join(p["exercise"] for p in signals["regressing"][:3])
        parts.append(f"- Regressing: {names}. Rebuild the working volume before chasing load.")
    if signals["progressing"]:
        names = ", ".join(p["exercise"] for p in signals["progressing"][:3])
        parts.append(f"- Progressing: {names}. Keep driving reps and volume.")
    delt = next((v for v in signals["muscle_volume_2wk"] if v.get("priority")), None)
    if delt and delt["status"] == "under":
        parts.append("- Side/rear delts under target. Add cable laterals and face pulls, high rep.")
    return "\n".join(parts)


async def generate_summary(session: Session) -> dict:
    signals = compute_signals(session)
    settings = get_settings()
    generated_at = datetime.utcnow().isoformat()

    if not settings.anthropic_configured:
        return {"generated_at": generated_at, "summary": _fallback_summary(signals), "signals": signals}

    import json

    unit = get_preferences(session)["weight_unit"]
    client = get_async_anthropic()
    user_msg = (
        "Deterministic signals from the user's recent Hevy data (weights in kg). Write a "
        "short, direct 'what to improve this week' card (~120-160 words, markdown, coach "
        "voice). This user trains mostly hypertrophy, so judge progress by the `progression` "
        "verdicts (progressing/holding/regressing, each with a reason across load, reps, and "
        "volume), NOT by estimated 1RM. Call out what's regressing, protect what's "
        "progressing, and check the side/rear-delt priority in `muscle_volume_2wk`. Give "
        f"judgment, don't restate every number. Present weights in {unit} (signals are kg; "
        "1 kg = 2.2046 lb).\n\n"
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


async def get_cached_summary(session: Session) -> dict:
    """Return the cached summary. Only generates (one Claude call) if nothing is cached
    yet; otherwise it's served from the DB. Regeneration is scheduled weekly, never on a
    page load, so browsing the dashboard costs no tokens."""
    cached = get_state(session, SUMMARY_KEY)
    if cached:
        return cached
    return await refresh_summary(session)


async def refresh_summary(session: Session) -> dict:
    """Generate a fresh summary and cache it (used on first load and the weekly job)."""
    data = await generate_summary(session)
    set_state(session, SUMMARY_KEY, data)
    return data
