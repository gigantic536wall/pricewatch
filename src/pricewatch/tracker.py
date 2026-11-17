"""Checks all active products once: fetch → extract → store → detect events."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .events import PriceEvent, Snapshot, detect_events
from .extract import ExtractionError, extract_price
from .fetch import Fetcher, FetchError
from .models import PriceCheck, Product

log = logging.getLogger(__name__)


@dataclass
class RunResult:
    checked: int = 0
    succeeded: int = 0
    failed: int = 0
    events: list[PriceEvent] = field(default_factory=list)


async def _last_successful(session: AsyncSession, product_id: int) -> PriceCheck | None:
    return await session.scalar(
        select(PriceCheck)
        .where(PriceCheck.product_id == product_id, PriceCheck.price.is_not(None))
        .order_by(PriceCheck.checked_at.desc(), PriceCheck.id.desc())
        .limit(1)
    )


async def _fetch_and_extract(fetcher: Fetcher, product: Product):
    """Returns an Extraction or an error message. Never raises for page problems."""
    try:
        html = await fetcher.get(product.url)
        return extract_price(html, selector=product.selector, default_currency=product.default_currency)
    except (FetchError, ExtractionError) as e:
        return str(e)


async def run_checks(session: AsyncSession, fetcher: Fetcher, product_ids: list[int] | None = None) -> RunResult:
    query = select(Product).where(Product.active.is_(True)).order_by(Product.id)
    if product_ids:
        query = query.where(Product.id.in_(product_ids))
    products = list(await session.scalars(query))

    # Pages are loaded concurrently; the fetcher keeps it polite per host.
    outcomes = await asyncio.gather(*(_fetch_and_extract(fetcher, p) for p in products))

    result = RunResult(checked=len(products))
    for product, outcome in zip(products, outcomes, strict=True):
        if isinstance(outcome, str):
            session.add(PriceCheck(product_id=product.id, error=outcome[:1000]))
            result.failed += 1
            log.warning("%s: %s", product.url, outcome)
            continue

        previous = await _last_successful(session, product.id)
        session.add(
            PriceCheck(
                product_id=product.id,
                price=outcome.price,
                currency=outcome.currency,
                in_stock=outcome.in_stock,
                method=outcome.method,
            )
        )
        if not product.name and outcome.name:
            product.name = outcome.name[:300]
        result.succeeded += 1

        result.events += detect_events(
            product_id=product.id,
            product_name=product.name or product.url,
            url=product.url,
            currency=outcome.currency,
            target_price=product.target_price,
            previous=Snapshot(previous.price, previous.in_stock) if previous and previous.price is not None else None,
            current=Snapshot(outcome.price, outcome.in_stock),
        )
    await session.flush()
    return result
