"""Fulfillment seam -- what happens AFTER an order is paid.

`FulfillmentHandler.on_paid(order, items)` is called by the webhook once an order
is confirmed paid. The registry is keyed by `FulfillmentType`; in P3 every type is
a `NoopFulfillment` (P5 fills `digital_delivery` -- download links + licence
certificate; P9 fills the physical types). A handler is registered per type, so
a market product adds behaviour without touching the organ.

STOCK HOLD HOOKS (roadmap E6): `on_created` runs BEFORE the order row is written -- a handler that cannot honour the sale (no
stock) RAISES a `CommerceError` and the order is never created; `on_cancelled` runs when an order that held something will
never be fulfilled (checkout failed after the hold, staff cancelled), so the hold is given back. Both are optional and
no-ops by default.

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


#: The P4 lifecycle hooks a handler MAY define (see the module docstring).
LIFECYCLE_HOOKS: tuple[str, ...] = ("on_created", "on_cancelled", "on_paused", "on_resumed", "on_revoked", "on_expired")


@runtime_checkable
class FulfillmentHandler(Protocol):
    """`on_paid` is the one required method; the lifecycle hooks are optional
    (`LIFECYCLE_HOOKS`) -- subclass `NoopFulfillment` to get all of them as no-ops."""

    def on_paid(self, order: Mapping[str, Any], items: Sequence[Mapping[str, Any]]) -> None: ...


class NoopFulfillment:
    """The default for every `FulfillmentType`: nothing to deliver, nothing to take back."""

    def on_paid(self, order: Mapping[str, Any], items: Sequence[Mapping[str, Any]]) -> None:
        return None

    def on_created(self, order: Mapping[str, Any], items: Sequence[Mapping[str, Any]]) -> None:
        return None

    def on_cancelled(self, order: Mapping[str, Any], items: Sequence[Mapping[str, Any]]) -> None:
        return None

    def on_paused(self, order: Mapping[str, Any], items: Sequence[Mapping[str, Any]]) -> None:
        return None

    def on_resumed(self, order: Mapping[str, Any], items: Sequence[Mapping[str, Any]]) -> None:
        return None

    def on_revoked(self, order: Mapping[str, Any], items: Sequence[Mapping[str, Any]]) -> None:
        return None

    def on_expired(self, order: Mapping[str, Any], items: Sequence[Mapping[str, Any]]) -> None:
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

    def _dispatch(self, hook: str, order: Mapping[str, Any], items: Sequence[Mapping[str, Any]]) -> list[FulfillmentType]:
        by_type: dict[FulfillmentType, list[Mapping[str, Any]]] = {}
        for item in items:
            by_type.setdefault(FulfillmentType(item["fulfillment_type"]), []).append(item)
        dispatched: list[FulfillmentType] = []
        for ftype in FulfillmentType:
            if ftype in by_type:
                method = getattr(self._handlers[ftype], hook, None)
                if method is not None:  # a pre-P4 handler has no lifecycle hooks: that is a no-op, not an error
                    method(order, by_type[ftype])
                dispatched.append(ftype)
        return dispatched

    def dispatch_paid(self, order: Mapping[str, Any], items: Sequence[Mapping[str, Any]]) -> list[FulfillmentType]:
        """Call each fulfillment type's handler ONCE with that type's items.
        Returns the types dispatched (declaration order)."""
        return self._dispatch("on_paid", order, items)

    def dispatch_created(self, order: Mapping[str, Any], items: Sequence[Mapping[str, Any]]) -> list[FulfillmentType]:
        """The order is about to be written. A handler may RAISE to refuse the sale (e.g. out of stock)."""
        return self._dispatch("on_created", order, items)

    def dispatch_cancelled(self, order: Mapping[str, Any], items: Sequence[Mapping[str, Any]]) -> list[FulfillmentType]:
        """The order will not be fulfilled (checkout failed after `on_created`, or staff cancelled it)."""
        return self._dispatch("on_cancelled", order, items)

    def dispatch_paused(self, order: Mapping[str, Any], items: Sequence[Mapping[str, Any]]) -> list[FulfillmentType]:
        """The order entered `disputed`."""
        return self._dispatch("on_paused", order, items)

    def dispatch_resumed(self, order: Mapping[str, Any], items: Sequence[Mapping[str, Any]]) -> list[FulfillmentType]:
        """The dispute was won."""
        return self._dispatch("on_resumed", order, items)

    def dispatch_revoked(self, order: Mapping[str, Any], items: Sequence[Mapping[str, Any]]) -> list[FulfillmentType]:
        """The order became `refunded` / `chargeback`."""
        return self._dispatch("on_revoked", order, items)

    def dispatch_expired(self, order: Mapping[str, Any], items: Sequence[Mapping[str, Any]]) -> list[FulfillmentType]:
        """The order became `expired`."""
        return self._dispatch("on_expired", order, items)


def make_fulfillment_registry(
    handlers: Optional[Mapping[FulfillmentType, FulfillmentHandler]] = None,
) -> FulfillmentRegistry:
    return FulfillmentRegistry(handlers)


__all__ = [
    "LIFECYCLE_HOOKS",
    "FulfillmentHandler",
    "FulfillmentRegistry",
    "NoopFulfillment",
    "make_fulfillment_registry",
]
