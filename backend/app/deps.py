from fastapi import HTTPException

from app.config import get_settings
from app.hevy import HevyClient, HevyError


def hevy_client_dep() -> HevyClient:
    settings = get_settings()
    if not settings.hevy_configured:
        raise HTTPException(status_code=400, detail="HEVY_API_KEY is not configured.")
    try:
        return HevyClient(settings)
    except HevyError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
