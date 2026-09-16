"""Pure-function BCB Olinda PTAX response parsing + date formatting.

No IO here — kept separate from `bcb_adapter.py` so parsing logic is
unit-testable against captured JSON fixtures without a network mock.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from noctusai_lib.integrations.fx.types import PtaxRate

_SOURCE = "bcb-ptax-olinda"
_BCB_DATE_FMT = "%m-%d-%Y"
_BCB_TIMESTAMP_FMT = "%Y-%m-%d %H:%M:%S.%f"


def format_bcb_date(quote_date: date) -> str:
    """BCB Olinda's OData functions take dates as `MM-DD-YYYY` strings
    (confirmed against the live `CotacaoDolarDia`/`CotacaoDolarPeriodo`
    functions 2026-09-16 — see `bcb_adapter.py` module docstring)."""
    return quote_date.strftime(_BCB_DATE_FMT)


def parse_ptax_response(payload: dict[str, Any]) -> PtaxRate | None:
    """Parse the OData JSON body of `CotacaoDolarPeriodo`/`CotacaoDolarDia`.

    Returns `None` when `value` is an empty list — the ONLY "no bulletin"
    signal BCB emits (confirmed 2026-09-16: a weekend date, a holiday
    date, and even a malformed `dataCotacao` string all return
    `{"value": []}` with HTTP 200, never a 4xx). The caller
    (`bcb_adapter.py`) turns `None` into `FxBulletinNotFoundError`.

    Raises `KeyError` (missing `value`/`cotacaoVenda`/`dataHoraCotacao`)
    or `ValueError` (timestamp doesn't match the expected format) on a
    row shape that doesn't match `TipoCotacaoDolar` — the caller wraps
    these into `FxUpstreamError` (an upstream contract change, not a
    "no bulletin" signal).

    Callers SHOULD parse the response body with `json.loads(text,
    parse_float=Decimal)` (not `response.json()`) before calling this —
    otherwise `cotacaoVenda` arrives as a `float` and the `Decimal(str(x))`
    fallback below round-trips through a `float` repr instead of the
    original decimal text. This function accepts either shape defensively
    (a `Decimal` already, or something `Decimal(str(...))`-coercible) but
    the float round-trip loses no precision here in practice (BCB's 5
    decimal places round-trip cleanly through IEEE-754 double), it is
    simply not the money-safe habit we want callers to form.
    """
    rows = payload["value"]
    if not rows:
        return None

    row = rows[0]
    rate = row["cotacaoVenda"]
    if not isinstance(rate, Decimal):
        rate = Decimal(str(rate))

    bulletin_at = datetime.strptime(row["dataHoraCotacao"], _BCB_TIMESTAMP_FMT)

    return PtaxRate(
        rate=rate,
        quote_date=bulletin_at.date(),
        bulletin_at=bulletin_at,
        source=_SOURCE,
    )


__all__ = [
    "format_bcb_date",
    "parse_ptax_response",
]
