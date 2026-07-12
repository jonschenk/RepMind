"""Streaming chat agent. Manual tool loop (not the SDK tool_runner) so the write path
can be intercepted: read tools auto-execute against the cache, but `propose_routine` is
captured and turned into an approval-gated preview instead of being executed."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from sqlmodel import Session

from app.chat.prompt import build_system_prompt
from app.chat.tools import ALL_TOOLS, execute_read_tool
from app.config import get_settings
from app.hevy import HevyClient
from app.llm import get_async_anthropic
from app.models import RoutineProposal
from app.state import get_preferences

# A full multi-day split needs many tool calls (exercise lookups + one propose_routine
# per day), so this must be generous or the model gets cut off mid-plan.
MAX_TOOL_ITERATIONS = 30


def _create_proposal(session: Session, proposed: dict) -> dict:
    row = RoutineProposal(
        status="pending",
        title=proposed.get("title", "Untitled routine"),
        payload=proposed,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return {
        "id": row.id,
        "title": row.title,
        "notes": proposed.get("notes"),
        "exercises": proposed.get("exercises", []),
        "status": row.status,
    }


async def stream_chat(
    history: list[dict], session: Session, client: HevyClient
) -> AsyncIterator[dict]:
    """Yield event dicts: {type: text|tool_use|proposal|done|error, ...}."""
    settings = get_settings()
    if not settings.anthropic_configured:
        yield {"type": "error", "message": "ANTHROPIC_API_KEY is not set."}
        return

    anthropic = get_async_anthropic()
    system = build_system_prompt(get_preferences(session)["weight_unit"])
    # Prior turns are plain text; the tool loop within this request adds block content.
    messages: list[dict[str, Any]] = [
        {"role": m["role"], "content": m["content"]} for m in history
    ]

    try:
        capped = True
        for _ in range(MAX_TOOL_ITERATIONS):
            async with anthropic.messages.stream(
                model=settings.chat_model,
                max_tokens=8000,
                thinking={"type": "adaptive"},
                system=system,
                tools=ALL_TOOLS,
                messages=messages,
            ) as stream:
                async for event in stream:
                    if event.type == "content_block_delta" and event.delta.type == "text_delta":
                        yield {"type": "text", "text": event.delta.text}
                final = await stream.get_final_message()

            # Echo the assistant turn (incl. thinking/tool_use blocks) back for context.
            messages.append({"role": "assistant", "content": final.content})

            if final.stop_reason != "tool_use":
                capped = False
                break

            tool_results = []
            for block in final.content:
                if block.type != "tool_use":
                    continue
                yield {"type": "tool_use", "name": block.name, "input": block.input}

                if block.name == "propose_routine":
                    proposal = _create_proposal(session, block.input)
                    yield {"type": "proposal", "proposal": proposal}
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": (
                                f"Routine '{proposal['title']}' was proposed and is now shown "
                                f"to the user as an approval card (proposal_id={proposal['id']}). "
                                "It has NOT been pushed to Hevy. Await the user's decision; do not "
                                "claim it has been added. You may briefly summarize the plan and its rationale."
                            ),
                        }
                    )
                else:
                    result_json = await execute_read_tool(
                        block.name, block.input, session, client
                    )
                    tool_results.append(
                        {"type": "tool_result", "tool_use_id": block.id, "content": result_json}
                    )

            messages.append({"role": "user", "content": tool_results})

        if capped:
            yield {
                "type": "text",
                "text": "\n\n_(I stopped after a lot of steps to avoid running away. Say \"continue\" and I'll finish the plan.)_",
            }
        yield {"type": "done"}
    except Exception as exc:  # never leave the SSE stream hanging
        yield {"type": "error", "message": str(exc)}
