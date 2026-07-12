from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.db import get_session
from app.deps import hevy_client_dep
from app.hevy import HevyClient, HevyError
from app.hevy.resolve import resolve_template_id
from app.hevy.schemas import (
    ResolvedExercise,
    ResolvedRoutine,
    ResolvedSet,
    build_routine_body,
)
from app.models import RoutineProposal

router = APIRouter(prefix="/api/routines", tags=["routines"])


@router.get("/proposals")
def list_proposals(session: Session = Depends(get_session)):
    rows = session.exec(
        select(RoutineProposal).order_by(RoutineProposal.created_at.desc())
    ).all()
    return rows


class ProposalUpdate(BaseModel):
    # Full replacement payload (title, notes, exercises) edited in the preview card.
    payload: dict[str, Any]


class ApproveRequest(BaseModel):
    # Optional edited payload to push instead of the stored one (edit-then-push).
    payload: Optional[dict[str, Any]] = None


@router.get("/proposals/{proposal_id}")
def get_proposal(proposal_id: int, session: Session = Depends(get_session)):
    row = session.get(RoutineProposal, proposal_id)
    if not row:
        raise HTTPException(404, "Proposal not found")
    return row


@router.patch("/proposals/{proposal_id}")
def update_proposal(
    proposal_id: int,
    body: ProposalUpdate,
    session: Session = Depends(get_session),
):
    """Save edits (notes, etc.) to a proposal without pushing. Lets the user refine the
    routine in the chat preview and add their own notes as they go."""
    row = session.get(RoutineProposal, proposal_id)
    if not row:
        raise HTTPException(404, "Proposal not found")
    if row.status == "pushed":
        raise HTTPException(409, "Already pushed to Hevy; edits no longer apply.")
    row.payload = body.payload
    row.title = body.payload.get("title", row.title)
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


@router.post("/proposals/{proposal_id}/approve")
async def approve_proposal(
    proposal_id: int,
    body: Optional[ApproveRequest] = None,
    session: Session = Depends(get_session),
    client: HevyClient = Depends(hevy_client_dep),
):
    """Resolve exercise names -> Hevy template UUIDs, build the wrapped body, and push.
    This is the ONLY path that writes a routine to Hevy. If an edited payload is supplied
    (from the preview card), it is persisted and pushed instead of the stored one."""
    row = session.get(RoutineProposal, proposal_id)
    if not row:
        raise HTTPException(404, "Proposal not found")
    if body and body.payload:
        row.payload = body.payload
        row.title = body.payload.get("title", row.title)
        session.add(row)
        session.commit()
    if row.status == "pushed":
        return {
            "id": row.id,
            "status": row.status,
            "hevy_routine_id": row.hevy_routine_id,
            "already": True,
        }

    payload = row.payload or {}
    exercises: list[ResolvedExercise] = []
    unresolved: list[str] = []

    for ex in payload.get("exercises", []):
        template_id = resolve_template_id(session, ex.get("name", ""))
        if not template_id:
            unresolved.append(ex.get("name", ""))
            continue
        sets = [
            ResolvedSet(
                type=s.get("type", "normal"),
                weight_kg=s.get("weight_kg"),
                reps=s.get("reps"),
            )
            for s in ex.get("sets", [])
        ]
        exercises.append(
            ResolvedExercise(
                exercise_template_id=template_id,
                rest_seconds=ex.get("rest_seconds"),
                notes=ex.get("notes"),
                sets=sets,
            )
        )

    if unresolved:
        # Never push a partial routine — surface the names we couldn't map.
        raise HTTPException(
            422,
            {
                "message": "Could not resolve some exercises to Hevy templates. Nothing pushed.",
                "unresolved": unresolved,
            },
        )

    if row.kind == "update" and not row.target_routine_id:
        raise HTTPException(422, "Update proposal has no target routine id. Nothing pushed.")

    # Destination folder applies only to NEW routines: a create places the routine into its
    # named folder (created or reused). Hevy forbids folder_id on a PUT, and a routine keeps
    # its folder across updates anyway, so updates carry no folder.
    folder_id: Optional[int] = None
    if row.kind != "update":
        folder_name = (payload.get("folder") or "").strip()
        if folder_name:
            folder_id = await client.find_or_create_folder(folder_name)

    routine = ResolvedRoutine(
        title=payload.get("title", "repMind routine"),
        notes=payload.get("notes"),
        folder_id=folder_id,
        exercises=exercises,
    )
    body = build_routine_body(routine, is_update=(row.kind == "update"))
    row.resolved_payload = body

    try:
        if row.kind == "update":
            result = await client.update_routine(row.target_routine_id, body)
        else:
            result = await client.create_routine(body)
    except HevyError as exc:
        row.status = "failed"
        row.error = str(exc)
        session.add(row)
        session.commit()
        raise HTTPException(502, f"Hevy push failed: {exc}")

    row.status = "pushed"
    row.hevy_routine_id = result.get("id")
    row.error = None
    session.add(row)
    session.commit()

    return {
        "id": row.id,
        "status": row.status,
        "hevy_routine_id": row.hevy_routine_id,
        "dry_run": result.get("dry_run", False),
        "resolved_payload": body,
    }
