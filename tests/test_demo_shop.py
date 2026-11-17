from datetime import date, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient

from pricewatch.demo_shop import PRODUCTS, create_app, price_on
from pricewatch.extract import extract_price

client = TestClient(create_app())
DAY = date(2026, 11, 17)


def test_prices_are_deterministic_and_move_over_time():
    p = PRODUCTS[0]
    assert price_on(p, DAY) == price_on(p, DAY)
    prices = {price_on(p, DAY + timedelta(days=i))[0] for i in range(60)}
    assert len(prices) > 10


def test_prices_stay_in_a_realistic_range():
    for p in PRODUCTS:
        for i in range(120):
            price, _ = price_on(p, DAY + timedelta(days=i))
            assert p.base_price * Decimal("0.55") < price < p.base_price * Decimal("1.12")


def test_tracker_reads_every_markup_style():
    """The extractor finds the right price on all demo pages, whatever the markup."""
    for p in PRODUCTS:
        html = client.get(f"/p/{p.slug}", params={"day": DAY.isoformat()}).text
        result = extract_price(html, selector=".price-now", default_currency="EUR")
        expected_price, expected_stock = price_on(p, DAY)
        assert result.price == expected_price, p.slug
        assert result.currency == "EUR"
        assert result.method == {"jsonld": "json-ld", "microdata": "microdata", "plain": "selector"}[p.markup]
        if p.markup != "plain":
            assert result.in_stock == expected_stock


def test_unknown_product_and_bad_day():
    assert client.get("/p/nope").status_code == 404
    assert client.get(f"/p/{PRODUCTS[0].slug}", params={"day": "yesterday"}).status_code == 400


def test_robots_txt():
    assert "Disallow: /shop/cart" in client.get("/robots.txt").text
