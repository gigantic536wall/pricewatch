"""Price statistics, computed in PostgreSQL with plain SQL (CTEs, DISTINCT ON, aggregates)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

PRODUCT_STATS_SQL = text("""
WITH ok AS (
    SELECT product_id, checked_at, price, currency, in_stock
    FROM price_checks
    WHERE price IS NOT NULL
),
latest AS (                                   -- newest successful check per product
    SELECT DISTINCT ON (product_id) product_id, price, currency, in_stock, checked_at
    FROM ok
    ORDER BY product_id, checked_at DESC
),
last_30_days AS (
    SELECT product_id, MIN(price) AS min_30, MAX(price) AS max_30, ROUND(AVG(price), 2) AS avg_30
    FROM ok
    WHERE checked_at >= CAST(:now AS timestamptz) - INTERVAL '30 days'
    GROUP BY product_id
),
week_ago AS (                                 -- the last price known 7 days ago
    SELECT DISTINCT ON (product_id) product_id, price AS price_7d
    FROM ok
    WHERE checked_at <= CAST(:now AS timestamptz) - INTERVAL '7 days'
    ORDER BY product_id, checked_at DESC
),
all_time AS (
    SELECT product_id, MIN(price) AS lowest, COUNT(*) AS checks
    FROM ok
    GROUP BY product_id
),
last_run AS (                                 -- did the most recent attempt fail?
    SELECT DISTINCT ON (product_id) product_id, error
    FROM price_checks
    ORDER BY product_id, checked_at DESC, id DESC
)
SELECT p.id, p.name, p.url, p.target_price, p.active,
       l.price, l.currency, l.in_stock, l.checked_at,
       w.min_30, w.max_30, w.avg_30,
       wa.price_7d,
       ROUND((l.price - wa.price_7d) / NULLIF(wa.price_7d, 0) * 100, 1) AS change_7d,
       a.lowest, COALESCE(a.checks, 0) AS checks,
       lr.error AS last_error
FROM products p
LEFT JOIN latest l        ON l.product_id = p.id
LEFT JOIN last_30_days w  ON w.product_id = p.id
LEFT JOIN week_ago wa     ON wa.product_id = p.id
LEFT JOIN all_time a      ON a.product_id = p.id
LEFT JOIN last_run lr     ON lr.product_id = p.id
WHERE (CAST(:product_id AS integer) IS NULL OR p.id = :product_id)
ORDER BY p.id
""")

DAILY_SERIES_SQL = text("""
-- One point per day: the last price seen that day.
SELECT DISTINCT ON (day) day, price, in_stock
FROM (
    SELECT (checked_at AT TIME ZONE 'UTC')::date AS day, checked_at, price, in_stock
    FROM price_checks
    WHERE product_id = :product_id AND price IS NOT NULL AND checked_at >= :since
) t
ORDER BY day, checked_at DESC
""")


@dataclass(frozen=True)
class ProductStats:
    id: int
    name: str | None
    url: str
    target_price: Decimal | None
    active: bool
    price: Decimal | None
    currency: str | None
    in_stock: bool | None
    checked_at: datetime | None
    min_30: Decimal | None
    max_30: Decimal | None
    avg_30: Decimal | None
    price_7d: Decimal | None
    change_7d: Decimal | None
    lowest: Decimal | None
    checks: int
    last_error: str | None

    @property
    def at_target(self) -> bool:
        return self.price is not None and self.target_price is not None and self.price <= self.target_price

    @property
    def is_lowest(self) -> bool:
        return self.price is not None and self.lowest is not None and self.checks > 1 and self.price <= self.lowest


@dataclass(frozen=True)
class Point:
    day: date
    price: Decimal
    in_stock: bool | None


async def product_stats(session: AsyncSession, now: datetime, product_id: int | None = None) -> list[ProductStats]:
    rows = await session.execute(PRODUCT_STATS_SQL, {"now": now, "product_id": product_id})
    return [ProductStats(**row._mapping) for row in rows]


async def daily_series(session: AsyncSession, product_id: int, now: datetime, days: int = 90) -> list[Point]:
    rows = await session.execute(DAILY_SERIES_SQL, {"product_id": product_id, "since": now - timedelta(days=days)})
    return [Point(r.day, r.price, r.in_stock) for r in rows]
