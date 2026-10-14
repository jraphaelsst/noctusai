"""igig finance -> finance organ importer (roadmap `erp-seed-2026-10` E10, `NOC-REMEDIATE[igig-finance-cutover]`).

Source: `igig.fatura` + `igig.fatura_item` (migration 011, NUMERIC reais) + `igig.cliente` (the counterparty
name). Destination: `fin_entries` (+ `fin_settlements` for paid invoices), integer cents, same org.

igig keeps NO cost ledger (`custo_hora*` are hourly cost RATES for the calculator, not money paid), so there is
nothing to import for "custos": expenses start in the organ. Recorded here so the gap is a decision, not an omission.

Mapping (one entry per fatura -- `valor_total` is the signed sum of its lines, `desconto` subtracts):

| igig                                   | organ                                                              |
|----------------------------------------|--------------------------------------------------------------------|
| fatura                                 | receivable entry, `source='import'`, `source_ref='igig:fatura:<id>'` |
| fatura.competencia ('YYYY-MM')         | `competence_month` (first day) -- the DRE month                    |
| fatura.vencimento (else month end)     | `due_date`                                                         |
| fatura.valor_total                     | `amount_cents = to_cents(...)` (the one seed half-even policy)    |
| status aberta / enviada / vencida      | `open` (`overdue` is computed on read, never stored)               |
| status paga                            | + one full `payment` settlement (`external_ref='igig:fatura:<id>:pago'`) on `pago_em` |
| status cancelada                       | entry cancelled (kept for audit; reconciles like any other)       |
| cliente.nome                           | `counterparty_name`                                                |
| any `mensalidade` line                 | category `Mensalidades` (DRE: gross_revenue)                       |
| otherwise (excedente / avulso / ...)   | category `Serviços` (DRE: gross_revenue)                           |

A fatura with `valor_total = 0` has nothing to book (the organ refuses a 0-amount entry): it is listed under
`skipped` and contributes 0 to both sides of the reconciliation. A negative total, an unparseable amount, a bad
`competencia`, or a total that disagrees with its own lines is an `issue` -- the reconciliation refuses.
"""
from __future__ import annotations

import calendar
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Iterable, Mapping, Optional

from noctusai_lib.integrations.persistence.table_reads import paged_rows
from noctusai_lib.primitives.money import cents_to_decimal, to_cents, to_decimal

from .._common import Scope, iso, to_date
from ..accounts import create_account
from ..categories import DEFAULT_CATEGORIES, find_category_by_hint
from ..entries import cancel_entry, create_entry, find_by_source
from ..settlements import settle_entry
from ..types import AccountKind, CategoryDirection, DreLine, EntryDirection, EntrySource, EntryStatus

logger = logging.getLogger(__name__)

SOURCE = EntrySource.IMPORT.value
REF_PREFIX = "igig:fatura:"
PAID_REF_SUFFIX = ":pago"
ACCOUNT_NAME = "Importado do igig"
DIRECTION = EntryDirection.RECEIVABLE.value

#: igig `fatura_item.tipo` -> the organ's default category NAME (income side). The DRE line is NOT stored here: it
#: is looked up from `DEFAULT_CATEGORIES` (`dre_line_for`) so the owner's table stays the single mapping.
CATEGORY_MENSALIDADE = "Mensalidades"
CATEGORY_SERVICOS = "Serviços"
ITEM_TYPE_CATEGORY: Mapping[str, str] = {
    "mensalidade": CATEGORY_MENSALIDADE,
    "excedente": CATEGORY_SERVICOS,
    "avulso": CATEGORY_SERVICOS,
    "desconto": CATEGORY_SERVICOS,
}
_OPEN_STATUSES = ("aberta", "enviada", "vencida")


def dre_line_for(category_name: str) -> Optional[DreLine]:
    """The DRE line the organ's default tree gives `category_name` (dre-structure.md §2a)."""
    for _group, _direction, children in DEFAULT_CATEGORIES:
        for child in children:
            if child.name == category_name:
                return child.dre_line
    return None


def category_for(item_types: Iterable[str]) -> str:
    """`Mensalidades` when the invoice carries a retainer line, else `Serviços`."""
    return CATEGORY_MENSALIDADE if "mensalidade" in set(item_types) else CATEGORY_SERVICOS


# ─── plan ────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PlannedEntry:
    source_ref: str
    fatura_id: str
    competence: str  # 'YYYY-MM'
    amount_cents: int
    amount_reais: Decimal
    due_date: date
    competence_month: date
    description: str
    counterparty_name: Optional[str]
    category_name: str
    dre_line: Optional[str]
    igig_status: str
    cancelled: bool
    settle_on: Optional[date]  # set when the fatura is paid

    @property
    def paid(self) -> bool:
        return self.settle_on is not None

    @property
    def settle_ref(self) -> str:
        return f"{self.source_ref}{PAID_REF_SUFFIX}"


@dataclass
class ImportPlan:
    org_id: str
    entries: list[PlannedEntry] = field(default_factory=list)
    skipped: list[dict] = field(default_factory=list)
    issues: list[dict] = field(default_factory=list)


def _issue(fatura: Mapping[str, Any], code: str, detail: str) -> dict:
    return {"fatura_id": str(fatura.get("id")), "competencia": fatura.get("competencia"), "code": code, "detail": detail}


def _parse_competence(raw: Any) -> Optional[date]:
    try:
        return datetime.strptime(str(raw), "%Y-%m").date().replace(day=1)
    except ValueError:
        return None


def _month_end(first_day: date) -> date:
    return first_day.replace(day=calendar.monthrange(first_day.year, first_day.month)[1])


def _signed_line_reais(item: Mapping[str, Any]) -> Decimal:
    """Mirror of igig's `valor_da_linha_fatura` on Decimal: `desconto` subtracts."""
    value = Decimal(int(item.get("quantidade") or 0)) * to_decimal(item.get("valor_unit") or 0)
    return -value if item.get("tipo") == "desconto" else value


def plan_import(
    org_id: str,
    faturas: Iterable[Mapping[str, Any]],
    itens: Iterable[Mapping[str, Any]],
    clientes: Iterable[Mapping[str, Any]],
) -> ImportPlan:
    """Pure mapping: igig rows of ONE org -> `ImportPlan`. No IO, deterministic order (competencia, id)."""
    plan = ImportPlan(org_id=str(org_id))
    lines_by_fatura: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for item in itens:
        lines_by_fatura[str(item.get("fatura_id"))].append(item)
    names = {str(c["id"]): (c.get("nome") or None) for c in clientes}

    for f in sorted(faturas, key=lambda r: (str(r.get("competencia")), str(r.get("id")))):
        if str(f.get("org_id")) != plan.org_id:
            plan.issues.append(_issue(f, "org_divergente", "fatura de outra org no conjunto de entrada."))
            continue
        month = _parse_competence(f.get("competencia"))
        if month is None:
            plan.issues.append(_issue(f, "competencia_invalida", f"competencia {f.get('competencia')!r} nao e AAAA-MM."))
            continue
        try:
            total = to_decimal(f.get("valor_total") if f.get("valor_total") is not None else 0)
            cents = to_cents(total)
        except ValueError as exc:
            plan.issues.append(_issue(f, "valor_invalido", str(exc)))
            continue
        status = str(f.get("status") or "")
        if status not in (*_OPEN_STATUSES, "paga", "cancelada"):
            plan.issues.append(_issue(f, "status_desconhecido", f"status {status!r} sem mapeamento."))
            continue
        lines = lines_by_fatura.get(str(f["id"]), [])
        if lines:
            lines_total = sum((_signed_line_reais(i) for i in lines), Decimal(0))
            if to_cents(lines_total) != cents:
                plan.issues.append(_issue(f, "linhas_divergentes", f"valor_total {total} != soma das linhas {lines_total}."))
                continue
        if cents < 0:
            plan.issues.append(_issue(f, "valor_negativo", f"valor_total {total} e negativo; o organ nao aceita lancamento <= 0."))
            continue
        if cents == 0:
            plan.skipped.append({"fatura_id": str(f["id"]), "competencia": f.get("competencia"), "reason": "valor_zero"})
            continue
        due = to_date(f.get("vencimento")) or _month_end(month)
        category = category_for(i.get("tipo") for i in lines)
        paid_on: Optional[date] = None
        if status == "paga":
            paid_on = to_date(f.get("pago_em")) or due
        ref = f"{REF_PREFIX}{f['id']}"
        client_name = names.get(str(f.get("cliente_id")))
        plan.entries.append(
            PlannedEntry(
                source_ref=ref,
                fatura_id=str(f["id"]),
                competence=str(f["competencia"]),
                amount_cents=cents,
                amount_reais=cents_to_decimal(cents),
                due_date=due,
                competence_month=month,
                description=f"Fatura {f['competencia']}" + (f" - {client_name}" if client_name else ""),
                counterparty_name=client_name,
                category_name=category,
                dre_line=(dre_line_for(category).value if dre_line_for(category) else None),
                igig_status=status,
                cancelled=status == "cancelada",
                settle_on=paid_on,
            )
        )
    return plan


# ─── reconciliation ──────────────────────────────────────────────────────────


@dataclass
class Reconciliation:
    """Totals per org x month x direction, BEFORE (igig NUMERIC) and AFTER (organ cents). `ok` only when all agree to the cent."""

    org_id: str
    rows: list[dict] = field(default_factory=list)
    mismatches: list[dict] = field(default_factory=list)
    issues: list[dict] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.mismatches and not self.issues

    def as_dict(self) -> dict:
        return {"ok": self.ok, "org_id": self.org_id, "rows": self.rows, "mismatches": self.mismatches, "issues": self.issues}


def reconcile(plan: ImportPlan, faturas: Iterable[Mapping[str, Any]]) -> Reconciliation:
    """Compare the NUMERIC totals of the source faturas with the cents the plan would book, per month.

    `before` is the exact `Decimal` sum of `valor_total` (every status); `after` is the sum of planned
    `amount_cents`. They must be equal to the cent -- a sub-cent source total, an unimportable fatura or a
    fatura the plan dropped all surface as a mismatch listing the fatura ids involved."""
    before: dict[str, Decimal] = defaultdict(Decimal)
    ids_before: dict[str, list[str]] = defaultdict(list)
    for f in faturas:
        month = str(f.get("competencia"))
        try:
            before[month] += to_decimal(f.get("valor_total") if f.get("valor_total") is not None else 0)
        except ValueError:
            before[month] += Decimal(0)  # reported through plan.issues
        ids_before[month].append(str(f.get("id")))
    after_cents: dict[str, int] = defaultdict(int)
    ids_after: dict[str, set[str]] = defaultdict(set)
    for e in plan.entries:
        after_cents[e.competence] += e.amount_cents
        ids_after[e.competence].add(e.fatura_id)

    rec = Reconciliation(org_id=plan.org_id, issues=list(plan.issues))
    for month in sorted(set(before) | set(after_cents)):
        b = before.get(month, Decimal(0))
        a = after_cents.get(month, 0)
        match = (b * 100) == Decimal(a)
        row = {
            "org_id": plan.org_id,
            "competencia": month,
            "direction": DIRECTION,
            "before_numeric": str(b),
            "after_cents": a,
            "after_reais": str(cents_to_decimal(a)),
            "match": match,
        }
        rec.rows.append(row)
        if not match:
            missing = sorted(set(ids_before.get(month, [])) - ids_after.get(month, set()))
            rec.mismatches.append({**row, "diff_cents": str((b * 100) - Decimal(a)), "faturas_not_booked": missing})
    return rec


# ─── read ────────────────────────────────────────────────────────────────────


def read_igig(igig_db: Any, org_id: str) -> tuple[list[dict], list[dict], list[dict]]:
    """`(faturas, fatura_itens, clientes)` of one org from a client bound to the `igig` schema. Paged (1 000-row cap)."""
    return (
        paged_rows(igig_db, "fatura", org_id),
        paged_rows(igig_db, "fatura_item", org_id),
        paged_rows(igig_db, "cliente", org_id),
    )


# ─── write ───────────────────────────────────────────────────────────────────


def _ensure_account(s: Scope) -> dict:
    for row in s.rows("accounts", eq={"name": ACCOUNT_NAME}):
        return row
    return create_account(s, {"kind": AccountKind.CHECKING.value, "name": ACCOUNT_NAME})


def apply_plan(s: Scope, plan: ImportPlan) -> dict:
    """Write `plan` through the organ's own services. Idempotent: an entry whose `(source, source_ref)` exists is not
    recreated, and a settlement replays by its `external_ref`. Refuses (writes nothing) when the plan carries issues."""
    if plan.issues:
        raise ValueError(f"plan has {len(plan.issues)} issue(s); reconcile first, nothing written")
    if str(s.org_id) != plan.org_id:
        raise ValueError("scope org differs from plan org")
    result = {"created": 0, "existing": 0, "settled": 0, "cancelled": 0}
    account_id: Optional[str] = None
    categories: dict[str, Optional[str]] = {}
    for e in plan.entries:
        if e.category_name not in categories:
            categories[e.category_name] = find_category_by_hint(s, e.category_name, CategoryDirection.INCOME)
        entry = find_by_source(s, SOURCE, e.source_ref)
        if entry is None:
            entry = create_entry(
                s,
                {
                    "direction": DIRECTION,
                    "description": e.description,
                    "amount_cents": e.amount_cents,
                    "due_date": iso(e.due_date),
                    "competence_month": iso(e.competence_month),
                    "counterparty_name": e.counterparty_name,
                    "category_id": categories[e.category_name],
                    "source": SOURCE,
                    "source_ref": e.source_ref,
                    "notes": f"Importado do igig (status {e.igig_status}).",
                },
            )[0]
            result["created"] += 1
        else:
            result["existing"] += 1
        if e.paid and entry["status"] != EntryStatus.PAID.value:
            if account_id is None:
                account_id = str(_ensure_account(s)["id"])
            settle_entry(
                s,
                entry["id"],
                {"account_id": account_id, "amount_cents": e.amount_cents, "settled_on": iso(e.settle_on), "external_ref": e.settle_ref},
            )
            result["settled"] += 1
        if e.cancelled and entry["status"] != EntryStatus.CANCELLED.value:
            cancel_entry(s, entry["id"])
            result["cancelled"] += 1
    return result


def written_totals(s: Scope) -> dict[str, int]:
    """Cents actually stored per competence month for igig-sourced entries (the post-write half of the reconciliation)."""
    totals: dict[str, int] = defaultdict(int)
    for row in s.rows("entries", eq={"source": SOURCE}):
        ref = str(row.get("source_ref") or "")
        if ref.startswith(REF_PREFIX):
            totals[str(row["competence_month"])[:7]] += int(row["amount_cents"])
    return dict(totals)


__all__ = [
    "ACCOUNT_NAME", "ITEM_TYPE_CATEGORY", "ImportPlan", "PlannedEntry", "REF_PREFIX", "Reconciliation",
    "apply_plan", "category_for", "dre_line_for", "plan_import", "read_igig", "reconcile", "written_totals",
]
