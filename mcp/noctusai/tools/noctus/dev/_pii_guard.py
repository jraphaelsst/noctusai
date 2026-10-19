"""Shared PII guard for every append-only ledger / history writer.

LGPD incident 2026-10-19: a live-extraction probe wrote a real CPF + marriage
date, and a customer phone number, into ``auto-improvement.ndjson`` (which is
then replicated to the append-only ``origin/ledgers`` branch). Ledgers are
permanent by design, so the only safe control is to REFUSE at write time.

Contract:
    * :func:`find_pii` -> ``[(kind, span)]`` (spans only; values never leave here).
    * :func:`assert_no_pii` raises :class:`PiiLedgerError` naming the KIND and
      the FIELD, never the value.
    * :func:`redact` is the one-shot correction path (used by the scrub of the
      existing rows and by tests); it keeps surrounding text.

False-positive control: CPF/CNPJ require a valid check digit; phone requires
the BR shape (``+55``/``55``+DDD, or ``(DD) 9xxxx-xxxx``); RG and personal
dates require their label; emails exclude team/service/example addresses.

KB § PATTERNS/compliance/lgpd.md (ledger rows are permanent: refuse, don't redact).
"""
from __future__ import annotations

import json
import re
from typing import Any, Iterable

KINDS = ("cpf", "cnpj", "phone", "email", "rg", "personal-date")


class PiiLedgerError(ValueError):
    """A ledger/history write was refused because it carries personal data.

    ``kind`` and ``field`` are safe to log; the value is never retained."""

    def __init__(self, kind: str, field: str) -> None:
        self.kind = kind
        self.field = field
        super().__init__(
            f"refused: {kind} detected in field {field!r}; ledgers are permanent - "
            f"never write personal data (use an id or a masked form)"
        )


_CPF = re.compile(r"(?<!\d)(\d{3}\.?\d{3}\.?\d{3}-?\d{2})(?!\d)")
_CNPJ = re.compile(r"(?<!\d)(\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2})(?!\d)")
_PHONE = re.compile(
    r"(?<![\w.])(?:"
    r"\+55[\s-]?\(?\d{2}\)?[\s-]?9?\d{4}[\s-]?\d{4}"
    r"|\(\d{2}\)\s?9?\d{4}-?\d{4}"
    r"|55[1-9]\d9\d{8}"
    r")(?!\d)"
)
_EMAIL = re.compile(r"(?<![\w.+-])[A-Za-z0-9][A-Za-z0-9._%+-]*@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,})(?![\w-])")
_RG = re.compile(r"\bRG\b[\s:nº°.-]*(\d{1,2}\.?\d{3}\.?\d{3}-?[\dxX])(?!\d)", re.IGNORECASE)
_PDATE = re.compile(
    r"(?i)(?:nascimento|casamento|nasc\b\.?|data[_ ]?nasc\w*|dt[_ ]?nasc\w*)"
    r"[^\n\d]{0,24}?(\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4})"
)

# Team / service / placeholder mailboxes that are not personal data.
_EMAIL_ALLOW_DOMAINS = (
    "example.com", "example.org", "example.test", "test.com", "noctusai.com",
    "anthropic.com", "b.com", "x.com", "users.noreply.github.com", "github.com", "localhost.localdomain",
)
_EMAIL_ALLOW_ADDRS = ("joaoraphaelsst@gmail.com",)


def _digits(s: str) -> list[int]:
    return [int(c) for c in s if c.isdigit()]


def valid_cpf(raw: str) -> bool:
    d = _digits(raw)
    if len(d) != 11 or len(set(d)) == 1:
        return False
    for n in (9, 10):
        s = sum(v * w for v, w in zip(d[:n], range(n + 1, 1, -1)))
        if d[n] != (s * 10 % 11) % 10:
            return False
    return True


def valid_cnpj(raw: str) -> bool:
    d = _digits(raw)
    if len(d) != 14 or len(set(d)) == 1:
        return False
    w1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    for n, w in ((12, w1), (13, [6] + w1)):
        r = sum(v * x for v, x in zip(d[:n], w)) % 11
        if d[n] != (0 if r < 2 else 11 - r):
            return False
    return True


def _email_is_personal(addr: str, domain: str) -> bool:
    if addr.lower() in _EMAIL_ALLOW_ADDRS:
        return False
    dom = domain.lower()
    if any(dom == a or dom.endswith("." + a) for a in _EMAIL_ALLOW_DOMAINS):
        return False
    local = addr.split("@", 1)[0].lower()
    if local in {"noreply", "no-reply", "support", "admin", "info"}:
        return False
    return True


def find_pii(text: str) -> list[tuple[str, tuple[int, int]]]:
    """Return ``[(kind, (start, end))]`` for every personal-data hit in ``text``."""
    if not text:
        return []
    hits: list[tuple[str, tuple[int, int]]] = []
    for m in _CPF.finditer(text):
        if valid_cpf(m.group(1)):
            hits.append(("cpf", m.span(1)))
    for m in _CNPJ.finditer(text):
        if valid_cnpj(m.group(1)):
            hits.append(("cnpj", m.span(1)))
    for m in _PHONE.finditer(text):
        hits.append(("phone", m.span()))
    for m in _EMAIL.finditer(text):
        if _email_is_personal(m.group(0), m.group(1)):
            hits.append(("email", m.span()))
    for m in _RG.finditer(text):
        hits.append(("rg", m.span(1)))
    for m in _PDATE.finditer(text):
        hits.append(("personal-date", m.span(1)))
    # de-overlap: earliest-start, prefer the longer span
    hits.sort(key=lambda h: (h[1][0], -(h[1][1] - h[1][0])))
    out: list[tuple[str, tuple[int, int]]] = []
    end = -1
    for kind, (s, e) in hits:
        if s >= end:
            out.append((kind, (s, e)))
            end = e
    return out


def redact(text: str) -> tuple[str, dict[str, int]]:
    """Replace each hit with ``[REDACTED-<kind>]``; return (text, counts)."""
    counts: dict[str, int] = {}
    pieces: list[str] = []
    pos = 0
    for kind, (s, e) in find_pii(text):
        pieces.append(text[pos:s])
        pieces.append(f"[REDACTED-{kind}]")
        counts[kind] = counts.get(kind, 0) + 1
        pos = e
    pieces.append(text[pos:])
    return "".join(pieces), counts


def _walk(obj: Any, path: str) -> Iterable[tuple[str, str]]:
    if isinstance(obj, str):
        yield path, obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from _walk(v, f"{path}.{k}" if path else str(k))
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            yield from _walk(v, f"{path}[{i}]")


def assert_no_pii(text: Any, *, field: str = "text") -> None:
    """Raise :class:`PiiLedgerError` (kind + field, never the value) on any hit.

    ``text`` may be a string, or a dict/list (walked, with a dotted field path);
    a string that parses as a JSON object (an NDJSON row) is walked the same way
    so the error names the JSON key."""
    if isinstance(text, str):
        s = text.lstrip()
        if s.startswith("{") and s.endswith("}"):
            try:
                text = json.loads(s)
            except ValueError:
                pass
    for path, val in _walk(text, field if not isinstance(text, dict) else ""):
        hits = find_pii(val)
        if hits:
            raise PiiLedgerError(hits[0][0], path or field)


def assert_rows_clean(ledger: str, rows: Iterable[str]) -> None:
    """Refuse a whole append when any NDJSON row carries personal data.

    The single choke point for every ledger writer (``Ledger.append`` of both
    the Fake and the Real store). Field = ``<ledger>#<row>.<json key path>``."""
    for i, row in enumerate(rows):
        assert_no_pii(row, field=f"{ledger}#{i}")
