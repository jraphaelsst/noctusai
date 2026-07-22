"""Cell-level parsers — date / código / contato / retorno-prefix. Every
function returns ``None`` (or the input passed through as ``*_raw``) on a
value it cannot confidently parse — "unparseable is fine, leave the
parsed field null" per the contract; nothing is ever silently dropped
because the verbatim ``*_raw`` column always keeps the original value.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Optional

# ─── dates ──────────────────────────────────────────────────────────────

_DATE_STR_RE = re.compile(r"^\s*(\d{1,2})\.(\d{1,2})\.(\d{2,4})\s*$")
# Plausible Excel-serial range for a real-estate lead dated 2000-2070ish.
_EXCEL_SERIAL_MIN, _EXCEL_SERIAL_MAX = 30000, 60000
_EXCEL_EPOCH_ORDINAL = date(1899, 12, 30).toordinal()  # Excel's (buggy) 1900 leap-year epoch


def looks_like_date_value(value: Any) -> bool:
    """Structural check used by the sheet-row classifier — does this cell
    look like SOME kind of date (without necessarily parsing cleanly)?"""
    if isinstance(value, (date, datetime)):
        return True
    if isinstance(value, str) and _DATE_STR_RE.match(value):
        return True
    if isinstance(value, (int, float)) and _EXCEL_SERIAL_MIN <= value <= _EXCEL_SERIAL_MAX:
        return True
    return False


def parse_date_cell(value: Any) -> Optional[date]:
    """Parse a DATA cell — ``datetime``/``date`` objects, Excel serials
    (``46204.0`` -> 2026-07-14), or ``dd.mm.yy``/``dd.mm.yyyy`` strings
    (``ABRIL_24`` / `` MARÇO_24``). Returns ``None`` when unparseable."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        m = _DATE_STR_RE.match(value)
        if not m:
            return None
        day, month, year = (int(g) for g in m.groups())
        if year < 100:
            year += 2000
        try:
            return date(year, month, day)
        except ValueError:
            return None
    if isinstance(value, (int, float)):
        if not (_EXCEL_SERIAL_MIN <= value <= _EXCEL_SERIAL_MAX):
            return None
        try:
            return date.fromordinal(_EXCEL_EPOCH_ORDINAL + int(value))
        except (ValueError, OverflowError):
            return None
    return None


# ─── código ──────────────────────────────────────────────────────────────

_CODIGO_PREFIX_RE = re.compile(r"^\s*(?:LOCA[ÇC][AÃ]O|EXCLUSIVIDADE|TERRENO)\s+", re.IGNORECASE)
_CODIGO_RE = re.compile(r"^\s*([A-Za-z]{1,4}\d{3,6})(.*)$", re.DOTALL)
_LEADING_DASH_RE = re.compile(r"^\s*-\s*")
_DASH_SPLIT_RE = re.compile(r"\s+-\s+")


def parse_codigo(raw: Optional[str]) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """``"ONE9622 Bosque dos Manacás - Km 21"`` -> (``"ONE9622"``,
    ``"Bosque dos Manacás"``, ``"Km 21"``). Strips a leading
    LOCAÇÃO/EXCLUSIVIDADE/TERRENO marker before matching the code token.
    Returns ``(None, None, None)`` when the cell doesn't start with a
    recognizable code token (e.g. a stray note leaked into the CODIGO
    column) — ``codigo_raw`` on the caller's row keeps the full verbatim
    string regardless."""
    if not raw:
        return None, None, None
    without_prefix = _CODIGO_PREFIX_RE.sub("", raw, count=1)
    m = _CODIGO_RE.match(without_prefix)
    if not m:
        return None, None, None
    codigo = m.group(1)
    rest = _LEADING_DASH_RE.sub("", m.group(2)).strip()
    if not rest:
        return codigo, None, None
    parts = [p.strip() for p in _DASH_SPLIT_RE.split(rest) if p.strip()]
    if not parts:
        return codigo, None, None
    if len(parts) == 1:
        return codigo, parts[0], None
    return codigo, parts[0], " - ".join(parts[1:])


# ─── contato ─────────────────────────────────────────────────────────────

def parse_contato(raw: Optional[str]) -> tuple[Optional[str], str]:
    """Returns ``(contato_norm, contato_tipo)``. ``contato_norm`` is
    digits-only for a phone, lowercased for an email; ``contato_tipo`` in
    ``{telefone, email, desconhecido}``."""
    if not raw or not str(raw).strip():
        return None, "desconhecido"
    value = str(raw).strip()
    if "@" in value:
        return value.lower(), "email"
    digits = re.sub(r"\D", "", value)
    if len(digits) >= 8:
        return digits, "telefone"
    return None, "desconhecido"


# ─── NOVO/RETORNO name-prefix leak ───────────────────────────────────────

_RETORNO_PREFIX_RE = re.compile(r"^\s*retorno\s*[:\-]?\s*", re.IGNORECASE)


def strip_retorno_prefix(cliente_raw: Optional[str]) -> tuple[Optional[str], bool]:
    """Pre-2026 sheets leak the NOVO/RETORNO signal into the CLIENTE
    column as a ``"Retorno "`` name prefix (``"Retorno Paula "`` ->
    ``"Paula"``, ``tipo_lead='retorno'``). Returns ``(clean_name,
    is_retorno)``."""
    if not cliente_raw:
        return cliente_raw, False
    m = _RETORNO_PREFIX_RE.match(cliente_raw)
    if not m:
        return cliente_raw.strip() or None, False
    cleaned = cliente_raw[m.end():].strip()
    return (cleaned or None), True


__all__ = [
    "looks_like_date_value",
    "parse_date_cell",
    "parse_codigo",
    "parse_contato",
    "strip_retorno_prefix",
]
