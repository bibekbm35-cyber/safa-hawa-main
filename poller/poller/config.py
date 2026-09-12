"""Poller configuration."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Shared with the API so both services read one variable. The API needs
    # SQLAlchemy's "+psycopg" driver suffix; raw psycopg does not understand
    # it, so we strip it in `dsn` below.
    database_url: str = "postgresql+psycopg://hawa:hawa@localhost:5432/safahawa"

    upstream_url: str = "https://air-quality-api.open-meteo.com/v1/air-quality"

    # Minutes between polls when running as a long-lived process.
    # Upstream publishes hourly; 15 minutes gives us four chances to catch each
    # new hour without hammering a free service.
    poll_interval_minutes: int = 15

    # How far back to re-request on every poll. Overlap is deliberate: it
    # repairs gaps left by a failed run, and the unique constraint makes the
    # duplicates free.
    lookback_hours: int = 6

    request_timeout_seconds: float = 20.0
    max_attempts: int = 4
    backoff_base_seconds: float = 2.0

    log_level: str = "INFO"
    metrics_port: int = 8001
    pushgateway_url: str | None = None

    @property
    def dsn(self) -> str:
        return self.database_url.replace("postgresql+psycopg://", "postgresql://")


settings = Settings()
