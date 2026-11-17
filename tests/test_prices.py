from decimal import Decimal

import pytest

from pricewatch.prices import parse_price


@pytest.mark.parametrize(
    ("text", "amount", "currency"),
    [
        ("1.299,00 €", "1299.00", "EUR"),
        ("€1,299.99", "1299.99", "EUR"),
        ("29,99 €", "29.99", "EUR"),
        ("EUR 29.99", "29.99", "EUR"),
        ("1 299,50 zł", "1299.50", "PLN"),
        ("1 299,50 €", "1299.50", "EUR"),
        ("CHF 49.–", "49.00", "CHF"),
        ("CHF 1'249.90", "1249.90", "CHF"),
        ("£12", "12.00", "GBP"),
        ("2.499 Kč", "2499.00", "CZK"),
        ("199 kr", "199.00", "SEK"),
        ("12,5", "12.50", None),
        ("1.299", "1299.00", None),
        ("1,299", "1299.00", None),
        ("1.234.567,89 €", "1234567.89", "EUR"),
    ],
)
def test_parses_european_formats(text, amount, currency):
    price = parse_price(text)
    assert price is not None
    assert price.amount == Decimal(amount)
    assert price.currency == currency


def test_takes_the_first_price():
    price = parse_price("Jetzt 29,99 € statt 39,99 €")
    assert price is not None and price.amount == Decimal("29.99")


def test_default_currency():
    price = parse_price("19.90", default_currency="EUR")
    assert price is not None and price.currency == "EUR"


@pytest.mark.parametrize("text", [None, "", "Ausverkauft", "Preis auf Anfrage"])
def test_returns_none_without_price(text):
    assert parse_price(text) is None


def test_currency_words_are_not_matched_inside_other_words():
    # "kr" inside "Kreditkarte" must not be read as Swedish krona.
    price = parse_price("29,90 Zahlung per Kreditkarte")
    assert price is not None and price.currency is None
