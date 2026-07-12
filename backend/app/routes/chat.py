import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlmodel import Session, select

from app.chat.agent import stream_chat
from app.db import get_session
from app.deps import hevy_client_dep
from app.hevy import HevyClient
from app.models import ChatMessage

router = APIRouter(prefix="/api/chat", tags=["chat"])

# How many recent turns to feed back as context (memory). The full log is kept in the DB.
CONTEXT_MESSAGES = 40


class ChatRequest(BaseModel):
    message: str


@router.get("/history")
def history(session: Session = Depends(get_session)):
    rows = session.exec(select(ChatMessage).order_by(ChatMessage.id)).all()
    return [{"role": r.role, "content": r.content} for r in rows]


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
        async for event in stream_chat(history, session, client):
            if event.get("type") == "text":
                assistant_text.append(event["text"])
            yield f"data: {json.dumps(event, default=str)}\n\n"
        text = "".join(assistant_text).strip()
        if text:
            session.add(ChatMessage(role="assistant", content=text))
            session.commit()

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
