"""The commerce -> finance bridge, through the `FinanceBooking` seam only (CONTRACT §2.4 / §3.5).

* an order reaching `paid` books the sale as a receivable (`source='commerce_order'`, `source_ref=order id`) for the
  PRINCIPAL (the order total) and, when the buyer pays installment interest, the interest as a SEPARATE receivable
  (`source_ref='<order id>:interest'`, category "Juros de parcelamento") -- CONTRACT §10.5.3: the DRE maps the interest
  to its own line, and the Simples tax base always counts it;
* cash is booked when the money is AVAILABLE, not when the card is approved: a gateway
  `received` books a `payment` settlement with the gateway's net + fee, once per credit
  (per parcela for an installment card charge), idempotent on `(payment, <gateway payment id>)`;
* a payment/refund of the whole charge is applied to the principal first and the overflow to the interest entry
  (`interest_source_ref` on the `FinanceBooking` seam);
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
INTEREST_SUFFIX = ":interest"
SALES_CATEGORY_HINT = "vendas"
INTEREST_CATEGORY_HINT = "juros de parcelamento"


def interest_cents(order: Mapping[str, Any], charge_row: Mapping[str, Any]) -> int:
    """What the buyer paid ABOVE the order total (installment interest, D33/D45); 0 when none or unknown."""
    total = order.get("total_cents")
    if total is None:
        return 0
    return max(int(charge_row["amount_cents"]) - int(total), 0)


def interest_ref(order: Mapping[str, Any], charge_row: Mapping[str, Any]) -> Optional[str]:
    """The `source_ref` of the order's interest receivable, or None when the charge carried no interest."""
    return f"{order['id']}{INTEREST_SUFFIX}" if interest_cents(order, charge_row) > 0 else None


def book_receivable(db: Any, org_id: Any, deps: MoneyDeps, order: Mapping[str, Any], charge_row: Mapping[str, Any]) -> Optional[str]:
    customer = get_row(db, "commerce_customers", org_id, order["customer_id"]) or {}
    paid_on = to_day(order.get("paid_at"))
    interest = interest_cents(order, charge_row)
    common = dict(
        counterparty_name=order.get("buyer_name") or customer.get("name") or None,
        counterparty_doc=order.get("buyer_doc") or customer.get("doc") or None,
        competence_month=paid_on,
        due_date=paid_on,
    )
    short = str(order["id"])[:8]
    principal_id = deps.finance.book_receivable(
        str(org_id),
        source=SOURCE,
        source_ref=str(order["id"]),
        description=f"Pedido {short}",
        amount_cents=int(charge_row["amount_cents"]) - interest,
        category_hint=SALES_CATEGORY_HINT,
        **common,
    )
    if interest > 0:
        deps.finance.book_receivable(
            str(org_id),
            source=SOURCE,
            source_ref=f"{order['id']}{INTEREST_SUFFIX}",
            description=f"Juros de parcelamento do pedido {short}",
            amount_cents=interest,
            category_hint=INTEREST_CATEGORY_HINT,
            **common,
        )
    return principal_id


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
        interest_source_ref=interest_ref(order, charge_row),
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
            interest_source_ref=interest_ref(order, charge_row),
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
        interest_source_ref=interest_ref(order, charge_row),
    )


__all__ = ["SOURCE", "book_chargeback_loss", "book_payment", "book_receivable", "book_refunds", "interest_cents", "interest_ref"]
