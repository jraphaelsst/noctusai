"""Orders -- persistence around the pure state machine.

`apply_transition` is the ONLY place an order's status changes: it asks
`order_state.transition` for the new status (an illegal move raises), writes it
with an optimistic guard (`WHERE status = <seen>` -- two racing writers cannot
both apply from the same state), and appends the `commerce_order_events` row.
A status change without its event cannot happen through this module.
"""
from __future__ import annotations

import logging
import secrets
from datetime import datetime
from typing import Any, Mapping, Optional

from noctusai_lib.integrations.persistence.table_reads import paged_rows

from ._common import first, get_row, new_id, now, now_iso, page_rows, tbl
from .errors import CommerceError, not_found
from .gateway import CheckoutGateway
from .order_charges import cancel_gateway_charge, current_attempt, ensure_attempt_row, set_attempt_status
from .order_state import InvalidTransition, OrderEvent, transition
from .types import ChargeAttemptStatus, OrderEventSource, OrderStatus

logger = logging.getLogger(__name__)

_ORDERS = "commerce_orders"
_ITEMS = "commerce_order_items"
_EVENTS = "commerce_order_events"
_CUSTOMERS = "commerce_customers"


class StaleOrder(Exception):
    """The order changed under us (another writer moved it from the status we read).
    Retryable: the webhook releases its inbox claim and lets the gateway redeliver."""


def new_token() -> str:
    """Opaque, unguessable public order handle (192 bits)."""
    return secrets.token_urlsafe(24)


def append_event(
    db: Any,
    org_id: Any,
    order_id: Any,
    *,
    from_status: Optional[str],
    to_status: str,
    source: OrderEventSource,
    reason: Optional[str] = None,
) -> dict:
    row = {
        "id": new_id(),
        "org_id": str(org_id),
        "order_id": str(order_id),
        "from_status": from_status,
        "to_status": to_status,
        "reason": reason,
        "source": source.value,
        "at": now_iso(),
    }
    return first(tbl(db, _EVENTS).insert(row).execute()) or row


def apply_transition(
    db: Any,
    org_id: Any,
    order: Mapping[str, Any],
    event: OrderEvent,
    *,
    source: OrderEventSource,
    reason: Optional[str] = None,
    extra: Optional[Mapping[str, Any]] = None,
) -> dict:
    """Move `order` by `event`; returns the updated order.

    Raises `InvalidTransition` (illegal move) or `StaleOrder` (lost a race).
    `extra` carries columns that change WITH the transition (`paid_at`, ...).
    """
    current = OrderStatus(order["status"])
    new_status = transition(current, event)
    patch = {**(extra or {}), "status": new_status.value, "updated_at": now_iso()}
    updated = (
        tbl(db, _ORDERS)
        .update(patch)
        .eq("org_id", str(org_id))
        .eq("id", str(order["id"]))
        .eq("status", current.value)
        .execute()
    )
    saved = first(updated)
    if saved is None:
        raise StaleOrder(f"order {order['id']} is no longer {current.value}")
    append_event(db, org_id, order["id"], from_status=current.value, to_status=new_status.value, source=source, reason=reason)
    return saved


# ─── reads ───────────────────────────────────────────────────────────────


def get_order(db: Any, org_id: Any, order_id: Any) -> dict:
    row = get_row(db, _ORDERS, org_id, order_id)
    if row is None:
        raise not_found("Pedido")
    return row


def get_order_by_token(db: Any, org_id: Any, token: str) -> Optional[dict]:
    resp = tbl(db, _ORDERS).select("*").eq("org_id", str(org_id)).eq("token", token).limit(1).execute()
    return first(resp)


def get_order_by_charge(db: Any, org_id: Any, charge_id: str) -> Optional[dict]:
    resp = tbl(db, _ORDERS).select("*").eq("org_id", str(org_id)).eq("gateway_charge_id", charge_id).limit(1).execute()
    return first(resp)


def list_items(db: Any, org_id: Any, order_id: Any) -> list[dict]:
    return paged_rows(db, _ITEMS, org_id, eq_filters={"order_id": str(order_id)})


def list_events(db: Any, org_id: Any, order_id: Any) -> list[dict]:
    rows = paged_rows(db, _EVENTS, org_id, eq_filters={"order_id": str(order_id)})
    return sorted(rows, key=lambda r: str(r.get("at", "")))


def list_orders(
    db: Any, org_id: Any, *, status: Optional[str] = None, page: int = 1, page_size: int = 20
) -> tuple[list[dict], int, int, int]:
    filters = {"status": OrderStatus(status).value} if status else None
    rows, total, page, size = page_rows(db, _ORDERS, org_id, page=page, page_size=page_size, eq_filters=filters)
    # A row-level customer label so the table needs no N+1 round trips.
    ids = sorted({str(r["customer_id"]) for r in rows})
    names: dict[str, dict] = {}
    if ids:
        resp = tbl(db, _CUSTOMERS).select("id,name,email").eq("org_id", str(org_id)).in_("id", ids).execute()
        names = {str(c["id"]): c for c in (resp.data or [])}
    for r in rows:
        c = names.get(str(r["customer_id"]))
        r["customer"] = {"id": str(r["customer_id"]), "name": (c or {}).get("name"), "email": (c or {}).get("email")}
    return rows, total, page, size


def order_detail(db: Any, org_id: Any, order_id: Any) -> dict:
    order = get_order(db, org_id, order_id)
    customer = get_row(db, _CUSTOMERS, org_id, order["customer_id"])
    return {
        **order,
        "customer": (
            {"id": str(customer["id"]), "name": customer.get("name"), "email": customer.get("email")}
            if customer
            else None
        ),
        "items": list_items(db, org_id, order_id),
        "events": list_events(db, org_id, order_id),
    }


# ─── staff actions ───────────────────────────────────────────────────────

def cancel_order(
    db: Any, org_id: Any, order_id: Any, *, reason: Optional[str] = None, gateway: Optional[CheckoutGateway] = None
) -> dict:
    """Cancel an order. With a `gateway` the live charge is VOIDED first (closes
    `NOC-REMEDIATE[commerce-gateway-cancel]`): if it cannot be proven dead the cancel is refused with 409
    `cobranca_anterior_ativa` -- a cancelled order must not keep a payable charge. Without a gateway (a host that
    never wired one) only the order moves, and a payment that still lands is ignored by the webhook + alerted."""
    order = get_order(db, org_id, order_id)
    if gateway is not None and order["status"] in (OrderStatus.CREATED.value, OrderStatus.PENDING_PAYMENT.value):
        rows = ensure_attempt_row(db, org_id, order)
        live = current_attempt(rows, order)
        if live is not None and live["status"] == ChargeAttemptStatus.PENDING.value:
            cancel_gateway_charge(gateway, org_id, live["gateway_charge_id"])
            set_attempt_status(db, org_id, live["id"], ChargeAttemptStatus.CANCELLED)
    try:
        return apply_transition(
            db, org_id, order, OrderEvent.CANCEL, source=OrderEventSource.STAFF, reason=reason or "cancelado pela equipe"
        )
    except InvalidTransition as exc:
        raise CommerceError(
            "transicao_invalida", f"Um pedido {order['status']} não pode ser cancelado.", 409
        ) from exc
    except StaleOrder as exc:
        raise CommerceError("pedido_alterado", "O pedido mudou enquanto você agia. Recarregue.", 409) from exc


def expire_overdue_orders(db: Any, org_id: Any, *, at: Optional[datetime] = None) -> int:
    """Expire this org's `pending_payment` orders past `expires_at` (a job entry
    point; the gateway's own overdue webhook does the same move). Returns the count."""
    moment = at or now()
    count = 0
    for order in paged_rows(db, _ORDERS, org_id, eq_filters={"status": OrderStatus.PENDING_PAYMENT.value}):
        expires = order.get("expires_at")
        if not expires:
            continue
        if datetime.fromisoformat(str(expires).replace("Z", "+00:00")) <= moment:
            try:
                apply_transition(db, org_id, order, OrderEvent.EXPIRED, source=OrderEventSource.SYSTEM, reason="prazo de pagamento esgotado")
                count += 1
            except StaleOrder:
                logger.info("commerce expire sweep lost a race on order=%s", order["id"])
    return count


def platform_fee_earned(order: Mapping[str, Any]) -> int:
    """The noc fee counted as EARNED (D27): only while the order is `paid`.
    `platform_fee_cents` is recorded as the EXPECTED fee at charge creation; a
    refund/chargeback (and anything not yet paid) earns nothing."""
    return int(order.get("platform_fee_cents") or 0) if order.get("status") == OrderStatus.PAID.value else 0


__all__ = [
    "StaleOrder",
    "append_event",
    "apply_transition",
    "cancel_order",
    "expire_overdue_orders",
    "get_order",
    "get_order_by_charge",
    "get_order_by_token",
    "list_events",
    "list_items",
    "list_orders",
    "new_token",
    "order_detail",
    "platform_fee_earned",
]
