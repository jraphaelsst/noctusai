"""CSV export / import of items.

Export: UTF-8 with BOM (Excel reads accents), CRLF, `;`-free (comma) delimiter, money as exact `1234.56`
(from integer cents -- never a float), category as its `Pai > Filho` path. EVERY text cell starting with a
formula character (`= + - @ TAB CR`) is prefixed with `'` (CSV injection). More than `MAX_EXPORT_ROWS`
matching rows is REFUSED (422), never silently truncated.

Import: the header names the columns (`ITEM_CSV_COLUMNS`; `sku` + `name` required, unknown columns refused,
a column absent from the header is left alone). Delimiter `,` or `;` (auto). The whole file is VALIDATED
FIRST: any bad row => 422 `importacao_invalida` listing every problem (line + field + code), nothing written.
`update_existing=True` updates rows whose SKU exists (a BLANK cell leaves the stored value untouched --
export, edit, re-import never wipes a field by accident); otherwise an existing SKU is a row error.
`dry_run=True` validates and reports counts without writing. Categories are matched by path and must
already exist (`categoria_inexistente`) -- the import never invents a taxonomy.

Honest limit: PostgREST has no multi-statement transaction, so a database failure MID-write (not a
validation error -- those are all caught before the first write) can leave a prefix applied; re-running the
same file is safe (rows already created become updates with `update_existing=True`).
"""
from __future__ import annotations

import csv
import io
import re
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from noctusai_lib.primitives.postgrest_errors import is_unique_violation

from ._common import Scope, now_iso
from .categories import category_paths
from .errors import (
    EXPORTACAO_GRANDE_DEMAIS,
    IMPORTACAO_INVALIDA,
    SKU_DUPLICADO,
    ItemsError,
)
from .items import build_row, list_items, normalize_item
from .validators import normalize_sku

MAX_EXPORT_ROWS = 50_000
MAX_IMPORT_ROWS = 5_000
MAX_IMPORT_BYTES = 5 * 1024 * 1024
MAX_REPORTED_ERRORS = 100
ITEMS_IMPORT_PATH_PATTERN = "/api/items/import"
ITEMS_IMPORT_MAX_BYTES = MAX_IMPORT_BYTES + 1024 * 1024  # multipart framing headroom
_FORMULA_LEAD = ("=", "+", "-", "@", "\t", "\r")
_PAGE = 200

ITEM_CSV_COLUMNS = (
    "sku", "name", "description", "item_type", "unit", "category", "ncm", "cest", "cfop_default", "origem",
    "gtin", "cost", "price", "weight_g", "length_mm", "width_mm", "height_mm", "is_active",
)
_MONEY = {"cost": "cost_cents", "price": "price_cents"}
_INTS = ("origem", "weight_g", "length_mm", "width_mm", "height_mm")
_TRUE = {"1", "true", "sim", "s", "yes", "y", "ativo"}
_FALSE = {"0", "false", "nao", "não", "n", "no", "inativo"}


def csv_safe(value: Any) -> str:
    """One cell: text starting with a formula character is neutralised with a leading `'`."""
    text = "" if value is None else str(value)
    return "'" + text if text.startswith(_FORMULA_LEAD) else text


def money(cents: Any) -> str:
    """Integer cents -> `1234.56` (exact)."""
    return f"{Decimal(int(cents or 0)) / 100:.2f}"


# ─── export ──────────────────────────────────────────────────────────────────


def items_csv(
    s: Scope,
    *,
    q: Optional[str] = None,
    item_type: Optional[str] = None,
    category_id: Optional[Any] = None,
    active: Optional[bool] = None,
    max_rows: int = MAX_EXPORT_ROWS,
) -> bytes:
    """The items matching the same filters as `GET /items`, as a CSV (re-importable)."""
    filters = dict(q=q, item_type=item_type, category_id=category_id, active=active)
    rows, total, _, _ = list_items(s, page=1, page_size=_PAGE, **filters)
    if total > max_rows:
        raise ItemsError(
            EXPORTACAO_GRANDE_DEMAIS, f"A exportação tem {total} itens; o limite é {max_rows}. Filtre antes.", 422,
            details={"total": total, "limit": max_rows},
        )
    paths = category_paths(s)
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\r\n")
    writer.writerow(ITEM_CSV_COLUMNS)
    page = 1
    while True:
        for r in rows:
            writer.writerow([
                csv_safe(r.get("sku")), csv_safe(r.get("name")), csv_safe(r.get("description")),
                r.get("item_type") or "", r.get("unit") or "",
                csv_safe(paths.get(str(r["category_id"]), "")) if r.get("category_id") else "",
                r.get("ncm") or "", r.get("cest") or "", r.get("cfop_default") or "",
                "" if r.get("origem") is None else r["origem"],
                r.get("gtin") or "", money(r.get("cost_cents")),
                "" if r.get("price_cents") is None else money(r["price_cents"]),
                *("" if r.get(c) is None else r[c] for c in ("weight_g", "length_mm", "width_mm", "height_mm")),
                "true" if r.get("is_active", True) else "false",
            ])
        if page * _PAGE >= total:
            break
        page += 1
        rows, _, _, _ = list_items(s, page=page, page_size=_PAGE, **filters)
    return ("﻿" + out.getvalue()).encode("utf-8")


# ─── import ──────────────────────────────────────────────────────────────────


def _decode(data: bytes) -> str:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


def parse_money_cents(raw: str) -> int:
    """`12,50` | `1.234,56` | `1234.56` -> cents, exactly. More than 2 decimals is refused (`1.234` is ambiguous)."""
    text = raw.strip().replace(" ", "").replace("R$", "")
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ValueError(raw) from None
    if not value.is_finite() or value < 0 or value != value.quantize(Decimal("0.01")):
        raise ValueError(raw)
    return int(value * 100)


def _parse_bool(raw: str) -> bool:
    low = raw.strip().lower()
    if low in _TRUE:
        return True
    if low in _FALSE:
        return False
    raise ValueError(raw)


class _RowErrors:
    def __init__(self) -> None:
        self.items: list[dict] = []
        self.total = 0

    def add(self, line: int, field: str, code: str, message: str) -> None:
        self.total += 1
        if len(self.items) < MAX_REPORTED_ERRORS:
            self.items.append({"line": line, "field": field, "code": code, "message": message})


def _rows_from(data: bytes) -> tuple[list[str], list[tuple[int, list[str]]]]:
    text = _decode(data)
    if not text.strip():
        raise ItemsError(IMPORTACAO_INVALIDA, "O CSV está vazio.", 422)
    head = text.splitlines()[0]
    delimiter = ";" if head.count(";") > head.count(",") else ","
    try:
        all_rows = list(csv.reader(io.StringIO(text, newline=""), delimiter=delimiter))
    except csv.Error:
        raise ItemsError(IMPORTACAO_INVALIDA, "O CSV está malformado.", 422) from None
    header = [c.strip().lower() for c in all_rows[0]]
    body = [(i, row) for i, row in enumerate(all_rows[1:], start=2) if any(c.strip() for c in row)]
    return header, body


def import_items_csv(
    s: Scope, data: bytes, *, update_existing: bool = False, dry_run: bool = False
) -> dict:
    """Validate the whole file, then write. Returns `{created, updated, dry_run}`."""
    if len(data) > MAX_IMPORT_BYTES:
        raise ItemsError(IMPORTACAO_INVALIDA, "O arquivo é grande demais.", 413)
    header, body = _rows_from(data)
    unknown = [c for c in header if c not in ITEM_CSV_COLUMNS]
    if unknown:
        raise ItemsError(IMPORTACAO_INVALIDA, f"Colunas desconhecidas: {', '.join(unknown)}.", 422, details={"columns": unknown})
    missing = [c for c in ("sku", "name") if c not in header]
    if missing:
        raise ItemsError(IMPORTACAO_INVALIDA, f"Colunas obrigatórias ausentes: {', '.join(missing)}.", 422, details={"columns": missing})
    if len(header) != len(set(header)):
        raise ItemsError(IMPORTACAO_INVALIDA, "O cabeçalho repete colunas.", 422)
    if len(body) > MAX_IMPORT_ROWS:
        raise ItemsError(IMPORTACAO_INVALIDA, f"O arquivo tem {len(body)} linhas; o limite é {MAX_IMPORT_ROWS}.", 422)

    by_path = {path.lower(): cid for cid, path in category_paths(s).items()}
    existing = {str(r["sku"]).upper(): r for r in s.rows("items")}
    errors = _RowErrors()
    seen: dict[str, int] = {}
    plan: list[tuple[str, str, dict]] = []  # (op, sku, normalized fields)

    for line, cells in body:
        cell = {col: (cells[i].strip() if i < len(cells) else "") for i, col in enumerate(header)}
        fields: dict[str, Any] = {}
        ok = True

        def fail(field: str, code: str, message: str) -> None:
            nonlocal ok
            ok = False
            errors.add(line, field, code, message)

        for col in header:
            raw = cell[col]
            if col == "sku" or raw == "":
                continue
            try:
                if col in _MONEY:
                    fields[_MONEY[col]] = parse_money_cents(raw)
                elif col in _INTS:
                    fields[col] = int(raw)
                elif col == "is_active":
                    fields[col] = _parse_bool(raw)
                elif col == "category":
                    cid = by_path.get(re.sub(r"\s*>\s*", " > ", raw).lower())
                    if cid is None:
                        fail("category", "categoria_inexistente", f"Categoria '{raw}' não existe.")
                    else:
                        fields["category_id"] = cid
                else:
                    fields[col] = raw
            except ValueError:
                fail(col, "valor_invalido", f"Valor inválido em '{col}'.")
        try:
            sku = normalize_sku(cell["sku"])
        except ItemsError as exc:
            errors.add(line, "sku", exc.code, exc.message)
            continue
        if sku in seen:
            fail("sku", SKU_DUPLICADO, f"SKU repetido no arquivo (linha {seen[sku]}).")
            continue
        seen[sku] = line
        known = existing.get(sku)
        if known is not None and not update_existing:
            fail("sku", SKU_DUPLICADO, "Já existe um item com este SKU.")
        if known is None and not cell["name"]:
            fail("name", "campo_obrigatorio", "Informe o nome do item.")
        if ok:
            try:
                normalized = normalize_item(s, {"sku": sku, **fields}, partial=known is not None)
            except ItemsError as exc:
                errors.add(line, str(exc.details.get("field", "")), exc.code, exc.message)
                continue
            plan.append(("update" if known is not None else "create", sku, normalized))

    if errors.total:
        raise ItemsError(
            IMPORTACAO_INVALIDA,
            f"O arquivo tem {errors.total} problema(s); nada foi importado.",
            422,
            details={"errors": errors.items, "error_count": errors.total},
        )
    created = sum(1 for op, _, _ in plan if op == "create")
    updated = len(plan) - created
    if not dry_run:
        for op, sku, fields in plan:
            if op == "create":
                try:
                    s.tbl("items").insert(build_row(fields, s.org_id)).execute()
                except Exception as exc:
                    if is_unique_violation(exc):
                        raise ItemsError(SKU_DUPLICADO, f"O SKU {sku} foi criado por outra requisição.", 409) from exc
                    raise
            else:
                patch = {k: v for k, v in fields.items() if k != "sku"}
                if patch:
                    patch["updated_at"] = now_iso()
                    s.tbl("items").update(patch).eq("org_id", s.org_id).eq("id", str(existing[sku]["id"])).execute()
    return {"created": created, "updated": updated, "dry_run": dry_run}


__all__ = [
    "ITEMS_IMPORT_MAX_BYTES",
    "ITEMS_IMPORT_PATH_PATTERN",
    "ITEM_CSV_COLUMNS",
    "MAX_EXPORT_ROWS",
    "MAX_IMPORT_BYTES",
    "MAX_IMPORT_ROWS",
    "csv_safe",
    "import_items_csv",
    "items_csv",
    "money",
    "parse_money_cents",
]
