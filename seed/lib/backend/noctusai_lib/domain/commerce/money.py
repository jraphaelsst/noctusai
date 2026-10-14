"""Shared plumbing of the P4 money services: the dependency bundle + tiny helpers.

`MoneyDeps` is what every money flow (webhook, refunds, dispute sync, regenerate,
jobs) needs besides the database: the per-org gateway (read / refund / cancel a charge),
the fulfillment registry (lifecycle hooks), the `FinanceBooking` seam (Noop for a product
without finance) and the e-mail sender used for staff alerts (None => alerts are logged,
never silently dropped).
"""
from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Callable, Mapping, Optional

from noctusai_lib.domain.finance.booking import FinanceBooking, NoopFinanceBooking
from noctusai_lib.integrations.email.types import EmailSender

from ._common import now
from .config import CommerceConfig
from .fulfillment import FulfillmentRegistry, make_fulfillment_registry
from .gateway import CheckoutGateway


logger = logging.getLogger(__name__)

#: `hook(db, order)` / `hook(db, order, reason=...)` -- sync or async. The seam the host wires in wave 3
#: (e.g. the fiscal slice's `on_order_paid` / `on_order_revoked`); an organ never imports the host's choice.
OrderHook = Callable[..., Any]


@dataclass(frozen=True)
class MoneyDeps:
    cfg: CommerceConfig
    gateway: CheckoutGateway
    fulfillment: FulfillmentRegistry = field(default_factory=make_fulfillment_registry)
    finance: FinanceBooking = field(default_factory=NoopFinanceBooking)
    email: Optional[EmailSender] = None
    #: Called when an order is (still) `paid` after a payment event; idempotent per order.
    on_paid_hooks: tuple[OrderHook, ...] = ()
    #: Called on a full refund / lost chargeback, with `reason="refunded" | "chargeback"`.
    on_revoked_hooks: tuple[OrderHook, ...] = ()


async def _fire(hooks: tuple[OrderHook, ...], db: Any, order: Mapping[str, Any], **kw: Any) -> None:
    for hook in hooks:
        try:
            result = hook(db, order, **kw)
            if inspect.isawaitable(result):
                await result
        except Exception:  # noqa: BLE001 - a follow-up hook never undoes the money state; it is retried by the next event/sweep
            logger.error("commerce order hook %r failed for order=%s", getattr(hook, "__name__", hook), order.get("id"), exc_info=True)


async def fire_paid(deps: "MoneyDeps", db: Any, order: Mapping[str, Any]) -> None:
    await _fire(deps.on_paid_hooks, db, order)


async def fire_revoked(deps: "MoneyDeps", db: Any, order: Mapping[str, Any], reason: str) -> None:
    await _fire(deps.on_revoked_hooks, db, order, reason=reason)


def rpc_json(response: Any) -> dict:
    """The jsonb object a `db.rpc(...).execute()` returned (PostgREST hands a scalar jsonb back as-is;
    some clients wrap it in a one-element list)."""
    data = getattr(response, "data", response)
    if isinstance(data, list):
        data = data[0] if data else {}
    if not isinstance(data, dict):
        raise ValueError(f"unexpected RPC payload: {type(data).__name__}")
    return data


def parse_ts(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def to_day(value: Any) -> date:
    moment = parse_ts(value) if value else None
    return (moment or now()).date()


__all__ = ["MoneyDeps", "OrderHook", "fire_paid", "fire_revoked", "parse_ts", "rpc_json", "to_day"]
