"""Parties CSV export / import.

* **Export** neutralises formula injection on EVERY text cell (`finance.exports.csv_safe`, the
  shared helper) and masks `doc` unless the caller is org admin (LGPD). More than
  `MAX_EXPORT_ROWS` rows is REFUSED (422), never silently truncated.
* **Import** is admin-only, row-by-row and non-atomic BY DESIGN: each row is validated with the
  same `PartyBody` the API uses; bad rows are REPORTED (`errors`), documents already registered are
  `skipped`, the rest are created. `dry_run=True` validates and detects duplicates (also inside the
  file) without writing. Cells keep the semicolon / comma dialect Excel-BR emits (auto-detected).
"""
from __future__ import annotations

import csv
import io
from typing import Any, Optional

from pydantic import ValidationError

from noctusai_lib.domain.finance.exports import csv_safe

from . import parties as svc
from ._common import Scope
from .errors import (
    EXPORTACAO_GRANDE_DEMAIS,
    IMPORTACAO_GRANDE_DEMAIS,
    IMPORTACAO_INVALIDA,
    PartiesError,
    invalid,
)
from .schemas import ADDRESS_FIELDS, PartyBody

MAX_EXPORT_ROWS = 20_000
MAX_IMPORT_ROWS = 5_000
MAX_IMPORT_BYTES = 5 * 1024 * 1024
#: Bodies above the seed's 1 MB webhook default: list `{IMPORT_UPLOAD_PATH_PATTERN: IMPORT_UPLOAD_MAX_BYTES}`
#: in `max_body_path_overrides` (create_product_app refuses to boot otherwise).
IMPORT_UPLOAD_PATH_PATTERN = "/api/parties/import"
IMPORT_UPLOAD_MAX_BYTES = MAX_IMPORT_BYTES + 1024 * 1024  # multipart framing headroom

_LIST_SEP = ";"
_ADDRESS_COLS = tuple(f"address_{k}" for k in ADDRESS_FIELDS)
CSV_COLUMNS = (
    "kind", "doc", "legal_name", "trade_name", "email", "phones", "roles",
    "state_registration", "municipal_registration", "is_active", "notes", *_ADDRESS_COLS,
)
#: pt-BR header spellings -> canonical column.
_ALIASES = {
    "tipo": "kind", "documento": "doc", "cpf_cnpj": "doc", "cpf/cnpj": "doc", "nome": "legal_name",
    "razao_social": "legal_name", "nome_fantasia": "trade_name", "telefones": "phones", "telefone": "phones",
    "papeis": "roles", "papéis": "roles", "inscricao_estadual": "state_registration",
    "inscricao_municipal": "municipal_registration", "ativo": "is_active", "observacoes": "notes",
}


# ─── export ──────────────────────────────────────────────────────────────────


def parties_csv(
    s: Scope, *, is_admin: bool, q: Optional[str] = None, kind: Optional[str] = None,
    role: Optional[str] = None, active: Optional[bool] = None, max_rows: int = MAX_EXPORT_ROWS,
) -> bytes:
    """UTF-8 (BOM, so Excel reads accents) CSV of the parties matching the same filters as `GET /`."""
    rows = svc.list_all(s, q=q, kind=kind, role=role, active=active, is_admin=is_admin)
    if len(rows) > max_rows:
        raise PartiesError(
            EXPORTACAO_GRANDE_DEMAIS, f"A exportação tem {len(rows)} linhas; o limite é {max_rows}. Restrinja o filtro.", 422,
            details={"total": len(rows), "limit": max_rows},
        )
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\r\n")
    writer.writerow(CSV_COLUMNS)
    for row in rows:
        p = svc.present_party(row, is_admin=is_admin, roles=row["roles"])
        addr = p.get("address") or {}
        writer.writerow([
            csv_safe(p["kind"]), csv_safe(p.get("doc")), csv_safe(p.get("legal_name")), csv_safe(p.get("trade_name")),
            csv_safe(p.get("email")), csv_safe(_LIST_SEP.join(p.get("phones") or [])),
            csv_safe(_LIST_SEP.join(p["roles"])), csv_safe(p.get("state_registration")),
            csv_safe(p.get("municipal_registration")), "sim" if p.get("is_active", True) else "nao",
            csv_safe(p.get("notes")), *(csv_safe(addr.get(k)) for k in ADDRESS_FIELDS),
        ])
    return b"\xef\xbb\xbf" + out.getvalue().encode("utf-8")


# ─── import ──────────────────────────────────────────────────────────────────


def _decode(data: bytes) -> str:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


def _split(cell: str) -> list[str]:
    return [part.strip() for part in cell.replace(",", _LIST_SEP).split(_LIST_SEP) if part.strip()]


def _row_to_body(row: dict[str, str]) -> dict[str, Any]:
    body: dict[str, Any] = {"kind": (row.get("kind") or "").strip().upper()}
    for key in ("doc", "legal_name", "trade_name", "email", "state_registration", "municipal_registration", "notes"):
        if (row.get(key) or "").strip():
            body[key] = row[key].strip()
    if (row.get("phones") or "").strip():
        body["phones"] = _split(row["phones"])
    if (row.get("roles") or "").strip():
        body["roles"] = [r.lower() for r in _split(row["roles"])]
    addr = {k: row[f"address_{k}"].strip() for k in ADDRESS_FIELDS if (row.get(f"address_{k}") or "").strip()}
    if addr:
        body["address"] = addr
    return body


def _read(data: bytes) -> list[tuple[int, dict[str, str]]]:
    if len(data) > MAX_IMPORT_BYTES:
        raise PartiesError(
            IMPORTACAO_GRANDE_DEMAIS, f"O arquivo passa de {MAX_IMPORT_BYTES // (1024 * 1024)} MB.", 413,
            details={"limit_bytes": MAX_IMPORT_BYTES},
        )
    text = _decode(data)
    if not text.strip():
        raise invalid("file", "O arquivo está vazio.", code=IMPORTACAO_INVALIDA)
    head = text.splitlines()[0]
    delimiter = ";" if head.count(";") > head.count(",") else ","
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    header = [(_ALIASES.get(h.strip().lower(), h.strip().lower())) for h in next(reader)]
    if "kind" not in header or "legal_name" not in header:
        raise invalid("file", "O cabeçalho precisa das colunas kind (tipo) e legal_name (nome).", code=IMPORTACAO_INVALIDA)
    rows: list[tuple[int, dict[str, str]]] = []
    for line, cells in enumerate(reader, start=2):
        if not any(c.strip() for c in cells):
            continue
        rows.append((line, dict(zip(header, cells))))
    if len(rows) > MAX_IMPORT_ROWS:
        raise PartiesError(
            IMPORTACAO_GRANDE_DEMAIS, f"O arquivo tem {len(rows)} linhas; o limite é {MAX_IMPORT_ROWS}.", 422,
            details={"total": len(rows), "limit": MAX_IMPORT_ROWS},
        )
    return rows


def import_parties(s: Scope, data: bytes, *, dry_run: bool = False) -> dict:
    """Import a CSV. Returns `{dry_run, created, skipped: [...], errors: [...]}` (line numbers are file lines)."""
    created = 0
    skipped: list[dict] = []
    errors: list[dict] = []
    seen_docs: set[str] = set()
    for line, row in _read(data):
        try:
            body = PartyBody.model_validate(_row_to_body(row))
            payload = body.model_dump(mode="python")
            doc = svc.normalize_doc(payload["kind"].value, payload.get("doc"))
            if doc and (doc in seen_docs or svc.find_by_doc(s, doc)):
                skipped.append({"line": line, "reason": "documento_duplicado", "doc_present": True})
                continue
            if dry_run:
                svc.normalize_phones(payload.get("phones"))
                svc.normalize_email(payload.get("email"))
            else:
                svc.create_party(s, payload)
            if doc:
                seen_docs.add(doc)
            created += 1
        except ValidationError as exc:
            first_err = exc.errors()[0]
            errors.append({"line": line, "field": ".".join(str(p) for p in first_err["loc"]) or None, "message": first_err["msg"]})
        except PartiesError as exc:
            errors.append({"line": line, "field": (exc.details or {}).get("field"), "code": exc.code, "message": exc.message})
    return {"dry_run": dry_run, "created": created, "skipped": skipped, "errors": errors}


__all__ = [
    "CSV_COLUMNS",
    "IMPORT_UPLOAD_MAX_BYTES",
    "IMPORT_UPLOAD_PATH_PATTERN",
    "MAX_EXPORT_ROWS",
    "MAX_IMPORT_BYTES",
    "MAX_IMPORT_ROWS",
    "import_parties",
    "parties_csv",
]
