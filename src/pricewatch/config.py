from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="PRICEWATCH_", extra="ignore")

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/pricewatch"
    user_agent: str = "PriceWatchBot/0.1 (+https://github.com/gigantic536wall/pricewatch)"
    request_timeout: float = 15.0
    # Minimum pause between two requests to the same host, to be polite to shops.
    per_host_delay: float = 2.0
    max_concurrency: int = 5
    respect_robots_txt: bool = True
    # Optional webhook (Discord, Slack, ntfy, Teams, …) for price-drop alerts.
    alert_webhook_url: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
