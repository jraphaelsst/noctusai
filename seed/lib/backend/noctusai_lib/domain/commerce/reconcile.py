"""Order <-> gateway reconciliation: refunds + the dispute (chargeback) lifecycle.

`sync_order_with_gateway` re-reads the charge (`get_charge`: the gateway is the source of truth
for money, never the webhook body) and brings the order to what the gateway shows:

* refunds -> `commerce_refunds` rows + `partially_refunded` / `refunded` (`refunds.py`);
* the dispute, from the charge status alone (W3: Asaas has no "lost" webhook, a loss is only
  visible as `chargeback` on the payment -- so `commerce_dispute_poll` calls this too):

    gateway `disputed`    + order paid/partially_refunded -> `disputed`   (+ `on_paused`, staff alert)
    gateway `chargeback`  + order disputed                -> `chargeback` (+ `on_revoked`, refund settlement, alert)
    gateway `chargeback`  + order paid/partially_refunded -> `chargeback` (a loss we never saw open)
    gateway paid again    + order disputed                -> `paid` | `partially_refunded` (+ `on_resumed`)

Every step is idempotent: calling it twice, or from the webhook AND the poll, converges.

A dispute / refund event on a LATER parcela of an installment card charge (a different gateway payment id than the
one stored) is surfaced to staff by the webhook (`webhook._on_money_change`), not applied.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from noctusai_lib.integrations.payments.errors import PaymentGatewayError
from noctusai_lib.integrations.payments.types import GatewayCharge

from . import finance_bridge
from .alerts import notify_staff
from .errors import GatewayNotConfigured
from .money import MoneyDeps, fire_revoked
from .order_charges import ensure_attempt_row, paid_attempt, current_attempt
from .order_state import OrderEvent
from .orders import apply_transition, list_items
from .refunds import apply_refund_state, list_refunds, reconcile_refunds, refunded_cents
from .types import OrderEventSource, OrderStatus

logger = logging.getLogger(__name__)

_LIVE = (OrderStatus.PAID.value, OrderStatus.PARTIALLY_REFUNDED.value)
_PAID_AGAIN = ("confirmed", "received", "partially_refunded", "refunded")


def _short(order: dict) -> str:
    return str(order["id"])[:8]


# NOC-REMEDIATE[commerce-installment-dispute]: dispute/refund events on a later parcela of an installment charge are alerted to staff, not applied; destination: installment-level charge model (P9) — 2026-10-14
async def sync_order_with_gateway(
    db: Any,
    org_id: Any,
    deps: MoneyDeps,
    order: dict,
    *,
    source: OrderEventSource,
    gateway_charge: Optional[GatewayCharge] = None,
) -> dict:
    """Reconcile `order` with the gateway; returns the (possibly moved) order. Raises on a gateway read failure."""
    rows = ensure_attempt_row(db, org_id, order)
    row = paid_attempt(rows) or current_attempt(rows, order)
    if row is None:
        return order
    if gateway_charge is None or gateway_charge.id_at_gateway != row["gateway_charge_id"]:
        try:
            gateway_charge = deps.gateway.charge_operations(org_id).get_charge(row["gateway_charge_id"])
        except (PaymentGatewayError, GatewayNotConfigured) as exc:
            logger.error("commerce sync: could not read charge for order=%s: %s", order["id"], exc)
            raise

    became_done = reconcile_refunds(db, org_id, order, row, gateway_charge)
    before = order["status"]
    order = apply_refund_state(db, org_id, deps, order, row, source=source, newly_done=became_done)
    if before != OrderStatus.REFUNDED.value and order["status"] == OrderStatus.REFUNDED.value:
        await fire_revoked(deps, db, order, "refunded")

    status = gateway_charge.status
    if status == "disputed" and order["status"] in _LIVE:
        order = apply_transition(db, org_id, order, OrderEvent.DISPUTE_OPENED, source=source, reason="contestação (chargeback) aberta")
        deps.fulfillment.dispatch_paused(order, list_items(db, org_id, order["id"]))
        await notify_staff(
            db, org_id, deps.email,
            subject=f"Contestação (chargeback) aberta no pedido {_short(order)}",
            lines=[
                f"O pedido {_short(order)} entrou em contestação junto ao emissor do cartão.",
                "A entrega foi pausada. Reúna as evidências (comprovante de entrega, comunicação com o cliente) e envie ao gateway no prazo.",
            ],
        )
    elif status == "chargeback" and order["status"] in (*_LIVE, OrderStatus.DISPUTED.value):
        was_dispute = order["status"] == OrderStatus.DISPUTED.value
        order = apply_transition(
            db, org_id, order, OrderEvent.DISPUTE_LOST if was_dispute else OrderEvent.CHARGEBACK, source=source,
            reason="contestação perdida: chargeback",
        )
        refunds = list_refunds(db, org_id, order["id"])
        deps.fulfillment.dispatch_revoked(order, list_items(db, org_id, order["id"]))
        finance_bridge.book_chargeback_loss(db, org_id, deps, order, row, refunds)
        await fire_revoked(deps, db, order, "chargeback")
        await notify_staff(
            db, org_id, deps.email,
            subject=f"Chargeback perdido no pedido {_short(order)}",
            lines=[f"A contestação do pedido {_short(order)} foi perdida: o valor foi devolvido ao cliente e o pedido está em chargeback."],
        )
    elif status in _PAID_AGAIN and order["status"] == OrderStatus.DISPUTED.value:
        refunds = list_refunds(db, org_id, order["id"])
        partial = refunded_cents(refunds) > 0
        order = apply_transition(
            db, org_id, order, OrderEvent.DISPUTE_WON_PARTIAL if partial else OrderEvent.DISPUTE_WON, source=source,
            reason="contestação ganha",
        )
        deps.fulfillment.dispatch_resumed(order, list_items(db, org_id, order["id"]))
        order = apply_refund_state(db, org_id, deps, order, row, source=source, newly_done=[])
        if order["status"] == OrderStatus.REFUNDED.value:
            await fire_revoked(deps, db, order, "refunded")
    return order


__all__ = ["sync_order_with_gateway"]
