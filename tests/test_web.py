"""Dashboard and JSON API, with the database session replaced by the test session."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal as D

import httpx
import pytest

from pricewatch.analytics import Point
from pricewatch.charts import line_chart, sparkline
from pricewatch.models import PriceCheck, Product
from pricewatch.web import app, get_session, money


@pytest.fixture
async def client(session):
    async def override():
        yield session

    app.dependency_overrides[get_session] = override
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
async def product(session):
    p = Product(url="https://shop.test/p/1", name="Mühle <Pro>", target_price=D("95"))
    session.add(p)
    await session.flush()
    now = datetime.now(UTC)
    for days_ago, price in [(10, "120"), (5, "105"), (0, "99")]:
        checked_at = now - timedelta(days=days_ago)
        session.add(PriceCheck(product_id=p.id, checked_at=checked_at, price=D(price), currency="EUR"))
    await session.flush()
    return p


async def test_dashboard_lists_products_and_escapes_names(client, product):
    html = (await client.get("/")).text
    assert "Mühle &lt;Pro&gt;" in html and "<Pro>" not in html
    assert "€99.00" in html
    assert 'class="spark down"' in html  # price went down over the period


async def test_product_page_with_chart(client, product):
    r = await client.get(f"/products/{product.id}")
    assert r.status_code == 200
    assert '<svg class="chart"' in r.text and "target €95.00" not in r.text  # label uses plain number format
    assert "target 95.00 EUR" in r.text


async def test_unknown_product_is_404(client, session):
    assert (await client.get("/products/999")).status_code == 404
    assert (await client.get("/api/products/999/history")).status_code == 404


async def test_api(client, product):
    (item,) = (await client.get("/api/products")).json()
    assert item["price"] == "99.00" and item["currency"] == "EUR" and item["target_price"] == "95.00"
    history = (await client.get(f"/api/products/{product.id}/history", params={"days": 30})).json()
    assert [p["price"] for p in history["points"]] == ["120.00", "105.00", "99.00"]


async def test_demo_shop_and_robots_are_served(client, session):
    assert "Kaffeewerk" in (await client.get("/shop/")).text
    assert "Disallow: /shop/cart" in (await client.get("/robots.txt")).text


def test_money_format():
    assert money(D("1234.5"), "EUR") == "€1,234.50"
    assert money(D("49"), "CHF") == "49.00 CHF"
    assert money(None, "EUR") == "–"


def test_charts_handle_edge_cases():
    day = datetime(2026, 11, 1).date()
    assert sparkline([Point(day, D("5"), True)]) == ""  # one point: no line
    assert "No price history" in line_chart([], currency="EUR")
    flat = [Point(day, D("5"), True), Point(day, D("5"), False)]
    svg = line_chart(flat, currency="EUR", target=D("5"))
    assert "sold-out" in svg and "nan" not in svg.lower()
