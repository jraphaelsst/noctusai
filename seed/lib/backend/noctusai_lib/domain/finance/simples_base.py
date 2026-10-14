"""`GET /reports/simples-base` -- the Simples Nacional tax base, SEPARATE from the DRE (CONTRACT §10.5.5).

Receita bruta for the PGDAS-D = sales + installment interest, the marketplace/gateway commission NOT netted,
minus cancellations/refunds; juros de mora excluded. The criterion changes on the 2027 boundary:

* months up to 2026-12 -- **cash basis** (the receipt: payment settlements by `settled_on`);
* months from 2027-01 -- **invoice basis** ("no momento do faturamento", Res. CGSN 190/2026 art. 2 §8; arts. 77-78 of
  CGSN 140 revoked). We approximate the invoice moment with the receivable's `competence_month` (the order's
  paid month); NFS-e/NF-e issuance dates are not yet an input -- see the `basis_note`.

A period crossing the boundary is split month by month, each row stamped with its `basis`. Lost chargebacks are
reported apart and NOT netted (whether they reduce the base is the contador's call -- KB dre-structure §4(e)).
It helps the owner check the number the contador computes; it never files anything.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Optional

from ._common import Scope, add_months, iso, month_start
from .dre import CHARGEBACK_PREFIX, INTEREST_SUFFIX, MAX_REPORT_MONTHS, _fetch_by_ids, _inherited, _month_key, _months, _Route, make_route
from .errors import invalid
from .types import DreLine, EntryDirection, EntryStatus, SettlementKind, TaxRegime

#: First month measured by the invoice criterion (Res. CGSN 190/2026 art. 9: effects from 2027-01-01).
INVOICE_BASIS_FROM = date(2027, 1, 1)
KB_DOC = "KB § PATTERNS/finance/dre-structure.md §6"

NOTES = (
    "Receita bruta = vendas + juros de parcelamento pagos pelo comprador; a comissão do gateway/marketplace NÃO é abatida (Solução de Consulta Cosit 94/2025 e 143/2021).",
    "Juros de mora recebidos ficam de fora (são receita financeira).",
    "Até 2026-12-31 o Simples admite o regime de caixa (recebimento); a partir de 2027-01-01 vale o faturamento (Res. CGSN 190/2026 art. 2 §8; arts. 77–78 da Res. CGSN 140 revogados).",
    "Este relatório ajuda a conferir o valor do PGDAS-D. Não transmite nada à Receita; quem apura e entrega é o seu contador.",
)
BASIS_NOTE = (
    "Base de faturamento aproximada pelo mês de competência do recebível (o pedido pago); a data de emissão da nota fiscal ainda não é um dado deste relatório."
)


def basis_of(month: str) -> str:
    """'cash' for months before 2027-01, 'invoice' from then on."""
    return "invoice" if date.fromisoformat(month + "-01") >= INVOICE_BASIS_FROM else "cash"


def _counts_as_gross(entry: dict, route: _Route) -> Optional[str]:
    """'interest' | 'sales' when a receivable belongs to the Simples gross revenue, else None."""
    if entry["direction"] != EntryDirection.RECEIVABLE.value or entry["status"] == EntryStatus.CANCELLED.value:
        return None
    if str(entry.get("source_ref") or "").endswith(INTEREST_SUFFIX):
        return "interest"  # tax-wise the buyer's interest is ALWAYS receita bruta, whatever DRE line the store picked
    cat = route.cats.get(str(entry["category_id"])) if entry.get("category_id") else None
    return "sales" if _inherited(cat, route.cats, "dre_line") == DreLine.GROSS_REVENUE.value else None


def simples_base(s: Scope, month_from: date, month_to: date, *, regime_prefill: Optional[str] = None) -> dict:
    start, end = month_start(month_from), month_start(month_to)
    if end < start:
        raise invalid("to", "A data final deve ser igual ou posterior à inicial.")
    months = _months(start, end)
    if len(months) > MAX_REPORT_MONTHS:
        raise invalid("to", f"O período pode ter no máximo {MAX_REPORT_MONTHS} meses.", code="periodo_grande_demais")

    route, _row = make_route(s, regime_prefill)
    cfg = route.cfg
    after = add_months(end, 1)

    rows = {m: {"month": m, "basis": basis_of(m), "sales_cents": 0, "interest_cents": 0, "refunds_cents": 0,
                "chargebacks_cents": 0, "base_cents": 0} for m in months}

    # invoice basis: receivables by competence month
    invoice_months = [m for m in months if rows[m]["basis"] == "invoice"]
    if invoice_months:
        entries = s.rows(
            "entries",
            eq={"direction": EntryDirection.RECEIVABLE.value},
            refine=lambda q: q.neq("status", EntryStatus.CANCELLED.value)
            .gte("competence_month", iso(date.fromisoformat(invoice_months[0] + "-01")))
            .lt("competence_month", iso(after)),
        )
        for e in entries:
            kind = _counts_as_gross(e, route)
            m = _month_key(e["competence_month"])
            if kind and m in rows and rows[m]["basis"] == "invoice":
                rows[m]["interest_cents" if kind == "interest" else "sales_cents"] += int(e["amount_cents"])

    transition_cents = 0  # 2026 sales received in 2027: which base do they belong to? (the contador's call)
    # settlements: receipts (cash months) and refunds (every month, by the refund's date)
    sts = s.rows("settlements", refine=lambda q: q.is_("reversed_at", "null").gte("settled_on", iso(start)).lt("settled_on", iso(after)))
    by_entry = _fetch_by_ids(s, "entries", (str(st["entry_id"]) for st in sts))
    for st in sts:
        entry = by_entry.get(str(st["entry_id"]))
        kind = _counts_as_gross(entry, route) if entry else None
        if entry is None or kind is None:
            continue
        m = _month_key(st["settled_on"])
        amount = int(st["amount_cents"])
        if st["kind"] == SettlementKind.PAYMENT.value and rows[m]["basis"] == "cash":
            rows[m]["interest_cents" if kind == "interest" else "sales_cents"] += amount
        elif st["kind"] == SettlementKind.PAYMENT.value and basis_of(_month_key(entry["competence_month"])) == "cash":
            transition_cents += amount
        elif st["kind"] == SettlementKind.REFUND.value:
            if str(st.get("external_ref") or "").startswith(CHARGEBACK_PREFIX):
                rows[m]["chargebacks_cents"] += amount
            else:
                rows[m]["refunds_cents"] += amount

    out_rows = []
    for m in months:
        r = rows[m]
        r["base_cents"] = r["sales_cents"] + r["interest_cents"] - r["refunds_cents"]
        out_rows.append(r)

    def total(rows_: list[dict]) -> dict:
        return {k: sum(r[k] for r in rows_) for k in ("sales_cents", "interest_cents", "refunds_cents", "chargebacks_cents", "base_cents")}

    warnings: list[dict[str, Any]] = []
    regime = cfg["tax_regime"]
    if regime == TaxRegime.UNKNOWN.value:
        warnings.append({"code": "regime_nao_informado", "severity": "warning",
                         "message": "O regime tributário não foi informado; este relatório vale para Simples Nacional/MEI.",
                         "action": "Informe o regime em Configurações da DRE."})
    elif regime == TaxRegime.PRESUMIDO.value:
        warnings.append({"code": "relatorio_somente_simples", "severity": "info",
                         "message": "Este relatório é a base do Simples Nacional; o Lucro Presumido usa outra apuração.",
                         "action": "Peça a apuração ao seu contador."})
    if any(r["chargebacks_cents"] for r in out_rows):
        warnings.append({"code": "chargeback_fora_da_base", "severity": "info",
                         "message": "Chargebacks perdidos NÃO foram abatidos da base: não há fonte que diga se contam como venda cancelada (LC 123 art. 3 §1).",
                         "action": "Pergunte ao contador."})
    if transition_cents:
        warnings.append({"code": "transicao_caixa_faturamento", "severity": "warning",
                         "message": "Há vendas de competência até 2026-12 recebidas já em 2027. Elas não entram na base de 2027 aqui (que usa o faturamento); "
                                    "como a transição do regime de caixa para o de faturamento trata esses valores não está em fonte que tenhamos lido.",
                         "action": "Pergunte ao contador em qual base essas vendas entram.", "details": {"cents": transition_cents}})
    if any(r["basis"] == "invoice" for r in out_rows):
        warnings.append({"code": "base_faturamento_aproximada", "severity": "info", "message": BASIS_NOTE,
                         "action": "Compare com as notas emitidas no mês."})
    return {
        "from": iso(start),
        "to": iso(end),
        "tax_regime": regime,
        "invoice_basis_from": INVOICE_BASIS_FROM.isoformat(),
        "crosses_basis_boundary": len({r["basis"] for r in out_rows}) > 1,
        "months": out_rows,
        "totals": {
            **total(out_rows),
            "cash_basis": total([r for r in out_rows if r["basis"] == "cash"]),
            "invoice_basis": total([r for r in out_rows if r["basis"] == "invoice"]),
        },
        "basis_note": BASIS_NOTE,
        "notes": list(NOTES),
        "warnings": warnings,
    }


__all__ = ["INVOICE_BASIS_FROM", "basis_of", "simples_base"]
