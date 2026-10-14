"""Reports -- cash flow (realized + projected), DRE by competence, receivables aging.

All three read through the org `Scope`, paging past PostgREST's 1 000-row cap. They
are READ-ONLY and derive everything from entries + ledger (no stored aggregates).
NOC-REMEDIATE[finance-report-sql-aggregates]: aggregation happens in Python after a
bounded paged read; an org with millions of ledger rows wants DB-side aggregates (an
RPC per report) -- move there when a real org crosses ~200k rows. -- 2026-10-13
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any, Optional

from ._common import Scope, add_months, iso, month_start, to_date, today
from .entries import mask_doc
from .errors import invalid
from .types import EntryDirection, EntryStatus, LedgerDirection, LedgerOrigin

MAX_REPORT_MONTHS = 60
_OPEN = (EntryStatus.OPEN.value, EntryStatus.PARTIAL.value)
AGING_BUCKETS: tuple[tuple[str, int, Optional[int]], ...] = (
    ("d1_30", 1, 30),
    ("d31_60", 31, 60),
    ("d61_90", 61, 90),
    ("d90_plus", 91, None),
)


def _month_key(value: Any) -> str:
    return to_date(value).strftime("%Y-%m")


def _months(start: date, end: date) -> list[str]:
    out, cur = [], month_start(start)
    last = month_start(end)
    while cur <= last:
        out.append(cur.strftime("%Y-%m"))
        cur = add_months(cur, 1)
    return out


def _check_range(date_from: date, date_to: date) -> None:
    if date_to < date_from:
        raise invalid("to", "A data final deve ser igual ou posterior à inicial.")
    if len(_months(date_from, date_to)) > MAX_REPORT_MONTHS:
        raise invalid("to", f"O período pode ter no máximo {MAX_REPORT_MONTHS} meses.", code="periodo_grande_demais")


# ─── cash flow ───────────────────────────────────────────────────────────────


def cashflow(s: Scope, date_from: date, date_to: date, *, account_id: Optional[Any] = None) -> dict:
    """Realized (ledger) + projected (open entries by `due_date`), bucketed by month."""
    _check_range(date_from, date_to)
    if account_id:
        s.require_owned("accounts", account_id, what="Conta", field="account_id")
    acc = str(account_id) if account_id else None

    def ledger_filter(query):
        return query.eq("account_id", acc) if acc else query

    # Opening balance: account openings (dated on/before the start) + ledger strictly before the period.
    accounts = [a for a in s.rows("accounts") if acc is None or str(a["id"]) == acc]
    opening = sum(
        int(a.get("opening_balance_cents") or 0)
        for a in accounts
        if to_date(a.get("opening_date")) is None or to_date(a.get("opening_date")) < date_from
    )
    before = s.rows("ledger", refine=lambda q: ledger_filter(q).lt("occurred_on", date_from.isoformat()))
    opening += sum(
        int(r["amount_cents"]) if r["direction"] == LedgerDirection.IN.value else -int(r["amount_cents"]) for r in before
    )

    buckets = {m: {"month": m, "realized_in_cents": 0, "realized_out_cents": 0,
                   "projected_in_cents": 0, "projected_out_cents": 0} for m in _months(date_from, date_to)}
    for r in s.rows(
        "ledger",
        refine=lambda q: ledger_filter(q).gte("occurred_on", date_from.isoformat()).lte("occurred_on", date_to.isoformat()),
    ):
        if acc is None and r["origin"] == LedgerOrigin.TRANSFER.value:
            continue  # between the org's own accounts: nets to zero in the aggregate view
        key = "realized_in_cents" if r["direction"] == LedgerDirection.IN.value else "realized_out_cents"
        buckets[_month_key(r["occurred_on"])][key] += int(r["amount_cents"])

    for e in s.rows(
        "entries",
        # postgrest-unbounded-ok: two literal enum values
        refine=lambda q: q.in_("status", list(_OPEN)).gte("due_date", date_from.isoformat()).lte("due_date", date_to.isoformat()),
    ):
        if acc and e.get("expected_account_id") and str(e["expected_account_id"]) != acc:
            continue
        remaining = int(e["amount_cents"]) - int(e.get("settled_cents") or 0)
        key = "projected_in_cents" if e["direction"] == EntryDirection.RECEIVABLE.value else "projected_out_cents"
        buckets[_month_key(e["due_date"])][key] += remaining

    rows = list(buckets.values())
    totals = {k: sum(b[k] for b in rows) for k in ("realized_in_cents", "realized_out_cents", "projected_in_cents", "projected_out_cents")}
    realized_net = totals["realized_in_cents"] - totals["realized_out_cents"]
    projected_net = totals["projected_in_cents"] - totals["projected_out_cents"]
    return {
        "from": date_from.isoformat(),
        "to": date_to.isoformat(),
        "account_id": acc,
        "opening_balance_cents": opening,
        "buckets": rows,
        "totals": totals,
        "closing_realized_balance_cents": opening + realized_net,
        "closing_projected_balance_cents": opening + realized_net + projected_net,
    }


# ─── DRE ─────────────────────────────────────────────────────────────────────


def dre(s: Scope, month_from: date, month_to: date) -> dict:
    """Income statement by `competence_month` x category tree (accrual basis: entry amounts, not cash)."""
    start, end = month_start(month_from), month_start(month_to)
    _check_range(start, end)
    months = _months(start, end)
    cats = {str(c["id"]): c for c in s.rows("categories")}
    entries = s.rows(
        "entries",
        refine=lambda q: q.neq("status", EntryStatus.CANCELLED.value)
        .gte("competence_month", iso(start)).lte("competence_month", iso(end)),
    )

    def zeros() -> dict[str, int]:
        return {m: 0 for m in months}

    own: dict[str, dict[str, dict[str, int]]] = defaultdict(lambda: {"revenue": zeros(), "expense": zeros()})
    uncategorized = {"revenue": zeros(), "expense": zeros()}
    for e in entries:
        side = "revenue" if e["direction"] == EntryDirection.RECEIVABLE.value else "expense"
        bucket = own[str(e["category_id"])][side] if e.get("category_id") and str(e["category_id"]) in cats else uncategorized[side]
        bucket[_month_key(e["competence_month"])] += int(e["amount_cents"])

    children: dict[Optional[str], list[str]] = defaultdict(list)
    for cid, c in cats.items():
        children[str(c["parent_id"]) if c.get("parent_id") else None].append(cid)

    def roll(cid: str) -> dict[str, dict[str, int]]:
        total = {side: dict(vals) for side, vals in own[cid].items()} if cid in own else {"revenue": zeros(), "expense": zeros()}
        for child in children.get(cid, []):
            sub = roll(child)
            for side in total:
                for m in months:
                    total[side][m] += sub[side][m]
        rolled[cid] = total
        return total

    rolled: dict[str, dict[str, dict[str, int]]] = {}
    for root in children.get(None, []):
        roll(root)

    nodes = []
    for cid, c in sorted(cats.items(), key=lambda kv: (str(kv[1].get("parent_id") or ""), str(kv[1]["name"]).lower())):
        tot = rolled.get(cid)
        if tot is None:
            continue
        revenue, expense = sum(tot["revenue"].values()), sum(tot["expense"].values())
        if revenue == 0 and expense == 0:
            continue
        nodes.append({
            "category_id": cid,
            "parent_id": str(c["parent_id"]) if c.get("parent_id") else None,
            "name": c["name"],
            "direction": c["direction"],
            "revenue_cents": revenue,
            "expense_cents": expense,
            "by_month": {m: {"revenue_cents": tot["revenue"][m], "expense_cents": tot["expense"][m]} for m in months},
        })

    rev_by_m, exp_by_m = zeros(), zeros()
    for cid in own:
        for m in months:
            rev_by_m[m] += own[cid]["revenue"][m]
            exp_by_m[m] += own[cid]["expense"][m]
    for m in months:
        rev_by_m[m] += uncategorized["revenue"][m]
        exp_by_m[m] += uncategorized["expense"][m]
    revenue_total, expense_total = sum(rev_by_m.values()), sum(exp_by_m.values())
    return {
        "from": iso(start),
        "to": iso(end),
        "months": months,
        "categories": nodes,
        "uncategorized": {
            "revenue_cents": sum(uncategorized["revenue"].values()),
            "expense_cents": sum(uncategorized["expense"].values()),
        },
        "totals": {
            "revenue_cents": revenue_total,
            "expense_cents": expense_total,
            "result_cents": revenue_total - expense_total,
            "by_month": {
                m: {"revenue_cents": rev_by_m[m], "expense_cents": exp_by_m[m], "result_cents": rev_by_m[m] - exp_by_m[m]}
                for m in months
            },
        },
    }


# ─── aging ───────────────────────────────────────────────────────────────────


def _bucket_of(days: int) -> str:
    for name, low, high in AGING_BUCKETS:
        if days >= low and (high is None or days <= high):
            return name
    return AGING_BUCKETS[0][0]


def aging(s: Scope, *, as_of: Optional[date] = None, is_admin: bool = False) -> dict:
    """Overdue receivables grouped by counterparty and age bucket (remaining amount, not face value)."""
    on = as_of or today()
    rows = s.rows(
        "entries",
        eq={"direction": EntryDirection.RECEIVABLE.value},
        # postgrest-unbounded-ok: two literal enum values
        refine=lambda q: q.in_("status", list(_OPEN)).lt("due_date", on.isoformat()),
    )
    groups: dict[str, dict] = {}
    for e in rows:
        remaining = int(e["amount_cents"]) - int(e.get("settled_cents") or 0)
        if remaining <= 0:
            continue
        days = (on - to_date(e["due_date"])).days
        key = e.get("counterparty_doc") or e.get("counterparty_name") or "-"
        g = groups.setdefault(key, {
            "counterparty_name": e.get("counterparty_name"),
            "counterparty_doc": e.get("counterparty_doc") if is_admin else mask_doc(e.get("counterparty_doc")),
            "buckets": {name: 0 for name, _, _ in AGING_BUCKETS},
            "total_cents": 0,
            "entries": 0,
            "oldest_due_date": e["due_date"],
        })
        g["buckets"][_bucket_of(days)] += remaining
        g["total_cents"] += remaining
        g["entries"] += 1
        if str(e["due_date"]) < str(g["oldest_due_date"]):
            g["oldest_due_date"] = e["due_date"]
    items = sorted(groups.values(), key=lambda g: (-g["total_cents"], str(g["counterparty_name"])))
    totals = {name: sum(g["buckets"][name] for g in items) for name, _, _ in AGING_BUCKETS}
    return {
        "as_of": on.isoformat(),
        "counterparties": items,
        "totals": {"buckets": totals, "total_cents": sum(g["total_cents"] for g in items)},
    }


__all__ = ["AGING_BUCKETS", "MAX_REPORT_MONTHS", "aging", "cashflow", "dre"]
