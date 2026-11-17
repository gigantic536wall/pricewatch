import httpx
import pytest
from sqlalchemy import func, select

from pricewatch.config import get_settings
from pricewatch.models import PriceCheck, Product
from pricewatch.web import app, get_fetcher, get_session


@pytest.fixture
async def client(session, demo_fetcher, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "cron_secret", "test-secret")
    monkeypatch.setattr(settings, "demo_mode", True)
    monkeypatch.setattr(settings, "alert_webhook_url", None)

    async def session_override():
        yield session

    async def fetcher_override():
        yield demo_fetcher

    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[get_fetcher] = fetcher_override
    # base_url = the demo shop host, so the tracker checks the in-process shop.
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://shop.test") as c:
        yield c
    app.dependency_overrides.clear()


async def test_rejects_missing_or_wrong_secret(client):
    assert (await client.get("/api/cron/check")).status_code == 401
    assert (await client.get("/api/cron/check", headers={"Authorization": "Bearer nope"})).status_code == 401


async def test_demo_run_adds_shop_products_and_checks_them(client, session):
    r = await client.get("/api/cron/check", headers={"Authorization": "Bearer test-secret"})
    assert r.status_code == 200
    body = r.json()
    assert body["demo_products_added"] == 6
    assert (body["checked"], body["succeeded"], body["failed"]) == (6, 6, 0)
    assert await session.scalar(select(func.count()).select_from(PriceCheck)) == 6

    second = (await client.get("/api/cron/check", headers={"Authorization": "Bearer test-secret"})).json()
    assert second["demo_products_added"] == 0
    assert await session.scalar(select(func.count()).select_from(Product)) == 6


async def test_disabled_without_configured_secret(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "cron_secret", None)
    assert (await client.get("/api/cron/check", headers={"Authorization": "Bearer None"})).status_code == 401
