"""Wallclock helpers — single source of truth for "current time" / "current period".

All functions read the system clock through `_now_provider`, which tests
swap via `frozen_time(...)`. Production code uses these helpers instead of
calling `datetime.now(timezone.utc)` directly so that tests + production
always agree on what "now" means at any given moment.

The bug class this module exists to prevent: mixing `date.today()` (local
timezone) with `datetime.now(timezone.utc)` for the same logical "current
period" computation. That mix passed at 17:00 UTC and broke at 00:47 UTC
on 2026-04-30 → 2026-05-01 because the local day was still 2026-04-30
while the UTC day had already rolled to 2026-05-01.

Adopted 2026-04-30 by `projects/timeutil-absorption/` (Wave-D-style
absorption surfaced by Wave C's project-end sweep).
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timezone
from typing import Callable, Iterator


def _real_now_utc() -> datetime:
    return datetime.now(timezone.utc)


# Module-level provider. Tests swap this via `frozen_time(...)`.
_now_provider: Callable[[], datetime] = _real_now_utc


def now_utc() -> datetime:
    """Return the current wallclock as an aware UTC `datetime`."""
    return _now_provider()


def today_utc() -> date:
    """Return the current wallclock as a UTC `date` (no time, no tz).

    Use this instead of `date.today()` for any computation whose result
    is compared against UTC-stored timestamps. `date.today()` reads the
    local timezone and drifts from UTC across midnight — that's the
    bug class this module exists to prevent.
    """
    return _now_provider().date()


def current_month_ref() -> str:
    """Return the current UTC month reference, formatted ``YYYY-MM``.

    The canonical "what month are we in" string used for period
    bucketing across the platform (financeiro contas-a-pagar,
    recorrencia lancamentos, BI dashboards, analytics). Production +
    tests must call this same function so they cannot drift across UTC
    midnight.
    """
    return _now_provider().strftime("%Y-%m")


def current_day_ref() -> str:
    """Return the current UTC day reference, formatted ``YYYY-MM-DD``.

    Used for due-date defaults, audit-log day buckets, and any other
    place that wants "today's date as a sortable string in UTC".
    """
    return _now_provider().strftime("%Y-%m-%d")


@contextmanager
def frozen_time(value: datetime) -> Iterator[None]:
    """Freeze wallclock to ``value`` for the duration of the with-block.

    ``value`` MUST be an aware UTC datetime (``tzinfo == timezone.utc``).
    Naive datetimes raise ``ValueError`` — passing one is the exact bug
    this module exists to prevent.

    Usage::

        from datetime import datetime, timezone
        from noctusai_lib.primitives.timeutil import current_month_ref, frozen_time

        with frozen_time(datetime(2026, 5, 1, 0, 47, tzinfo=timezone.utc)):
            assert current_month_ref() == "2026-05"
    """
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ValueError(
            f"frozen_time requires an aware UTC datetime; got naive {value!r}"
        )
    global _now_provider
    previous = _now_provider
    _now_provider = lambda: value
    try:
        yield
    finally:
        _now_provider = previous
