"""Per-sheet column-shape detection — anchored on ``ORIGEM`` always being
column index 2 (verified empirically across all 29 monthly sheets), then
locating the CONTATO column by VALUE VOCABULARY (phone/email pattern),
working outward from there. No hardcoded per-sheet column map: the same
detector runs against every sheet and empirically resolves to 3 distinct
shapes (a NOVO/RETORNO-column shape used by the 5 most-recent 2026
sheets, and two no-NOVO/RETORNO-column shapes that differ only in
whether a TIER column is present) — fewer than the "5 shapes" impression
in the brief, because two of those turned out to be the SAME shape once
detected by value rather than by header text (several sheets' header ROW
carries a stray leaked value in the ORIGEM/CODIGO header cell — e.g.
``FEVEREIRO_2026``'s header row literally contains ``"SENSEYS"`` at
column 2 — which would corrupt a header-text-based detector; this one
never reads the header row for shape decisions, only the classified data
rows).

Row classification (header-like / blank / candidate-data) happens BEFORE
shape detection so header debris never leaks into the sample (this
matters for `` MARÇO_24``'s header row, which carries extra junk columns
--— ``ADILAINE``/a phone number/``ALE``/a note — that are not part of any
real data row).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

ORIGEM_COL = 2  # verified: column index 2 in all 29 monthly sheets
_MIN_LEAD_COL = 3
_MAX_SCAN_COL = 10
_TIER_VOCAB = {"SIMPLES", "DESTAQUE", "SUPER DESTAQUE", "TRIPLO DESTAQUE"}
_NOVO_RETORNO_VOCAB = {"NOVO", "RETORNO"}


def _norm(value: Any) -> str:
    return "" if value is None else str(value).strip()


def is_header_like(row: tuple) -> bool:
    """A row is header-like when column 0 is literally ``"DATA"`` or
    column 1 is literally ``"CODIGO"``/``"CODIGOS"`` (case-insensitive) —
    a signal that never appears in a real DATA/CODIGO data cell, so it
    reliably catches BOTH the row-1 header (most sheets) and the row-2
    header (``AGOSTO_24`` / ``FEVEREIRO_25``) without needing to know in
    advance which row number the header lands on."""
    if len(row) < 2:
        return False
    c0 = _norm(row[0]).upper()
    c1 = _norm(row[1]).upper()
    return c0 == "DATA" or c1 in ("CODIGO", "CODIGOS")


def is_blank(row: tuple) -> bool:
    return all(v is None or (isinstance(v, str) and not v.strip()) for v in row)


def is_phone_or_email(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    if "@" in value:
        return True
    digits = "".join(ch for ch in value if ch.isdigit())
    return len(digits) >= 8


@dataclass(frozen=True)
class SheetShape:
    contato_idx: int
    cliente_idx: int
    corretor_idx: int
    novo_retorno_idx: Optional[int]
    tier_idx: Optional[int]


def detect_shape(sample_rows: list[tuple]) -> SheetShape:
    """Detect the column shape from a sample of already-classified
    candidate-data rows (blank/header rows excluded by the caller).

    Algorithm (value-vocabulary, not header text):
      1. ``contato_idx`` = the column (3..9) with the most phone/email-
         pattern matches by ABSOLUTE COUNT (not fraction — a rare column
         that happens to be 100%-phone on a handful of rows must not
         outrank the real, high-volume contato column; this is exactly
         what happened on ``ABRIL_24``, which occasionally packs a
         SECOND lead's phone into columns 8, discovered while validating
         this detector against the real workbook).
      2. ``corretor_idx`` = ``contato_idx + 1``.
      3. ``novo_retorno_idx`` = column 3 IFF it exists as a gap (i.e.
         ``contato_idx - 1 > 3``) AND its sampled values are
         predominantly ``NOVO``/``RETORNO``.
      4. ``cliente_idx`` = ``contato_idx - 1``.
      5. ``tier_idx`` = ``corretor_idx + 1`` IFF its sampled values are
         predominantly in the tier vocabulary.
    """
    if not sample_rows:
        raise ValueError("cannot detect shape from an empty sample")

    width = len(sample_rows[0])
    best_idx, best_matches = _MIN_LEAD_COL, -1
    for col in range(_MIN_LEAD_COL, min(_MAX_SCAN_COL, width)):
        matches = sum(1 for row in sample_rows if col < len(row) and is_phone_or_email(row[col]))
        if matches > best_matches:
            best_matches, best_idx = matches, col
    contato_idx = best_idx

    novo_retorno_idx = None
    if contato_idx - 1 > _MIN_LEAD_COL:
        values = [_norm(row[_MIN_LEAD_COL]).upper() for row in sample_rows if len(row) > _MIN_LEAD_COL and _norm(row[_MIN_LEAD_COL])]
        if values and sum(1 for v in values if v in _NOVO_RETORNO_VOCAB) / len(values) > 0.5:
            novo_retorno_idx = _MIN_LEAD_COL

    cliente_idx = contato_idx - 1
    corretor_idx = contato_idx + 1

    tier_idx = None
    tier_col = corretor_idx + 1
    if tier_col < _MAX_SCAN_COL + 2:
        values = [_norm(row[tier_col]).upper() for row in sample_rows if len(row) > tier_col and _norm(row[tier_col])]
        if values and sum(1 for v in values if v in _TIER_VOCAB) / len(values) > 0.4:
            tier_idx = tier_col

    return SheetShape(
        contato_idx=contato_idx,
        cliente_idx=cliente_idx,
        corretor_idx=corretor_idx,
        novo_retorno_idx=novo_retorno_idx,
        tier_idx=tier_idx,
    )


__all__ = [
    "ORIGEM_COL",
    "is_header_like",
    "is_blank",
    "is_phone_or_email",
    "SheetShape",
    "detect_shape",
]
