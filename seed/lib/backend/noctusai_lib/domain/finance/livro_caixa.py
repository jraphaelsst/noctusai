"""Livro Caixa (E21): the cash-basis book an ME/EPP keeps -- date, histórico, entrada, saída, saldo.

Legal anchor: LC 123/2006 art. 26 §2 (the ME/EPP optante by the cash regime keeps a Livro Caixa with ALL its financial and
bank movement) and Res. CGSN 140/2018 art. 63 ("Livro Caixa", not needed if Diário + Razão are kept). Source: market brief §B
(`project-history/roadmaps/erp-seed-2026-10-market-brief.md`). This is a VIEW over the ledger -- the books of record stay the
ledger and its settlements; the software prepares the listing, the contador signs the books.

* **Every account together.** The book is the business's cash, not one bank's: all accounts' ledger rows in the period.
* **Transfers between own accounts are not income or expense** and are left out (they net to zero across accounts).
* **Saldo anterior** = the accounts' opening balances dated before the period + the whole ledger before it. An account whose
  opening date falls INSIDE the period shows its opening balance as a line on that date (so the running saldo reconciles).
* **Pagination is presentation only**: `saldo` and the totals are computed over the whole period, then the JSON is sliced.
  CSV and PDF carry every row (capped; over the cap is refused 422, never truncated).

NOC-REMEDIATE[finance-report-sql-aggregates]: the saldo anterior sums the whole prior ledger in Python after a paged read (as
`reports.cashflow` does); an org past ~200k ledger rows wants a DB-side aggregate RPC. -- 2026-10-14
"""
from __future__ import annotations

import csv
import io
from datetime import date
from typing import Any

from noctusai_lib.domain._organ_common import csv_safe

from . import _pdf
from ._common import Scope, to_date
from .dre import _fetch_by_ids
from .errors import FinanceError, invalid
from .exports import EXPORT_TOO_BIG, MAX_EXPORT_ROWS, money
from .types import LedgerDirection, LedgerOrigin

PDF_MAX_ROWS = 5_000
#: Within one day: opening balances, then the settled amount, then its fee, then anything else; ties by when it was booked.
_RANK = {LedgerOrigin.OPENING.value: 0, LedgerOrigin.SETTLEMENT.value: 1, LedgerOrigin.FEE.value: 2}
KB_DOC = "KB § PATTERNS/finance/dre-structure.md §7"
LEGAL_BASIS = "LC 123/2006 art. 26 §2 · Res. CGSN 140/2018 art. 63"
DISCLAIMER = (
    "Listagem preparada pelo sistema a partir das baixas e movimentações das contas. "
    "A escrituração do livro é responsabilidade de um contador (CRC); este documento não substitui a escrituração oficial."
)


def livro_caixa(s: Scope, date_from: date, date_to: date, *, max_rows: int = MAX_EXPORT_ROWS) -> dict:
    """The whole book for `[date_from, date_to]` (days, inclusive). Rows are ordered by date, then id."""
    if date_to < date_from:
        raise invalid("to", "A data final deve ser igual ou posterior à inicial.")
    accounts = {str(a["id"]): a for a in s.rows("accounts")}
    start, end = date_from.isoformat(), date_to.isoformat()

    before_cents = 0
    lines: list[dict[str, Any]] = []
    for a in accounts.values():
        opening = int(a.get("opening_balance_cents") or 0)
        od = to_date(a.get("opening_date"))
        if not opening:
            continue
        if od is None or od < date_from:
            before_cents += opening
        elif od <= date_to:
            lines.append({"on": od.isoformat(), "sort": (0, "", ""), "kind": "opening", "history": f"Saldo inicial — {a['name']}",
                          "in": opening if opening > 0 else 0, "out": -opening if opening < 0 else 0,
                          "counterparty": None, "category": None, "ledger_id": None, "account": a["name"]})

    # ledger before the period (opening rows are part of it): only the signed sum is needed
    prior = s.rows("ledger", refine=lambda q: q.lt("occurred_on", start))
    before_cents += sum(int(r["amount_cents"]) if r["direction"] == LedgerDirection.IN.value else -int(r["amount_cents"]) for r in prior)

    count = (
        s.tbl("ledger").select("id", count="exact").eq("org_id", s.org_id)
        .gte("occurred_on", start).lte("occurred_on", end).range(0, 0).execute()
    )
    total_rows = int(getattr(count, "count", None) or 0)
    if total_rows > max_rows:
        raise FinanceError(
            EXPORT_TOO_BIG, f"O livro tem {total_rows} lançamentos; o limite é {max_rows}. Restrinja o período.", 422,
            details={"total": total_rows, "limit": max_rows},
        )
    ledger = s.rows("ledger", refine=lambda q: q.gte("occurred_on", start).lte("occurred_on", end))
    movements = [r for r in ledger if r["origin"] != LedgerOrigin.TRANSFER.value]

    settlements = _fetch_by_ids(s, "settlements", (str(r["settlement_id"]) for r in movements if r.get("settlement_id")))
    entries = _fetch_by_ids(s, "entries", (str(st["entry_id"]) for st in settlements.values()))
    cats = {str(c["id"]): c["name"] for c in s.rows("categories")}
    for r in movements:
        st = settlements.get(str(r["settlement_id"])) if r.get("settlement_id") else None
        entry = entries.get(str(st["entry_id"])) if st else None
        amount = int(r["amount_cents"])
        incoming = r["direction"] == LedgerDirection.IN.value
        lines.append({
            "on": str(r["occurred_on"])[:10], "sort": (_RANK.get(r["origin"], 3), str(r.get("created_at") or ""), str(r["id"])), "kind": r["origin"],
            "history": str(r.get("description") or ""),
            "in": amount if incoming else 0, "out": 0 if incoming else amount,
            "counterparty": (entry or {}).get("counterparty_name"),
            "category": cats.get(str((entry or {}).get("category_id"))) if entry and entry.get("category_id") else None,
            "ledger_id": str(r["id"]), "account": accounts.get(str(r["account_id"]), {}).get("name"),
        })
    lines.sort(key=lambda x: (x["on"], x["sort"]))

    saldo = before_cents
    total_in = total_out = 0
    for line in lines:
        saldo += line["in"] - line["out"]
        line["balance_cents"] = saldo
        total_in += line["in"]
        total_out += line["out"]
        del line["sort"]
    return {
        "from": start, "to": end,
        "opening_balance_cents": before_cents,
        "total_in_cents": total_in, "total_out_cents": total_out,
        "closing_balance_cents": saldo,
        "rows": lines,
        "row_count": len(lines),
        "legal_basis": LEGAL_BASIS,
        "notes": [
            "Todas as contas somadas; transferências entre contas próprias não entram.",
            "Regime de caixa: a data é a da movimentação (baixa/tarifa), não a do vencimento.",
        ],
        "disclaimer": DISCLAIMER,
        "source": KB_DOC,
    }


def page_of(book: dict, page: int, page_size: int) -> dict:
    """The JSON the screen needs: the totals of the whole period + one slice of its rows."""
    rows = book["rows"]
    lo = (page - 1) * page_size
    return {**{k: v for k, v in book.items() if k != "rows"}, "rows": rows[lo:lo + page_size], "page": page, "page_size": page_size}


_COLUMNS = ("data", "historico", "contraparte", "categoria", "conta", "entrada", "saida", "saldo")


def livro_caixa_csv(book: dict) -> bytes:
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\r\n")
    w.writerow(["livro caixa", book["from"], book["to"], "base legal", book["legal_basis"]])
    w.writerow(["saldo anterior", money(book["opening_balance_cents"])])
    w.writerow(_COLUMNS)
    for r in book["rows"]:
        w.writerow([
            r["on"], csv_safe(r["history"]), csv_safe(r["counterparty"]), csv_safe(r["category"]), csv_safe(r["account"]),
            money(r["in"]) if r["in"] else "", money(r["out"]) if r["out"] else "", money(r["balance_cents"]),
        ])
    w.writerow(["total", "", "", "", "", money(book["total_in_cents"]), money(book["total_out_cents"]), money(book["closing_balance_cents"])])
    w.writerow([])
    w.writerow([csv_safe(book["disclaimer"])])
    return b"\xef\xbb\xbf" + out.getvalue().encode("utf-8")


def _br(day: str) -> str:
    d = date.fromisoformat(day)
    return d.strftime("%d/%m/%Y")


def livro_caixa_pdf(book: dict) -> bytes:
    if book["row_count"] > PDF_MAX_ROWS:
        raise FinanceError(
            EXPORT_TOO_BIG, f"O PDF comporta até {PDF_MAX_ROWS} linhas e o período tem {book['row_count']}; use o CSV ou restrinja o período.", 422,
            details={"total": book["row_count"], "limit": PDF_MAX_ROWS},
        )
    rows = [[_br(book["from"]), "Saldo anterior", "", "", "", "", _pdf.brl(book["opening_balance_cents"])]]
    for r in book["rows"]:
        rows.append([_br(r["on"]), r["history"], r["counterparty"] or "", r["account"] or "",
                     _pdf.brl(r["in"]) if r["in"] else "", _pdf.brl(r["out"]) if r["out"] else "", _pdf.brl(r["balance_cents"])])
    body = _pdf.table(
        [("Data", False), ("Histórico", False), ("Contraparte", False), ("Conta", False), ("Entrada", True), ("Saída", True), ("Saldo", True)],
        rows,
        total_row=["", "Total do período", "", "", _pdf.brl(book["total_in_cents"]), _pdf.brl(book["total_out_cents"]), _pdf.brl(book["closing_balance_cents"])],
    )
    return _pdf.document(
        "Livro Caixa", [f"Período: {_br(book['from'])} a {_br(book['to'])}", f"Base legal: {book['legal_basis']}"], body, [book["disclaimer"], *book["notes"]],
    )


__all__ = ["DISCLAIMER", "LEGAL_BASIS", "PDF_MAX_ROWS", "livro_caixa", "livro_caixa_csv", "livro_caixa_pdf", "page_of"]
