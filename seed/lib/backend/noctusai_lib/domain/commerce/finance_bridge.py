"""The commerce -> finance bridge, through the `FinanceBooking` seam only (CONTRACT §2.4 / §3.5).

* an order reaching `paid` books ONE receivable (`source='commerce_order'`, `source_ref=order id`)
  for what the buyer actually pays (the paid charge, interest included);
* cash is booked when the money is AVAILABLE, not when the card is approved: a gateway
  `received` books a `payment` settlement with the gateway's net + fee, once per credit
  (per parcela for an installment card charge), idempotent on `(payment, <gateway payment id>)`;
* every `done` refund books a `refund` settlement (`external_ref = commerce_refunds.id`), and a
  LOST chargeback books the remaining paid amount as a refund settlement
  (`external_ref = 'chargeback:<charge row id>'`).

Every call is idempotent, so a redelivered webhook / re-run job converges. A product without
finance passes `NoopFinanceBooking` (every call returns None). Failures are NOT swallowed here:
the caller decides whether a retry (webhook) or a logged event (staff action) is right.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any, Mapping, Optional

from noctusai_lib.integrations.payments.types import GatewayCharge

from ._common import get_row
from .money import MoneyDeps, to_day
from .types import RefundStatus

logger = logging.getLogger(__name__)

SOURCE = "commerce_order"


def book_receivable(db: Any, org_id: Any, deps: MoneyDeps, order: Mapping[str, Any], charge_row: Mapping[str, Any]) -> Optional[str]:
    customer = get_row(db, "commerce_customers", org_id, order["customer_id"]) or {}
    paid_on = to_day(order.get("paid_at"))
    return deps.finance.book_receivable(
        str(org_id),
        source=SOURCE,
        source_ref=str(order["id"]),
        description=f"Pedido {str(order['id'])[:8]}",
        counterparty_name=order.get("buyer_name") or customer.get("name") or None,
        counterparty_doc=order.get("buyer_doc") or customer.get("doc") or None,
        amount_cents=int(charge_row["amount_cents"]),
        competence_month=paid_on,
        due_date=paid_on,
        category_hint="vendas",
    )


def book_payment(
    db: Any, org_id: Any, deps: MoneyDeps, order: Mapping[str, Any], charge_row: Mapping[str, Any], gateway_charge: GatewayCharge
) -> Optional[str]:
    """Book the credit of one gateway payment (a `received` charge): net + fee, on its credit date."""
    book_receivable(db, org_id, deps, order, charge_row)
    fee = gateway_charge.fee.amount_cents if gateway_charge.fee is not None else 0
    settled_on: date = gateway_charge.credit_date or (gateway_charge.paid_at.date() if gateway_charge.paid_at else to_day(None))
    return deps.finance.book_settlement(
        str(org_id),
        source=SOURCE,
        source_ref=str(order["id"]),
        kind="payment",
        external_ref=gateway_charge.id_at_gateway,
        amount_cents=gateway_charge.amount.amount_cents,
        fee_cents=fee,
        settled_on=settled_on,
    )


def book_refunds(db: Any, org_id: Any, deps: MoneyDeps, order: Mapping[str, Any], charge_row: Mapping[str, Any], refunds: list[dict]) -> int:
    """Book every `done` refund as a refund settlement; returns how many calls were made (all idempotent)."""
    done = [r for r in refunds if r["status"] == RefundStatus.DONE.value]
    if not done:
        return 0
    book_receivable(db, org_id, deps, order, charge_row)
    for refund in done:
        deps.finance.book_settlement(
            str(org_id),
            source=SOURCE,
            source_ref=str(order["id"]),
            kind="refund",
            external_ref=str(refund["id"]),
            amount_cents=int(refund["amount_cents"]),
            fee_cents=0,
            settled_on=to_day(refund.get("done_at")),
        )
    return len(done)


def book_chargeback_loss(
    db: Any, org_id: Any, deps: MoneyDeps, order: Mapping[str, Any], charge_row: Mapping[str, Any], refunds: list[dict]
) -> Optional[str]:
    """A lost dispute returns the not-yet-refunded rest of the charge to the buyer."""
    refunded = sum(int(r["amount_cents"]) for r in refunds if r["status"] == RefundStatus.DONE.value)
    remaining = int(charge_row["amount_cents"]) - refunded
    if remaining <= 0:
        return None
    book_receivable(db, org_id, deps, order, charge_row)
    return deps.finance.book_settlement(
        str(org_id),
        source=SOURCE,
        source_ref=str(order["id"]),
        kind="refund",
        external_ref=f"chargeback:{charge_row['id']}",
        amount_cents=remaining,
        fee_cents=0,
        settled_on=to_day(None),
    )


__all__ = ["SOURCE", "book_chargeback_loss", "book_payment", "book_receivable", "book_refunds"]
