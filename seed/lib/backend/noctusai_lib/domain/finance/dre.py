"""The structured DRE (CONTRACT §10 / §10.5; `KB § PATTERNS/finance/dre-structure.md`).

Replaces the old category-tree statement. Three layers, kept apart on purpose:

1. **Facts** -- every money fact that touches the result, month-stamped and routed to a `DreLine`:
   entries (accrual, by `competence_month`), refund/chargeback settlements and fees (by the settlement's own
   `settled_on` month -- §10.2), gateway-sync fee rows. A category's `dre_line` is DATA (per store); the
   provisional choices live in `fin_dre_settings` (`dre_settings.py`).
2. **Statement** -- the lines in NBC TG 1002 §5.1 order plus subtotals that are COMPUTED here, never stored.
3. **Guidance** -- plain-language help per line, `warnings[]`, `accountant_alerts[]` (D47): part of the payload.

Rules worth knowing:

* Transfers (`direction='transfer'` categories) never enter the DRE.
* Money whose category has no line lands in the `unclassified` block with a warning and is NOT part of
  `net_result` (it is reported as `unclassified.net_cents`, never dropped).
* DAS routing by regime (§10.5.2): Simples -> `deductions` (whole), or with `das_split_irpj_csll` the configured
  IRPJ/CSLL share goes to `income_taxes`; MEI -> `administrative_expenses`; Presumido/unknown -> the category's own
  line (the revenue taxes are `deductions`, IRPJ/CSLL their own category).
* Installment interest (`source_ref` ending `:interest`) always routes through `installment_interest_line`.
* The managerial view regroups the SAME facts (variable vs fixed) and reconciles to `net_result`.

NOC-REMEDIATE[finance-fee-kind-from-gateway]: gateway-sync and settlement data carry NO field telling an
antecipacao fee or a chargeback fee apart from the MDR, so every fee lands on `gateway_fee_line`. The settings
`anticipation_fee_line` / `chargeback_fee_line` and `classify_fee()` are the seam: when the gateway adapter exposes
the fee kind (Asaas `anticipationFee`/chargeback fee, Stripe `fee_details`), `classify_fee` is the ONE place to
read it. -- 2026-10-14
"""
from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Iterable, Mapping, Optional

from noctusai_lib.integrations.persistence.table_reads import batched

from . import dre_settings as settings_svc
from ._common import Scope, add_months, iso, month_start, to_date
from .categories import default_behavior, ensure_default_categories
from .dre_help import LINE_HELP, STATEMENT_ORDER, SUBTOTAL_HELP, TITLE_DEFAULT, TITLE_MEI
from .errors import invalid
from .types import CategoryBehavior, CategoryDirection, DreLine, EntryDirection, EntryStatus, LedgerDirection, LedgerOrigin, SettlementKind, TaxRegime

logger = logging.getLogger(__name__)

#: Above this trailing-12-month gross revenue the store leaves NBC TG 1002 (microentidade) -> NBC TG 1001 (R$ 4.8 M).
MICRO_ENTITY_LIMIT_CENTS = 480_000_000
INTEREST_SUFFIX = ":interest"
CHARGEBACK_PREFIX = "chargeback:"
GATEWAY_FEE_DESCRIPTION_PREFIX = "Tarifa do gateway:"
INTEREST_CATEGORY_NAME = "Juros de parcelamento"
VIEWS = ("statement", "managerial")
MAX_REPORT_MONTHS = 60

_REVENUE_SIDE = (DreLine.GROSS_REVENUE.value, DreLine.FINANCIAL_REVENUE.value, DreLine.OTHER_OPERATING.value)
_UNCLASSIFIED = DreLine.UNCLASSIFIED.value
_REAL_LINES = tuple(v.value for v in DreLine if v is not DreLine.UNCLASSIFIED)
_RECEIVABLE = EntryDirection.RECEIVABLE.value
_PAYABLE = EntryDirection.PAYABLE.value


def _natural_direction(line: str) -> str:
    """The entry direction that ADDS to `line`'s value (the opposite direction is a contra)."""
    return _RECEIVABLE if line in _REVENUE_SIDE else _PAYABLE


def _effect_sign(line: str) -> int:
    """How a line's value moves `net_result`: revenue-side lines add, the rest subtract."""
    return 1 if line in _REVENUE_SIDE else -1


# ─── fee classification seam ────────────────────────────────────────────────


def classify_fee(row: Optional[Mapping[str, Any]] = None) -> str:
    """Which fee a settlement fee / gateway fee row is: `gateway` | `anticipation` | `chargeback`.

    Today EVERY fee is `gateway` (see the module NOC-REMEDIATE): the data does not say. This is the single seam."""
    return "gateway"


_FEE_SETTING = {
    "gateway": "gateway_fee_line",
    "anticipation": "anticipation_fee_line",
    "chargeback": "chargeback_fee_line",
}
_FEE_NAME = {
    "gateway": "Taxas do gateway/cartão (MDR)",
    "anticipation": "Antecipação de recebíveis",
    "chargeback": "Tarifa de chargeback",
}


# ─── fact accumulation ──────────────────────────────────────────────────────


@dataclass
class _Cell:
    line: str
    key: str
    name: str
    behavior: str
    category_id: Optional[str]
    source: str
    months: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    @property
    def total(self) -> int:
        return sum(self.months.values())


class _Facts:
    def __init__(self) -> None:
        self.cells: dict[tuple[str, str], _Cell] = {}
        self.unclassified_categories: dict[str, int] = {}  # name -> cents of effect (absolute)
        self.uncategorized_revenue_cents = 0
        self.uncategorized_expense_cents = 0
        self.has_chargeback = False

    def add(self, line: str, key: str, name: str, month: str, value: int, *, behavior: Optional[str] = None,
            category_id: Optional[str] = None, source: str = "entries") -> None:
        cell = self.cells.get((line, key))
        if cell is None:
            cell = self.cells[(line, key)] = _Cell(
                line=line, key=key, name=name, behavior=behavior or default_behavior(line).value,
                category_id=category_id, source=source,
            )
        cell.months[month] += value

    def of_line(self, line: str) -> list[_Cell]:
        return sorted((c for c in self.cells.values() if c.line == line), key=lambda c: (-abs(c.total), c.name.lower()))


def _month_key(value: Any) -> str:
    return to_date(value).strftime("%Y-%m")  # type: ignore[union-attr]


def _months(start: date, end: date) -> list[str]:
    out, cur = [], month_start(start)
    last = month_start(end)
    while cur <= last:
        out.append(cur.strftime("%Y-%m"))
        cur = add_months(cur, 1)
    return out


def _inherited(cat: Optional[Mapping[str, Any]], cats: Mapping[str, Mapping[str, Any]], attr: str) -> Optional[str]:
    """`attr` of the category or its nearest ancestor that sets it (cycle-safe)."""
    seen: set[str] = set()
    cur = cat
    while cur is not None and str(cur["id"]) not in seen:
        seen.add(str(cur["id"]))
        if cur.get(attr) is not None:
            return str(cur[attr])
        parent = cur.get("parent_id")
        cur = cats.get(str(parent)) if parent else None
    return None


def _fetch_by_ids(s: Scope, table: str, ids: Iterable[str]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for chunk in batched(sorted(set(ids))):
        # postgrest-unbounded-ok: batched ids (`.in_` rides in the URL)
        for row in s.rows(table, refine=lambda q, c=chunk: q.in_("id", c)):
            out[str(row["id"])] = row
    return out


class _Route:
    """Per-request routing context: categories + the store's settings."""

    def __init__(self, cats: dict[str, dict], cfg: Mapping[str, Any]) -> None:
        self.cats = cats
        self.regime: str = cfg["tax_regime"]
        self.split = bool(cfg["das_split_irpj_csll"])
        self.share_bps = int(cfg["das_irpj_csll_share_bps"] or 0)
        self.cfg = cfg

    def entry_line(self, entry: Mapping[str, Any]) -> tuple[str, Optional[dict], str]:
        """`(line, category, special)` for an entry; `special` = 'interest' | 'das' | ''."""
        cat = self.cats.get(str(entry["category_id"])) if entry.get("category_id") else None
        if entry["direction"] == _RECEIVABLE and str(entry.get("source_ref") or "").endswith(INTEREST_SUFFIX):
            return str(self.cfg["installment_interest_line"]), cat, "interest"
        if cat is not None and cat.get("is_das") and entry["direction"] == _PAYABLE:
            if self.regime == TaxRegime.MEI.value:
                return DreLine.ADMINISTRATIVE_EXPENSES.value, cat, "das"
            if self.regime == TaxRegime.SIMPLES.value:
                return DreLine.DEDUCTIONS.value, cat, "das"
        line = _inherited(cat, self.cats, "dre_line")
        return (line if line in _REAL_LINES else _UNCLASSIFIED), cat, ""

    def behavior(self, cat: Optional[Mapping[str, Any]], line: str) -> str:
        return _inherited(cat, self.cats, "behavior") or default_behavior(line).value


def make_route(s: Scope, regime_prefill: Optional[str] = None) -> tuple[_Route, Optional[dict]]:
    """The per-request routing context (categories + the store's settings) every report needs, and the raw settings row.

    Seeds the default category tree on first use. One place for what `build_dre`, `simples_base`, the budget report and
    the MEI report all do first (recurrence rule)."""
    ensure_default_categories(s)
    cats = {str(c["id"]): c for c in s.rows("categories")}
    row = settings_svc.load_row(s)
    cfg = {**settings_svc.defaults(regime_prefill), **{k: v for k, v in (row or {}).items() if v is not None}}
    return _Route(cats, cfg), row


def _collect(s: Scope, months: list[str], route: _Route) -> _Facts:
    facts = _Facts()
    first_day = month_start(date.fromisoformat(months[0] + "-01"))
    last_day = month_start(date.fromisoformat(months[-1] + "-01"))
    after = add_months(last_day, 1)

    # 1) entries -- accrual by competence month
    entries = s.rows(
        "entries",
        refine=lambda q: q.neq("status", EntryStatus.CANCELLED.value)
        .gte("competence_month", iso(first_day)).lte("competence_month", iso(last_day)),
    )
    for e in entries:
        cat = route.cats.get(str(e["category_id"])) if e.get("category_id") else None
        if cat is not None and cat["direction"] == CategoryDirection.TRANSFER.value:
            continue  # transfers between own accounts never enter the DRE
        line, cat, special = route.entry_line(e)
        amount, month = int(e["amount_cents"]), _month_key(e["competence_month"])
        if line == _UNCLASSIFIED:
            signed = amount if e["direction"] == _RECEIVABLE else -amount
            if cat is None:
                if e["direction"] == _RECEIVABLE:
                    facts.uncategorized_revenue_cents += amount
                else:
                    facts.uncategorized_expense_cents += amount
                name = "Sem categoria"
                key = "__none__:" + e["direction"]
            else:
                name, key = str(cat["name"]), str(cat["id"])
                facts.unclassified_categories[name] = facts.unclassified_categories.get(name, 0) + abs(signed)
            facts.add(_UNCLASSIFIED, key, name, month, signed, behavior=CategoryBehavior.FIXED.value, category_id=str(cat["id"]) if cat else None)
            continue
        if special == "das" and route.regime == TaxRegime.SIMPLES.value and route.split and route.share_bps > 0:
            irpj = amount * route.share_bps // 10_000
            if irpj:
                facts.add(DreLine.INCOME_TAXES.value, f"das-irpj:{cat['id']}", f"{cat['name']} (parcela IRPJ/CSLL do DAS)", month, irpj,
                          behavior=CategoryBehavior.VARIABLE.value, category_id=str(cat["id"]))
            amount -= irpj
        name = INTEREST_CATEGORY_NAME if special == "interest" and cat is None else (str(cat["name"]) if cat else "Sem categoria")
        value = amount if e["direction"] == _natural_direction(line) else -amount
        facts.add(line, str(cat["id"]) if cat else f"__interest__:{line}", name, month, value,
                  behavior=route.behavior(cat, line), category_id=str(cat["id"]) if cat else None)

    # 2) settlements -- refunds / chargebacks / fees take the settlement's own month
    sts = s.rows(
        "settlements",
        refine=lambda q: q.is_("reversed_at", "null").gte("settled_on", iso(first_day)).lt("settled_on", iso(after)),
    )
    by_entry = _fetch_by_ids(s, "entries", (str(st["entry_id"]) for st in sts))
    for st in sts:
        entry = by_entry.get(str(st["entry_id"]))
        if entry is None:
            logger.warning("finance dre: settlement %s has no entry in this org; skipped", st.get("id"))
            continue
        month = _month_key(st["settled_on"])
        if st["kind"] == SettlementKind.REFUND.value:
            amount = int(st["amount_cents"])
            if entry["direction"] == _RECEIVABLE:
                is_cb = str(st.get("external_ref") or "").startswith(CHARGEBACK_PREFIX)
                line = str(route.cfg["chargeback_line"]) if is_cb else DreLine.DEDUCTIONS.value
                facts.has_chargeback = facts.has_chargeback or is_cb
                value = amount if line not in _REVENUE_SIDE else -amount
                facts.add(line, "__chargeback__" if is_cb else "__refunds__",
                          "Chargebacks (valor devolvido ao comprador)" if is_cb else "Estornos e cancelamentos", month, value,
                          behavior=CategoryBehavior.VARIABLE.value, source="settlements")
            else:  # money back from a supplier: a contra on the expense's own line
                cat = route.cats.get(str(entry["category_id"])) if entry.get("category_id") else None
                line = _inherited(cat, route.cats, "dre_line")
                if line in _REAL_LINES:
                    facts.add(line, str(cat["id"]), str(cat["name"]), month, -amount if _natural_direction(line) == _PAYABLE else amount,
                              behavior=route.behavior(cat, line), category_id=str(cat["id"]), source="settlements")
        fee = int(st.get("fee_cents") or 0)
        if fee > 0:
            if entry["direction"] == _RECEIVABLE:
                kind = classify_fee(st)
                line = str(route.cfg[_FEE_SETTING[kind]])
                facts.add(line, f"__fee__:{kind}", _FEE_NAME[kind], month, fee if line not in _REVENUE_SIDE else -fee, source="settlements")
            else:  # a fee for paying a bill is a bank charge: cost of money
                facts.add(DreLine.FINANCIAL_EXPENSES.value, "__fee__:bank", "Tarifas bancárias (baixas)", month, fee, source="settlements")

    # 3) gateway-sync fee rows (a fee for a charge not settled with its own fee_cents)
    rows = s.rows(
        "ledger",
        refine=lambda q: q.eq("origin", LedgerOrigin.ADJUSTMENT.value).eq("direction", LedgerDirection.OUT.value)
        .is_("reverses_id", "null").gte("occurred_on", iso(first_day)).lt("occurred_on", iso(after)),
    )
    for row in rows:
        if not str(row.get("description") or "").startswith(GATEWAY_FEE_DESCRIPTION_PREFIX):
            continue
        kind = classify_fee(row)
        line = str(route.cfg[_FEE_SETTING[kind]])
        amount = int(row["amount_cents"])
        facts.add(line, f"__fee__:{kind}", _FEE_NAME[kind], _month_key(row["occurred_on"]), amount if line not in _REVENUE_SIDE else -amount, source="gateway_sync")
    return facts


# ─── statement assembly ─────────────────────────────────────────────────────


def _series(months: list[str], per_month: Mapping[str, int]) -> dict[str, int]:
    return {m: int(per_month.get(m, 0)) for m in months}


def _detail(cell: _Cell, months: list[str]) -> dict:
    by_month = _series(months, cell.months)
    return {
        "category_id": cell.category_id,
        "name": cell.name,
        "cents": sum(by_month.values()),
        "by_month": by_month,
        "behavior": cell.behavior,
        "source": cell.source,
    }


def _line_by_month(facts: _Facts, line: str, months: list[str]) -> dict[str, int]:
    total = {m: 0 for m in months}
    for c in facts.of_line(line):
        for m in months:
            total[m] += c.months.get(m, 0)
    return total


def _build_statement(facts: _Facts, months: list[str]) -> tuple[list[dict], dict[str, dict[str, int]]]:
    line_m = {ln: _line_by_month(facts, ln, months) for ln in _REAL_LINES}
    L = lambda ln: line_m[ln]  # noqa: E731
    sub: dict[str, dict[str, int]] = {}
    sub["net_revenue"] = {m: L("gross_revenue")[m] - L("deductions")[m] for m in months}
    sub["gross_result"] = {m: sub["net_revenue"][m] - L("cost_of_sales")[m] for m in months}
    sub["result_before_financial"] = {
        m: sub["gross_result"][m] - L("selling_expenses")[m] - L("administrative_expenses")[m] + L("other_operating")[m] for m in months
    }
    sub["result_before_income_taxes"] = {
        m: sub["result_before_financial"][m] + L("financial_revenue")[m] - L("financial_expenses")[m] for m in months
    }
    sub["net_result"] = {m: sub["result_before_income_taxes"][m] - L("income_taxes")[m] for m in months}

    items: list[dict] = []
    for kind, key in STATEMENT_ORDER:
        if kind == "line":
            by_month = line_m[key]
            detail = [d for d in (_detail(c, months) for c in facts.of_line(key)) if any(d["by_month"].values())]
            items.append({
                "key": key, "kind": "line", "label": LINE_HELP[key]["label"], "sign": _effect_sign(key),
                "cents": sum(by_month.values()), "by_month": by_month, "detail": detail,
                "empty": not detail or all(d["cents"] == 0 for d in detail),
            })
        else:
            items.append({
                "key": key, "kind": "subtotal", "label": SUBTOTAL_HELP[key]["label"], "sign": 1,
                "cents": sum(sub[key].values()), "by_month": sub[key], "detail": [], "empty": False,
            })
    return items, sub


def _build_managerial(facts: _Facts, months: list[str]) -> dict:
    """Contribution margin: gross revenue - variable (deductions, cost of sales, variable selling) = margin;
    margin - fixed + other income = net result. The same rows as the statement, regrouped."""
    revenue: list[dict] = []
    variable: list[dict] = []
    fixed: list[dict] = []
    other_income: list[dict] = []
    for cell in facts.cells.values():
        if cell.line == _UNCLASSIFIED:
            continue
        sign = _effect_sign(cell.line)
        by_month = {m: sign * cell.months.get(m, 0) for m in months}  # effect on net result
        total = sum(by_month.values())
        if not any(by_month.values()):
            continue
        row = {"line": cell.line, "category_id": cell.category_id, "name": cell.name, "by_month": by_month, "cents": total}
        if cell.line == DreLine.GROSS_REVENUE.value:
            revenue.append(row)
        elif total > 0:
            other_income.append(row)
        elif cell.behavior == CategoryBehavior.VARIABLE.value:
            variable.append({**row, "cents": -total, "by_month": {m: -v for m, v in by_month.items()}})
        else:
            fixed.append({**row, "cents": -total, "by_month": {m: -v for m, v in by_month.items()}})

    def total(rows: list[dict]) -> dict[str, int]:
        return {m: sum(r["by_month"][m] for r in rows) for m in months}

    rev_m, var_m, fix_m, oth_m = total(revenue), total(variable), total(fixed), total(other_income)
    margin_m = {m: rev_m[m] - var_m[m] for m in months}
    net_m = {m: margin_m[m] - fix_m[m] + oth_m[m] for m in months}
    order = lambda rows: sorted(rows, key=lambda r: (-abs(r["cents"]), r["name"].lower()))  # noqa: E731
    revenue_total = sum(rev_m.values())
    margin_total = sum(margin_m.values())
    return {
        "revenue": {"cents": revenue_total, "by_month": rev_m, "detail": order(revenue)},
        "variable_costs": {"cents": sum(var_m.values()), "by_month": var_m, "detail": order(variable)},
        "contribution_margin": {
            "cents": margin_total,
            "by_month": margin_m,
            "percent_of_revenue_bps": (margin_total * 10_000 // revenue_total) if revenue_total > 0 else None,
        },
        "fixed_costs": {"cents": sum(fix_m.values()), "by_month": fix_m, "detail": order(fixed)},
        "other_income": {"cents": sum(oth_m.values()), "by_month": oth_m, "detail": order(other_income)},
        "net_result": {"cents": sum(net_m.values()), "by_month": net_m},
    }


# ─── guidance ───────────────────────────────────────────────────────────────


def _warning(code: str, severity: str, message: str, action: str, **details: Any) -> dict:
    out = {"code": code, "severity": severity, "message": message, "action": action}
    if details:
        out["details"] = details
    return out


def _alert(code: str, message: str, why: str, source: str) -> dict:
    return {"code": code, "message": message, "why": why, "source": source}


def _guidance(
    facts: _Facts, route: _Route, presented: Mapping[str, Any], *, trailing_gross: int, cost_of_sales_cents: int
) -> tuple[list[dict], list[dict]]:
    warnings: list[dict] = []
    alerts: list[dict] = []
    regime = route.regime
    if regime == TaxRegime.UNKNOWN.value:
        warnings.append(_warning(
            "regime_nao_informado", "warning",
            "O regime tributário da loja não foi informado. Sem ele não sabemos onde colocar o DAS (deduções, despesa administrativa ou IRPJ/CSLL).",
            "Informe o regime em Configurações da DRE (MEI, Simples Nacional ou Lucro Presumido).",
        ))
        alerts.append(_alert(
            "definir_regime", "Confirme com seu contador qual é o regime tributário da empresa.",
            "O regime muda onde cada imposto aparece na DRE e como a receita é medida.", "Código Civil art. 1.182; LC 123/2006 art. 26 §2 [norma].",
        ))
    if facts.unclassified_categories:
        names = sorted(facts.unclassified_categories)
        warnings.append(_warning(
            "categoria_sem_linha_dre", "warning",
            f"{len(names)} categoria(s) com movimento ainda não têm linha da DRE: {', '.join(names[:5])}{'…' if len(names) > 5 else ''}. "
            "Esses valores ficam no bloco 'Sem classificação' e não entram no resultado.",
            "Abra Categorias e escolha a linha da DRE de cada uma.", categories=names,
        ))
    if facts.uncategorized_revenue_cents:
        warnings.append(_warning(
            "receita_sem_categoria", "warning",
            "Há receitas sem categoria: elas não aparecem na Receita bruta até serem categorizadas.",
            "Edite os lançamentos de receita e escolha a categoria (ex.: Vendas).", cents=facts.uncategorized_revenue_cents,
        ))
    provisional = [n for n, c in presented["choices"].items() if c["provisional"]]
    if provisional:
        warnings.append(_warning(
            "escolha_provisoria", "info",
            "Algumas escolhas desta DRE ainda são provisórias (ex.: taxa do gateway em despesas com vendas). Elas têm fonte, mas dependem do seu contador.",
            "Revise a lista do contador e confirme cada escolha.", choices=provisional,
        ))
    if trailing_gross > MICRO_ENTITY_LIMIT_CENTS:
        warnings.append(_warning(
            "limite_microentidade_excedido", "warning",
            "A receita bruta dos últimos 12 meses passou de R$ 4,8 milhões: a loja sai do padrão de microentidade (NBC TG 1002) e cai no NBC TG 1001, com mais divulgações.",
            "Fale com um contador sobre a mudança de padrão contábil.", trailing_12m_gross_cents=trailing_gross,
        ))
        alerts.append(_alert(
            "padrao_nbc_tg_1001", "Procure um contador: acima de R$ 4,8 milhões a escrituração segue o NBC TG 1001.",
            "A DRE já está em despesas por função (exigida), mas as notas explicativas e demais demonstrações passam a ser obrigatórias.",
            "NBC TG 1001 [norma]; KB § PATTERNS/finance/dre-structure.md §1.",
        ))
    if cost_of_sales_cents:
        warnings.append(_warning(
            "cmv_por_compras", "info",
            "Sem controle de estoque, o Custo das vendas é a soma das compras do mês — uma aproximação do custo real do que foi vendido.",
            "Confirme com seu contador se essa aproximação serve para a sua loja.",
        ))
    if facts.has_chargeback:
        alerts.append(_alert(
            "chargeback_base_simples", "Pergunte ao contador se o chargeback perdido reduz a base do Simples.",
            "Não há fonte brasileira que diga se um chargeback perdido é 'venda cancelada' (LC 123 art. 3 §1); aqui ele entra como dedução provisória.",
            "KB § PATTERNS/finance/dre-structure.md §4(e) [em aberto].",
        ))
    if regime in (TaxRegime.SIMPLES.value, TaxRegime.PRESUMIDO.value):
        alerts.append(_alert(
            "escrituracao_contabil", "A escrituração contábil é responsabilidade de um contador (CRC); este sistema prepara, classifica e exporta — não assina nem entrega obrigações.",
            "ME/EPP precisam no mínimo de livro-caixa; distribuição de lucros acima do presumido exige contabilidade completa.",
            "Código Civil art. 1.182; LC 123 art. 26 §2 e art. 14 §§1–2 [norma].",
        ))
    if regime == TaxRegime.SIMPLES.value:
        alerts.append(_alert(
            "simples_competencia_2027", "A partir de 2027-01-01 o Simples deixa de permitir o regime de caixa: a receita conta no faturamento.",
            "A base do PGDAS-D muda de critério; use o relatório 'Base do Simples' para conferir.",
            "Res. CGSN 190/2026 art. 2 §8 e art. 8 XXIII [órgão oficial].",
        ))
    return warnings, alerts


# ─── public API ─────────────────────────────────────────────────────────────


def _check_range(start: date, end: date) -> None:
    if end < start:
        raise invalid("to", "A data final deve ser igual ou posterior à inicial.")
    if len(_months(start, end)) > MAX_REPORT_MONTHS:
        raise invalid("to", f"O período pode ter no máximo {MAX_REPORT_MONTHS} meses.", code="periodo_grande_demais")


def build_dre(
    s: Scope,
    month_from: date,
    month_to: date,
    *,
    view: str = "statement",
    regime_prefill: Optional[str] = None,
) -> dict:
    """The DRE for `[month_from, month_to]` (whole months). `view` = 'statement' | 'managerial'."""
    if view not in VIEWS:
        raise invalid("view", "Visão inválida (use 'statement' ou 'managerial').", code="visao_invalida")
    start, end = month_start(month_from), month_start(month_to)
    _check_range(start, end)
    months = _months(start, end)

    route, row = make_route(s, regime_prefill)

    # Trailing 12 months ending at the last month: needs facts BEYOND the window when the window is short.
    trailing_start = min(start, add_months(end, -11))
    ext_months = _months(trailing_start, end)
    facts = _collect(s, ext_months, route)
    trailing = ext_months[-12:]
    trailing_gross = sum(c.months.get(m, 0) for c in facts.of_line(DreLine.GROSS_REVENUE.value) for m in trailing)

    items, sub = _build_statement(facts, months)
    net_by_month = sub["net_result"]
    unclassified_cells = facts.of_line(_UNCLASSIFIED)
    unclassified_by_month = {m: sum(c.months.get(m, 0) for c in unclassified_cells) for m in months}
    unclassified_detail = [d for d in (_detail(c, months) for c in unclassified_cells) if any(d["by_month"].values())]
    cost_of_sales = sum(i["cents"] for i in items if i["key"] == DreLine.COST_OF_SALES.value)

    presented = settings_svc.present(row, regime_prefill=regime_prefill)
    warnings, alerts = _guidance(facts, route, presented, trailing_gross=trailing_gross, cost_of_sales_cents=cost_of_sales)
    help_ = {**{k: v for k, v in LINE_HELP.items()}, **{k: v for k, v in SUBTOTAL_HELP.items()}}
    is_mei = route.regime == TaxRegime.MEI.value
    out: dict[str, Any] = {
        "from": iso(start),
        "to": iso(end),
        "months": months,
        "view": view,
        "title": TITLE_MEI if is_mei else TITLE_DEFAULT,
        "standard": "nbc_tg_1001" if trailing_gross > MICRO_ENTITY_LIMIT_CENTS else "nbc_tg_1002",
        "tax_regime": route.regime,
        "trailing_12m_gross_revenue_cents": trailing_gross,
        "net_result_cents": sum(net_by_month.values()),
        "unclassified": {
            "net_cents": sum(unclassified_by_month.values()),
            "by_month": unclassified_by_month,
            "detail": unclassified_detail,
            "included_in_net_result": False,
        },
        "help": help_,
        "warnings": warnings,
        "accountant_alerts": alerts,
    }
    if view == "managerial":
        managerial = _build_managerial(facts, months)
        managerial["title"] = "Visão gerencial — margem de contribuição"
        out["managerial"] = managerial
    else:
        out["statement"] = items
    return out


__all__ = [
    "CHARGEBACK_PREFIX",
    "GATEWAY_FEE_DESCRIPTION_PREFIX",
    "INTEREST_CATEGORY_NAME",
    "INTEREST_SUFFIX",
    "MICRO_ENTITY_LIMIT_CENTS",
    "VIEWS",
    "build_dre",
    "classify_fee",
    "make_route",
]
