"""Exports: `entries.csv` and `dre.csv` (spreadsheets) and `ledger.ofx` (OFX 2.x, importable by any accounting tool).

* **CSV injection.** A cell that begins with `= + - @ TAB CR` is a formula to Excel/Sheets; it is
  prefixed with `'` (contract §3.4). Applied to EVERY text cell -- descriptions and counterparty
  names are attacker-influenced (a buyer typed them). Numbers are written by us, from ints.
* **LGPD.** `counterparty_doc` goes through `present_entry`: masked unless the caller is org admin.
* **Caps.** More than `MAX_EXPORT_ROWS` matching rows is REFUSED (422), never silently truncated.
* **Org scope.** Everything is read through the caller's `Scope`; a foreign account id is a 404.
"""
from __future__ import annotations

import csv
import io
import re
from datetime import date, timezone
from decimal import Decimal
from typing import Any, Optional
from xml.etree import ElementTree as ET

from ._common import Scope, iso, now, to_date, today
from .accounts import account_balance, get_account
from .entries import list_entries, present_entry
from .errors import FinanceError
from .types import AccountKind, LedgerDirection, LedgerOrigin

MAX_EXPORT_ROWS = 50_000
EXPORT_TOO_BIG = "exportacao_grande_demais"
_FORMULA_LEAD = ("=", "+", "-", "@", "\t", "\r")
_XML_ILLEGAL = re.compile("[^\x09\x0a\x0d\x20-퟿-�]")
_PAGE = 200

CSV_COLUMNS = (
    "id", "direction", "status", "description", "counterparty_name", "counterparty_doc", "category",
    "cost_center", "competence_month", "due_date", "amount", "settled", "overdue", "source", "source_ref", "notes",
)


def csv_safe(value: Any) -> str:
    """One cell: text starting with a formula character is neutralised with a leading `'`."""
    text = "" if value is None else str(value)
    return "'" + text if text.startswith(_FORMULA_LEAD) else text


def money(cents: Any) -> str:
    """Integer cents -> `1234.56` (exact; never a float)."""
    return f"{Decimal(int(cents or 0)) / 100:.2f}"


# ─── entries.csv ─────────────────────────────────────────────────────────────


def entries_csv(
    s: Scope,
    *,
    is_admin: bool,
    direction: Optional[str] = None,
    status: Optional[str] = None,
    overdue: Optional[bool] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    category_id: Optional[Any] = None,
    cost_center_id: Optional[Any] = None,
    q: Optional[str] = None,
    max_rows: int = MAX_EXPORT_ROWS,
) -> bytes:
    """UTF-8 (BOM, so Excel reads accents) CSV of the entries matching the same filters as `GET /entries`."""
    filters = dict(direction=direction, status=status, overdue=overdue, date_from=date_from, date_to=date_to,
                   category_id=category_id, cost_center_id=cost_center_id, q=q)
    rows, total, _, _ = list_entries(s, page=1, page_size=_PAGE, **filters)
    if total > max_rows:
        raise FinanceError(
            EXPORT_TOO_BIG, f"A exportação tem {total} linhas; o limite é {max_rows}. Restrinja o período.", 422,
            details={"total": total, "limit": max_rows},
        )
    categories = {str(r["id"]): r.get("name") for r in s.rows("categories")}
    centers = {str(r["id"]): r.get("name") for r in s.rows("cost_centers")}
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\r\n")
    writer.writerow(CSV_COLUMNS)
    on = today()
    page = 1
    while rows:
        for row in rows:
            e = present_entry(row, is_admin=is_admin, on=on)
            writer.writerow([
                csv_safe(e["id"]), csv_safe(e["direction"]), csv_safe(e["status"]), csv_safe(e.get("description")),
                csv_safe(e.get("counterparty_name")), csv_safe(e.get("counterparty_doc")),
                csv_safe(categories.get(str(e.get("category_id")))), csv_safe(centers.get(str(e.get("cost_center_id")))),
                iso(e.get("competence_month")) or "", iso(e.get("due_date")) or "",
                money(e["amount_cents"]), money(e.get("settled_cents")), "sim" if e["overdue"] else "nao",
                csv_safe(e.get("source")), csv_safe(e.get("source_ref")), csv_safe(e.get("notes")),
            ])
        if page * _PAGE >= total:
            break
        page += 1
        rows, _, _, _ = list_entries(s, page=page, page_size=_PAGE, **filters)
    return b"\xef\xbb\xbf" + out.getvalue().encode("utf-8")


# ─── dre.csv ─────────────────────────────────────────────────────────────────


def dre_csv(
    s: Scope, month_from: date, month_to: date, *, view: str = "statement", regime_prefill: Optional[str] = None
) -> bytes:
    """The structured DRE (`dre.build_dre`) as a spreadsheet: one row per line / subtotal / category detail,
    one column per month plus a total, then the unclassified block and the warnings (so a printout never hides them).
    Amounts are in reais with two decimals, as the line's own sign convention (deductions and expenses are positive)."""
    from .dre import build_dre  # local: exports must stay importable without the DRE module graph

    report = build_dre(s, month_from, month_to, view=view, regime_prefill=regime_prefill)
    months = report["months"]
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\r\n")
    writer.writerow([csv_safe(report["title"])])
    writer.writerow(["periodo", report["from"], report["to"], "regime", csv_safe(report["tax_regime"])])
    writer.writerow([])
    writer.writerow(["tipo", "linha", "nome", *months, "total"])

    def emit(kind: str, key: str, name: Any, by_month: dict, total: int) -> None:
        writer.writerow([kind, csv_safe(key), csv_safe(name), *(money(by_month.get(m, 0)) for m in months), money(total)])

    if view == "managerial":
        m = report["managerial"]
        for key, label in (("revenue", "Receita bruta"), ("variable_costs", "(-) Custos e despesas variáveis"),
                           ("contribution_margin", "= Margem de contribuição"), ("fixed_costs", "(-) Custos e despesas fixos"),
                           ("other_income", "(+) Outras receitas"), ("net_result", "= Resultado líquido")):
            block = m[key]
            emit("linha" if key not in ("contribution_margin", "net_result") else "subtotal", key, label, block["by_month"], block["cents"])
            for d in block.get("detail", []):
                emit("detalhe", d["line"], d["name"], d["by_month"], d["cents"])
    else:
        for item in report["statement"]:
            emit("subtotal" if item["kind"] == "subtotal" else "linha", item["key"], item["label"], item["by_month"], item["cents"])
            for d in item["detail"]:
                emit("detalhe", item["key"], d["name"], d["by_month"], d["cents"])
    un = report["unclassified"]
    if un["detail"]:
        emit("sem_classificacao", "unclassified", "Sem classificação (fora do resultado)", un["by_month"], un["net_cents"])
        for d in un["detail"]:
            emit("detalhe", "unclassified", d["name"], d["by_month"], d["cents"])
    writer.writerow([])
    for w in report["warnings"]:
        writer.writerow(["aviso", csv_safe(w["code"]), csv_safe(w["message"])])
    for a in report["accountant_alerts"]:
        writer.writerow(["alerta_contador", csv_safe(a["code"]), csv_safe(a["message"])])
    return b"\xef\xbb\xbf" + out.getvalue().encode("utf-8")


# ─── ledger.ofx ──────────────────────────────────────────────────────────────

_ACCT_TYPE = {
    AccountKind.CHECKING.value: "CHECKING",
    AccountKind.SAVINGS.value: "SAVINGS",
    AccountKind.INVESTMENT.value: "MONEYMRKT",
    AccountKind.CREDIT_CARD.value: "CREDITLINE",
}
_TRN_TYPE = {LedgerOrigin.FEE.value: "SRVCHG", LedgerOrigin.TRANSFER.value: "XFER"}
_ORIGIN_NAME = {
    LedgerOrigin.SETTLEMENT.value: "Baixa", LedgerOrigin.FEE.value: "Tarifa", LedgerOrigin.TRANSFER.value: "Transferência",
    LedgerOrigin.ADJUSTMENT.value: "Ajuste", LedgerOrigin.OPENING.value: "Saldo inicial",
}


def _x(value: Any, limit: int) -> str:
    return _XML_ILLEGAL.sub(" ", "" if value is None else str(value)).strip()[:limit]


def _dt(d: date) -> str:
    return f"{d.strftime('%Y%m%d')}120000[-3:BRT]"


def _signed(cents: int) -> str:
    return f"{Decimal(cents) / 100:.2f}"


def ledger_ofx(
    s: Scope, account_id: Any, *, date_from: Optional[date] = None, date_to: Optional[date] = None,
    max_rows: int = MAX_EXPORT_ROWS,
) -> bytes:
    """The account's ledger over `[from, to]` as OFX 2.x (FITID = ledger row id, so a re-import dedupes)."""
    account = get_account(s, account_id)
    end = date_to or today()
    start = date_from or to_date(account.get("opening_date")) or end.replace(day=1)
    aid = str(account["id"])
    count = (
        s.tbl("ledger").select("id", count="exact").eq("org_id", s.org_id).eq("account_id", aid)
        .gte("occurred_on", start.isoformat()).lte("occurred_on", end.isoformat()).range(0, 0).execute()
    )
    total = int(getattr(count, "count", None) or 0)
    if total > max_rows:
        raise FinanceError(
            EXPORT_TOO_BIG, f"A exportação tem {total} lançamentos; o limite é {max_rows}. Restrinja o período.", 422,
            details={"total": total, "limit": max_rows},
        )
    ledger = s.rows(
        "ledger", eq={"account_id": aid},
        refine=lambda q: q.gte("occurred_on", start.isoformat()).lte("occurred_on", end.isoformat()),
    )
    ledger.sort(key=lambda r: (str(r["occurred_on"]), str(r["id"])))
    balance = account_balance(s, aid, end)

    ofx = ET.Element("OFX")
    sonrs = ET.SubElement(ET.SubElement(ofx, "SIGNONMSGSRSV1"), "SONRS")
    status = ET.SubElement(sonrs, "STATUS")
    ET.SubElement(status, "CODE").text = "0"
    ET.SubElement(status, "SEVERITY").text = "INFO"
    ET.SubElement(sonrs, "DTSERVER").text = _dt(now().astimezone(timezone.utc).date())
    ET.SubElement(sonrs, "LANGUAGE").text = "POR"
    trnrs = ET.SubElement(ET.SubElement(ofx, "BANKMSGSRSV1"), "STMTTRNRS")
    ET.SubElement(trnrs, "TRNUID").text = "0"
    st2 = ET.SubElement(trnrs, "STATUS")
    ET.SubElement(st2, "CODE").text = "0"
    ET.SubElement(st2, "SEVERITY").text = "INFO"
    stmt = ET.SubElement(trnrs, "STMTRS")
    ET.SubElement(stmt, "CURDEF").text = "BRL"
    acct = ET.SubElement(stmt, "BANKACCTFROM")
    ET.SubElement(acct, "BANKID").text = _x(account.get("bank_code"), 9) or "0000"
    if account.get("agency"):
        ET.SubElement(acct, "BRANCHID").text = _x(account["agency"], 22)
    ET.SubElement(acct, "ACCTID").text = _x(account.get("number"), 22) or aid.replace("-", "")[:22]
    ET.SubElement(acct, "ACCTTYPE").text = _ACCT_TYPE.get(account["kind"], "CHECKING")
    tranlist = ET.SubElement(stmt, "BANKTRANLIST")
    ET.SubElement(tranlist, "DTSTART").text = _dt(start)
    ET.SubElement(tranlist, "DTEND").text = _dt(end)
    for row in ledger:
        cents = int(row["amount_cents"]) * (1 if row["direction"] == LedgerDirection.IN.value else -1)
        trn = ET.SubElement(tranlist, "STMTTRN")
        ET.SubElement(trn, "TRNTYPE").text = _TRN_TYPE.get(row["origin"], "CREDIT" if cents > 0 else "DEBIT")
        ET.SubElement(trn, "DTPOSTED").text = _dt(to_date(row["occurred_on"]))  # type: ignore[arg-type]
        ET.SubElement(trn, "TRNAMT").text = _signed(cents)
        ET.SubElement(trn, "FITID").text = _x(row["id"], 255)
        ET.SubElement(trn, "NAME").text = _x(_ORIGIN_NAME.get(row["origin"], row["origin"]), 32)
        ET.SubElement(trn, "MEMO").text = _x(row.get("description"), 255)
    bal = ET.SubElement(stmt, "LEDGERBAL")
    ET.SubElement(bal, "BALAMT").text = _signed(int(balance["balance_cents"]))
    ET.SubElement(bal, "DTASOF").text = _dt(end)

    header = (
        '<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n'
        '<?OFX OFXHEADER="200" VERSION="220" SECURITY="NONE" OLDFILEUID="NONE" NEWFILEUID="NONE"?>\n'
    )
    return header.encode("utf-8") + ET.tostring(ofx, encoding="utf-8")


__all__ = ["CSV_COLUMNS", "EXPORT_TOO_BIG", "MAX_EXPORT_ROWS", "csv_safe", "dre_csv", "entries_csv", "ledger_ofx", "money"]
