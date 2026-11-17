from decimal import Decimal

import pytest

from pricewatch.extract import ExtractionError, extract_price

JSONLD = """
<html><head><script type="application/ld+json">
{"@context": "https://schema.org", "@graph": [
  {"@type": "BreadcrumbList"},
  {"@type": "Product", "name": "Espresso Machine",
   "offers": {"@type": "Offer", "price": "349.00", "priceCurrency": "EUR",
              "availability": "https://schema.org/InStock"}}
]}
</script></head><body><span class="price">999 €</span></body></html>
"""

MICRODATA = """
<div itemscope itemtype="https://schema.org/Product">
  <h1 itemprop="name">Kaffeemühle</h1>
  <div itemprop="offers" itemscope itemtype="https://schema.org/Offer">
    <meta itemprop="priceCurrency" content="EUR">
    <span itemprop="price" content="89.90">89,90 €</span>
    <link itemprop="availability" href="https://schema.org/OutOfStock">
  </div>
</div>
"""

PLAIN = """
<html><head><title>Wasserkocher | Shop</title></head>
<body><h1>Wasserkocher 1,7 l</h1>
<div class="buy"><span class="price-now">Jetzt 1.249,00&nbsp;€</span></div></body></html>
"""


def test_json_ld_wins_over_page_text():
    r = extract_price(JSONLD, selector=".price")
    assert (r.price, r.currency, r.in_stock, r.name, r.method) == (
        Decimal("349.00"),
        "EUR",
        True,
        "Espresso Machine",
        "json-ld",
    )


def test_microdata():
    r = extract_price(MICRODATA)
    assert (r.price, r.currency, r.in_stock, r.name, r.method) == (
        Decimal("89.90"),
        "EUR",
        False,
        "Kaffeemühle",
        "microdata",
    )


def test_css_selector_fallback():
    r = extract_price(PLAIN, selector=".price-now")
    assert (r.price, r.currency, r.name, r.method) == (Decimal("1249.00"), "EUR", "Wasserkocher 1,7 l", "selector")


def test_default_currency_applies_when_page_has_none():
    r = extract_price('<h1>X</h1><p class="p">19,90</p>', selector=".p", default_currency="EUR")
    assert r.currency == "EUR"


def test_broken_json_ld_is_skipped():
    html = '<script type="application/ld+json">{oops</script><span class="p">5 €</span>'
    assert extract_price(html, selector=".p").price == Decimal("5.00")


def test_aggregate_offer_uses_low_price():
    html = """<script type="application/ld+json">{"@type": "Product", "name": "T-Shirt",
      "offers": {"@type": "AggregateOffer", "lowPrice": 15, "highPrice": 25, "priceCurrency": "EUR"}}</script>"""
    assert extract_price(html).price == Decimal("15.00")


def test_no_price_raises():
    with pytest.raises(ExtractionError):
        extract_price("<h1>Ausverkauft</h1>", selector=".price")
