"""A small fake shop ("Kaffeewerk") to demo and test the tracker without scraping real sites.

Prices change once a day, deterministically: the same product has the same price on the same day,
so the tracker sees realistic movements (small changes, sales, sold-out days).
Product pages use the three markup styles found in real shops: JSON-LD, microdata and plain HTML.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from html import escape

from fastapi import APIRouter, FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, PlainTextResponse


@dataclass(frozen=True)
class DemoProduct:
    slug: str
    name: str
    base_price: Decimal
    markup: str  # "jsonld" | "microdata" | "plain"


PRODUCTS = [
    DemoProduct("espresso-maschine-classic", "Espressomaschine Classic", Decimal("349.00"), "jsonld"),
    DemoProduct("kaffeemuehle-pro", "Kaffeemühle Pro 64 mm", Decimal("189.00"), "microdata"),
    DemoProduct("milchkaennchen-600", "Milchkännchen 600 ml", Decimal("24.90"), "plain"),
    DemoProduct("handfilter-v60", "Handfilter V60 Keramik", Decimal("29.90"), "jsonld"),
    DemoProduct("kaffeewaage-timer", "Kaffeewaage mit Timer", Decimal("54.90"), "microdata"),
    DemoProduct("bohnen-ethiopia-1kg", "Kaffeebohnen Ethiopia 1 kg", Decimal("32.50"), "plain"),
]
BY_SLUG = {p.slug: p for p in PRODUCTS}


def _rand(*parts: object) -> float:
    """Deterministic number in [0, 1) for the given inputs."""
    digest = hashlib.sha256(":".join(map(str, parts)).encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


def price_on(product: DemoProduct, day: date) -> tuple[Decimal, bool]:
    """Price and stock status of a product on a day."""
    week = day.isocalendar()
    # Drift slowly within ±8 % week by week, wiggle a little day by day.
    drift = (_rand(product.slug, "week", week.year, week.week) - 0.5) * 0.16
    wiggle = (_rand(product.slug, "day", day) - 0.5) * 0.02
    factor = 1 + drift + wiggle
    # About one week in six is a sale week with 15–30 % off.
    if _rand(product.slug, "sale", week.year, week.week) < 1 / 6:
        factor *= 1 - (0.15 + 0.15 * _rand(product.slug, "sale-size", week.year, week.week))
    price = (product.base_price * Decimal(str(factor))).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    price = price - Decimal("0.01") if price >= 10 else price  # shop-style .x9 prices
    in_stock = _rand(product.slug, "stock", day) > 0.07
    return price.quantize(Decimal("0.01")), in_stock


def _de(amount: Decimal) -> str:
    """German price format: 1.234,50"""
    whole, frac = f"{amount:.2f}".split(".")
    return f"{int(whole):,}".replace(",", ".") + "," + frac


def render_product(product: DemoProduct, day: date) -> str:
    price, in_stock = price_on(product, day)
    stock_text = "Auf Lager" if in_stock else "Ausverkauft"
    if product.markup == "jsonld":
        data = {
            "@context": "https://schema.org",
            "@type": "Product",
            "name": product.name,
            "sku": product.slug,
            "offers": {
                "@type": "Offer",
                "price": str(price),
                "priceCurrency": "EUR",
                "availability": f"https://schema.org/{'InStock' if in_stock else 'OutOfStock'}",
            },
        }
        head = f'<script type="application/ld+json">{json.dumps(data, ensure_ascii=False)}</script>'
        body = f'<h1>{escape(product.name)}</h1><p class="price">{_de(price)} €</p><p>{stock_text}</p>'
    elif product.markup == "microdata":
        head = ""
        avail = "InStock" if in_stock else "OutOfStock"
        body = (
            '<article itemscope itemtype="https://schema.org/Product">'
            f'<h1 itemprop="name">{escape(product.name)}</h1>'
            '<div itemprop="offers" itemscope itemtype="https://schema.org/Offer">'
            '<meta itemprop="priceCurrency" content="EUR">'
            f'<span itemprop="price" content="{price}">{_de(price)} €</span>'
            f'<link itemprop="availability" href="https://schema.org/{avail}"> <span>{stock_text}</span>'
            "</div></article>"
        )
    else:
        head = ""
        body = (
            f"<h1>{escape(product.name)}</h1>"
            f'<div class="buybox"><span class="label">Unser Preis:</span> '
            f'<span class="price-now">{_de(price)}&nbsp;€</span><small>inkl. MwSt.</small></div>'
            f"<p>{stock_text}</p>"
        )
    return _page(product.name, head, body)


def _page(title: str, head: str, body: str) -> str:
    return (
        f'<!doctype html><html lang="de"><head><meta charset="utf-8"><title>{escape(title)} | Kaffeewerk</title>'
        f'<meta name="viewport" content="width=device-width, initial-scale=1">{head}'
        "<style>body{font-family:system-ui;max-width:640px;margin:2rem auto;padding:0 1rem}"
        ".price,.price-now,[itemprop=price]{font-size:1.6rem;font-weight:700}</style></head>"
        f'<body><p><a href="/shop/">☕ Kaffeewerk</a> · Demo-Shop für PriceWatch</p>{body}</body></html>'
    )


ROBOTS_TXT = "User-agent: *\nDisallow: /shop/cart\nAllow: /\n"

router = APIRouter(prefix="/shop", tags=["demo shop"])


def _day(day: str | None) -> date:
    if day is None:
        return datetime.now(UTC).date()
    try:
        return date.fromisoformat(day)
    except ValueError as e:
        raise HTTPException(400, "day must be YYYY-MM-DD") from e


@router.get("/", response_class=HTMLResponse)
def shop_index(day: str | None = Query(None)) -> str:
    d = _day(day)
    items = "".join(
        f'<li><a href="/shop/p/{p.slug}">{escape(p.name)}</a> – {_de(price_on(p, d)[0])} €</li>' for p in PRODUCTS
    )
    return _page("Shop", "", f"<h1>Kaffeewerk</h1><ul>{items}</ul>")


@router.get("/p/{slug}", response_class=HTMLResponse)
def shop_product(slug: str, day: str | None = Query(None, description="Simulate another day, YYYY-MM-DD")) -> str:
    p = BY_SLUG.get(slug)
    if p is None:
        raise HTTPException(404, "Produkt nicht gefunden")
    return render_product(p, _day(day))


def create_app() -> FastAPI:
    """The demo shop on its own (the main app also includes the router)."""
    app = FastAPI(title="Kaffeewerk demo shop", docs_url=None, redoc_url=None)
    app.include_router(router)

    @app.get("/robots.txt", response_class=PlainTextResponse)
    def robots() -> str:
        return ROBOTS_TXT

    return app
