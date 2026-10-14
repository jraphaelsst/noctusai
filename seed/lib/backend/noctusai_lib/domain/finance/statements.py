"""Bank statement import (OFX 1.x/2.x, CSV): caps, dedupe, persistence, suggestions.

Order of defences (every one runs BEFORE the expensive or dangerous step):

1. **size** -- more than `MAX_STATEMENT_BYTES` => 413 `extrato_grande_demais`;
2. **line cap** -- more than `MAX_STATEMENT_LINES` (raw newlines / `<STMTTRN>` blocks) => 422
   `extrato_linhas_demais`, counted on the BYTES, before any parser sees them;
3. **sha256 re-import** -- the same file into the same account => 409 `extrato_ja_importado`.
   The lookup is `(org, account, sha256)`; the message never names another account;
4. only then the format parser (`ofx.py` / `csv_import.py`).

The raw file is NOT retained (bank statements are personal data; contract §3.2 keeps only the
sha256 + the parsed lines). Re-uploading an OVERLAPPING statement skips lines whose
`fitid` is already on the account instead of failing the whole import.

PostgREST has no multi-statement transaction: the import row is written first (its
unique `(account, sha256)` makes a concurrent double upload lose with a 409), the lines
second, and a failure in between deletes the import row (lines cascade) so a retry is clean.
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Optional

from noctusai_lib.integrations.persistence.table_reads import IN_FILTER_BATCH, batched
from noctusai_lib.primitives.postgrest_errors import is_unique_violation

from ._common import Scope, first, iso, new_id, now_iso
from .accounts import require_usable_account
from .csv_import import CsvColumnMap, parse_csv
from .errors import FinanceError, conflict, invalid
from .matching import apply_suggestions
from .ofx import EXTRATO_INVALIDO, ParsedStatement, count_transactions, looks_like_ofx, parse_ofx
from .types import MatchStatus, StatementFormat, values

logger = logging.getLogger(__name__)

MAX_STATEMENT_BYTES = 5 * 1024 * 1024
MAX_STATEMENT_LINES = 50_000
#: `POST /statements` is an `UploadFile` route: the host MUST list it in `max_body_path_overrides`
#: (`{STATEMENT_UPLOAD_PATH_PATTERN: STATEMENT_UPLOAD_MAX_BYTES}`) or the 1 MB webhook default 413s a real file.
STATEMENT_UPLOAD_PATH_PATTERN = "/api/finance/statements"
STATEMENT_UPLOAD_MAX_BYTES = MAX_STATEMENT_BYTES + 1024 * 1024  # multipart framing headroom
INSERT_BATCH = 500

EXTRATO_JA_IMPORTADO = "extrato_ja_importado"
EXTRATO_GRANDE_DEMAIS = "extrato_grande_demais"
EXTRATO_LINHAS_DEMAIS = "extrato_linhas_demais"
EXTRATO_FORMATO = "extrato_formato_desconhecido"
COLUNAS_OBRIGATORIAS = "mapa_de_colunas_obrigatorio"


def parse_column_map(raw: Optional[str]) -> Optional[CsvColumnMap]:
    """The `column_map` form field (JSON text) -> a validated map; `None` when absent."""
    if raw is None or not raw.strip():
        return None
    if len(raw) > 4096:
        raise invalid("column_map", "Mapa de colunas grande demais.", code="mapa_de_colunas_invalido")
    try:
        return CsvColumnMap.model_validate(json.loads(raw))
    except (ValueError, TypeError) as exc:  # json.JSONDecodeError and pydantic.ValidationError are ValueErrors
        raise invalid("column_map", "Mapa de colunas inválido.", code="mapa_de_colunas_invalido") from exc


def detect_format(filename: Optional[str], data: bytes, declared: Optional[str]) -> str:
    if declared:
        if declared not in values(StatementFormat):
            raise invalid("format", "Formato inválido (use ofx ou csv).")
        return declared
    name = (filename or "").lower()
    if name.endswith((".ofx", ".qfx")) or looks_like_ofx(data):
        return StatementFormat.OFX.value
    if name.endswith((".csv", ".txt")):
        return StatementFormat.CSV.value
    raise FinanceError(EXTRATO_FORMATO, "Não foi possível identificar o formato do extrato (OFX ou CSV).", 422)


def check_caps(data: bytes, fmt_hint: Optional[str] = None) -> None:
    """Size, then line count -- on the raw bytes, BEFORE any parser runs."""
    if len(data) > MAX_STATEMENT_BYTES:
        raise FinanceError(EXTRATO_GRANDE_DEMAIS, "O extrato excede o limite de 5 MB.", 413)
    if not data.strip():
        raise FinanceError(EXTRATO_INVALIDO, "O arquivo está vazio.", 422)
    # newlines for text formats; an OFX 2.x file may be ONE line, so its transaction blocks count too
    if data.count(b"\n") + 1 > MAX_STATEMENT_LINES or count_transactions(data) > MAX_STATEMENT_LINES:
        raise FinanceError(EXTRATO_LINHAS_DEMAIS, "O extrato excede o limite de 50 mil linhas.", 422)


def parse_statement(fmt: str, data: bytes, *, account_id: str, column_map: Optional[CsvColumnMap]) -> ParsedStatement:
    if fmt == StatementFormat.OFX.value:
        return parse_ofx(data)
    if column_map is None:
        raise invalid("column_map", "Informe o mapa de colunas para importar um CSV.", code=COLUNAS_OBRIGATORIAS)
    return parse_csv(data, column_map, account_id=account_id)


def _existing_fitids(s: Scope, account_id: str, fitids: list[str]) -> set[str]:
    have: set[str] = set()
    for chunk in batched(fitids, IN_FILTER_BATCH):
        # postgrest-unbounded-ok: one IN_FILTER_BATCH of fitids, unique per account
        resp = (
            s.tbl("statement_lines").select("fitid").eq("org_id", s.org_id).eq("account_id", account_id)
            .in_("fitid", chunk).limit(len(chunk)).execute()
        )
        have.update(str(r["fitid"]) for r in (resp.data or []))
    return have


def import_statement(
    s: Scope,
    account_id: Any,
    *,
    filename: Optional[str],
    data: bytes,
    fmt: Optional[str] = None,
    column_map: Optional[CsvColumnMap] = None,
    user_id: Optional[str] = None,
) -> dict:
    """Import one statement file into one of the org's accounts.

    Returns `{import, lines: n_new, duplicates_skipped, skipped_zero, suggested}`.
    """
    check_caps(data)
    account = require_usable_account(s, account_id)
    digest = hashlib.sha256(data).hexdigest()
    prior = (
        s.tbl("statement_imports").select("id").eq("org_id", s.org_id).eq("account_id", str(account["id"]))
        .eq("sha256", digest).limit(1).execute()
    )
    if prior.data:
        raise conflict(EXTRATO_JA_IMPORTADO, "Este extrato já foi importado nesta conta.")
    fmt = detect_format(filename, data, fmt)
    parsed = parse_statement(fmt, data, account_id=str(account["id"]), column_map=column_map)

    import_row = {
        "id": new_id(),
        "org_id": s.org_id,
        "account_id": str(account["id"]),
        "format": fmt,
        "filename": (filename or "extrato")[:255],
        "sha256": digest,
        "period_start": iso(parsed.period_start),
        "period_end": iso(parsed.period_end),
        "imported_by": user_id,
        "at": now_iso(),
    }
    try:
        saved = first(s.tbl("statement_imports").insert(import_row).execute()) or import_row
    except Exception as exc:
        if is_unique_violation(exc):
            raise conflict(EXTRATO_JA_IMPORTADO, "Este extrato já foi importado nesta conta.") from exc
        raise

    try:
        have = _existing_fitids(s, str(account["id"]), [l.fitid for l in parsed.lines])
        fresh = [l for l in parsed.lines if l.fitid not in have]
        rows = [
            {
                "id": new_id(),
                "org_id": s.org_id,
                "import_id": saved["id"],
                "account_id": str(account["id"]),
                "posted_on": l.posted_on.isoformat(),
                "amount_cents": l.amount_cents,
                "description": l.description,
                "fitid": l.fitid,
                "match_status": MatchStatus.UNMATCHED.value,
                "ledger_id": None,
                "suggested_entry_id": None,
            }
            for l in fresh
        ]
        for chunk in batched(rows, INSERT_BATCH):
            s.tbl("statement_lines").insert(chunk).execute()
    except Exception:
        _discard_import(s, str(saved["id"]))
        raise
    try:
        suggested = apply_suggestions(s, str(account["id"]), rows)
    except Exception:
        # Suggestions are a convenience over lines that are already safely stored: never fail the import.
        logger.exception("finance: statement import %s stored but suggesting matches failed", saved["id"])
        suggested = 0
    return {
        "import": saved,
        "lines": len(rows),
        "duplicates_skipped": len(parsed.lines) - len(rows),
        "skipped_zero": parsed.skipped_zero,
        "suggested": suggested,
    }


def _discard_import(s: Scope, import_id: str) -> None:
    try:
        s.tbl("statement_lines").delete().eq("org_id", s.org_id).eq("import_id", import_id).execute()
        s.tbl("statement_imports").delete().eq("org_id", s.org_id).eq("id", import_id).execute()
    except Exception:
        logger.exception("finance: could not roll back half-written statement import %s", import_id)


def list_imports(s: Scope, *, account_id: Optional[Any] = None, page: int = 1, page_size: int = 20):
    return s.page(
        "statement_imports",
        page=page,
        page_size=page_size,
        refine=(lambda q: q.eq("account_id", str(account_id))) if account_id else None,
        order=(("at", True), ("id", True)),
    )


def list_lines(s: Scope, import_id: Any, *, match_status: Optional[str] = None, page: int = 1, page_size: int = 50):
    s.get("statement_imports", import_id, what="Extrato")
    if match_status is not None and match_status not in values(MatchStatus):
        raise invalid("match_status", "Situação inválida.")

    def refine(q):
        q = q.eq("import_id", str(import_id))
        return q.eq("match_status", match_status) if match_status else q

    return s.page("statement_lines", page=page, page_size=page_size, refine=refine,
                  order=(("posted_on", False), ("id", False)))


__all__ = [
    "COLUNAS_OBRIGATORIAS",
    "EXTRATO_FORMATO",
    "EXTRATO_GRANDE_DEMAIS",
    "EXTRATO_JA_IMPORTADO",
    "EXTRATO_LINHAS_DEMAIS",
    "MAX_STATEMENT_BYTES",
    "MAX_STATEMENT_LINES",
    "STATEMENT_UPLOAD_MAX_BYTES",
    "STATEMENT_UPLOAD_PATH_PATTERN",
    "check_caps",
    "detect_format",
    "import_statement",
    "list_imports",
    "list_lines",
    "parse_column_map",
    "parse_statement",
]
