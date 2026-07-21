import json
import logging

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select

from app.coach.weekly_review import generate_weekly_review, stream_weekly_review
from app.db import get_session
from app.deps import hevy_client_dep
from app.hevy import HevyClient
from app.models import RoutineProposal, WeeklyReview

logger = logging.getLogger("repmind.weekly")

router = APIRouter(prefix="/api/weekly", tags=["weekly"])


def _assemble(review: WeeklyReview, session: Session) -> dict:
    payload = review.payload or {}
    proposals = []
    for pid in payload.get("proposal_ids", []):
        row = session.get(RoutineProposal, pid)
        if not row or row.status == "dismissed":
            continue
        proposals.append(
            {
                "id": row.id,
                "kind": row.kind,
                "target_routine_id": row.target_routine_id,
                "title": row.title,
                "diff": row.diff,
                "payload": row.payload,
                "status": row.status,
                "hevy_routine_id": row.hevy_routine_id,
            }
        )
    return {
        "id": review.id,
        "generated_at": review.generated_at.isoformat(),
        "period": {"start": review.period_start.isoformat(), "end": review.period_end.isoformat()},
        "narrative": payload.get("narrative", ""),
        "signals": payload.get("signals", {}),
        "proposals": proposals,
    }


@router.get("")
def latest_review(session: Session = Depends(get_session)):
    review = session.exec(
        select(WeeklyReview).order_by(WeeklyReview.generated_at.desc())
    ).first()
    if not review:
        return {"exists": False}
    return {"exists": True, **_assemble(review, session)}


@router.post("/generate")
async def generate(
    session: Session = Depends(get_session),
    client: HevyClient = Depends(hevy_client_dep),
):
    return await generate_weekly_review(session, client)


@router.post("/generate/stream")
async def generate_stream(
    session: Session = Depends(get_session),
    client: HevyClient = Depends(hevy_client_dep),
):
    """Stream generation progress as SSE: `step` events per phase (incl. heartbeats during the
    long draft), then a `done` event, so the UI shows live progress instead of a frozen wait."""

    async def event_source():
        try:
            async for ev in stream_weekly_review(session, client):
                yield f"data: {json.dumps(ev, default=str)}\n\n"
        except Exception as exc:  # noqa: BLE001 - surface to the client instead of hanging
            logger.exception("Weekly review generation failed: %s", exc)
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
