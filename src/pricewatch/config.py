import os
from functools import lru_cache
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def to_asyncpg_url(url: str) -> str:
    """Turns the URLs hosting providers give (postgres://…?sslmode=require) into what SQLAlchemy+asyncpg expects."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            url = "postgresql+asyncpg://" + url[len(prefix) :]
    parts = urlsplit(url)
    query = []
    for key, value in parse_qsl(parts.query):
        if key == "sslmode":
            query.append(("ssl", value))  # asyncpg calls it "ssl"
        elif key in ("channel_binding", "options"):
            continue  # not supported by asyncpg
        else:
            query.append((key, value))
    return urlunsplit(parts._replace(query=urlencode(query)))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="PRICEWATCH_", extra="ignore", populate_by_name=True)

    database_url: str = Field(
        "postgresql+asyncpg://postgres:postgres@localhost:5432/pricewatch",
        # Direct (non-pooled) connections first: Neon/Vercel provide several names.
        validation_alias=AliasChoices(
            "PRICEWATCH_DATABASE_URL",
            "DATABASE_URL_UNPOOLED",
            "DATABASE_POSTGRES_URL_NON_POOLING",
            "DATABASE_URL",
        ),
    )
    user_agent: str = "PriceWatchBot/0.1 (+https://github.com/gigantic536wall/pricewatch)"
    request_timeout: float = 15.0
    # Minimum pause between two requests to the same host, to be polite to shops.
    per_host_delay: float = 2.0
    max_concurrency: int = 5
    respect_robots_txt: bool = True
    # Optional webhook (Discord, Slack, ntfy, Teams, …) for price-drop alerts.
    alert_webhook_url: str | None = None
    # Protects /api/cron/check (sent by Vercel Cron as "Authorization: Bearer …").
    cron_secret: str | None = Field(None, validation_alias=AliasChoices("PRICEWATCH_CRON_SECRET", "CRON_SECRET"))
    # Public demo: the bundled demo shop's products are tracked automatically.
    demo_mode: bool = False
    # True on serverless platforms (no long-lived connection pool there).
    serverless: bool = Field(default_factory=lambda: bool(os.environ.get("VERCEL")))

    @field_validator("database_url")
    @classmethod
    def _normalize_url(cls, v: str) -> str:
        return to_asyncpg_url(v)


@lru_cache
def get_settings() -> Settings:
    return Settings()
