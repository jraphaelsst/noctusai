"""Reconciliation: suggest and apply a match between a statement line and an entry.

**Match order (contract §3.4) -- link first, settle only if still open.** A statement line
is the BANK's record of money that moved. Money the organ already knows about (a commerce
payment the bridge settled, a gateway sync) sits in `fin_ledger` unreconciled; matching the
line to it books NOTHING new -- it only stamps `statement_line.ledger_id`. A settlement is
created only when the entry is still open (the manual-payment case that erp-imobiliario
never booked). Doing it the other way round would double-count the same money.

Direction convention: a line's `amount_cents` is signed (money IN positive); a ledger row
carries `direction`. Both sides are compared in that vocabulary.

Auto-suggestion (never auto-applies): same amount, within `SUGGEST_WINDOW_DAYS`, same
direction. An unreconciled ledger row is preferred over an open entry; two lines never get
the same candidate (greedy, by posted date).
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any, Optional

from noctusai_lib.integrations.persistence.table_reads import IN_FILTER_BATCH, batched
from noctusai_lib.primitives.postgrest_errors import is_unique_violation

from ._common import Scope, iso, to_date
from .entries import get_entry
from .errors import FinanceError, conflict, invalid
from .settlements import settle_entry
from .types import EntryDirection, EntryStatus, LedgerDirection, LedgerOrigin, MatchStatus, SettlementKind

logger = logging.getLogger(__name__)

SUGGEST_WINDOW_DAYS = 3
LINHA_JA_CONCILIADA = "linha_ja_conciliada"
LINHA_IGNORADA = "linha_ignorada"
LEDGER_JA_CONCILIADO = "ledger_ja_conciliado"
LANCAMENTO_JA_BAIXADO = "lancamento_ja_baixado"
DIRECAO_DIVERGENTE = "direcao_divergente"

_OPEN = (EntryStatus.OPEN.value, EntryStatus.PARTIAL.value)
_PENDING = (MatchStatus.UNMATCHED.value, MatchStatus.SUGGESTED.value)


def line_direction(amount_cents: int) -> str:
    return LedgerDirection.IN.value if int(amount_cents) > 0 else LedgerDirection.OUT.value


def _days(a: Any, b: Any) -> int:
    return abs((to_date(a) - to_date(b)).days)  # type: ignore[operator]


# ─── ledger pool ─────────────────────────────────────────────────────────────


def _ids_with(s: Scope, table: str, column: str, ids: list[str]) -> set[str]:
    """Which of `ids` appear in `table.column` (batched: `.in_()` rides in the URL)."""
    found: set[str] = set()
    for chunk in batched(ids, IN_FILTER_BATCH):
        # postgrest-unbounded-ok: one IN_FILTER_BATCH of ids; each id matches at most a handful of rows
        resp = s.tbl(table).select(column).eq("org_id", s.org_id).in_(column, chunk).limit(len(chunk) * 4).execute()
        found.update(str(r[column]) for r in (resp.data or []) if r.get(column))
    return found


def unreconciled(s: Scope, rows: list[dict]) -> list[dict]:
    """The `settlement` ledger rows among `rows` that are live and not yet tied to any statement line."""
    cands = [r for r in rows if r.get("origin") == LedgerOrigin.SETTLEMENT.value and not r.get("reverses_id")]
    if not cands:
        return []
    ids = [str(r["id"]) for r in cands]
    gone = _ids_with(s, "ledger", "reverses_id", ids) | _ids_with(s, "statement_lines", "ledger_id", ids)
    return [r for r in cands if str(r["id"]) not in gone]


def ledger_pool(s: Scope, account_id: Any, date_from: date, date_to: date) -> list[dict]:
    """Unreconciled settlement ledger rows of the account within `[date_from, date_to]`."""
    rows = s.rows(
        "ledger",
        eq={"account_id": str(account_id)},
        refine=lambda q: q.eq("origin", LedgerOrigin.SETTLEMENT.value)
        .is_("reverses_id", "null")
        .gte("occurred_on", date_from.isoformat())
        .lte("occurred_on", date_to.isoformat()),
    )
    return unreconciled(s, rows)


def _entry_ids_for(s: Scope, ledger_rows: list[dict]) -> dict[str, str]:
    """ledger id -> entry id (through the ledger row's settlement)."""
    sids = sorted({str(r["settlement_id"]) for r in ledger_rows if r.get("settlement_id")})
    by_settlement: dict[str, str] = {}
    for chunk in batched(sids, IN_FILTER_BATCH):
        # postgrest-unbounded-ok: one IN_FILTER_BATCH of settlement ids, one row each
        resp = s.tbl("settlements").select("id,entry_id").eq("org_id", s.org_id).in_("id", chunk).limit(len(chunk)).execute()
        by_settlement.update({str(r["id"]): str(r["entry_id"]) for r in (resp.data or [])})
    return {str(r["id"]): by_settlement[str(r["settlement_id"])] for r in ledger_rows if str(r.get("settlement_id")) in by_settlement}


# ─── suggestion ──────────────────────────────────────────────────────────────


def suggest_for_lines(s: Scope, account_id: Any, lines: list[dict]) -> dict[str, str]:
    """`{line_id: entry_id}` for the pending `lines` of one account (read-only)."""
    pending = sorted(
        (l for l in lines if l["match_status"] in _PENDING and int(l["amount_cents"]) != 0),
        key=lambda l: (str(l["posted_on"]), str(l["id"])),
    )
    if not pending:
        return {}
    window = timedelta(days=SUGGEST_WINDOW_DAYS)
    first_day = to_date(min(l["posted_on"] for l in pending)) - window  # type: ignore[operator]
    last_day = to_date(max(l["posted_on"] for l in pending)) + window  # type: ignore[operator]

    pool = ledger_pool(s, account_id, first_day, last_day)
    pool_entry = _entry_ids_for(s, pool)
    open_entries = s.rows(
        "entries",
        refine=lambda q: q.in_("status", list(_OPEN))  # postgrest-unbounded-ok: two literal enum values
        .gte("due_date", first_day.isoformat())
        .lte("due_date", last_day.isoformat()),
    )
    taken_ledger: set[str] = set()
    taken_entries: set[str] = set()
    out: dict[str, str] = {}
    for line in pending:
        amount = abs(int(line["amount_cents"]))
        direction = line_direction(line["amount_cents"])
        best: Optional[tuple[int, str, str]] = None  # (distance, tiebreak id, entry id)
        best_ledger: Optional[str] = None
        for row in pool:
            rid = str(row["id"])
            eid = pool_entry.get(rid)
            if (
                eid is None or rid in taken_ledger or row["direction"] != direction
                or int(row["amount_cents"]) != amount or eid in taken_entries
                or _days(row["occurred_on"], line["posted_on"]) > SUGGEST_WINDOW_DAYS
            ):
                continue
            cand = (_days(row["occurred_on"], line["posted_on"]), rid, eid)
            if best is None or cand < best:
                best, best_ledger = cand, rid
        if best is not None and best_ledger is not None:
            taken_ledger.add(best_ledger)
            taken_entries.add(best[2])
            out[str(line["id"])] = best[2]
            continue
        wanted = EntryDirection.RECEIVABLE.value if direction == LedgerDirection.IN.value else EntryDirection.PAYABLE.value
        best = None
        for e in open_entries:
            eid = str(e["id"])
            if (
                e["direction"] != wanted or eid in taken_entries
                or int(e["amount_cents"]) - int(e.get("settled_cents") or 0) != amount
                or _days(e["due_date"], line["posted_on"]) > SUGGEST_WINDOW_DAYS
            ):
                continue
            cand = (_days(e["due_date"], line["posted_on"]), eid, eid)
            if best is None or cand < best:
                best = cand
        if best is not None:
            taken_entries.add(best[2])
            out[str(line["id"])] = best[2]
    return out


def apply_suggestions(s: Scope, account_id: Any, lines: list[dict]) -> int:
    """Persist `suggest_for_lines` (status `suggested` + `suggested_entry_id`); returns how many lines got one."""
    found = suggest_for_lines(s, account_id, lines)
    for line_id, entry_id in found.items():
        s.tbl("statement_lines").update(
            {"match_status": MatchStatus.SUGGESTED.value, "suggested_entry_id": entry_id}
        ).eq("org_id", s.org_id).eq("id", line_id).in_("match_status", list(_PENDING)).execute()  # postgrest-unbounded-ok: two literals
    return len(found)


# ─── match ───────────────────────────────────────────────────────────────────


def _require_pending_line(s: Scope, line_id: Any) -> dict:
    line = s.get("statement_lines", line_id, what="Linha de extrato")
    if line["match_status"] == MatchStatus.MATCHED.value:
        raise conflict(LINHA_JA_CONCILIADA, "Esta linha já está conciliada.")
    if line["match_status"] == MatchStatus.IGNORED.value:
        raise conflict(LINHA_IGNORADA, "Esta linha foi ignorada; ela não pode ser conciliada.")
    return line


def _link(s: Scope, line: dict, ledger_id: str, entry_id: str) -> dict:
    patch = {"ledger_id": ledger_id, "match_status": MatchStatus.MATCHED.value, "suggested_entry_id": entry_id}
    try:
        s.tbl("statement_lines").update(patch).eq("org_id", s.org_id).eq("id", str(line["id"])).in_(
            "match_status", list(_PENDING)  # postgrest-unbounded-ok: two literals
        ).execute()
    except Exception as exc:
        if is_unique_violation(exc):
            raise conflict(LEDGER_JA_CONCILIADO, "Este movimento já está conciliado com outra linha.") from exc
        raise
    return {**line, **patch}


def _entry_ledger_candidates(s: Scope, entry_id: str, line: dict) -> list[dict]:
    """Unreconciled ledger rows of THIS entry's live settlements that equal the line (same account, direction, amount)."""
    settlements = s.rows("settlements", eq={"entry_id": entry_id}, refine=lambda q: q.is_("reversed_at", "null"))
    mine = [st for st in settlements if str(st["account_id"]) == str(line["account_id"])]
    if not mine:
        return []
    rows: list[dict] = []
    for st in mine:
        rows.extend(s.rows("ledger", eq={"settlement_id": str(st["id"])}))
    wanted = line_direction(line["amount_cents"])
    rows = [r for r in rows if r["direction"] == wanted and int(r["amount_cents"]) == abs(int(line["amount_cents"]))]
    return sorted(unreconciled(s, rows), key=lambda r: (_days(r["occurred_on"], line["posted_on"]), str(r["id"])))


def match_line(s: Scope, line_id: Any, entry_id: Any, *, user_id: Optional[str] = None) -> dict:
    """Reconcile a statement line with an entry. Returns `{line, entry, ledger_id, settlement_id, created_settlement}`."""
    line = _require_pending_line(s, line_id)
    entry = get_entry(s, entry_id)  # 404 for a foreign-org id
    if entry["status"] == EntryStatus.CANCELLED.value:
        raise conflict("lancamento_cancelado", "O lançamento está cancelado.")

    # 1. money the organ already knows about: link, book nothing.
    candidates = _entry_ledger_candidates(s, str(entry["id"]), line)
    if candidates:
        row = candidates[0]
        linked = _link(s, line, str(row["id"]), str(entry["id"]))
        return {"line": linked, "entry": entry, "ledger_id": str(row["id"]),
                "settlement_id": str(row["settlement_id"]), "created_settlement": False}

    # 2. nothing to link to: settle -- but only an entry that is still open.
    amount = abs(int(line["amount_cents"]))
    wanted_dir = EntryDirection.RECEIVABLE.value if int(line["amount_cents"]) > 0 else EntryDirection.PAYABLE.value
    if entry["direction"] != wanted_dir:
        raise invalid("entry_id", "O sentido do lançamento não combina com a linha do extrato.", code=DIRECAO_DIVERGENTE)
    if entry["status"] not in _OPEN:
        raise conflict(
            LANCAMENTO_JA_BAIXADO,
            "O lançamento já está baixado e nenhum movimento pendente de conciliação corresponde a esta linha.",
        )
    result = settle_entry(
        s,
        entry["id"],
        {
            "account_id": line["account_id"],
            "kind": SettlementKind.PAYMENT.value,
            "settled_on": iso(line["posted_on"]),
            "amount_cents": amount,
            "method": "statement",
            # idempotent on a double click / retry: the replay finds this settlement instead of booking a second
            "external_ref": f"stmt:{line['id']}",
            "statement_line_id": line["id"],
        },
        user_id=user_id,
    )
    settlement = result["settlement"]
    ledger_rows = [
        r for r in s.rows("ledger", eq={"settlement_id": str(settlement["id"])})
        if r["origin"] == LedgerOrigin.SETTLEMENT.value and not r.get("reverses_id")
    ]
    if not ledger_rows:  # settle_entry heals/books these; an empty set means the write did not land
        raise FinanceError("conciliacao_falhou", "A baixa não gerou movimento no razão; tente novamente.", 500)
    linked = _link(s, line, str(ledger_rows[0]["id"]), str(entry["id"]))
    return {"line": linked, "entry": result["entry"], "ledger_id": str(ledger_rows[0]["id"]),
            "settlement_id": str(settlement["id"]), "created_settlement": not result["replayed"]}


def ignore_line(s: Scope, line_id: Any) -> dict:
    line = s.get("statement_lines", line_id, what="Linha de extrato")
    if line["match_status"] == MatchStatus.MATCHED.value:
        raise conflict(LINHA_JA_CONCILIADA, "Esta linha já está conciliada.")
    if line["match_status"] == MatchStatus.IGNORED.value:
        return line
    patch = {"match_status": MatchStatus.IGNORED.value, "suggested_entry_id": None}
    s.tbl("statement_lines").update(patch).eq("org_id", s.org_id).eq("id", str(line["id"])).in_(
        "match_status", list(_PENDING)  # postgrest-unbounded-ok: two literals
    ).execute()
    return {**line, **patch}


__all__ = [
    "DIRECAO_DIVERGENTE",
    "LANCAMENTO_JA_BAIXADO",
    "LEDGER_JA_CONCILIADO",
    "LINHA_IGNORADA",
    "LINHA_JA_CONCILIADA",
    "SUGGEST_WINDOW_DAYS",
    "apply_suggestions",
    "ignore_line",
    "ledger_pool",
    "line_direction",
    "match_line",
    "suggest_for_lines",
    "unreconciled",
]
