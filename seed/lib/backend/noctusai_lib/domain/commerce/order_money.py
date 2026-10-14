"""The money view of an order -- charges, refunds, reminders -- for `GET /orders/{id}` (CONTRACT §2.5).

Kept apart from `orders.order_detail` (which `refunds` / `order_charges` would otherwise import in a cycle).
"""
from __future__ import annotations

from typing import Any

from noctusai_lib.integrations.persistence.table_reads import paged_rows

from .order_charges import list_charges
from .refunds import list_refunds

_REMINDERS = "commerce_order_reminders"


def list_reminders(db: Any, org_id: Any, order_id: Any) -> list[dict]:
    rows = paged_rows(db, _REMINDERS, org_id, eq_filters={"order_id": str(order_id)}, order_col="kind", id_key="kind")
    return sorted(rows, key=lambda r: str(r.get("sent_at", "")))


def money_detail(db: Any, org_id: Any, order_id: Any) -> dict:
    return {
        "charges": list_charges(db, org_id, order_id),
        "refunds": list_refunds(db, org_id, order_id),
        "reminders": list_reminders(db, org_id, order_id),
    }


__all__ = ["list_reminders", "money_detail"]
