"""`commerce_order_charges` -- one row per charge attempt of an order (CONTRACT §2.3).

`commerce_orders.gateway_charge_id` points at the CURRENT attempt; earlier attempts stay as
rows (cancelled / expired) so a late payment on a superseded charge can still be recognised.
A pre-P4 order has a gateway charge but no row: `ensure_attempt_row` lazily backfills attempt 1
from the order (those orders had no interest, so `total_cents` is what was charged).
"""
from __future__ import annotations

import logging
from typing import Any, Mapping, Optional

from noctusai_lib.integrations.payments.errors import PaymentGatewayError
from noctusai_lib.integrations.persistence.table_reads import paged_rows
from noctusai_lib.primitives.postgrest_errors import is_unique_violation

from ._common import first, new_id, now_iso, tbl
from .errors import CommerceError, GatewayNotConfigured
from .gateway import CheckoutGateway
from .types import ChargeAttemptStatus, OrderStatus

logger = logging.getLogger(__name__)

_CHARGES = "commerce_order_charges"
_ORDERS = "commerce_orders"

_ORDER_TO_ATTEMPT = {
    OrderStatus.PENDING_PAYMENT.value: ChargeAttemptStatus.PENDING,
    OrderStatus.CREATED.value: ChargeAttemptStatus.PENDING,
    OrderStatus.EXPIRED.value: ChargeAttemptStatus.EXPIRED,
    OrderStatus.FAILED.value: ChargeAttemptStatus.FAILED,
    OrderStatus.CANCELLED.value: ChargeAttemptStatus.CANCELLED,
}


def list_charges(db: Any, org_id: Any, order_id: Any) -> list[dict]:
    rows = paged_rows(db, _CHARGES, org_id, eq_filters={"order_id": str(order_id)})
    return sorted(rows, key=lambda r: int(r["attempt"]))


def charge_by_gateway_id(db: Any, org_id: Any, gateway: str, gateway_charge_id: str) -> Optional[dict]:
    resp = (
        tbl(db, _CHARGES).select("*").eq("org_id", str(org_id)).eq("gateway", gateway)
        .eq("gateway_charge_id", gateway_charge_id).limit(1).execute()
    )
    return first(resp)


def insert_attempt(
    db: Any,
    org_id: Any,
    order_id: Any,
    *,
    attempt: int,
    gateway: str,
    gateway_charge_id: str,
    payment_method: str,
    installment_count: int,
    amount_cents: int,
    status: ChargeAttemptStatus = ChargeAttemptStatus.PENDING,
    checkout_url: Optional[str] = None,
    pix_qr: Optional[Mapping[str, Any]] = None,
    due_at: Optional[str] = None,
) -> dict:
    row = {
        "id": new_id(),
        "org_id": str(org_id),
        "order_id": str(order_id),
        "attempt": attempt,
        "gateway": gateway,
        "gateway_charge_id": gateway_charge_id,
        "payment_method": payment_method,
        "installment_count": installment_count,
        "amount_cents": amount_cents,
        "status": status.value,
        "checkout_url": checkout_url,
        "pix_qr": dict(pix_qr) if pix_qr else None,
        "due_at": due_at,
        "created_at": now_iso(),
        "closed_at": None if status is ChargeAttemptStatus.PENDING else now_iso(),
    }
    return first(tbl(db, _CHARGES).insert(row).execute()) or row


def set_attempt_status(db: Any, org_id: Any, charge_id: Any, status: ChargeAttemptStatus) -> None:
    patch: dict[str, Any] = {"status": status.value, "closed_at": None if status is ChargeAttemptStatus.PENDING else now_iso()}
    tbl(db, _CHARGES).update(patch).eq("org_id", str(org_id)).eq("id", str(charge_id)).execute()


def ensure_attempt_row(db: Any, org_id: Any, order: Mapping[str, Any]) -> list[dict]:
    """The order's charge rows, backfilling attempt 1 for a pre-P4 order that has a gateway charge."""
    rows = list_charges(db, org_id, order["id"])
    if rows or not order.get("gateway_charge_id"):
        return rows
    status = _ORDER_TO_ATTEMPT.get(order["status"], ChargeAttemptStatus.PAID)
    try:
        row = insert_attempt(
            db, org_id, order["id"], attempt=1, gateway=order["gateway"], gateway_charge_id=order["gateway_charge_id"],
            payment_method=order["payment_method"], installment_count=1, amount_cents=int(order["total_cents"]),
            status=status, checkout_url=order.get("checkout_url"), pix_qr=order.get("pix_qr"), due_at=order.get("expires_at"),
        )
    except Exception as exc:  # noqa: BLE001 - narrowed below
        if not is_unique_violation(exc):
            raise
        return list_charges(db, org_id, order["id"])  # a concurrent backfill won
    if int(order.get("charge_attempts") or 0) < 1:
        tbl(db, _ORDERS).update({"charge_attempts": 1}).eq("org_id", str(org_id)).eq("id", str(order["id"])).execute()
    return [row]


def current_attempt(rows: list[dict], order: Mapping[str, Any]) -> Optional[dict]:
    """The row `commerce_orders.gateway_charge_id` points at."""
    for row in rows:
        if row["gateway_charge_id"] == order.get("gateway_charge_id"):
            return row
    return None


def paid_attempt(rows: list[dict]) -> Optional[dict]:
    paid = [r for r in rows if r["status"] == ChargeAttemptStatus.PAID.value]
    return paid[-1] if paid else None


def cancel_gateway_charge(gateway: CheckoutGateway, org_id: Any, gateway_charge_id: str) -> str:
    """Void an UNPAID charge at the gateway. Returns `cancelled` | `already_gone`; raises 409
    `cobranca_anterior_ativa` when it cannot be proven dead (paid, unreadable or the cancel failed)."""
    try:
        ops = gateway.charge_operations(org_id)
    except GatewayNotConfigured as exc:
        raise CommerceError("pagamento_indisponivel", "O pagamento não está disponível nesta loja agora.", 503) from exc
    try:
        charge = ops.get_charge(gateway_charge_id)
        if charge.status == "cancelled":
            return "already_gone"
        if charge.status not in ("pending", "overdue"):
            raise CommerceError(
                "cobranca_anterior_ativa", "O pagamento anterior já foi recebido ou está em análise. Aguarde a confirmação.", 409
            )
        ops.cancel_charge(gateway_charge_id)
        return "cancelled"
    except PaymentGatewayError as exc:
        if exc.status == 404:
            return "already_gone"
        logger.error("commerce: could not cancel charge (code=%s status=%s)", exc.code, exc.status)
        raise CommerceError(
            "cobranca_anterior_ativa", "Não foi possível cancelar a cobrança anterior. Tente novamente em instantes.", 409
        ) from exc


__all__ = [
    "cancel_gateway_charge",
    "charge_by_gateway_id",
    "current_attempt",
    "ensure_attempt_row",
    "insert_attempt",
    "list_charges",
    "paid_attempt",
    "set_attempt_status",
]
