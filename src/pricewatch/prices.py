"""Parsing of price strings as they appear on European shop pages."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

CURRENCY_SYMBOLS = {
    "€": "EUR",
    "eur": "EUR",
    "euro": "EUR",
    "$": "USD",
    "usd": "USD",
    "£": "GBP",
    "gbp": "GBP",
    "chf": "CHF",
    "fr.": "CHF",
    "zł": "PLN",
    "zl": "PLN",
    "pln": "PLN",
    "kč": "CZK",
    "czk": "CZK",
    "kr": "SEK",
    "sek": "SEK",
    "dkk": "DKK",
    "nok": "NOK",
}

# A number with optional thousands separators and decimals, e.g. 1.299,00 / 1,299.00 / 1 299 / 49.– / 12
NUMBER = re.compile(r"\d{1,3}(?:[.,'   ]\d{3})+(?:[.,]\d{1,2}|[.,][-–])?|\d+(?:[.,]\d{1,2}|[.,][-–])?")


@dataclass(frozen=True)
class Price:
    amount: Decimal
    currency: str | None


def _normalize_number(raw: str) -> Decimal | None:
    s = raw.replace(" ", " ").replace(" ", " ")
    s = re.sub(r"[.,][-–]$", "", s)  # "49.–" means 49.00 (Swiss/German style)
    s = s.replace(" ", "").replace("'", "")

    last_dot, last_comma = s.rfind("."), s.rfind(",")
    if last_dot >= 0 and last_comma >= 0:
        # Both present: the one further right is the decimal separator.
        decimal_sep = "." if last_dot > last_comma else ","
        thousands_sep = "," if decimal_sep == "." else "."
        s = s.replace(thousands_sep, "").replace(decimal_sep, ".")
    elif last_dot >= 0 or last_comma >= 0:
        sep = "." if last_dot >= 0 else ","
        parts = s.split(sep)
        # One separator followed by exactly 3 digits is a thousands separator: 1.299 / 1,299.
        if len(parts) > 2 or (len(parts) == 2 and len(parts[1]) == 3):
            s = s.replace(sep, "")
        else:
            s = s.replace(sep, ".")
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def detect_currency(text: str) -> str | None:
    lowered = text.lower()
    for symbol, code in sorted(CURRENCY_SYMBOLS.items(), key=lambda kv: -len(kv[0])):
        if symbol in ("kr", "fr.", "zl"):
            if re.search(rf"(?<![a-z]){re.escape(symbol)}(?![a-z])", lowered):
                return code
        elif symbol in lowered:
            return code
    return None


def parse_price(text: str | None, default_currency: str | None = None) -> Price | None:
    """Returns the first price in the text, e.g. "Jetzt 1.299,00 € statt 1.499 €" → 1299.00 EUR."""
    if not text:
        return None
    match = NUMBER.search(text)
    if not match:
        return None
    amount = _normalize_number(match.group(0))
    if amount is None:
        return None
    return Price(amount=amount.quantize(Decimal("0.01")), currency=detect_currency(text) or default_currency)
