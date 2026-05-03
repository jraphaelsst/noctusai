"""Parsing & formatting helpers absorbed from per-product duplicates.

Trip history (recurrence rule N=2 → triage formalize, 2026-04-29):

- `_safe_float`: erp/ai_service.py + pf/ai_service.py — identical bodies
  modulo log message wording. Both used to extract a numeric value from
  free-text LLM output.
- `_safe_json_loads`: daily-life/ai_service.py + mailing/ai_service.py —
  identical bodies. Both strip a markdown code-fence (```json ... ```)
  before delegating to `json.loads`, returning `None` on parse failure.
- `_fmt_brl` / `_format_money`: erp/metas_digest_service.py +
  pf/monthly_narrative_service.py + erp/dimob_service.py — three
  flavors of "format a numeric value as BRL". Unified under
  `format_brl(value, *, decimals=2, with_currency=True)` with kwargs.
- `_parse_iso`: noctusai_seed/llm_router.py + core/admin_llm_usage.py —
  identical bodies. Both raise `HTTPException(400)` on invalid input.

These were each at N=2 (triage threshold) when absorbed; the function body
in seed lib is the single source of truth going forward, and the
per-product copies should be replaced with `from noctusai_lib.primitives.parsing
import ...`.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Optional, Union

from fastapi import HTTPException

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Numeric parsing
# ---------------------------------------------------------------------------

def safe_float(text: Any, default: float = 0.0) -> float:
    """Extract a float from messy text; return `default` on failure.

    Strips everything but digits, dot, and minus sign before parsing — so
    `"R$ 1.234,56"` becomes `1.23456` (caller decides if locale matters)
    and `"42 anos"` becomes `42.0`. Use only when the input shape is
    truly arbitrary; for structured input prefer `float(text)` directly
    and let it raise.
    """
    if text is None:
        return default
    if isinstance(text, (int, float)):
        return float(text)
    cleaned = "".join(c for c in str(text) if c.isdigit() or c in ".-")
    if not cleaned or cleaned in {".", "-", "-."}:
        logger.warning(
            "noctusai_lib.primitives.parsing.safe_float: input %r contains no parseable digits "
            "(cleaned=%r); using default %s",
            text, cleaned, default,
        )
        return default
    try:
        return float(cleaned)
    except ValueError as exc:
        logger.warning(
            "noctusai_lib.primitives.parsing.safe_float: cannot parse %r as float "
            "(cleaned=%r, %s); using default %s",
            text, cleaned, exc, default,
        )
        return default


# ---------------------------------------------------------------------------
# JSON parsing — tolerates LLM markdown wrapping
# ---------------------------------------------------------------------------

def safe_json_loads(raw: str) -> Optional[Union[list, dict]]:
    """Parse JSON tolerating ` ```json ... ``` ` markdown fences.

    LLM responses often wrap their JSON in code fences even when the
    prompt asks for raw JSON. This helper strips the fence + optional
    `json` language tag before delegating to `json.loads`. Returns
    `None` on parse failure (caller decides the fallback).
    """
    if not raw:
        return None
    stripped = raw.strip()
    if stripped.startswith("```"):
        # Form: ``` ... ```  OR  ```json ... ```
        parts = stripped.split("```", 2)
        if len(parts) >= 2:
            stripped = parts[1]
            if stripped.lstrip().lower().startswith("json"):
                stripped = stripped.lstrip()[4:]
            stripped = stripped.strip().rstrip("`").strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError as exc:
        logger.warning(
            "noctusai_lib.primitives.parsing.safe_json_loads: input did not parse as JSON "
            "(%s); first 200 chars: %r",
            exc, stripped[:200],
        )
        return None


# ---------------------------------------------------------------------------
# BRL currency formatting
# ---------------------------------------------------------------------------

def format_brl(
    value: Optional[Union[float, int]],
    *,
    decimals: int = 2,
    with_currency: bool = True,
) -> str:
    """Format a numeric value in Brazilian Real notation.

    `decimals=2, with_currency=True` (default) → ``"R$ 1.234,56"``
    `decimals=0, with_currency=True`           → ``"R$ 1.234"``
    `decimals=2, with_currency=False`          → ``"1234.56"`` (raw, for
        DIMOB-style fixed-format files where locale separators are
        forbidden)

    Returns ``"R$ 0"`` (or ``"0.00"`` if `with_currency=False`) when
    value is `None` or non-numeric. Logs a warning on non-numeric
    input so the operator sees the data-quality issue.
    """
    if value is None:
        return "R$ 0" if with_currency else "0.00"
    try:
        v = float(value)
    except (TypeError, ValueError) as exc:
        logger.warning(
            "noctusai_lib.primitives.parsing.format_brl: cannot coerce %r to float "
            "(%s); using zero",
            value, exc,
        )
        return "R$ 0" if with_currency else "0.00"

    if not with_currency:
        return f"{v:.{decimals}f}"
    # Build a locale-correct BRL string without depending on the system
    # locale — `,`-decimal + `.`-thousand separator. Python's `format`
    # spec uses the opposite, so we swap via a sentinel char.
    formatted = f"{v:,.{decimals}f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"R$ {formatted}"


# ---------------------------------------------------------------------------
# ISO datetime parsing
# ---------------------------------------------------------------------------

def parse_iso_or_400(value: Optional[str]) -> Optional[datetime]:
    """Parse an ISO-8601 datetime string, raising HTTP 400 on invalid input.

    `None` and empty-string return `None` (caller treats as "not provided").
    A non-empty string MUST parse — if `datetime.fromisoformat` raises,
    this raises `HTTPException(400)` so the FastAPI layer surfaces it
    as a 400 to the client.

    The trailing-`Z` form (`"2026-04-29T15:30:00Z"`) is normalized to
    `"+00:00"` before parsing — Python's stdlib didn't support `Z` until
    3.11, and even then explicit normalization is clearer.
    """
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid ISO date: {value}",
        ) from exc


def parse_iso_or_none(value: Optional[str]) -> Optional[datetime]:
    """Same as `parse_iso_or_400` but returns `None` on invalid input.

    Use in non-HTTP contexts (background jobs, scripts) where raising
    is wrong.
    """
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError) as exc:
        logger.warning(
            "noctusai_lib.primitives.parsing.parse_iso_or_none: cannot parse %r "
            "as ISO datetime (%s); returning None",
            value, exc,
        )
        return None
