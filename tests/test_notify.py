import json
from decimal import Decimal as D

import httpx
import respx

from pricewatch.events import EventKind, PriceEvent
from pricewatch.notify import build_request, format_text, send_events

EVENT = PriceEvent(
    kind=EventKind.TARGET_REACHED,
    product_id=3,
    product_name="Kaffeemühle Pro",
    url="https://shop.example/p/3",
    price=D("159.00"),
    currency="EUR",
    previous_price=D("189.00"),
    target_price=D("165.00"),
)


def test_text_contains_all_facts():
    text = format_text(EVENT)
    assert text.splitlines() == [
        "🎯 Target price reached: Kaffeemühle Pro",
        "Now 159.00 EUR (was 189.00 EUR, -15.9%)",
        "Your target: 165.00 EUR",
        "https://shop.example/p/3",
    ]


def test_discord_format_never_pings_people():
    req = build_request("https://discord.com/api/webhooks/1/abc", EVENT)
    assert req["json"]["content"].startswith("🎯")
    assert req["json"]["allowed_mentions"] == {"parse": []}


def test_slack_format():
    assert "text" in build_request("https://hooks.slack.com/services/T/B/x", EVENT)["json"]


def test_ntfy_format_uses_headers():
    req = build_request("https://ntfy.sh/my-prices", EVENT)
    assert req["headers"]["Click"] == EVENT.url
    assert "Target price reached" in req["headers"]["Title"]
    assert req["content"].decode().startswith("Now 159.00 EUR")


def test_generic_json_for_other_services():
    payload = build_request("https://hooks.zapier.com/hooks/catch/1/2", EVENT)["json"]
    assert payload["event"] == "target_reached"
    assert payload["price"] == "159.00" and payload["change_percent"] == "-15.9"
    json.dumps(payload)  # must be serializable


@respx.mock
async def test_send_counts_deliveries_and_survives_failures():
    url = "https://example.com/hook"
    route = respx.post(url)
    route.side_effect = [httpx.Response(204), httpx.Response(500)]
    assert await send_events(url, [EVENT, EVENT]) == 1
    assert route.call_count == 2


async def test_nothing_to_send():
    assert await send_events("https://example.com/hook", []) == 0
