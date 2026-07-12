"""Assemble the system prompt from the editable coach-context.md plus fixed operating
rules (tool usage, the never-auto-write guarantee, units)."""

from functools import lru_cache
from pathlib import Path

_DEFAULT_CONTEXT = (
    "You are a knowledgeable, direct lifting coach for a single user. "
    "Be concise and specific."
)

# backend/app/chat/prompt.py -> repo root is parents[3]
_COACH_CONTEXT_PATH = Path(__file__).resolve().parents[3] / "coach-context.md"

OPERATING_RULES = """
## How you work

- You have tools to read this user's real Hevy training history (workouts, per-lift
  estimated-1RM trends, stalled lifts, exercise search). Use them before making claims
  about their training — don't guess at numbers you can look up.
- All logged weights and estimated 1RMs returned by tools are in KILOGRAMS. The user
  often thinks in pounds (1 kg ~= 2.205 lb); convert when it aids clarity. When you
  propose routine weights, express them in kilograms.
- When the user asks for a routine/session, call the `propose_routine` tool. This does
  NOT push anything to Hevy — it renders a preview the user must explicitly approve.
  Never claim you have "added" or "pushed" a routine; you propose, they approve.
- Resolve exercises by their real names as they appear in the user's history so they map
  to the correct Hevy exercise. If unsure of the exact name, use the exercise-search tool.
- If recent history shows a stalled or grindy lift, address it in the plan rather than
  ignoring it.
""".strip()


@lru_cache
def load_coach_context() -> str:
    try:
        return _COACH_CONTEXT_PATH.read_text(encoding="utf-8").strip()
    except OSError:
        return _DEFAULT_CONTEXT


def build_system_prompt() -> str:
    # Read fresh each call (cache cleared on demand) so edits to coach-context.md apply
    # without a restart during a session.
    load_coach_context.cache_clear()
    return f"{load_coach_context()}\n\n{OPERATING_RULES}"
