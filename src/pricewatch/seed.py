"""Back-fills price history for demo-shop products, so charts have data from day one."""

from __future__ import annotations

import re
from datetime import UTC, datetime, time, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from .demo_shop import BY_SLUG, price_on
from .models import PriceCheck, Product

DEMO_URL = re.compile(r"/shop/p/([a-z0-9-]+)")


def demo_slug(url: str) -> str | None:
    match = DEMO_URL.search(url)
    return match.group(1) if match and match.group(1) in BY_SLUG else None


async def seed_demo_history(session: AsyncSession, days: int = 90, now: datetime | None = None) -> int:
    """Replaces the history of demo-shop products with one check per day (08:00 UTC). Returns rows created."""
    now = now or datetime.now(UTC)
    products = [p for p in await session.scalars(select(Product)) if demo_slug(p.url)]
    if not products:
        return 0
    await session.execute(delete(PriceCheck).where(PriceCheck.product_id.in_([p.id for p in products])))

    created = 0
    first_day = now.date() - timedelta(days=days - 1)
    for product in products:
        demo = BY_SLUG[demo_slug(product.url)]  # type: ignore[index]
        method = {"jsonld": "json-ld", "microdata": "microdata", "plain": "selector"}[demo.markup]
        for i in range(days):
            day = first_day + timedelta(days=i)
            checked_at = datetime.combine(day, time(8, 0), tzinfo=UTC)
            if checked_at > now:
                break
            price, in_stock = price_on(demo, day)
            session.add(
                PriceCheck(
                    product_id=product.id,
                    checked_at=checked_at,
                    price=price,
                    currency="EUR",
                    in_stock=None if demo.markup == "plain" else in_stock,
                    method=method,
                )
            )
            created += 1
    await session.flush()
    return created
