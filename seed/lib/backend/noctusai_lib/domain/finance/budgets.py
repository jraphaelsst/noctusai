"""Budgets (E21): the planned amount per category and month, and the report that sets it against the actual.

* `fin_budgets` -- one row per `(org, category, month)`; months are first-of-month dates. Writes are admin-only (the router).
* **Actual = the DRE's own numbers.** `budget_report` reuses `dre._collect` (the same accrual-by-competence-month facts, the
  same per-store line routing), so the budget screen and the DRE can never disagree about what a month spent. Only the
  entry-sourced cells are used: refunds, chargebacks and gateway fees are DRE-level facts without a category, so they stay in
  the DRE and are NOT netted here (said on the report).
* Each category is its own row (no parent roll-up): a budget is set where the money is booked.
* `variance_cents = actual - budget`. Whether that is good depends on the side: more income than planned is good, more expense
  than planned is not -- `status` carries the verdict (`ok` | `over` | `under` | `no_budget`), the sign never has to be decoded.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any, Mapping, Optional

from noctusai_lib.integrations.persistence.table_reads import batched
from noctusai_lib.primitives.postgrest_errors import is_unique_violation

from ._common import Scope, first, iso, month_start, new_id, now_iso, to_date
from .categories import ensure_default_categories
from .dre import MAX_REPORT_MONTHS, _collect, _months, make_route
from .errors import conflict, invalid, not_found
from .types import CategoryDirection, DreLine

logger = logging.getLogger(__name__)

KB_DOC = "KB § PATTERNS/finance/dre-structure.md"
NOTES = (
    "O realizado usa a mesma base da DRE: competência do lançamento, sem cancelados e sem transferências entre contas.",
    "Estornos, chargebacks e tarifas de baixa são fatos da DRE sem categoria própria e não entram aqui.",
    "Cada categoria tem a sua linha; o orçamento de uma categoria-mãe não soma o das filhas.",
)


def _first_of_month(value: Any) -> date:
    d = to_date(value)
    if d is None:
        raise invalid("month", "Informe o mês.")
    return month_start(d)


def list_budgets(s: Scope, month_from: date, month_to: date) -> list[dict]:
    start, end = month_start(month_from), month_start(month_to)
    rows = s.rows("budgets", refine=lambda q: q.gte("month", iso(start)).lte("month", iso(end)))
    rows.sort(key=lambda r: (str(r["month"]), str(r["category_id"])))
    return rows


def upsert_budgets(s: Scope, items: list[Mapping[str, Any]]) -> list[dict]:
    """Set `(category, month) -> amount` for every item (idempotent). Every category must belong to this org (422 otherwise)."""
    seen: dict[tuple[str, str], int] = {}
    for item in items:
        key = (str(item["category_id"]), iso(_first_of_month(item["month"])))  # type: ignore[arg-type]
        seen[key] = int(item["amount_cents"])  # the last value for a repeated key wins
    cat_ids = {c for c, _ in seen}
    owned = {str(r["id"]): r for r in s.rows("categories")}
    for cid in cat_ids:
        cat = owned.get(cid)
        if cat is None:
            raise invalid("category_id", "Categoria não encontrada.", code="referencia_invalida")
        if cat["direction"] == CategoryDirection.TRANSFER.value:
            raise invalid("category_id", "Transferências entre contas não têm orçamento.", code="categoria_sem_orcamento")
    existing: dict[tuple[str, str], dict] = {}
    for chunk in batched(sorted(cat_ids)):  # `.in_` rides in the URL
        # postgrest-unbounded-ok: batched ids; `rows` pages past the 1 000-row cap
        for r in s.rows("budgets", refine=lambda q, c=chunk: q.in_("category_id", c)):
            existing[(str(r["category_id"]), str(r["month"])[:10])] = r
    now = now_iso()
    out: list[dict] = []
    for (cid, month), amount in sorted(seen.items()):
        current = existing.get((cid, month))
        try:
            if current is None:
                row = {"id": new_id(), "org_id": s.org_id, "category_id": cid, "month": month, "amount_cents": amount,
                       "created_at": now, "updated_at": now}
                out.append(first(s.tbl("budgets").insert(row).execute()) or row)
            elif int(current["amount_cents"]) != amount:
                patch = {"amount_cents": amount, "updated_at": now}
                s.tbl("budgets").update(patch).eq("org_id", s.org_id).eq("id", str(current["id"])).execute()
                out.append({**current, **patch})
            else:
                out.append(current)
        except Exception as exc:
            if is_unique_violation(exc):  # lost a race with a concurrent save of the same cell
                raise conflict("orcamento_duplicado", "Este orçamento acabou de ser alterado; recarregue e tente de novo.") from exc
            raise
    return out


def delete_budget(s: Scope, budget_id: Any) -> None:
    if s.find("budgets", budget_id) is None:
        raise not_found("Orçamento")
    s.tbl("budgets").delete().eq("org_id", s.org_id).eq("id", str(budget_id)).execute()


def _status(direction: str, budget: int, actual: int, has_budget: bool) -> str:
    if not has_budget:
        return "no_budget"
    if direction == CategoryDirection.EXPENSE.value:
        return "over" if actual > budget else "ok"
    return "under" if actual < budget else "ok"


def budget_report(s: Scope, month_from: date, month_to: date, *, regime_prefill: Optional[str] = None) -> dict:
    """Budget vs actual by category x month over whole months `[month_from, month_to]`."""
    start, end = month_start(month_from), month_start(month_to)
    if end < start:
        raise invalid("to", "A data final deve ser igual ou posterior à inicial.")
    months = _months(start, end)
    if len(months) > MAX_REPORT_MONTHS:
        raise invalid("to", f"O período pode ter no máximo {MAX_REPORT_MONTHS} meses.", code="periodo_grande_demais")

    ensure_default_categories(s)
    route, _row = make_route(s, regime_prefill)
    cats = route.cats
    facts = _collect(s, months, route)

    actual: dict[str, dict[str, int]] = {}
    for cell in facts.cells.values():
        if cell.source != "entries" or not cell.category_id:
            continue
        cat = cats.get(cell.category_id)
        if cat is None or cat["direction"] == CategoryDirection.TRANSFER.value:
            continue
        # An unclassified cell carries the entry's own sign (receivable +, payable -); a classified one is already
        # positive on its natural side. Either way the category's side makes the figure positive.
        flip = -1 if (cell.line == DreLine.UNCLASSIFIED.value and cat["direction"] == CategoryDirection.EXPENSE.value) else 1
        bucket = actual.setdefault(cell.category_id, {})
        for m, v in cell.months.items():
            bucket[m] = bucket.get(m, 0) + flip * int(v)

    budgets: dict[str, dict[str, int]] = {}
    for b in list_budgets(s, start, end):
        budgets.setdefault(str(b["category_id"]), {})[str(b["month"])[:7]] = int(b["amount_cents"])

    def path(cat: Mapping[str, Any]) -> str:
        names, cur, seen = [], cat, set()
        while cur is not None and str(cur["id"]) not in seen:
            seen.add(str(cur["id"]))
            names.append(str(cur["name"]))
            cur = cats.get(str(cur["parent_id"])) if cur.get("parent_id") else None
        return " / ".join(reversed(names))

    rows: list[dict] = []
    for cid in sorted(set(actual) | set(budgets), key=lambda c: (cats[c]["direction"], path(cats[c]).lower())):
        cat = cats[cid]
        cells = {}
        total = {"budget_cents": 0, "actual_cents": 0}
        for m in months:
            has = m in budgets.get(cid, {})
            b, a = budgets.get(cid, {}).get(m, 0), actual.get(cid, {}).get(m, 0)
            cells[m] = {"budget_cents": b, "actual_cents": a, "variance_cents": a - b, "status": _status(cat["direction"], b, a, has)}
            total["budget_cents"] += b
            total["actual_cents"] += a
        has_any = bool(budgets.get(cid))
        rows.append({
            "category_id": cid, "name": cat["name"], "path": path(cat), "direction": cat["direction"], "months": cells,
            "total": {**total, "variance_cents": total["actual_cents"] - total["budget_cents"],
                      "status": _status(cat["direction"], total["budget_cents"], total["actual_cents"], has_any)},
        })

    def side(direction: str) -> dict:
        mine = [r for r in rows if r["direction"] == direction]
        by_month = {m: {"budget_cents": sum(r["months"][m]["budget_cents"] for r in mine),
                        "actual_cents": sum(r["months"][m]["actual_cents"] for r in mine)} for m in months}
        for v in by_month.values():
            v["variance_cents"] = v["actual_cents"] - v["budget_cents"]
        tb, ta = sum(v["budget_cents"] for v in by_month.values()), sum(v["actual_cents"] for v in by_month.values())
        return {"by_month": by_month, "budget_cents": tb, "actual_cents": ta, "variance_cents": ta - tb}

    income, expense = side(CategoryDirection.INCOME.value), side(CategoryDirection.EXPENSE.value)
    warnings: list[dict[str, Any]] = []
    if not budgets:
        warnings.append({"code": "sem_orcamento", "severity": "info",
                         "message": "Nenhum orçamento foi definido para este período; só o realizado é mostrado.",
                         "action": "Defina o valor planejado por categoria e mês."})
    return {
        "from": iso(start),
        "to": iso(end),
        "months": months,
        "rows": rows,
        "income": income,
        "expense": expense,
        "result": {"budget_cents": income["budget_cents"] - expense["budget_cents"],
                   "actual_cents": income["actual_cents"] - expense["actual_cents"]},
        "warnings": warnings,
        "notes": list(NOTES),
        "source": KB_DOC,
    }


__all__ = ["budget_report", "delete_budget", "list_budgets", "upsert_budgets"]
