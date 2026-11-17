"""Public demo: tracks the bundled demo shop on the same server."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .demo_shop import PRODUCTS
from .models import Product


async def ensure_demo_products(session: AsyncSession, base_url: str) -> int:
    """Adds the demo-shop products for this base URL if they are missing. Returns how many were added."""
    base = base_url.rstrip("/")
    existing = set(await session.scalars(select(Product.url)))
    added = 0
    for p in PRODUCTS:
        url = f"{base}/shop/p/{p.slug}"
        if url in existing:
            continue
        session.add(
            Product(
                url=url,
                name=p.name,
                selector=".price-now" if p.markup == "plain" else None,
                default_currency="EUR",
                target_price=(p.base_price * Decimal("0.88")).quantize(Decimal("1")),
            )
        )
        added += 1
    await session.flush()
    return added
