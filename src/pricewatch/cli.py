"""Command line interface: `uv run pricewatch --help`."""

from __future__ import annotations

import asyncio
import logging
from decimal import Decimal, InvalidOperation
from typing import Annotated
from urllib.parse import urlsplit

import typer
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from .config import get_settings
from .db import engine, session_scope
from .demo_shop import PRODUCTS as DEMO_PRODUCTS
from .events import EventKind
from .fetch import Fetcher
from .models import PriceCheck, Product
from .notify import send_events
from .tracker import run_checks

app = typer.Typer(help="PriceWatch: track prices of products in online shops.", no_args_is_help=True)


def _run(coro):
    async def wrapper():
        try:
            return await coro
        finally:
            await engine.dispose()

    return asyncio.run(wrapper())


def _decimal(value: str | None) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(value.replace(",", "."))
    except InvalidOperation as e:
        raise typer.BadParameter(f"Not a number: {value}") from e


@app.command()
def add(
    url: str,
    name: Annotated[str | None, typer.Option(help="Display name (otherwise taken from the page)")] = None,
    selector: Annotated[
        str | None, typer.Option(help="CSS selector of the price, for shops without structured data")
    ] = None,
    currency: Annotated[str | None, typer.Option(help="Currency if the page does not say, e.g. EUR")] = None,
    target: Annotated[str | None, typer.Option(help="Alert when the price is at or below this value")] = None,
):
    """Start tracking a product page."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise typer.BadParameter("URL must start with http:// or https://", param_hint="URL")

    async def go():
        async with session_scope() as s:
            product = Product(
                url=url,
                name=name,
                selector=selector,
                default_currency=currency.upper() if currency else None,
                target_price=_decimal(target),
            )
            s.add(product)
            await s.flush()
            return product.id

    try:
        product_id = _run(go())
    except IntegrityError:
        typer.echo("This URL is already tracked.", err=True)
        raise typer.Exit(1) from None
    typer.echo(f"Added product #{product_id}. Run `pricewatch check` to fetch its price.")


@app.command("list")
def list_products():
    """Show tracked products with their latest price."""

    async def go():
        latest = (
            select(PriceCheck.product_id, func.max(PriceCheck.id).label("id"))
            .where(PriceCheck.price.is_not(None))
            .group_by(PriceCheck.product_id)
            .subquery()
        )
        async with session_scope() as s:
            rows = await s.execute(
                select(Product, PriceCheck)
                .outerjoin(latest, latest.c.product_id == Product.id)
                .outerjoin(PriceCheck, PriceCheck.id == latest.c.id)
                .order_by(Product.id)
            )
            return rows.all()

    rows = _run(go())
    if not rows:
        typer.echo("No products yet. Add one with `pricewatch add URL`.")
        return
    for product, check in rows:
        price = f"{check.price} {check.currency or ''}".strip() if check else "–"
        target = f"  target {product.target_price}" if product.target_price else ""
        stock = {True: "", False: "  SOLD OUT", None: ""}[check.in_stock if check else None]
        typer.echo(f"#{product.id:<3} {price:>12}{target}{stock}  {product.name or product.url}")


LABELS = {
    EventKind.TARGET_REACHED: "🎯 Target reached",
    EventKind.PRICE_DROP: "📉 Price drop",
    EventKind.BACK_IN_STOCK: "📦 Back in stock",
}


async def _check_once(ids: list[int] | None) -> None:
    async with Fetcher() as fetcher, session_scope() as s:
        result = await run_checks(s, fetcher, ids)
    typer.echo(f"Checked {result.checked}: {result.succeeded} ok, {result.failed} failed.")
    for e in result.events:
        change = f" ({e.change_percent:+}%)" if e.change_percent is not None else ""
        typer.echo(f"{LABELS[e.kind]}: {e.product_name} now {e.price} {e.currency or ''}{change}")
    webhook = get_settings().alert_webhook_url
    if webhook and result.events:
        sent = await send_events(webhook, result.events)
        typer.echo(f"Sent {sent}/{len(result.events)} alerts.")


@app.command()
def check(ids: Annotated[list[int] | None, typer.Argument(help="Only these product ids")] = None):
    """Fetch the current price of all active products once (and send alerts)."""
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    _run(_check_once(ids))


@app.command()
def watch(every: Annotated[int, typer.Option(help="Minutes between runs", min=5)] = 360):
    """Check prices again and again, e.g. on a small server. Stop with Ctrl+C."""
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(message)s")

    async def loop():
        while True:
            try:
                await _check_once(None)
            except Exception:  # keep watching even if one run fails (e.g. database restart)
                logging.exception("Check run failed")
            await asyncio.sleep(every * 60)

    try:
        _run(loop())
    except KeyboardInterrupt:
        typer.echo("Stopped.")


@app.command()
def remove(product_id: int):
    """Stop tracking a product and delete its history."""

    async def go():
        async with session_scope() as s:
            product = await s.get(Product, product_id)
            if product:
                await s.delete(product)
            return product is not None

    if not _run(go()):
        typer.echo(f"No product #{product_id}.", err=True)
        raise typer.Exit(1)
    typer.echo(f"Removed product #{product_id}.")


@app.command("add-demo")
def add_demo(base_url: Annotated[str, typer.Option(help="Where the demo shop runs")] = "http://127.0.0.1:8001"):
    """Track all products of the bundled demo shop (targets about 12 % below the usual price)."""

    async def go():
        added = 0
        async with session_scope() as s:
            existing = set(await s.scalars(select(Product.url)))
            for p in DEMO_PRODUCTS:
                url = f"{base_url.rstrip('/')}/shop/p/{p.slug}"
                if url in existing:
                    continue
                s.add(
                    Product(
                        url=url,
                        name=p.name,
                        selector=".price-now" if p.markup == "plain" else None,
                        default_currency="EUR",
                        target_price=(p.base_price * Decimal("0.88")).quantize(Decimal("1")),
                    )
                )
                added += 1
        return added

    typer.echo(f"Added {_run(go())} demo products.")


@app.command("seed-history")
def seed_history(days: Annotated[int, typer.Option(min=1, max=365)] = 90):
    """Fill in past daily prices for demo-shop products (replaces their history)."""
    from .seed import seed_demo_history

    async def go():
        async with session_scope() as s:
            return await seed_demo_history(s, days)

    typer.echo(f"Created {_run(go())} price checks for demo products.")


@app.command()
def serve(
    host: str = "127.0.0.1",
    port: Annotated[int, typer.Option(envvar="PORT")] = 8000,
    reload: bool = False,
):
    """Run the web dashboard, JSON API and demo shop."""
    import uvicorn

    uvicorn.run("pricewatch.web:app", host=host, port=port, reload=reload, proxy_headers=True)


@app.command("demo-shop")
def demo_shop(port: int = 8001):
    """Run the bundled demo shop on http://127.0.0.1:PORT/shop/."""
    import uvicorn

    from .demo_shop import create_app

    uvicorn.run(create_app(), host="127.0.0.1", port=port)
