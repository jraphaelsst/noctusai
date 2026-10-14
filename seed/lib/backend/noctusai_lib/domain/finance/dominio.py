"""Domínio export (E16/E21): the accounting entries of a period in the Thomson Reuters Domínio "leiaute com separador".

`GET /exports/dominio.txt` turns the cash movements of a period into Domínio **lançamentos em lote** (record 6000 with child
6100 rows), using the contador's accounting codes: `fin_categories.accounting_code` for the P&L side and
`fin_accounts.accounting_code` for the bank/cash/gateway side. See `DOMINIO-LAYOUT.md` next to this file for what is verified
against the official layout + sample file and what is UNVERIFIED.

**Mapping (cash basis -- by `settled_on`, unreversed settlements only; the same facts the Livro Caixa lists)**

| fact                         | debit            | credit           |
|------------------------------|------------------|------------------|
| receivable payment           | account          | category         |
| receivable refund            | category         | account          |
| payable payment              | category         | account          |
| payable refund               | account          | category         |
| settlement fee               | fee category (*) | account          |
| gateway-sync fee (ledger)    | fee category (*) | account          |
| transfer between own accounts| destination acct | source account   |

(*) the default category `Taxas de cartão/gateway` for a receivable's fee / the gateway-sync fee, `Tarifas bancárias` for a payable's
fee (the same placement the DRE uses, `dre._FEE_NAME`). It is resolved BY NAME among the org's categories: rename or delete it and
the export asks for the mapping instead of guessing.

**Refusal, not guesswork.** If any category, account or fee category this period needs has no accounting code -- or a fact has no
category / no counter-part -- the call is refused 422 `dominio_codigos_ausentes` listing exactly what to fix. Nothing partial is ever
produced: a half-mapped file imported into the books is worse than none.

This is a *cash-movement* export. It does not create receivable/payable (accrual) postings, inventory or tax lines; the contador
completes the books. Sent to a licensed contador (CRC), not filed by the software.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any, Mapping, Optional

from noctusai_lib.primitives.accents import fold_accents_ascii
from noctusai_lib.primitives.identificador import cnpj_dv_valido, cpf_dv_valido

from ._common import Scope, to_date
from .dre import GATEWAY_FEE_DESCRIPTION_PREFIX, _fetch_by_ids
from .errors import FinanceError, invalid
from .exports import EXPORT_TOO_BIG, MAX_EXPORT_ROWS
from .types import EntryDirection, LedgerDirection, LedgerOrigin, SettlementKind

CODES_MISSING = "dominio_codigos_ausentes"
#: Domínio's `Descrição do histórico` has no stated length limit in the layout page; kept conservative. UNVERIFIED.
MAX_HISTORY_CHARS = 250
FEE_CATEGORY_RECEIVABLE = "Taxas de cartão/gateway"
FEE_CATEGORY_PAYABLE = "Tarifas bancárias"


def _ascii(text: Any, limit: int = MAX_HISTORY_CHARS) -> str:
    """Printable ASCII for the file: accents folded (`ç` -> `c`), the field separator and line breaks removed.

    The official sample is plain ASCII and the layout page states no encoding, so ASCII is the only form that cannot be
    misread on import. UNVERIFIED whether Domínio would accept cp1252 accents."""
    folded = fold_accents_ascii("" if text is None else str(text))
    return re.sub(r"[|\s]+", " ", folded).strip()[:limit]


def _value(cents: int) -> str:
    """`1234,56` -- comma decimal, no thousands separator, exactly as the official sample (`5571,24`)."""
    return f"{int(cents) // 100},{int(cents) % 100:02d}"


def _day(value: Any) -> str:
    d = to_date(value)
    return d.strftime("%d/%m/%Y")  # type: ignore[union-attr]


def _valid_inscription(raw: Optional[str]) -> str:
    cleaned = "".join(ch for ch in str(raw or "").upper() if ch.isalnum())
    if (len(cleaned) == 14 and cnpj_dv_valido(cleaned)) or (len(cleaned) == 11 and cleaned.isdigit() and cpf_dv_valido(cleaned)):
        return cleaned
    raise invalid("cnpj", "Informe o CNPJ (ou CPF) da empresa, com dígitos verificadores válidos.", code="inscricao_invalida")


def _norm_code(value: Any) -> Optional[str]:
    text = str(value).strip() if value is not None else ""
    return text or None


def dominio_export(
    s: Scope, date_from: date, date_to: date, *, inscription: str, history_code: Optional[int] = None, max_rows: int = MAX_EXPORT_ROWS,
) -> bytes:
    """The Domínio file for `[date_from, date_to]`. Raises 422 listing every missing code / unmappable fact."""
    if date_to < date_from:
        raise invalid("to", "A data final deve ser igual ou posterior à inicial.")
    company = _valid_inscription(inscription)
    start, end = date_from.isoformat(), date_to.isoformat()

    accounts = {str(a["id"]): a for a in s.rows("accounts")}
    cats = {str(c["id"]): c for c in s.rows("categories")}
    by_name = {str(c["name"]).strip().lower(): c for c in cats.values() if c.get("active", True)}

    sts = s.rows("settlements", refine=lambda q: q.is_("reversed_at", "null").gte("settled_on", start).lte("settled_on", end))
    entries = _fetch_by_ids(s, "entries", (str(st["entry_id"]) for st in sts))
    ledger = s.rows(
        "ledger", refine=lambda q: q.gte("occurred_on", start).lte("occurred_on", end).in_("origin", [LedgerOrigin.TRANSFER.value, LedgerOrigin.ADJUSTMENT.value]),
    )
    if len(sts) + len(ledger) > max_rows:
        raise FinanceError(
            EXPORT_TOO_BIG, f"A exportação tem {len(sts) + len(ledger)} movimentos; o limite é {max_rows}. Restrinja o período.", 422,
            details={"total": len(sts) + len(ledger), "limit": max_rows},
        )

    missing_cats: dict[str, str] = {}
    missing_accounts: dict[str, str] = {}
    issues: dict[str, int] = {}
    postings: list[tuple[str, str, str, int, str]] = []  # (day, debit, credit, cents, history)

    def issue(code: str) -> None:
        issues[code] = issues.get(code, 0) + 1

    def acct_code(account_id: Any) -> Optional[str]:
        a = accounts.get(str(account_id))
        if a is None:
            issue("conta_desconhecida")
            return None
        code = _norm_code(a.get("accounting_code"))
        if code is None:
            missing_accounts[str(a["id"])] = str(a["name"])
        return code

    def cat_code(cat: Optional[Mapping[str, Any]], label: str) -> Optional[str]:
        if cat is None:
            issue(label)
            return None
        code = _norm_code(cat.get("accounting_code"))
        if code is None:
            missing_cats[str(cat["id"])] = str(cat["name"])
        return code

    def fee_category(name: str) -> Optional[Mapping[str, Any]]:
        cat = by_name.get(name.lower())
        if cat is None:
            issue("categoria_de_tarifa_ausente:" + name)
        return cat

    for st in sorted(sts, key=lambda r: (str(r["settled_on"]), str(r["id"]))):
        entry = entries.get(str(st["entry_id"]))
        if entry is None:
            issue("baixa_sem_lancamento")
            continue
        receivable = entry["direction"] == EntryDirection.RECEIVABLE.value
        payment = st["kind"] == SettlementKind.PAYMENT.value
        cat = cats.get(str(entry["category_id"])) if entry.get("category_id") else None
        a_code = acct_code(st["account_id"])
        c_code = cat_code(cat, "lancamento_sem_categoria")
        day = _day(st["settled_on"])
        text = _ascii(entry.get("description"))
        cents = int(st["amount_cents"])
        money_in = receivable == payment  # money enters the account
        if a_code and c_code:
            postings.append((day, a_code, c_code, cents, text) if money_in else (day, c_code, a_code, cents, text))
        fee = int(st.get("fee_cents") or 0)
        if fee > 0:
            fcat = fee_category(FEE_CATEGORY_RECEIVABLE if receivable else FEE_CATEGORY_PAYABLE)
            f_code = cat_code(fcat, "tarifa_sem_categoria") if fcat else None
            if a_code and f_code:
                postings.append((day, f_code, a_code, fee, _ascii("Tarifa: " + str(entry.get("description") or ""))))

    transfers: dict[str, list[Mapping[str, Any]]] = {}
    reversed_ids = {str(r["reverses_id"]) for r in ledger if r.get("reverses_id")}
    for row in ledger:
        if row.get("reverses_id") or str(row["id"]) in reversed_ids:
            continue
        if row["origin"] == LedgerOrigin.TRANSFER.value:
            transfers.setdefault(str(row.get("transfer_group")), []).append(row)
        elif str(row.get("description") or "").startswith(GATEWAY_FEE_DESCRIPTION_PREFIX) and row["direction"] == LedgerDirection.OUT.value:
            a_code = acct_code(row["account_id"])
            fcat = fee_category(FEE_CATEGORY_RECEIVABLE)
            f_code = cat_code(fcat, "tarifa_sem_categoria") if fcat else None
            if a_code and f_code:
                postings.append((_day(row["occurred_on"]), f_code, a_code, int(row["amount_cents"]), _ascii(row.get("description"))))
        else:
            issue("ajuste_manual_sem_categoria")
    for group in transfers.values():
        outs = [r for r in group if r["direction"] == LedgerDirection.OUT.value]
        ins = [r for r in group if r["direction"] == LedgerDirection.IN.value]
        if len(outs) != 1 or len(ins) != 1:
            issue("transferencia_sem_contrapartida")
            continue
        src, dst = acct_code(outs[0]["account_id"]), acct_code(ins[0]["account_id"])
        if src and dst:
            postings.append((_day(outs[0]["occurred_on"]), dst, src, int(outs[0]["amount_cents"]), _ascii(outs[0].get("description") or "Transferencia entre contas")))

    if missing_cats or missing_accounts or issues:
        raise FinanceError(
            CODES_MISSING,
            "O Domínio precisa do código contábil de cada categoria e conta usadas no período. Preencha os códigos listados e exporte de novo.",
            422,
            details={
                "categories": [{"id": k, "name": v} for k, v in sorted(missing_cats.items(), key=lambda kv: kv[1].lower())],
                "accounts": [{"id": k, "name": v} for k, v in sorted(missing_accounts.items(), key=lambda kv: kv[1].lower())],
                "issues": [{"code": k, "count": v} for k, v in sorted(issues.items())],
            },
        )
    if not postings:
        raise FinanceError("dominio_sem_movimento", "Não há movimentos para exportar neste período.", 422)

    hist = "" if history_code is None else str(int(history_code))
    lines = [f"|0000|{company}|"]
    for day, debit, credit, cents, text in sorted(postings, key=lambda p: (p[0][6:] + p[0][3:5] + p[0][:2], p[4], p[1], p[2], p[3])):
        lines.append("|6000|X||||")  # one batch (one debit : one credit) per posting, exactly the sample's shape
        lines.append(f"|6100|{day}|{_ascii(debit, 40)}|{_ascii(credit, 40)}|{_value(cents)}|{hist}|{text}||||")  # usuário, filial, SCP left empty
    return ("\r\n".join(lines) + "\r\n").encode("ascii")


__all__ = ["CODES_MISSING", "dominio_export"]
