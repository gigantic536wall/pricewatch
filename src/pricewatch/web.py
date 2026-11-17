"""Web dashboard and JSON API: `uv run pricewatch serve`."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates
from markupsafe import Markup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from . import charts
from .analytics import daily_series, product_stats
from .db import SessionLocal
from .demo_shop import ROBOTS_TXT
from .demo_shop import router as demo_shop_router
from .models import PriceCheck

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


def money(amount: Decimal | None, currency: str | None = None) -> str:
    if amount is None:
        return "–"
    symbol = {"EUR": "€", "GBP": "£", "USD": "$"}.get(currency or "", "")
    return f"{symbol}{amount:,.2f}" if symbol else f"{amount:,.2f} {currency or ''}".strip()


templates.env.filters["money"] = money


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session


Session = Annotated[AsyncSession, Depends(get_session)]


def now() -> datetime:
    return datetime.now(UTC)


app = FastAPI(
    title="PriceWatch",
    description="Price history and statistics for tracked products.",
    docs_url="/api/docs",
    redoc_url=None,
    openapi_url="/api/openapi.json",
)
app.include_router(demo_shop_router)


@app.get("/robots.txt", response_class=PlainTextResponse, include_in_schema=False)
def robots() -> str:
    return ROBOTS_TXT


@app.get("/healthz", include_in_schema=False)
def healthz() -> dict:
    return {"ok": True}


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def dashboard(request: Request, session: Session):
    t = now()
    stats = await product_stats(session, t)
    sparks = {s.id: Markup(charts.sparkline(await daily_series(session, s.id, t, days=30))) for s in stats}
    totals = {
        "products": len(stats),
        "at_target": sum(s.at_target for s in stats),
        "failing": sum(1 for s in stats if s.last_error),
        "checks": sum(s.checks for s in stats),
    }
    return templates.TemplateResponse(request, "index.html", {"stats": stats, "sparks": sparks, "totals": totals})


@app.get("/products/{product_id}", response_class=HTMLResponse, include_in_schema=False)
async def product_page(request: Request, product_id: int, session: Session, days: int = Query(90, ge=7, le=365)):
    t = now()
    found = await product_stats(session, t, product_id)
    if not found:
        raise HTTPException(404, "Product not found")
    s = found[0]
    series = await daily_series(session, product_id, t, days=days)
    recent = list(
        await session.scalars(
            select(PriceCheck)
            .where(PriceCheck.product_id == product_id)
            .order_by(PriceCheck.checked_at.desc(), PriceCheck.id.desc())
            .limit(15)
        )
    )
    chart = Markup(charts.line_chart(series, currency=s.currency, target=s.target_price))
    return templates.TemplateResponse(
        request, "product.html", {"s": s, "chart": chart, "recent": recent, "days": days, "points": len(series)}
    )


# ---- JSON API ---------------------------------------------------------------------------------


@app.get("/api/products", tags=["api"], summary="All products with current price and statistics")
async def api_products(session: Session) -> list[dict]:
    return [_stats_json(s) for s in await product_stats(session, now())]


@app.get("/api/products/{product_id}/history", tags=["api"], summary="Daily price history")
async def api_history(product_id: int, session: Session, days: int = Query(90, ge=1, le=365)) -> dict:
    if not await product_stats(session, now(), product_id):
        raise HTTPException(404, "Product not found")
    series = await daily_series(session, product_id, now(), days=days)
    return {
        "product_id": product_id,
        "days": days,
        "points": [{"day": p.day.isoformat(), "price": str(p.price), "in_stock": p.in_stock} for p in series],
    }


def _stats_json(s) -> dict:
    def dec(v):
        return None if v is None else str(v)

    return {
        "id": s.id,
        "name": s.name,
        "url": s.url,
        "price": dec(s.price),
        "currency": s.currency,
        "in_stock": s.in_stock,
        "checked_at": s.checked_at.isoformat() if s.checked_at else None,
        "target_price": dec(s.target_price),
        "at_target": s.at_target,
        "min_30d": dec(s.min_30),
        "max_30d": dec(s.max_30),
        "avg_30d": dec(s.avg_30),
        "change_7d_percent": dec(s.change_7d),
        "lowest_ever": dec(s.lowest),
        "last_error": s.last_error,
    }
