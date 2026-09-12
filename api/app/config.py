"""Runtime configuration, read from the environment.

Nothing here has a hardcoded production value on purpose. Every setting that
changes between laptop / CI / cluster is an environment variable, which is what
lets the same image run in all three places.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # postgresql+psycopg://user:password@host:5432/dbname
    database_url: str = "postgresql+psycopg://hawa:hawa@localhost:5432/safahawa"

    # How old the newest reading may get before /readyz starts complaining.
    # Upstream publishes hourly, so 3h of silence means the poller is stuck.
    staleness_threshold_minutes: int = 180

    # Comma-separated list of browser origins allowed to call this API.
    cors_origins: str = "http://localhost:5173"

    log_level: str = "INFO"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
