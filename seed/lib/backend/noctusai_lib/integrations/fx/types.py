"""FX/PTAX value objects + Protocol."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class PtaxRate:
    """One published BCB PTAX venda (sell) rate, fechamento (closing) bulletin.

    `rate` is a `Decimal` — never a `float` — this is money, and PTAX
    carries 5 decimal places (`Decimal("5.14900")`) that a float would
    silently misrepresent.

    `quote_date` is the date the bulletin was ACTUALLY published for,
    which may be EARLIER than the date a caller requested: BCB publishes
    no bulletin on weekends, holidays, or before ~13:00 on the current
    day, so `get_ptax()` walks back to the most recent published
    bulletin. Consumers MUST persist `quote_date` alongside `rate` — a
    cost record priced off a walked-back bulletin must record which
    trading day actually priced it, never the date it was requested for.

    `bulletin_at` is the full timestamp BCB attached to the bulletin
    (its `dataHoraCotacao` field) — finer-grained than `quote_date`,
    kept for audit/debugging.
    """

    rate: Decimal
    quote_date: date
    bulletin_at: datetime
    source: str


@runtime_checkable
class FxRateAdapter(Protocol):
    """Surface every FX-rate connector implements. Both `FakeFxRateAdapter`
    and `BcbPtaxAdapter` satisfy this Protocol naturally."""

    def get_ptax(self, quote_date: date) -> PtaxRate:
        """Return the latest published PTAX venda/fechamento bulletin with
        `bulletin's quote_date <= quote_date`.

        Raises `FxBulletinNotFoundError` when no bulletin exists within
        the adapter's lookback window — NEVER a silent fallback rate."""
        ...
