"""Deterministic, offline PTAX fake.

Mirrors `BcbPtaxAdapter`'s walk-back + not-found behaviour without
touching the network, so consumer tests exercise the SAME code path
(including `FxBulletinNotFoundError`) the Real adapter would take.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal

from noctusai_lib.integrations.fx.errors import FxBulletinNotFoundError
from noctusai_lib.integrations.fx.types import PtaxRate

_DEFAULT_SOURCE = "fake-ptax"
_DEFAULT_LOOKBACK_DAYS = 10
# Naive (no tzinfo) to mirror `BcbPtaxAdapter`: BCB's own `dataHoraCotacao`
# carries no timezone marker (it's BRT wall-clock, ~13:00), and
# `datetime.strptime` on the Real adapter produces a naive datetime — a
# tz-aware Fake would silently disagree with the Real on comparability.
_DEFAULT_BULLETIN_HOUR = time(13, 0)


class FakeFxRateAdapter:
    """In-memory PTAX fake.

    Seed with `bulletins={date(...): Decimal("5.15"), ...}` — one entry
    per BUSINESS DAY a bulletin exists (skip weekends/holidays in the
    fixture to exercise the walk-back path the same way BCB's real
    calendar would). `get_ptax(quote_date)` walks BACKWARD up to
    `lookback_days` (default 10, matching `BcbPtaxAdapter`) looking for
    the latest bulletin `<= quote_date`; raises the SAME
    `FxBulletinNotFoundError` the Real adapter raises when none exists
    in that window — never a silent fallback rate.
    """

    def __init__(
        self,
        bulletins: dict[date, Decimal] | None = None,
        lookback_days: int = _DEFAULT_LOOKBACK_DAYS,
    ) -> None:
        self._bulletins: dict[date, Decimal] = dict(bulletins or {})
        self._lookback_days = lookback_days
        self.lookups: list[date] = []  # test-observable call log

    def set_rate(self, quote_date: date, rate: Decimal) -> None:
        """Seed/override a single bulletin (test convenience)."""
        self._bulletins[quote_date] = rate

    def get_ptax(self, quote_date: date) -> PtaxRate:
        self.lookups.append(quote_date)

        for offset in range(self._lookback_days + 1):
            candidate = quote_date - timedelta(days=offset)
            rate = self._bulletins.get(candidate)
            if rate is not None:
                return PtaxRate(
                    rate=rate,
                    quote_date=candidate,
                    bulletin_at=datetime.combine(candidate, _DEFAULT_BULLETIN_HOUR),
                    source=_DEFAULT_SOURCE,
                )

        raise FxBulletinNotFoundError(quote_date, self._lookback_days)


__all__ = ["FakeFxRateAdapter"]
