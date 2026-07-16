"""Claude API cost/usage tracking.

Each LLM call records its token usage + an estimated dollar cost, tagged by surface, so the
user can see what repMind is spending. Best-effort: recording never breaks the caller."""

from __future__ import annotations

import logging
from datetime import datetime

from sqlmodel import Session, select

from app.db import engine
from app.models import LlmUsage

logger = logging.getLogger("repmind.usage")

# Estimated USD per 1M tokens (input, output). Thinking tokens bill as output. These are
# list prices and may drift; treat the totals as an estimate. Sonnet 5 shown at intro rate.
PRICING: dict[str, tuple[float, float]] = {
    "claude-opus-4-8": (5.0, 25.0),
    "claude-opus-4-7": (5.0, 25.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-fable-5": (10.0, 50.0),
}


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    in_price, out_price = PRICING.get(model, (5.0, 25.0))  # default to Opus-tier if unknown
    return round(input_tokens / 1e6 * in_price + output_tokens / 1e6 * out_price, 6)


def record_usage(surface: str, model: str, input_tokens: int, output_tokens: int) -> None:
    """Persist one call's usage. Swallows all errors so it never breaks the request."""
    try:
        cost = estimate_cost(model, input_tokens, output_tokens)
        with Session(engine) as session:
            session.add(
                LlmUsage(
                    surface=surface,
                    model=model,
                    input_tokens=int(input_tokens or 0),
                    output_tokens=int(output_tokens or 0),
                    cost_usd=cost,
                )
            )
            session.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning("usage recording failed: %s", exc)


def usage_summary(session: Session) -> dict:
    """Current-calendar-month and last-30-day totals, plus a per-surface breakdown."""
    now = datetime.utcnow()
    month_start = datetime(now.year, now.month, 1)
    rows = session.exec(select(LlmUsage)).all()

    month = {"cost_usd": 0.0, "input_tokens": 0, "output_tokens": 0, "by_surface": {}}
    all_time_cost = 0.0
    calls = 0
    for r in rows:
        all_time_cost += r.cost_usd
        if r.created_at and r.created_at >= month_start:
            calls += 1
            month["cost_usd"] += r.cost_usd
            month["input_tokens"] += r.input_tokens
            month["output_tokens"] += r.output_tokens
            s = month["by_surface"].setdefault(r.surface, {"cost_usd": 0.0, "calls": 0})
            s["cost_usd"] += r.cost_usd
            s["calls"] += 1

    month["cost_usd"] = round(month["cost_usd"], 4)
    for s in month["by_surface"].values():
        s["cost_usd"] = round(s["cost_usd"], 4)
    return {
        "month_label": now.strftime("%B %Y"),
        "month": month,
        "month_calls": calls,
        "all_time_cost_usd": round(all_time_cost, 4),
    }
