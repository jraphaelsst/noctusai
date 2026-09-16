"""Recurring-revenue math, shared by the analytics and billing admin views.

The previous MRR summed `plans.price_monthly` over every `active`+`trial`
subscription: a trial (which pays nothing) counted as revenue, a yearly
subscription counted its full monthly list price instead of what it pays,
and the unbounded select silently stopped at 1 000 rows.

Here:

* counted statuses are the ones still billing: active, past_due, grace;
* a managed subscription contributes what it actually pays
  (`amount_cents`, divided by 12 when yearly);
* a legacy row (no `amount_cents`) falls back to its plan's
  `price_monthly` — the only price it ever had;
* non-BRL amounts are reported separately, never silently mixed in.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Iterable

from noctusai_lib.integrations.persistence.paging import iter_paged_rows

BILLING_STATUSES = ("active", "past_due", "grace")


@dataclass
class MrrResult:
    mrr_brl: Decimal = Decimal("0")
    counted: int = 0
    non_brl: dict[str, Decimal] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        mrr = self.mrr_brl.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return {
            "mrr": float(mrr),
            "arr": float((mrr * 12).quantize(Decimal("0.01"))),
            "counted_subscriptions": self.counted,
            "non_brl_mrr": {k: float(v.quantize(Decimal("0.01"))) for k, v in self.non_brl.items()},
        }


def monthly_amount(sub: dict[str, Any], plan_price_monthly: dict[str, Any]) -> tuple[Decimal, str]:
    """(monthly amount in major units, currency) for one subscription."""
    cents = sub.get("amount_cents")
    if cents is not None:
        amount = Decimal(int(cents)) / 100
        if sub.get("billing_cycle") == "yearly":
            amount = amount / 12
        return amount, str(sub.get("currency") or "BRL").upper()
    price = plan_price_monthly.get(str(sub.get("plan_id")), 0) or 0
    return Decimal(str(price)), "BRL"


def compute_mrr(subs: Iterable[dict[str, Any]], plan_price_monthly: dict[str, Any]) -> MrrResult:
    result = MrrResult()
    for sub in subs:
        if sub.get("status") not in BILLING_STATUSES:
            continue
        amount, currency = monthly_amount(sub, plan_price_monthly)
        result.counted += 1
        if currency == "BRL":
            result.mrr_brl += amount
        else:
            result.non_brl[currency] = result.non_brl.get(currency, Decimal("0")) + amount
    return result


def load_billing_subscriptions(db: Any) -> list[dict[str, Any]]:
    return list(
        iter_paged_rows(
            lambda start, end: db.table("subscriptions")
            .select("id, org_id, plan_id, status, amount_cents, currency, billing_cycle, started_at, canceled_at, created_at")
            .order("id")
            .range(start, end)
            .execute()
            .data,
            label="subscriptions (mrr)",
        )
    )


def load_plan_prices(db: Any) -> dict[str, Any]:
    rows = list(
        iter_paged_rows(
            lambda start, end: db.table("plans")
            .select("id, price_monthly")
            .order("id")
            .range(start, end)
            .execute()
            .data,
            label="plans (mrr)",
        )
    )
    return {str(p["id"]): p.get("price_monthly") or 0 for p in rows}


def current_mrr(db: Any) -> MrrResult:
    return compute_mrr(load_billing_subscriptions(db), load_plan_prices(db))


__all__ = [
    "BILLING_STATUSES",
    "MrrResult",
    "compute_mrr",
    "current_mrr",
    "load_billing_subscriptions",
    "load_plan_prices",
    "monthly_amount",
]
