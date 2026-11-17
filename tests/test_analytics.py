"""SQL analytics against a real PostgreSQL database."""

import itertools
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D

from pricewatch.analytics import daily_series, product_stats
from pricewatch.demo_shop import BY_SLUG, price_on
from pricewatch.models import PriceCheck, Product
from pricewatch.seed import demo_slug, seed_demo_history

NOW = datetime(2026, 11, 17, 12, 0, tzinfo=UTC)


def at(days_ago: int, hour: int = 8) -> datetime:
    return (NOW - timedelta(days=days_ago)).replace(hour=hour, minute=0)


_counter = itertools.count(1)


async def add_product(session, **kwargs) -> Product:
    product = Product(url=kwargs.pop("url", f"https://shop.test/p/{next(_counter)}"), **kwargs)
    session.add(product)
    await session.flush()
    return product


async def test_stats_for_a_product(session):
    p = await add_product(session, name="Mill", target_price=D("90"))
    for days_ago, price in [(40, "120"), (20, "110"), (8, "100"), (3, "95"), (0, "88")]:
        session.add(PriceCheck(product_id=p.id, checked_at=at(days_ago), price=D(price), currency="EUR"))
    session.add(PriceCheck(product_id=p.id, checked_at=at(0, hour=11), error="Timeout"))  # newest attempt failed
    await session.flush()

    (s,) = await product_stats(session, NOW)
    assert s.price == D("88.00") and s.currency == "EUR"
    assert (s.min_30, s.max_30) == (D("88.00"), D("110.00"))  # the 40-day-old price is outside the window
    assert s.avg_30 == D("98.25")
    assert s.price_7d == D("100.00")  # last price known 7 days ago
    assert s.change_7d == D("-12.0")
    assert s.lowest == D("88.00") and s.is_lowest
    assert s.at_target
    assert s.checks == 5
    assert s.last_error == "Timeout"


async def test_product_without_checks(session):
    await add_product(session, name="New")
    (s,) = await product_stats(session, NOW)
    assert s.price is None and s.checks == 0 and not s.at_target and s.change_7d is None


async def test_filter_by_product(session):
    a = await add_product(session, name="A")
    await add_product(session, name="B")
    assert [s.name for s in await product_stats(session, NOW, product_id=a.id)] == ["A"]


async def test_daily_series_keeps_last_price_per_day(session):
    p = await add_product(session)
    session.add_all(
        [
            PriceCheck(product_id=p.id, checked_at=at(1, 8), price=D("10")),
            PriceCheck(product_id=p.id, checked_at=at(1, 18), price=D("9")),
            PriceCheck(product_id=p.id, checked_at=at(0, 8), price=D("11")),
            PriceCheck(product_id=p.id, checked_at=at(0, 9), error="HTTP 503"),
        ]
    )
    await session.flush()
    points = await daily_series(session, p.id, NOW, days=30)
    assert [(pt.day, pt.price) for pt in points] == [(at(1).date(), D("9.00")), (at(0).date(), D("11.00"))]


async def test_seed_history_matches_demo_shop(session):
    slug = "kaffeemuehle-pro"
    p = await add_product(session, url=f"http://127.0.0.1:8001/shop/p/{slug}")
    await add_product(session, url="https://other.example/p/1")  # not a demo product: untouched

    created = await seed_demo_history(session, days=30, now=NOW)

    assert created == 30
    points = await daily_series(session, p.id, NOW, days=30)
    assert len(points) == 30
    assert all(pt.price == price_on(BY_SLUG[slug], pt.day)[0] for pt in points)
    assert demo_slug("https://x/shop/p/unknown") is None
