import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session

from app.config import get_settings
from app.db import engine, init_db
from app.hevy import HevyClient
from app.models import SyncState
from app.routes import chat, dashboard, routines, sync
from app.sync.service import run_sync

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("repmind")


async def _startup_sync() -> None:
    """Best-effort sync on boot (full on first run, delta after). Never blocks startup."""
    settings = get_settings()
    if not settings.hevy_configured:
        logger.info("HEVY_API_KEY not set — skipping startup sync.")
        return
    try:
        with Session(engine) as session:
            client = HevyClient(settings)
            result = await run_sync(session, client)
            logger.info("Startup sync: %s", result)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Startup sync failed (continuing): %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # Kick off sync in the background so the API is available immediately.
    asyncio.create_task(_startup_sync())
    yield


app = FastAPI(title="repMind", lifespan=lifespan)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sync.router)
app.include_router(dashboard.router)
app.include_router(chat.router)
app.include_router(routines.router)


@app.get("/api/health")
def health():
    s = get_settings()
    with Session(engine) as session:
        state = session.get(SyncState, 1)
    return {
        "status": "ok",
        "hevy_configured": s.hevy_configured,
        "anthropic_configured": s.anthropic_configured,
        "dry_run": s.dry_run,
        "model": s.anthropic_model,
        "full_sync_done": bool(state and state.full_sync_done),
        "workout_count": state.workout_count if state else 0,
    }
