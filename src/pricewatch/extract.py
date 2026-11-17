"""Finds the price of a product on an HTML page.

Strategies, from most to least reliable:
1. JSON-LD structured data (schema.org Product / Offer), used by most modern shops for Google Shopping
2. Microdata and meta tags (itemprop="price", product:price:amount)
3. A CSS selector configured for the product, for shops without structured data
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal

from selectolax.lexbor import LexborHTMLParser as HTMLParser

from .prices import Price, parse_price


@dataclass(frozen=True)
class Extraction:
    price: Decimal
    currency: str | None
    in_stock: bool | None
    name: str | None
    method: str


class ExtractionError(Exception):
    pass


def _iter_jsonld(node: object):
    """Yields every dict in JSON-LD, including items inside @graph and lists."""
    if isinstance(node, list):
        for item in node:
            yield from _iter_jsonld(item)
    elif isinstance(node, dict):
        yield node
        for key in ("@graph", "offers", "itemListElement"):
            if key in node:
                yield from _iter_jsonld(node[key])


def _types(obj: dict) -> set[str]:
    t = obj.get("@type", [])
    return {x.split("/")[-1] for x in ([t] if isinstance(t, str) else t)}


def _availability(value: object) -> bool | None:
    if not isinstance(value, str):
        return None
    v = value.split("/")[-1].lower()
    if v in {"instock", "limitedavailability", "onlineonly", "presale", "preorder"}:
        return True
    if v in {"outofstock", "soldout", "discontinued"}:
        return False
    return None


def from_jsonld(tree: HTMLParser) -> Extraction | None:
    for script in tree.css('script[type="application/ld+json"]'):
        try:
            data = json.loads(script.text(strip=True) or "null")
        except json.JSONDecodeError:
            continue
        for obj in _iter_jsonld(data):
            if "Product" not in _types(obj):
                continue
            name = obj.get("name")
            offers = [
                o
                for o in _iter_jsonld(obj.get("offers", []))
                if _types(o) & {"Offer", "AggregateOffer"} or "price" in o
            ]
            for offer in offers:
                raw = offer.get("price", offer.get("lowPrice"))
                if raw is None:
                    continue
                price = parse_price(str(raw), default_currency=offer.get("priceCurrency"))
                if price:
                    return Extraction(
                        price.amount, price.currency, _availability(offer.get("availability")), name, "json-ld"
                    )
    return None


def from_meta(tree: HTMLParser) -> Extraction | None:
    node = tree.css_first('[itemprop="price"]') or tree.css_first('meta[property="product:price:amount"]')
    if node is None:
        return None
    raw = node.attributes.get("content") or node.text(strip=True)
    currency_node = tree.css_first('[itemprop="priceCurrency"]') or tree.css_first(
        'meta[property="product:price:currency"]'
    )
    currency = currency_node.attributes.get("content") if currency_node else None
    price = parse_price(raw, default_currency=currency)
    if not price:
        return None
    availability = tree.css_first('[itemprop="availability"]')
    in_stock = (
        _availability(availability.attributes.get("href") or availability.attributes.get("content"))
        if availability
        else None
    )
    name_node = tree.css_first('[itemprop="name"]') or tree.css_first('meta[property="og:title"]')
    name = (name_node.attributes.get("content") or name_node.text(strip=True)) if name_node else None
    return Extraction(price.amount, price.currency, in_stock, name, "microdata")


def from_selector(tree: HTMLParser, selector: str, default_currency: str | None) -> Extraction | None:
    node = tree.css_first(selector)
    if node is None:
        return None
    price: Price | None = parse_price(node.text(separator=" ", strip=True), default_currency=default_currency)
    if not price:
        return None
    title = tree.css_first("h1") or tree.css_first("title")
    return Extraction(price.amount, price.currency, None, title.text(strip=True) if title else None, "selector")


def extract_price(html: str, selector: str | None = None, default_currency: str | None = None) -> Extraction:
    """Tries structured data first, then the configured CSS selector."""
    tree = HTMLParser(html)
    result = from_jsonld(tree) or from_meta(tree)
    if result is None and selector:
        result = from_selector(tree, selector, default_currency)
    if result is None:
        raise ExtractionError("No price found (no structured data and no matching selector)")
    if result.currency is None and default_currency:
        result = Extraction(result.price, default_currency, result.in_stock, result.name, result.method)
    return result
