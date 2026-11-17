"""Integration tests: tracker + PostgreSQL + the demo shop."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from pricewatch.demo_shop import BY_SLUG, price_on
from pricewatch.events import EventKind
from pricewatch.models import PriceCheck, Product
from pricewatch.tracker import run_checks

SHOP = "http://shop.test/shop/p"
DAY1, DAY2 = date(2026, 11, 2), date(2026, 11, 3)


def url(slug: str, day: date) -> str:
    return f"{SHOP}/{slug}?day={day.isoformat()}"


async def test_stores_prices_errors_and_names(session, demo_fetcher):
    espresso = Product(url=url("espresso-maschine-classic", DAY1))  # JSON-LD, no name given
    beans = Product(url=url("bohnen-ethiopia-1kg", DAY1), selector=".price-now", default_currency="EUR")  # plain HTML
    missing = Product(url=f"{SHOP}/does-not-exist")
    session.add_all([espresso, beans, missing])
    await session.flush()

    result = await run_checks(session, demo_fetcher)

    assert (result.checked, result.succeeded, result.failed) == (3, 2, 1)
    checks = {c.product_id: c for c in await session.scalars(select(PriceCheck))}
    assert checks[espresso.id].price == price_on(BY_SLUG["espresso-maschine-classic"], DAY1)[0]
    assert checks[espresso.id].method == "json-ld"
    assert checks[beans.id].price == price_on(BY_SLUG["bohnen-ethiopia-1kg"], DAY1)[0]
    assert checks[beans.id].method == "selector"
    assert checks[missing.id].price is None and checks[missing.id].error == "HTTP 404"
    assert espresso.name == "Espressomaschine Classic"  # filled in from the page


async def test_target_alert_fires_once(session, demo_fetcher):
    slug = "kaffeewaage-timer"
    price_day1 = price_on(BY_SLUG[slug], DAY1)[0]
    product = Product(url=url(slug, DAY1), name="Waage", target_price=price_day1 + Decimal("10"))
    session.add(product)
    await session.flush()

    first = await run_checks(session, demo_fetcher)
    assert [e.kind for e in first.events] == [EventKind.TARGET_REACHED]
    assert first.events[0].price == price_day1

    product.url = url(slug, DAY2)  # next day, still below the target
    second = await run_checks(session, demo_fetcher, [product.id])
    assert EventKind.TARGET_REACHED not in [e.kind for e in second.events]
    assert await session.scalar(select(func.count()).select_from(PriceCheck)) == 2


async def test_inactive_products_are_skipped(session, demo_fetcher):
    session.add(Product(url=url("handfilter-v60", DAY1), active=False))
    await session.flush()
    assert (await run_checks(session, demo_fetcher)).checked == 0


async def test_database_rejects_a_check_with_price_and_error(session):
    product = Product(url=url("handfilter-v60", DAY1))
    session.add(product)
    await session.flush()
    session.add(PriceCheck(product_id=product.id, price=Decimal("5"), error="both"))
    with pytest.raises(IntegrityError, match="price_xor_error"):
        await session.flush()
