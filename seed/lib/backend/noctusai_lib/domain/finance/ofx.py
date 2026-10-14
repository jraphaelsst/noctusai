"""OFX statement parsing -- 2.x (XML) via `defusedxml`, 1.x (SGML) via our own bounded tokenizer.

A bank statement is UNTRUSTED input from the internet:

* **OFX 2.x** is XML, so it is parsed with `defusedxml` with `forbid_dtd=True`: a DOCTYPE
  (and therefore every entity declaration -- XXE, billion-laughs, quadratic blow-up) is
  refused outright. A real bank statement has no DTD.
* **OFX 1.x** is SGML (unclosed leaf tags). No library parses it safely, so this module
  tokenizes it with ONE linear regex pass (`<TAG>value` runs) -- no recursion, no entity
  expansion, no backtracking -- over a body the caller has already size-capped.

Both paths yield the same `ParsedStatement`; neither ever returns a raw exception to the
caller (every failure is a `FinanceError` with a stable pt-BR code).

Amounts are integer cents (`Decimal` quantized, never `float`).
"""
from __future__ import annotations

import hashlib
import html
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Optional

from defusedxml import ElementTree as SafeET
from defusedxml.common import DefusedXmlException

from .errors import FinanceError

EXTRATO_INVALIDO = "extrato_invalido"
EXTRATO_MOEDA_INVALIDA = "extrato_moeda_invalida"

MAX_DESCRIPTION_CHARS = 500
MAX_FITID_CHARS = 200
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_TOKEN = re.compile(r"<(/?)([A-Za-z][A-Za-z0-9_.]*)>([^<]*)")
_TRN_FIELDS = ("TRNTYPE", "DTPOSTED", "TRNAMT", "FITID", "NAME", "MEMO", "CHECKNUM", "REFNUM")


@dataclass(frozen=True)
class ParsedLine:
    """One statement line. `amount_cents` is SIGNED (money in positive)."""

    posted_on: date
    amount_cents: int
    description: str
    fitid: str


@dataclass
class ParsedStatement:
    lines: list[ParsedLine]
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    skipped_zero: int = 0
    currency: str = "BRL"
    warnings: list[str] = field(default_factory=list)


def bad(message: str = "Não foi possível ler o extrato: o arquivo não é um OFX válido.") -> FinanceError:
    return FinanceError(EXTRATO_INVALIDO, message, 422)


# ─── scalar parsing ──────────────────────────────────────────────────────────


def parse_amount_cents(raw: str) -> int:
    """`-1234.56` / `1.234,56` / `1234,5` -> signed integer cents; never a float."""
    text = (raw or "").strip().replace(" ", "")
    if not text:
        raise bad("Valor ausente em uma linha do extrato.")
    if "," in text and "." in text:
        # the LAST separator is the decimal one
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise bad("Valor inválido em uma linha do extrato.") from None
    if not value.is_finite() or abs(value) >= Decimal("1e12"):
        raise bad("Valor fora do intervalo em uma linha do extrato.")
    cents = (value * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    if cents != value * 100:
        raise bad("Valor com mais de duas casas decimais em uma linha do extrato.")
    return int(cents)


def parse_ofx_date(raw: str) -> date:
    """`20261003120000[-3:BRT]` / `20261003` -> `date` (the statement's own calendar day)."""
    digits = re.match(r"\s*(\d{8})", raw or "")
    if not digits:
        raise bad("Data inválida em uma linha do extrato.")
    text = digits.group(1)
    try:
        return date(int(text[:4]), int(text[4:6]), int(text[6:8]))
    except ValueError:
        raise bad("Data inválida em uma linha do extrato.") from None


def clean_text(value: Optional[str], limit: int = MAX_DESCRIPTION_CHARS) -> str:
    return _CTRL.sub(" ", (value or "")).strip()[:limit]


def derived_fitid(*parts: object) -> str:
    return hashlib.sha256("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()


# ─── shape detection + decoding ──────────────────────────────────────────────


def looks_like_ofx(data: bytes) -> bool:
    head = data[:2048].lstrip(b"\xef\xbb\xbf \t\r\n").upper()
    return head.startswith((b"OFXHEADER", b"<?XML", b"<?OFX", b"<OFX"))


def _decode_sgml(data: bytes) -> str:
    """OFX 1.x header names the charset (BR banks: 1252); otherwise UTF-8, then the BR-legacy cp1252."""
    head = data[:600].decode("ascii", errors="ignore").upper()
    wants_legacy = bool(re.search(r"CHARSET:\s*(1252|WINDOWS-1252|ISO-8859-1|LATIN1)", head))
    if not wants_legacy:
        try:
            return data.decode("utf-8-sig")
        except UnicodeDecodeError:
            pass
    return data.decode("cp1252", errors="replace")


def count_transactions(data: bytes) -> int:
    """How many `<STMTTRN>` blocks the raw bytes carry -- the line cap runs on this BEFORE any parse."""
    return len(re.findall(rb"<STMTTRN[\s>]", data, flags=re.IGNORECASE))


# ─── building lines ──────────────────────────────────────────────────────────


def _line_from(fields: dict[str, str], seen: dict[str, int], position: int) -> Optional[ParsedLine]:
    amount = parse_amount_cents(fields.get("TRNAMT", ""))
    posted = parse_ofx_date(fields.get("DTPOSTED", ""))
    name, memo = clean_text(fields.get("NAME")), clean_text(fields.get("MEMO"))
    description = f"{name} - {memo}" if name and memo and name != memo else (name or memo)
    description = description or clean_text(fields.get("TRNTYPE")) or "Lançamento"
    if amount == 0:
        return None
    fitid = clean_text(fields.get("FITID"), MAX_FITID_CHARS)
    if not fitid:
        fitid = derived_fitid("ofx", posted, amount, description, position)
    # A bank that reuses a FITID for two DIFFERENT lines of one file would collide on the
    # per-account unique: the Nth repeat gets a stable suffix instead of a 500.
    seen[fitid] = seen.get(fitid, 0) + 1
    if seen[fitid] > 1:
        fitid = f"{fitid}#{seen[fitid]}"
    return ParsedLine(posted_on=posted, amount_cents=amount, description=description[:MAX_DESCRIPTION_CHARS], fitid=fitid)


def _finish(raw_blocks: list[dict[str, str]], start: Optional[str], end: Optional[str], currency: str) -> ParsedStatement:
    if currency and currency.upper() != "BRL":
        raise FinanceError(EXTRATO_MOEDA_INVALIDA, "Só extratos em reais (BRL) podem ser importados.", 422)
    seen: dict[str, int] = {}
    lines: list[ParsedLine] = []
    skipped = 0
    for position, block in enumerate(raw_blocks, start=1):
        line = _line_from(block, seen, position)
        if line is None:
            skipped += 1
        else:
            lines.append(line)
    period_start = parse_ofx_date(start) if start else None
    period_end = parse_ofx_date(end) if end else None
    if lines:
        period_start = period_start or min(l.posted_on for l in lines)
        period_end = period_end or max(l.posted_on for l in lines)
    return ParsedStatement(lines=lines, period_start=period_start, period_end=period_end, skipped_zero=skipped, currency="BRL")


# ─── OFX 1.x (SGML) ──────────────────────────────────────────────────────────


def parse_ofx_sgml(data: bytes) -> ParsedStatement:
    text = _decode_sgml(data)
    body_at = text.upper().find("<OFX")
    if body_at < 0:
        raise bad()
    blocks: list[dict[str, str]] = []
    current: Optional[dict[str, str]] = None
    start = end = None
    currency = "BRL"
    for closing, tag, value in _TOKEN.findall(text[body_at:]):
        tag = tag.upper()
        value = value.strip()
        if tag == "STMTTRN":
            if closing:
                if current is not None:
                    blocks.append(current)
                current = None
            else:
                current = {}  # an unclosed previous block is dropped by `current = {}`; its fields are never trusted
            continue
        if closing:
            continue
        if current is not None:
            if tag in _TRN_FIELDS:
                current[tag] = html.unescape(value)
        elif tag == "DTSTART" and start is None:
            start = value
        elif tag == "DTEND" and end is None:
            end = value
        elif tag == "CURDEF" and value:
            currency = value
    if current is not None:
        raise bad("O extrato termina no meio de um lançamento.")
    if not blocks and "STMTTRN" not in text.upper():
        raise bad("Nenhum lançamento encontrado no arquivo.")
    return _finish(blocks, start, end, currency)


# ─── OFX 2.x (XML) ───────────────────────────────────────────────────────────


def parse_ofx_xml(data: bytes) -> ParsedStatement:
    try:
        root = SafeET.fromstring(data, forbid_dtd=True, forbid_entities=True, forbid_external=True)
    except DefusedXmlException:
        raise bad("O extrato usa declarações XML não permitidas (DTD/entidades).") from None
    except (SafeET.ParseError, ValueError):
        raise bad() from None
    blocks: list[dict[str, str]] = []
    start = end = None
    currency = "BRL"
    for el in root.iter():
        tag = str(el.tag).split("}")[-1].upper()
        if tag == "STMTTRN":
            block: dict[str, str] = {}
            for child in el:
                name = str(child.tag).split("}")[-1].upper()
                if name in _TRN_FIELDS:
                    block[name] = (child.text or "").strip()
            blocks.append(block)
        elif tag == "DTSTART" and start is None:
            start = (el.text or "").strip()
        elif tag == "DTEND" and end is None:
            end = (el.text or "").strip()
        elif tag == "CURDEF" and (el.text or "").strip():
            currency = el.text.strip()
    return _finish(blocks, start, end, currency)


def parse_ofx(data: bytes) -> ParsedStatement:
    """Parse OFX 2.x or 1.x bytes (already size/line capped by the caller)."""
    upper = data.upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        # No real bank statement carries a DTD; refusing it for BOTH dialects keeps a hostile
        # file from ever reaching a parser, whatever the parser would have done with it.
        raise bad("O extrato usa declarações XML não permitidas (DTD/entidades).")
    head = data[:2048].lstrip(b"\xef\xbb\xbf \t\r\n")
    if head[:5].lower() == b"<?xml":
        return parse_ofx_xml(data)
    if looks_like_ofx(data):
        return parse_ofx_sgml(data)
    raise bad()


__all__ = [
    "EXTRATO_INVALIDO",
    "EXTRATO_MOEDA_INVALIDA",
    "ParsedLine",
    "ParsedStatement",
    "bad",
    "clean_text",
    "count_transactions",
    "derived_fitid",
    "looks_like_ofx",
    "parse_amount_cents",
    "parse_ofx",
    "parse_ofx_date",
    "parse_ofx_sgml",
    "parse_ofx_xml",
]
