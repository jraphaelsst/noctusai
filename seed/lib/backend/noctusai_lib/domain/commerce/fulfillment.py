"""Fulfillment seam -- what happens AFTER an order is paid.

`FulfillmentHandler.on_paid(order, items)` is called by the webhook once an order
is confirmed paid. The registry is keyed by `FulfillmentType`; in P3 every type is
a `NoopFulfillment` (P5 fills `digital_delivery` -- download links + licence
certificate; P9 fills the physical types). A handler is registered per type, so
a market product adds behaviour without touching the organ.

IDEMPOTENCY CONTRACT: the webhook calls `on_paid` for every confirmed-payment
delivery of a `paid` order (Asaas sends `PAYMENT_CONFIRMED` and `PAYMENT_RECEIVED`
as two distinct events) and re-calls it when a previous call raised and the gateway
redelivers. A handler MUST therefore be idempotent per `order["id"]` (an atomic
"claim" row, as the store's `send_once`), never "fire once by luck".
"""
from __future__ import annotations

import logging
from typing import Any, Mapping, Optional, Protocol, Sequence, runtime_checkable

from .types import FulfillmentType

logger = logging.getLogger(__name__)


@runtime_checkable
class FulfillmentHandler(Protocol):
    def on_paid(self, order: Mapping[str, Any], items: Sequence[Mapping[str, Any]]) -> None: ...


class NoopFulfillment:
    """The P3 default for every `FulfillmentType`: nothing to deliver yet."""

    def on_paid(self, order: Mapping[str, Any], items: Sequence[Mapping[str, Any]]) -> None:
        return None


class FulfillmentRegistry:
    """`FulfillmentType -> handler`, defaulting every type to `NoopFulfillment`."""

    def __init__(self, handlers: Optional[Mapping[FulfillmentType, FulfillmentHandler]] = None) -> None:
        noop = NoopFulfillment()
        self._handlers: dict[FulfillmentType, FulfillmentHandler] = {ft: noop for ft in FulfillmentType}
        for ftype, handler in (handlers or {}).items():
            self.register(ftype, handler)

    def register(self, ftype: FulfillmentType, handler: FulfillmentHandler) -> None:
        self._handlers[FulfillmentType(ftype)] = handler

    def handler_for(self, ftype: FulfillmentType | str) -> FulfillmentHandler:
        return self._handlers[FulfillmentType(ftype)]

    def dispatch_paid(self, order: Mapping[str, Any], items: Sequence[Mapping[str, Any]]) -> list[FulfillmentType]:
        """Call each fulfillment type's handler ONCE with that type's items.
        Returns the types dispatched (declaration order)."""
        by_type: dict[FulfillmentType, list[Mapping[str, Any]]] = {}
        for item in items:
            by_type.setdefault(FulfillmentType(item["fulfillment_type"]), []).append(item)
        dispatched: list[FulfillmentType] = []
        for ftype in FulfillmentType:
            if ftype in by_type:
                self._handlers[ftype].on_paid(order, by_type[ftype])
                dispatched.append(ftype)
        return dispatched


def make_fulfillment_registry(
    handlers: Optional[Mapping[FulfillmentType, FulfillmentHandler]] = None,
) -> FulfillmentRegistry:
    return FulfillmentRegistry(handlers)


__all__ = [
    "FulfillmentHandler",
    "FulfillmentRegistry",
    "NoopFulfillment",
    "make_fulfillment_registry",
]
