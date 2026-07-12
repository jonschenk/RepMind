from functools import lru_cache

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
    anthropic_model: str = "claude-opus-4-8"

    database_url: str = "sqlite:///./repmind.db"

    # A lift is "stalled" if it hasn't set a new estimated-1RM PR within this many of its
    # most recent sessions.
    stall_lookback_sessions: int = 4

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
