"""MEI Relatório Mensal de Receitas Brutas (E21) -- the monthly revenue book of the Microempreendedor Individual.

Legal anchor: Res. CGSN 140/2018 art. 106 (+ arts. 108, 109), Annex X; the MEI must KEEP it (for the Fisco, on request), with the
sale invoices attached, filled by the 20th of the following month [P&R-MEI 3.6]. The software prepares the figures; it files nothing.

**Model fields -- UNVERIFIED.** The brief cites the report and its legal anchor but not its field list, and the official Annex X text
could not be fetched when this was written (gov.br serves the form as a download, the Receita P&R-MEI PDF only cites it). The
structure below is the model as the implementer knows it -- three activity groups (comércio / indústria / serviços), each split
into "com dispensa de documento fiscal" and "com documento fiscal emitido", a total per group (I-IX) and the grand total (X).
Confirm it against the official PDF before putting it in front of a Fisco; `FIELDS` is the ONE place to adjust the labels.

**How a figure is built**
* Basis = **cash** (the MEI's receipts): payment settlements of receivables by `settled_on`, minus refunds of the same kind.
  Only receivables that count as gross revenue (`simples_base._counts_as_gross`) enter -- sales and installment interest.
* Activity group = the category's `activity_kind`, inherited from an ancestor. A receipt whose category has none goes to
  `unassigned_cents` (NOT guessed) and raises a critical warning: the grand total in the model would otherwise be short.
* "Com nota" = the entry's `has_invoice` is true. `null` (not informed) counts as "sem nota" -- the common MEI case, a sale to a
  pessoa física (art. 106 dispensa) -- AND is counted apart (`unknown_invoice_cents`) with a warning so it is never silent.
* Only `tax_regime = mei` is applicable; for other regimes the report is still computed but `applicable=False` with a warning.

NOC-REMEDIATE[finance-mei-has-invoice-from-commerce]: `has_invoice` is manual today; commerce's finance bridge should pass it from
the order's fiscal document (`FinanceBooking.book_receivable(has_invoice=...)` already accepts it). -- 2026-10-14
"""
from __future__ import annotations

import csv
import io
from datetime import date
from typing import Any, Optional

from noctusai_lib.domain._organ_common import csv_safe

from . import _pdf
from ._common import Scope, add_months, iso, month_start
from .dre import _fetch_by_ids, _inherited, _month_key, make_route
from .exports import money
from .simples_base import _counts_as_gross
from .types import ActivityKind, SettlementKind, TaxRegime

KB_DOC = "KB § PATTERNS/finance/dre-structure.md §7"
LEGAL_BASIS = "Res. CGSN 140/2018 art. 106, 108 e 109 (Anexo X)"
DEADLINE_DAY = 20

#: group -> (label, roman numerals of the three rows). UNVERIFIED against the official Annex X (see the module docstring).
FIELDS: dict[str, dict[str, str]] = {
    ActivityKind.COMERCIO.value: {
        "title": "Revenda de mercadorias (comércio)",
        "without": "Revenda de mercadorias com dispensa de emissão de documento fiscal", "without_roman": "I",
        "with": "Revenda de mercadorias com documento fiscal emitido", "with_roman": "II",
        "total": "Total das receitas com revenda de mercadorias", "total_roman": "III",
    },
    ActivityKind.INDUSTRIA.value: {
        "title": "Venda de produtos industrializados (indústria)",
        "without": "Venda de produtos industrializados com dispensa de emissão de documento fiscal", "without_roman": "IV",
        "with": "Venda de produtos industrializados com documento fiscal emitido", "with_roman": "V",
        "total": "Total das receitas com venda de produtos industrializados", "total_roman": "VI",
    },
    ActivityKind.SERVICOS.value: {
        "title": "Prestação de serviços",
        "without": "Prestação de serviços com dispensa de emissão de documento fiscal", "without_roman": "VII",
        "with": "Prestação de serviços com documento fiscal emitido", "with_roman": "VIII",
        "total": "Total das receitas com prestação de serviços", "total_roman": "IX",
    },
}
GRAND_TOTAL = {"label": "Total geral das receitas brutas no mês", "roman": "X"}
ATTACH_NOTE = (
    "Anexe a este relatório as notas fiscais de venda ou prestação de serviços emitidas e as notas fiscais de compra de mercadorias e "
    "de serviços tomados (P&R-MEI 3.6)."
)
DISCLAIMER = (
    "Relatório preparado pelo sistema a partir das baixas registradas. O MEI deve mantê-lo e apresentá-lo quando o Fisco solicitar; "
    "este sistema não o transmite a nenhum órgão. Confira os valores e os anexos antes de guardar."
)


def mei_monthly(s: Scope, month: date, *, regime_prefill: Optional[str] = None) -> dict:
    start = month_start(month)
    after = add_months(start, 1)
    route, _row = make_route(s, regime_prefill)
    regime = route.regime

    groups = {k: {"without_invoice_cents": 0, "with_invoice_cents": 0, "total_cents": 0} for k in FIELDS}
    unassigned = 0
    unknown_invoice = 0
    sts = s.rows(
        "settlements",
        refine=lambda q: q.is_("reversed_at", "null").gte("settled_on", iso(start)).lt("settled_on", iso(after)),
    )
    by_entry = _fetch_by_ids(s, "entries", (str(st["entry_id"]) for st in sts))
    for st in sts:
        entry = by_entry.get(str(st["entry_id"]))
        if entry is None or _counts_as_gross(entry, route) is None:
            continue
        sign = 1 if st["kind"] == SettlementKind.PAYMENT.value else -1
        amount = sign * int(st["amount_cents"])
        cat = route.cats.get(str(entry["category_id"])) if entry.get("category_id") else None
        kind = _inherited(cat, route.cats, "activity_kind")
        if kind not in groups:
            unassigned += amount
            continue
        invoiced = entry.get("has_invoice")
        if invoiced is None:
            unknown_invoice += amount
        groups[kind]["with_invoice_cents" if invoiced else "without_invoice_cents"] += amount
    for g in groups.values():
        g["total_cents"] = g["without_invoice_cents"] + g["with_invoice_cents"]

    total = sum(g["total_cents"] for g in groups.values())
    warnings: list[dict[str, Any]] = []
    if regime != TaxRegime.MEI.value:
        warnings.append({"code": "relatorio_somente_mei", "severity": "info",
                         "message": "Este relatório é exclusivo do MEI; o regime tributário informado é outro." if regime != TaxRegime.UNKNOWN.value
                         else "O regime tributário não foi informado; este relatório vale apenas para o MEI.",
                         "action": "Confirme o regime em Configurações da DRE."})
    if unassigned:
        warnings.append({"code": "atividade_nao_definida", "severity": "critical",
                         "message": "Há receita recebida em categorias sem a atividade (comércio, indústria ou serviços); ela NÃO está nos totais abaixo.",
                         "action": "Defina a atividade da categoria em Cadastros > Categorias.", "details": {"cents": unassigned}})
    if unknown_invoice:
        warnings.append({"code": "nota_fiscal_nao_informada", "severity": "warning",
                         "message": "Há receita sem a informação de nota fiscal; ela foi contada como 'sem documento fiscal' (venda a pessoa física).",
                         "action": "Marque, nos recebimentos de vendas para empresas (CNPJ), que houve nota fiscal.", "details": {"cents": unknown_invoice}})
    if total < 0:
        warnings.append({"code": "mes_com_estorno_maior", "severity": "warning",
                         "message": "Os estornos do mês superam os recebimentos; confira se foram lançados no mês correto.", "action": "Revise as baixas do mês."})
    deadline = add_months(start, 1).replace(day=DEADLINE_DAY)
    return {
        "month": _month_key(start),
        "tax_regime": regime,
        "applicable": regime == TaxRegime.MEI.value,
        "basis": "cash",
        "deadline": iso(deadline),
        "groups": groups,
        "fields": FIELDS,
        "grand_total": GRAND_TOTAL,
        "total_cents": total,
        "unassigned_cents": unassigned,
        "unknown_invoice_cents": unknown_invoice,
        "warnings": warnings,
        "notes": [
            "Regime de caixa: conta o que foi recebido no mês (data da baixa), menos estornos.",
            "Estrutura do modelo (Anexo X da Res. CGSN 140/2018) a conferir com o PDF oficial.",
            ATTACH_NOTE,
        ],
        "legal_basis": LEGAL_BASIS,
        "disclaimer": DISCLAIMER,
        "source": KB_DOC,
    }


def mei_monthly_csv(report: dict) -> bytes:
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\r\n")
    w.writerow(["relatorio mensal de receitas brutas", report["month"], "base legal", report["legal_basis"]])
    w.writerow(["item", "descricao", "valor"])
    for key, f in FIELDS.items():
        g = report["groups"][key]
        w.writerow([f["without_roman"], csv_safe(f["without"]), money(g["without_invoice_cents"])])
        w.writerow([f["with_roman"], csv_safe(f["with"]), money(g["with_invoice_cents"])])
        w.writerow([f["total_roman"], csv_safe(f["total"]), money(g["total_cents"])])
    w.writerow([GRAND_TOTAL["roman"], csv_safe(GRAND_TOTAL["label"]), money(report["total_cents"])])
    if report["unassigned_cents"]:
        w.writerow(["", "Receita sem atividade definida (fora dos totais)", money(report["unassigned_cents"])])
    w.writerow([])
    for wn in report["warnings"]:
        w.writerow(["aviso", csv_safe(wn["code"]), csv_safe(wn["message"])])
    w.writerow([csv_safe(report["disclaimer"])])
    return b"\xef\xbb\xbf" + out.getvalue().encode("utf-8")


def mei_monthly_pdf(report: dict) -> bytes:
    rows: list[list[object]] = []
    for key, f in FIELDS.items():
        g = report["groups"][key]
        rows.append([f["without_roman"], f["without"], _pdf.brl(g["without_invoice_cents"])])
        rows.append([f["with_roman"], f["with"], _pdf.brl(g["with_invoice_cents"])])
        rows.append([f["total_roman"], f["total"], _pdf.brl(g["total_cents"])])
    body = _pdf.table([("Item", False), ("Descrição", False), ("Valor (R$)", True)], rows,
                      total_row=[GRAND_TOTAL["roman"], GRAND_TOTAL["label"], _pdf.brl(report["total_cents"])])
    if report["unassigned_cents"]:
        body += f"<p>Receita sem atividade definida (fora dos totais): R$ {_pdf.esc(_pdf.brl(report['unassigned_cents']))}</p>"
    body += "<p>CNPJ: ______________________ &nbsp; Empresário: ______________________________ &nbsp; Local e data: ______________ &nbsp; Assinatura: ______________</p>"
    y, m = report["month"].split("-")
    return _pdf.document(
        "Relatório Mensal de Receitas Brutas",
        [f"Período de apuração: {m}/{y}", f"Base legal: {report['legal_basis']}", f"Preenchimento até o dia {DEADLINE_DAY} do mês seguinte."],
        body,
        [report["disclaimer"], *report["notes"][1:]],
    )


__all__ = ["DISCLAIMER", "FIELDS", "GRAND_TOTAL", "LEGAL_BASIS", "mei_monthly", "mei_monthly_csv", "mei_monthly_pdf"]
