"""Decides which price changes are worth an alert. Pure functions, no database."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum


class EventKind(StrEnum):
    TARGET_REACHED = "target_reached"  # price fell to or below the target price
    PRICE_DROP = "price_drop"  # notable drop compared to the last known price
    BACK_IN_STOCK = "back_in_stock"


@dataclass(frozen=True)
class Snapshot:
    price: Decimal
    in_stock: bool | None


@dataclass(frozen=True)
class PriceEvent:
    kind: EventKind
    product_id: int
    product_name: str
    url: str
    price: Decimal
    currency: str | None
    previous_price: Decimal | None
    target_price: Decimal | None

    @property
    def change_percent(self) -> Decimal | None:
        if not self.previous_price:
            return None
        return ((self.price - self.previous_price) / self.previous_price * 100).quantize(Decimal("0.1"))


def detect_events(
    *,
    product_id: int,
    product_name: str,
    url: str,
    currency: str | None,
    target_price: Decimal | None,
    previous: Snapshot | None,
    current: Snapshot,
    drop_threshold_percent: Decimal = Decimal("10"),
) -> list[PriceEvent]:
    """Events for one new check. Alerts fire only on changes, never on every run."""

    def event(kind: EventKind) -> PriceEvent:
        return PriceEvent(
            kind,
            product_id,
            product_name,
            url,
            current.price,
            currency,
            previous.price if previous else None,
            target_price,
        )

    events: list[PriceEvent] = []
    at_target = target_price is not None and current.price <= target_price
    was_at_target = previous is not None and target_price is not None and previous.price <= target_price

    if at_target and not was_at_target:
        events.append(event(EventKind.TARGET_REACHED))
    elif previous is not None and previous.price > 0 and not at_target:
        drop = (previous.price - current.price) / previous.price * 100
        if drop >= drop_threshold_percent:
            events.append(event(EventKind.PRICE_DROP))

    if previous is not None and previous.in_stock is False and current.in_stock is True:
        events.append(event(EventKind.BACK_IN_STOCK))
    return events
