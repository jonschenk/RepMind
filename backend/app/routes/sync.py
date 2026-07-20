from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.db import get_session
from app.deps import hevy_client_dep
from app.hevy import HevyClient
from app.models import SyncState
from app.sync.service import run_sync

router = APIRouter(prefix="/api/sync", tags=["sync"])


@router.post("")
async def sync_now(
    session: Session = Depends(get_session),
    client: HevyClient = Depends(hevy_client_dep),
):
    # An explicit "Sync now" should get everything fresh, including templates and body
    # measurements (which otherwise refresh on their own slower cadence).
    return await run_sync(session, client, force_refresh=True)


@router.get("/status")
def sync_status(session: Session = Depends(get_session)):
    state = session.get(SyncState, 1)
    if state is None:
        return {"full_sync_done": False, "workout_count": 0, "last_synced_at": None}
    return {
        "full_sync_done": state.full_sync_done,
        "workout_count": state.workout_count,
        "last_synced_at": state.last_synced_at,
        "templates_synced_at": state.templates_synced_at,
    }
