import os
from pathlib import Path

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from pricewatch.config import Settings
from pricewatch.demo_shop import create_app
from pricewatch.fetch import Fetcher
from pricewatch.models import Base


def _test_database_url() -> str | None:
    if url := os.environ.get("PRICEWATCH_TEST_DATABASE_URL"):
        return url
    env = Path(__file__).parent.parent / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("PRICEWATCH_TEST_DATABASE_URL="):
                return line.split("=", 1)[1].strip().strip('"')
    return None


@pytest.fixture
async def session():
    """A session on an empty test database. Skipped when no test database is configured."""
    url = _test_database_url()
    if not url:
        pytest.skip("PRICEWATCH_TEST_DATABASE_URL not set")
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        yield s
    await engine.dispose()


@pytest.fixture
async def demo_fetcher():
    """A fetcher whose HTTP requests go straight to the in-process demo shop (no network)."""
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app()), base_url="http://shop.test")
    async with Fetcher(Settings(per_host_delay=0), client=client) as fetcher:
        yield fetcher
    await client.aclose()
