import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlmodel import Session

from app.analysis.summary import SUMMARY_KEY, refresh_summary
from app.coach.weekly_review import generate_weekly_review
from app.config import get_settings
from app.db import engine, init_db
from app.hevy import HevyClient
from app.models import SyncState
from app.routes import chat, dashboard, routines, settings as settings_routes, sync, weekly
from app.state import get_state
from app.sync.service import run_sync

scheduler = AsyncIOScheduler()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("repmind")


async def _weekly_review_job() -> None:
    """Pre-generate the weekly review so it's ready in-app. Best-effort."""
    settings = get_settings()
    if not (settings.hevy_configured and settings.anthropic_configured):
        return
    try:
        with Session(engine) as session:
            client = HevyClient(settings)
            await generate_weekly_review(session, client)
            logger.info("Scheduled weekly review generated.")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Scheduled weekly review failed: %s", exc)


async def _summary_refresh_job() -> None:
    """Regenerate the cached 'what to improve this week' summary. Scheduled for Saturday
    morning; never triggered by a page load."""
    settings = get_settings()
    if not settings.anthropic_configured:
        return
    try:
        with Session(engine) as session:
            await refresh_summary(session)
            logger.info("Scheduled dashboard summary refreshed.")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Scheduled summary refresh failed: %s", exc)


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
            # One-time: generate the summary if none is cached yet, so the first dashboard
            # load is instant. Cached in the DB thereafter (survives restarts/deploys).
            if settings.anthropic_configured and get_state(session, SUMMARY_KEY) is None:
                await refresh_summary(session)
                logger.info("Initial dashboard summary generated and cached.")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Startup sync failed (continuing): %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # Kick off sync in the background so the API is available immediately.
    asyncio.create_task(_startup_sync())
    # Weekly review pre-generation (Monday 06:00 local). In-app is the delivery surface.
    scheduler.add_job(
        _weekly_review_job, "cron", day_of_week="mon", hour=6, minute=0, id="weekly_review"
    )
    # "What to improve this week" refreshes Saturday morning (end of the training week),
    # never on a page load.
    scheduler.add_job(
        _summary_refresh_job, "cron", day_of_week="sat", hour=7, minute=0, id="summary_refresh"
    )
    scheduler.start()
    yield
    scheduler.shutdown(wait=False)


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
app.include_router(weekly.router)
app.include_router(settings_routes.router)


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
        "chat_model": s.chat_model,
        "coach_model": s.anthropic_model,
        "full_sync_done": bool(state and state.full_sync_done),
        "workout_count": state.workout_count if state else 0,
    }


# --- Serve the built frontend (production) ----------------------------------------
# When the built SPA exists, this one process serves both API and UI (no Node runtime,
# single origin, no CORS). Registered AFTER the API routers so /api/* still wins.
_STATIC_DIR = Path(settings.static_dir) if settings.static_dir else (
    Path(__file__).resolve().parents[2] / "frontend" / "dist"
)

if _STATIC_DIR.is_dir():
    logger.info("Serving built frontend from %s", _STATIC_DIR)

    @app.get("/{full_path:path}")
    async def spa(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")
        candidate = (_STATIC_DIR / full_path).resolve()
        # Serve a real asset if it exists and stays inside the static dir; else index.html.
        if full_path and candidate.is_file() and _STATIC_DIR.resolve() in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(_STATIC_DIR / "index.html")
