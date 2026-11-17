from decimal import Decimal as D

from pricewatch.events import EventKind, Snapshot, detect_events


def kinds(previous, current, target=None):
    events = detect_events(
        product_id=1,
        product_name="Espresso",
        url="https://shop/p",
        currency="EUR",
        target_price=None if target is None else D(target),
        previous=previous,
        current=current,
    )
    return [e.kind for e in events]


def snap(price, in_stock=True):
    return Snapshot(D(price), in_stock)


def test_target_reached_fires_once_when_crossing():
    assert kinds(snap("320"), snap("299"), target="300") == [EventKind.TARGET_REACHED]
    # Still below target on the next run: no new alert.
    assert kinds(snap("299"), snap("295"), target="300") == []


def test_target_reached_on_first_check():
    assert kinds(None, snap("280"), target="300") == [EventKind.TARGET_REACHED]


def test_no_alert_above_target():
    assert kinds(snap("320"), snap("310"), target="300") == []


def test_big_drop_without_target():
    assert kinds(snap("100"), snap("85")) == [EventKind.PRICE_DROP]
    assert kinds(snap("100"), snap("95")) == []  # 5 % is below the 10 % threshold
    assert kinds(snap("100"), snap("120")) == []  # price went up


def test_back_in_stock():
    assert kinds(snap("50", in_stock=False), snap("50", in_stock=True)) == [EventKind.BACK_IN_STOCK]
    assert kinds(snap("50", in_stock=None), snap("50", in_stock=True)) == []  # unknown before


def test_target_and_back_in_stock_together():
    result = kinds(snap("320", in_stock=False), snap("290", in_stock=True), target="300")
    assert result == [EventKind.TARGET_REACHED, EventKind.BACK_IN_STOCK]


def test_change_percent():
    (event,) = detect_events(
        product_id=1,
        product_name="X",
        url="u",
        currency="EUR",
        target_price=None,
        previous=snap("200"),
        current=snap("150"),
    )
    assert event.change_percent == D("-25.0")
