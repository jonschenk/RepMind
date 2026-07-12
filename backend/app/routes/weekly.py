from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from app.coach.weekly_review import generate_weekly_review
from app.db import get_session
from app.deps import hevy_client_dep
from app.hevy import HevyClient
from app.models import RoutineProposal, WeeklyReview

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
