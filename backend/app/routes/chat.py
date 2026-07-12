import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlmodel import Session, select

from app.chat.agent import stream_chat
from app.db import get_session
from app.deps import hevy_client_dep
from app.hevy import HevyClient
from app.models import ChatMessage, RoutineProposal

router = APIRouter(prefix="/api/chat", tags=["chat"])

# How many recent turns to feed back as context (memory). The full log is kept in the DB.
CONTEXT_MESSAGES = 40


class ChatRequest(BaseModel):
    message: str


def _proposal_card(p: RoutineProposal) -> dict:
    """Reconstruct the card shape the stream emits, from a stored proposal row."""
    payload = p.payload or {}
    return {
        "id": p.id,
        "title": p.title,
        "notes": payload.get("notes"),
        "folder": payload.get("folder"),
        "exercises": payload.get("exercises", []),
        "status": p.status,
    }


@router.get("/history")
def history(session: Session = Depends(get_session)):
    rows = session.exec(select(ChatMessage).order_by(ChatMessage.id)).all()
    # Replay still-pending approval cards, grouped under the assistant turn that made them,
    # so they survive a page reload (the streamed proposal events are otherwise ephemeral).
    pending = session.exec(
        select(RoutineProposal)
        .where(RoutineProposal.status == "pending")
        .where(RoutineProposal.chat_message_id.is_not(None))
        .order_by(RoutineProposal.id)
    ).all()
    by_msg: dict[int, list[dict]] = {}
    for p in pending:
        by_msg.setdefault(p.chat_message_id, []).append(_proposal_card(p))
    return [
        {"role": r.role, "content": r.content, "proposals": by_msg.get(r.id, [])}
        for r in rows
    ]


@router.post("")
async def chat(
    req: ChatRequest,
    session: Session = Depends(get_session),
    client: HevyClient = Depends(hevy_client_dep),
):
    # Persist the user turn, then build context from the recent stored history (memory).
    session.add(ChatMessage(role="user", content=req.message))
    session.commit()

    recent = session.exec(
        select(ChatMessage).order_by(ChatMessage.id.desc()).limit(CONTEXT_MESSAGES)
    ).all()
    history = [{"role": m.role, "content": m.content} for m in reversed(recent)]

    async def event_source():
        assistant_text: list[str] = []
        proposal_ids: list[int] = []
        async for event in stream_chat(history, session, client):
            etype = event.get("type")
            if etype == "text":
                assistant_text.append(event["text"])
            elif etype == "proposal":
                pid = event.get("proposal", {}).get("id")
                if pid is not None:
                    proposal_ids.append(pid)
            yield f"data: {json.dumps(event, default=str)}\n\n"
        text = "".join(assistant_text).strip()
        # Persist the assistant turn if it said anything OR produced approval cards, then
        # link those proposals to it so the cards replay from history after a reload.
        if text or proposal_ids:
            msg = ChatMessage(role="assistant", content=text)
            session.add(msg)
            session.commit()
            session.refresh(msg)
            if proposal_ids:
                linked = session.exec(
                    select(RoutineProposal).where(RoutineProposal.id.in_(proposal_ids))
                ).all()
                for p in linked:
                    p.chat_message_id = msg.id
                    session.add(p)
                session.commit()

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
