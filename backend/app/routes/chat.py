import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlmodel import Session

from app.chat.agent import stream_chat
from app.db import get_session
from app.deps import hevy_client_dep
from app.hevy import HevyClient

router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]


@router.post("")
async def chat(
    req: ChatRequest,
    session: Session = Depends(get_session),
    client: HevyClient = Depends(hevy_client_dep),
):
    history = [{"role": m.role, "content": m.content} for m in req.messages]

    async def event_source():
        async for event in stream_chat(history, session, client):
            yield f"data: {json.dumps(event, default=str)}\n\n"

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
