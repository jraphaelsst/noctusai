"""Text helpers shared by the organs: PostgREST-safe search terms, CSV cells, document masking."""
from __future__ import annotations

import re
from typing import Any, Optional

# Formula-injection leads: ASCII + full-width look-alikes (spreadsheets fold them), tab / CR / LF.
_FORMULA_LEAD = ("=", "+", "-", "@", "＝", "＋", "－", "＠", "\t", "\r", "\n")
_LEADING_BLANKS = " \t\r\n 　"


def like_term(q: str) -> str:
    """A safe ILIKE pattern for a user search term (no wildcards / PostgREST operators from the user)."""
    cleaned = re.sub(r"[%_,()*\\.:\"]", " ", q or "").strip()
    return f"%{cleaned}%"


def like_term_wildcard(q: str) -> str:
    """Like `like_term`, but each operator / wildcard character becomes a `%`.

    A SKU typed as `A.B` still finds `A.B_C`; PostgREST operator characters never reach the filter.
    """
    cleaned = re.sub(r"[%_,()*\\.:\"]+", "%", (q or "").strip())
    return f"%{cleaned.strip('%')}%"


def csv_safe(value: Any) -> str:
    """One cell: text a spreadsheet would read as a formula is neutralised with a leading `'`.

    Covers the ASCII leads, their full-width look-alikes, and the same leads hidden behind leading
    whitespace (`" =1+1"`).
    """
    text = "" if value is None else str(value)
    probe = text.lstrip(_LEADING_BLANKS)
    if text.startswith(_FORMULA_LEAD) or (probe and probe.startswith(_FORMULA_LEAD)):
        return "'" + text
    return text


def mask_doc(doc: Optional[str]) -> Optional[str]:
    """`***.456.789-**` (CPF) / `**.***.678/9012-**` (CNPJ): enough to recognise, not to reuse."""
    if not doc:
        return doc
    d = "".join(ch for ch in str(doc) if ch.isalnum())
    if len(d) == 11:
        return f"***.{d[3:6]}.{d[6:9]}-**"
    if len(d) == 14:
        return f"**.***.{d[5:8]}/{d[8:12]}-**"
    return "*" * len(d)


__all__ = ["csv_safe", "like_term", "like_term_wildcard", "mask_doc"]
