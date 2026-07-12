from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Repo-root .env (backend runs from backend/, .env lives one level up).
    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    hevy_api_key: str = ""
    anthropic_api_key: str = ""

    # When true, Hevy write calls are logged and not sent. Reads/sync still hit Hevy.
    dry_run: bool = True

    hevy_base_url: str = "https://api.hevyapp.com"
    # Interactive chat fires several tool calls per message, so it uses the cheaper
    # Sonnet 5 (same request surface as Opus: adaptive thinking, tool use, streaming).
    chat_model: str = "claude-sonnet-5"
    # Weekly review, dashboard summary, and notes run ~2-3x/week (scheduled) where the
    # extra quality is worth the cost, so they stay on Opus.
    anthropic_model: str = "claude-opus-4-8"

    database_url: str = "sqlite:///./repmind.db"

    # Production: directory of the built frontend (frontend/dist). When present, the API
    # process also serves the SPA, so no Node runtime is needed on the host. Defaults to
    # the repo's frontend/dist; override with STATIC_DIR.
    static_dir: Optional[str] = None

    # A lift is "stalled" if it hasn't set a new estimated-1RM PR within this many of its
    # most recent sessions.
    stall_lookback_sessions: int = 4

    # A session counts as a "heavy" lane session if its top working set is at or below this
    # rep count; otherwise it's a "hypertrophy" session. Keeps heavy/light days from muddying
    # each other's trends.
    heavy_rep_threshold: int = 5

    # Weekly review looks back this many days.
    weekly_review_days: int = 7

    cors_origins: list[str] = ["http://localhost:5173"]

    @property
    def hevy_configured(self) -> bool:
        return bool(self.hevy_api_key)

    @property
    def anthropic_configured(self) -> bool:
        return bool(self.anthropic_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
