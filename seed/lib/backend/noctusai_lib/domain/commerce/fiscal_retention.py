"""Fiscal retention of the buyer's tax identity (owner decision D30, 2026-10-13).

LGPD art. 16 II (legal obligation) + CTN art. 173: a sale is a tax record, so
when an order reaches `paid` the buyer's CPF/CNPJ + name are SNAPSHOTTED onto
the order (`buyer_doc`, `buyer_name`) and `fiscal_retain_until` is set to
1 January of (payment year + 6) -- five years counted from 1 Jan of the year
after the payment. `anonymize_customer` scrubs the customer row but leaves
these order fields on orders that reached paid (incl. later refunded /
chargeback: they were sales). `purge_expired_fiscal_retention` erases them
once the window has passed.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Mapping, Optional

from ._common import first, get_row, now_iso, tbl

logger = logging.getLogger(__name__)

_ORDERS = "commerce_orders"
_CUSTOMERS = "commerce_customers"


def retain_until_for(paid_at: Any) -> date:
    """1 Jan of (paid year + 6). `paid_at` is an ISO string / datetime / date."""
    if isinstance(paid_at, (datetime, date)):
        year = paid_at.year
    else:
        year = int(str(paid_at)[:4])
    return date(year + 6, 1, 1)


def snapshot_fiscal_identity(db: Any, org_id: Any, order: Mapping[str, Any]) -> dict:
    """Copy the customer's CURRENT doc + name onto a paid order; returns the order.

    Called after the payment's customer data was merged (payment-source values
    already win via `merge_customer_fields`). Idempotent: an order that already
    carries `fiscal_retain_until` is returned untouched.
    """
    if order.get("fiscal_retain_until"):
        return dict(order)
    customer = get_row(db, _CUSTOMERS, org_id, order["customer_id"]) or {}
    patch = {
        "buyer_doc": customer.get("doc"),
        "buyer_name": customer.get("name"),
        "fiscal_retain_until": retain_until_for(order.get("paid_at") or now_iso()).isoformat(),
    }
    updated = (
        tbl(db, _ORDERS).update(patch).eq("org_id", str(org_id)).eq("id", str(order["id"])).is_("fiscal_retain_until", "null").execute()
    )
    return first(updated) or {**order, **patch}


# Scheduled daily by `jobs.commerce_fiscal_purge` (registered via `jobs.register_commerce_jobs`); also callable by hand.
def purge_expired_fiscal_retention(db: Any, org_id: Any = None, today: Optional[date] = None) -> int:
    """Null buyer_doc / buyer_name / fiscal_retain_until where the window ended
    (`fiscal_retain_until <= today`). `org_id=None` sweeps every org. Returns the
    number of orders purged."""
    cutoff = (today or date.today()).isoformat()
    query = tbl(db, _ORDERS).update(
        {"buyer_doc": None, "buyer_name": None, "fiscal_retain_until": None, "updated_at": now_iso()}
    ).lte("fiscal_retain_until", cutoff)
    if org_id is not None:
        query = query.eq("org_id", str(org_id))
    rows = query.execute().data or []
    if rows:
        logger.info("commerce fiscal retention: purged %d expired order record(s)", len(rows))
    return len(rows)


__all__ = ["purge_expired_fiscal_retention", "retain_until_for", "snapshot_fiscal_identity"]
