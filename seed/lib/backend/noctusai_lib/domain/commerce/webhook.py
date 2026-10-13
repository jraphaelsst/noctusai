"""Payment webhook handling -- inbox claim -> order transition -> release on failure.

The router has ALREADY verified the delivery (5-pin: per-org token compared
constant-time by the seed's `parse_webhook_event`, fail-closed on an unset token,
secret resolved per request, rate limit, status-pinned tests) and hands over a
verified, normalised `GatewayEvent`.

* Duplicates: the seed `EventInbox` claim (PK `(gateway, event_id)`). A claimed
  delivery whose processing raised is RELEASED so the gateway's retry is not lost.
* `charge_paid`        -> `paid` (a `pending_payment`/`expired` order directly; a
  `created`/`failed` order via the recovery step first -- real money arrived, it is
  never dropped on the floor), then customer enrichment from the gateway's data
  (payment is the source of truth) and the fulfillment dispatch.
* `charge_failed` (Asaas "overdue") -> `expired` for a `pending_payment` order.
* `charge_refunded`    -> `refunded`, or `chargeback` when the raw event is
  `PAYMENT_CHARGEBACK_REQUESTED`; only a `paid` order moves.
* Anything else / an unknown order / a payment for a cancelled order -> ignored
  (logged), still 200: gateways retry forever on a non-2xx.

Out-of-order safety comes from the state machine: a late `paid` event cannot
resurrect a refunded order (`refunded` is terminal), and a duplicate state move is
a no-op, not an error.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Optional

from noctusai_lib.domain.payments.event_inbox import EventInbox
from noctusai_lib.integrations.payments.webhook_events import GatewayEvent
from noctusai_lib.primitives.exceptions import NotFoundError

from ._common import now_iso
from .customers import enrich_from_payment
from .fulfillment import FulfillmentRegistry
from .gateway import CheckoutGateway
from .order_state import OrderEvent
from .orders import (
    apply_transition,
    get_order,
    get_order_by_charge,
    list_items,
)
from .types import OrderEventSource, OrderStatus

logger = logging.getLogger(__name__)

DUPLICATE = "duplicate"
IGNORED = "ignored"
PROCESSED = "processed"

_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def _find_order(db: Any, org_id: Any, event: GatewayEvent) -> Optional[dict]:
    if event.external_reference and _UUID_RE.match(event.external_reference):
        try:
            return get_order(db, org_id, event.external_reference)
        except NotFoundError:
            pass  # fall through to the charge-id lookup
    if event.charge_id_at_gateway:
        return get_order_by_charge(db, org_id, event.charge_id_at_gateway)
    return None


def handle_event(
    db: Any,
    org_id: Any,
    event: GatewayEvent,
    *,
    inbox: EventInbox,
    gateway: CheckoutGateway,
    fulfillment: FulfillmentRegistry,
) -> str:
    """Process one verified delivery. Returns `duplicate` | `ignored` | `processed`."""
    gateway_name, event_id = event.inbox_key
    if not inbox.claim(gateway=gateway_name, event_id=event_id):
        return DUPLICATE
    try:
        return _dispatch(db, org_id, event, gateway=gateway, fulfillment=fulfillment)
    except Exception:
        inbox.release(gateway=gateway_name, event_id=event_id)
        raise


def _dispatch(
    db: Any, org_id: Any, event: GatewayEvent, *, gateway: CheckoutGateway, fulfillment: FulfillmentRegistry
) -> str:
    if event.kind not in ("charge_paid", "charge_failed", "charge_refunded"):
        return IGNORED
    order = _find_order(db, org_id, event)
    if order is None:
        logger.warning("commerce webhook: %s for an unknown order (event ignored)", event.kind)
        return IGNORED

    if event.kind == "charge_paid":
        return _on_paid(db, org_id, order, event, gateway=gateway, fulfillment=fulfillment)
    if event.kind == "charge_failed":
        if order["status"] == OrderStatus.PENDING_PAYMENT.value:
            apply_transition(
                db, org_id, order, OrderEvent.EXPIRED, source=OrderEventSource.WEBHOOK, reason="cobrança vencida"
            )
            return PROCESSED
        return IGNORED
    return _on_refund(db, org_id, order, event)


def _on_paid(
    db: Any,
    org_id: Any,
    order: dict,
    event: GatewayEvent,
    *,
    gateway: CheckoutGateway,
    fulfillment: FulfillmentRegistry,
) -> str:
    status = order["status"]
    if status in (OrderStatus.CANCELLED.value, OrderStatus.REFUNDED.value, OrderStatus.CHARGEBACK.value):
        # Money arrived for an order we closed: never resurrect it, never hide it.
        logger.error(
            "commerce webhook: PAYMENT for a %s order=%s (charge=%s) needs MANUAL handling (refund or reopen)",
            status, order["id"], event.charge_id_at_gateway,
        )
        return IGNORED

    if status != OrderStatus.PAID.value:
        if status == OrderStatus.CREATED.value:
            order = apply_transition(
                db, org_id, order, OrderEvent.CHARGE_CREATED, source=OrderEventSource.WEBHOOK,
                reason="pagamento recebido antes do registro da cobrança",
            )
        elif status == OrderStatus.FAILED.value:
            order = apply_transition(
                db, org_id, order, OrderEvent.RETRY, source=OrderEventSource.WEBHOOK,
                reason="pagamento recebido para um pedido que havia falhado",
            )
        extra: dict[str, Any] = {"paid_at": now_iso()}
        if event.charge_id_at_gateway and not order.get("gateway_charge_id"):
            extra["gateway_charge_id"] = event.charge_id_at_gateway
        order = apply_transition(
            db, org_id, order, OrderEvent.PAYMENT_CONFIRMED, source=OrderEventSource.WEBHOOK,
            reason="pagamento confirmado", extra=extra,
        )
        _enrich_customer(db, org_id, order, event, gateway)

    # Idempotent handlers (see fulfillment module): also runs for the second
    # confirmation event of an already-paid order and for a redelivery after a failure.
    fulfillment.dispatch_paid(order, list_items(db, org_id, order["id"]))
    return PROCESSED


def _enrich_customer(db: Any, org_id: Any, order: dict, event: GatewayEvent, gateway: CheckoutGateway) -> None:
    payment = (event.raw or {}).get("payment") or {}
    gateway_customer_id = payment.get("customer")
    if not gateway_customer_id:
        return
    try:
        data = gateway.customer_data(org_id, str(gateway_customer_id))
        if data:
            enrich_from_payment(db, org_id, order["customer_id"], data)
    except Exception:  # noqa: BLE001 - enrichment must never undo a confirmed payment
        logger.warning("commerce webhook: customer enrichment failed for order=%s (payment stays confirmed)", order["id"], exc_info=True)


def _on_refund(db: Any, org_id: Any, order: dict, event: GatewayEvent) -> str:
    chargeback = (event.raw or {}).get("event") == "PAYMENT_CHARGEBACK_REQUESTED"
    target = OrderEvent.CHARGEBACK if chargeback else OrderEvent.REFUND
    if order["status"] != OrderStatus.PAID.value:
        return IGNORED
    apply_transition(
        db, org_id, order, target, source=OrderEventSource.WEBHOOK,
        reason="chargeback solicitado" if chargeback else "pagamento estornado",
    )
    return PROCESSED


__all__ = ["DUPLICATE", "IGNORED", "PROCESSED", "handle_event"]
