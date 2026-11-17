"""Sends price events to a webhook. The payload format is chosen from the URL:
Discord, Slack, ntfy (push notifications to phones), or generic JSON for anything else (Zapier, n8n, Make, …).
"""

from __future__ import annotations

import logging
from decimal import Decimal
from urllib.parse import urlsplit

import httpx

from .events import EventKind, PriceEvent

log = logging.getLogger(__name__)

TITLES = {
    EventKind.TARGET_REACHED: "🎯 Target price reached",
    EventKind.PRICE_DROP: "📉 Price drop",
    EventKind.BACK_IN_STOCK: "📦 Back in stock",
}


def _money(amount: Decimal | None, currency: str | None) -> str:
    return "–" if amount is None else f"{amount:.2f} {currency or ''}".strip()


def format_text(event: PriceEvent) -> str:
    lines = [f"{TITLES[event.kind]}: {event.product_name}", f"Now {_money(event.price, event.currency)}"]
    if event.previous_price is not None and event.change_percent is not None:
        lines[-1] += f" (was {_money(event.previous_price, event.currency)}, {event.change_percent:+}%)"
    if event.target_price is not None:
        lines.append(f"Your target: {_money(event.target_price, event.currency)}")
    lines.append(event.url)
    return "\n".join(lines)


def build_request(webhook_url: str, event: PriceEvent) -> dict:
    """Keyword arguments for httpx.post, in the format the receiving service expects."""
    host = urlsplit(webhook_url).netloc.lower()
    text = format_text(event)
    if host in ("discord.com", "discordapp.com") or host.endswith(".discord.com"):
        return {"json": {"content": text[:2000], "allowed_mentions": {"parse": []}}}
    if host == "hooks.slack.com":
        return {"json": {"text": text}}
    if host == "ntfy.sh" or host.startswith("ntfy."):
        title, _, body = text.partition("\n")
        # HTTP headers must be ASCII: the emoji goes into ntfy's Tags instead.
        ascii_title = title.encode("ascii", "ignore").decode().strip()
        return {"content": body.encode(), "headers": {"Title": ascii_title, "Tags": "moneybag", "Click": event.url}}
    return {
        "json": {
            "event": event.kind.value,
            "product_id": event.product_id,
            "product_name": event.product_name,
            "url": event.url,
            "price": str(event.price),
            "currency": event.currency,
            "previous_price": None if event.previous_price is None else str(event.previous_price),
            "target_price": None if event.target_price is None else str(event.target_price),
            "change_percent": None if event.change_percent is None else str(event.change_percent),
            "text": text,
        }
    }


async def send_events(webhook_url: str, events: list[PriceEvent], client: httpx.AsyncClient | None = None) -> int:
    """Sends each event; returns how many were delivered. Failures are logged, never raised."""
    if not events:
        return 0
    own_client = client is None
    client = client or httpx.AsyncClient(timeout=10)
    delivered = 0
    try:
        for event in events:
            try:
                response = await client.post(webhook_url, **build_request(webhook_url, event))
                response.raise_for_status()
                delivered += 1
            except httpx.HTTPError as e:
                log.warning("Could not send alert for %s: %s", event.product_name, e)
    finally:
        if own_client:
            await client.aclose()
    return delivered
