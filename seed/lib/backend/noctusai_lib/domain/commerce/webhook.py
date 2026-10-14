"""Payment webhook handling -- inbox claim -> re-read the gateway -> order/finance/fulfillment -> release on failure.

The router has ALREADY verified the delivery (5-pin: per-org token compared constant-time by the
seed's `parse_webhook_event`, fail-closed on an unset token, secret resolved per request, rate
limit, status-pinned tests) and hands over a verified, normalised `GatewayEvent`.

P4 rules (CONTRACT §0 / §2.2 / §2.4):

* **Never trust a webhook body for money.** Branch on `event.kind` / `event.detail` ONLY -- never on
  `event.raw` -- and re-read the charge (`get_charge`) before acting: the amounts, the status, the
  refunds and the dispute state all come from that read.
* Duplicates: the seed `EventInbox` claim. A claimed delivery whose processing raised is RELEASED so
  the gateway's retry is not lost; every step below is idempotent, so a retry converges.

  charge_paid            -> `paid` (`created`/`failed` recover through CHARGE_CREATED/RETRY first -- real money is
                            never dropped), fulfillment; the order's receivable is booked in finance;
                            a gateway-`received` charge (money AVAILABLE) books a payment settlement with
                            net + fee, once per credit (per parcela for installments).
  charge_failed/overdue  -> `expired` (only for the CURRENT attempt), `on_expired`.
  charge_cancelled       -> the attempt row is closed; a removal we did not do expires a pending order.
  charge_refunded / charge_partially_refunded / charge_dispute
                         -> `reconcile.sync_order_with_gateway`: refund rows, `partially_refunded`/`refunded`,
                            `disputed` (+ `on_paused`, staff alert) / `paid` (won) / `chargeback` (lost).
                            `charge_refunded` + `detail=chargeback_opened` is a DISPUTE, not a chargeback.

* A payment on a SUPERSEDED attempt (the buyer paid an old Pix after regenerating): if the order is not
  paid yet it becomes the paying attempt (the live newer charge is cancelled); if the order is already
  paid it is an EXTRA payment -- recorded on the attempt row + order event and a staff alert suggests a refund.
* Anything else / an unknown order / a payment for a closed order -> ignored (logged, staff alerted when
  it is money), still 200: gateways retry forever on a non-2xx.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Optional

from noctusai_lib.domain.payments.event_inbox import EventInbox
from noctusai_lib.integrations.payments.errors import PaymentGatewayError
from noctusai_lib.integrations.payments.types import GatewayCharge
from noctusai_lib.integrations.payments.webhook_events import GatewayEvent
from noctusai_lib.primitives.exceptions import NotFoundError

from . import finance_bridge
from ._common import now_iso, tbl
from .alerts import notify_staff
from .customers import enrich_from_payment
from .fiscal_retention import snapshot_fiscal_identity
from .money import MoneyDeps, fire_paid
from .order_charges import (
    cancel_gateway_charge,
    charge_by_gateway_id,
    current_attempt,
    ensure_attempt_row,
    set_attempt_status,
)
from .order_state import OrderEvent
from .orders import append_event, apply_transition, get_order, get_order_by_charge, list_items
from .reconcile import sync_order_with_gateway
from .types import ChargeAttemptStatus, OrderEventSource, OrderStatus

logger = logging.getLogger(__name__)

DUPLICATE = "duplicate"
IGNORED = "ignored"
PROCESSED = "processed"

_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")

_HANDLED = (
    "charge_paid", "charge_failed", "charge_refunded", "charge_partially_refunded", "charge_dispute", "charge_cancelled",
)
_CLOSED = (OrderStatus.CANCELLED.value, OrderStatus.REFUNDED.value, OrderStatus.CHARGEBACK.value)
_UNPAID = (OrderStatus.CREATED.value, OrderStatus.PENDING_PAYMENT.value, OrderStatus.EXPIRED.value, OrderStatus.FAILED.value)
_MONEY_STATES = (
    OrderStatus.PAID.value, OrderStatus.PARTIALLY_REFUNDED.value, OrderStatus.DISPUTED.value,
    OrderStatus.REFUNDED.value, OrderStatus.CHARGEBACK.value,
)
_PAID_READS = ("confirmed", "received", "partially_refunded", "refunded", "disputed", "chargeback")


class StaleGatewayRead(Exception):
    """The gateway's read does not (yet) show what its event announced. Retryable: the inbox claim is
    released so the gateway redelivers once its own state has caught up."""


def _find_order(db: Any, org_id: Any, event: GatewayEvent) -> Optional[dict]:
    if event.external_reference and _UUID_RE.match(event.external_reference):
        try:
            return get_order(db, org_id, event.external_reference)
        except NotFoundError:
            pass  # fall through to the charge-id lookup
    if event.charge_id_at_gateway:
        order = get_order_by_charge(db, org_id, event.charge_id_at_gateway)
        if order is not None:
            return order
        row = charge_by_gateway_id(db, org_id, "asaas", event.charge_id_at_gateway)
        if row is not None:
            try:
                return get_order(db, org_id, row["order_id"])
            except NotFoundError:
                return None
    return None


async def handle_event(db: Any, org_id: Any, event: GatewayEvent, *, inbox: EventInbox, deps: MoneyDeps) -> str:
    """Process one verified delivery. Returns `duplicate` | `ignored` | `processed`."""
    gateway_name, event_id = event.inbox_key
    if not inbox.claim(gateway=gateway_name, event_id=event_id):
        return DUPLICATE
    try:
        return await _dispatch(db, org_id, event, deps=deps)
    except Exception:
        inbox.release(gateway=gateway_name, event_id=event_id)
        raise


async def _dispatch(db: Any, org_id: Any, event: GatewayEvent, *, deps: MoneyDeps) -> str:
    if event.kind not in _HANDLED:
        return IGNORED
    order = _find_order(db, org_id, event)
    if order is None:
        logger.warning("commerce webhook: %s for an unknown order (event ignored)", event.kind)
        return IGNORED
    if event.kind == "charge_paid":
        return await _on_paid(db, org_id, order, event, deps=deps)
    if event.kind == "charge_failed":
        return _on_failed(db, org_id, order, event, deps=deps)
    if event.kind == "charge_cancelled":
        return _on_cancelled(db, org_id, order, event, deps=deps)
    return await _on_money_change(db, org_id, order, event, deps=deps)


# ─── attribution: which attempt does this event belong to? ─────────────────


def _attribute(db: Any, org_id: Any, order: dict, event: GatewayEvent, deps: MoneyDeps) -> tuple[str, Optional[dict]]:
    """`("current"|"superseded"|"installment"|"unknown", attempt_row)`."""
    rows = ensure_attempt_row(db, org_id, order)
    current = current_attempt(rows, order)
    charge_id = event.charge_id_at_gateway
    if not charge_id or not rows:
        return "current", current
    row = next((r for r in rows if r["gateway_charge_id"] == charge_id), None)
    if row is not None:
        return ("current" if current is not None and row["id"] == current["id"] else "superseded"), row
    # An id we never stored: a later PARCELA of an installment card charge, or something foreign.
    if current is not None and int(current["installment_count"]) > 1:
        return "installment", current
    return "unknown", None


def _read(deps: MoneyDeps, org_id: Any, charge_id: str) -> GatewayCharge:
    return deps.gateway.charge_operations(org_id).get_charge(charge_id)


# ─── paid ──────────────────────────────────────────────────────────────────


async def _on_paid(db: Any, org_id: Any, order: dict, event: GatewayEvent, *, deps: MoneyDeps) -> str:
    kind, row = _attribute(db, org_id, order, event, deps)
    short = str(order["id"])[:8]
    if kind == "unknown":
        logger.error("commerce webhook: payment on an UNKNOWN charge for order=%s (charge=%s)", order["id"], event.charge_id_at_gateway)
        await notify_staff(
            db, org_id, deps.email, subject=f"Pagamento não identificado no pedido {short}",
            lines=[f"Um pagamento chegou para o pedido {short} numa cobrança que o sistema não conhece. Confira no painel do gateway."],
        )
        return IGNORED

    gw = _read(deps, org_id, event.charge_id_at_gateway) if event.charge_id_at_gateway else None
    if gw is None or gw.status not in _PAID_READS:
        logger.warning("commerce webhook: charge_paid for order=%s but the gateway read is %s; ignored", order["id"], getattr(gw, "status", None))
        return IGNORED

    status = order["status"]
    if status in _CLOSED:
        # Money arrived for an order we closed: never resurrect it, never hide it.
        logger.error("commerce webhook: PAYMENT for a %s order=%s needs MANUAL handling (refund or reopen)", status, order["id"])
        await notify_staff(
            db, org_id, deps.email, subject=f"Pagamento recebido em pedido {status} ({short})",
            lines=[f"Entrou um pagamento no pedido {short}, que está {status}. Reembolse ou reabra o pedido manualmente."],
        )
        return IGNORED

    if kind == "superseded":
        if row is None:  # pragma: no cover - 'superseded' always carries its row
            return IGNORED
        if status not in _UNPAID:
            return await _extra_payment(db, org_id, order, row, deps=deps)
        order = _adopt_superseded(db, org_id, order, row, deps=deps)
        row = current_attempt(ensure_attempt_row(db, org_id, order), order)
        status = order["status"]
    newly_paid = status in _UNPAID
    if newly_paid:
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
        _enrich_customer(db, org_id, order, gw, deps)
    if row is not None and row["status"] != ChargeAttemptStatus.PAID.value:
        set_attempt_status(db, org_id, row["id"], ChargeAttemptStatus.PAID)
        row = {**row, "status": ChargeAttemptStatus.PAID.value}

    # D30: snapshot the tax identity AFTER enrichment (payment values win); idempotent.
    order = snapshot_fiscal_identity(db, org_id, order)

    if row is not None:
        finance_bridge.book_receivable(db, org_id, deps, order, row)
        if gw.status in ("received", "partially_refunded", "refunded"):
            finance_bridge.book_payment(db, org_id, deps, order, row, gw)

    if order["status"] == OrderStatus.PAID.value:
        # Idempotent handlers (see fulfillment module): also runs for the second confirmation event.
        deps.fulfillment.dispatch_paid(order, list_items(db, org_id, order["id"]))
        await fire_paid(deps, db, order)
    return PROCESSED


def _adopt_superseded(db: Any, org_id: Any, order: dict, row: dict, *, deps: MoneyDeps) -> dict:
    """An unpaid order got paid through an OLD attempt: that attempt becomes the current one and the
    newer live charge (if any) is cancelled so the buyer cannot pay twice."""
    rows = ensure_attempt_row(db, org_id, order)
    newer = current_attempt(rows, order)
    if newer is not None and newer["id"] != row["id"] and newer["status"] == ChargeAttemptStatus.PENDING.value:
        try:
            cancel_gateway_charge(deps.gateway, org_id, newer["gateway_charge_id"])
            set_attempt_status(db, org_id, newer["id"], ChargeAttemptStatus.CANCELLED)
        except Exception:  # noqa: BLE001 - the payment is real; a cancel failure is reported, not fatal
            logger.error("commerce webhook: could not cancel the newer charge of order=%s", order["id"], exc_info=True)
    tbl(db, "commerce_orders").update(
        {"gateway_charge_id": row["gateway_charge_id"], "checkout_url": row.get("checkout_url"), "pix_qr": row.get("pix_qr"),
         "payment_method": row["payment_method"], "updated_at": now_iso()}
    ).eq("org_id", str(org_id)).eq("id", str(order["id"])).execute()
    append_event(
        db, org_id, order["id"], from_status=order["status"], to_status=order["status"], source=OrderEventSource.WEBHOOK,
        reason="pagamento recebido em uma tentativa anterior; ela passa a ser a cobrança do pedido",
    )
    return get_order(db, org_id, order["id"])


async def _extra_payment(db: Any, org_id: Any, order: dict, row: dict, *, deps: MoneyDeps) -> str:
    """A second payment on a superseded attempt of an already-paid order: record it, tell staff, never silent."""
    if row["status"] != ChargeAttemptStatus.PAID.value:
        set_attempt_status(db, org_id, row["id"], ChargeAttemptStatus.PAID)
        append_event(
            db, org_id, order["id"], from_status=order["status"], to_status=order["status"], source=OrderEventSource.WEBHOOK,
            reason=f"pagamento EXTRA recebido na tentativa {row['attempt']}; avalie reembolsar",
        )
        short = str(order["id"])[:8]
        await notify_staff(
            db, org_id, deps.email, subject=f"Pagamento duplicado no pedido {short}",
            lines=[
                f"O pedido {short} já estava pago, mas o cliente também pagou uma cobrança anterior (tentativa {row['attempt']}).",
                f"Valor: R$ {int(row['amount_cents']) / 100:.2f}. Sugestão: reembolse essa cobrança no painel do gateway.",
            ],
        )
    return PROCESSED


def _enrich_customer(db: Any, org_id: Any, order: dict, gw: GatewayCharge, deps: MoneyDeps) -> None:
    """Payment is the source of truth for the buyer's data (D26): the customer id comes from the
    gateway READ, not from the delivery body."""
    gateway_customer_id = (gw.raw or {}).get("customer")
    if not gateway_customer_id:
        return
    try:
        data = deps.gateway.customer_data(org_id, str(gateway_customer_id))
        if data:
            enrich_from_payment(db, org_id, order["customer_id"], data)
    except Exception:  # noqa: BLE001 - enrichment must never undo a confirmed payment
        logger.warning("commerce webhook: customer enrichment failed for order=%s (payment stays confirmed)", order["id"], exc_info=True)


# ─── overdue / cancelled ───────────────────────────────────────────────────


def _on_failed(db: Any, org_id: Any, order: dict, event: GatewayEvent, *, deps: MoneyDeps) -> str:
    kind, row = _attribute(db, org_id, order, event, deps)
    if kind == "superseded" and row is not None:
        if row["status"] == ChargeAttemptStatus.PENDING.value:
            set_attempt_status(db, org_id, row["id"], ChargeAttemptStatus.EXPIRED)
        return IGNORED
    if kind != "current":
        return IGNORED
    if order["status"] == OrderStatus.PENDING_PAYMENT.value:
        _expire(db, org_id, order, row, deps=deps, reason="cobrança vencida")
        return PROCESSED
    return IGNORED


def _on_cancelled(db: Any, org_id: Any, order: dict, event: GatewayEvent, *, deps: MoneyDeps) -> str:
    kind, row = _attribute(db, org_id, order, event, deps)
    if row is None or row["status"] == ChargeAttemptStatus.CANCELLED.value:
        return IGNORED  # our own cancel (regenerate / staff cancel) already closed it
    if row["status"] == ChargeAttemptStatus.PAID.value:
        logger.error("commerce webhook: gateway deleted a PAID charge (order=%s); needs manual handling", order["id"])
        return IGNORED
    set_attempt_status(db, org_id, row["id"], ChargeAttemptStatus.CANCELLED)
    if kind == "current" and order["status"] == OrderStatus.PENDING_PAYMENT.value:
        _expire(db, org_id, order, None, deps=deps, reason="cobrança removida no gateway")
    return PROCESSED


def _expire(db: Any, org_id: Any, order: dict, row: Optional[dict], *, deps: MoneyDeps, reason: str) -> dict:
    order = apply_transition(db, org_id, order, OrderEvent.EXPIRED, source=OrderEventSource.WEBHOOK, reason=reason)
    if row is not None and row["status"] == ChargeAttemptStatus.PENDING.value:
        set_attempt_status(db, org_id, row["id"], ChargeAttemptStatus.EXPIRED)
    deps.fulfillment.dispatch_expired(order, list_items(db, org_id, order["id"]))
    return order


# ─── refunds / disputes ────────────────────────────────────────────────────


async def _on_money_change(db: Any, org_id: Any, order: dict, event: GatewayEvent, *, deps: MoneyDeps) -> str:
    if order["status"] not in _MONEY_STATES:
        logger.warning("commerce webhook: %s for order=%s in %s (never paid); ignored", event.kind, order["id"], order["status"])
        return IGNORED
    kind, row = _attribute(db, org_id, order, event, deps)
    short = str(order["id"])[:8]
    if kind in ("superseded", "installment", "unknown"):
        logger.error("commerce webhook: %s on a %s charge of order=%s needs manual handling", event.kind, kind, order["id"])
        await notify_staff(
            db, org_id, deps.email, subject=f"Evento financeiro em cobrança secundária do pedido {short}",
            lines=[f"Chegou um evento de {event.kind} para uma cobrança que não é a principal do pedido {short} (tipo: {kind}). Trate no painel do gateway."],
        )
        return IGNORED
    gw = _read(deps, org_id, event.charge_id_at_gateway) if event.charge_id_at_gateway else None
    if event.kind == "charge_refunded" and event.detail == "chargeback_opened" and (gw is None or gw.status not in ("disputed", "chargeback")):
        raise StaleGatewayRead(f"chargeback announced for order {order['id']} but the charge reads {getattr(gw, 'status', None)}")
    await sync_order_with_gateway(db, org_id, deps, order, source=OrderEventSource.WEBHOOK, gateway_charge=gw)
    return PROCESSED


__all__ = ["DUPLICATE", "IGNORED", "PROCESSED", "StaleGatewayRead", "handle_event"]
