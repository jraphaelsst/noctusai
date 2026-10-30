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

import os
from contextlib import contextmanager
from datetime import date, datetime, timezone
from typing import Callable, Iterator
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def _real_now_utc() -> datetime:
    return datetime.now(timezone.utc)


# Module-level provider. Tests swap this via `frozen_time(...)`.
_now_provider: Callable[[], datetime] = _real_now_utc


def now_utc() -> datetime:
    """Return the current wallclock as an aware UTC `datetime`."""
    return _now_provider()


def now_utc_iso() -> str:
    """Return the current wallclock as an ISO 8601 string with UTC offset.

    Canonical string form of `now_utc()` — composes with `_now_provider`
    so `frozen_time(...)` pins this too. Used everywhere a service
    serializes "now" into a payload field (``placed_at``, ``submitted_at``,
    ``fetched_at``, ``retention_until`` comparisons, …).

    Lifted from N=4 byte-identical product-local helpers (adconnect
    sellout + orders + financial, core webhook_retention) all defined as
    ``def _now_iso() -> str: return datetime.now(timezone.utc).isoformat()``.

    Note: includes microseconds. A divergent variant (vista_showcase
    strips microseconds via ``.replace(microsecond=0)``) is kept
    product-local — see `accept-with-rationale` catalog if/when it is
    formalized.
    """
    return _now_provider().isoformat()


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


#: Env var naming the platform's wall-clock timezone (IANA name). One setting for
#: every "what time is it HERE" decision the platform makes on its own — the
#: scheduler's cron triggers above all. Per-org data (a finance org's reminder
#: timezone, a clinic's agenda timezone) keeps its own column; this is the
#: PLATFORM clock, not a tenant's.
PLATFORM_TIMEZONE_ENV = "NOCTUS_TIMEZONE"

#: The platform clock when `NOCTUS_TIMEZONE` is unset — the operator is in Brazil.
DEFAULT_PLATFORM_TIMEZONE = "America/Sao_Paulo"


def platform_timezone_name() -> str:
    """The platform timezone (IANA name): `NOCTUS_TIMEZONE`, default
    `America/Sao_Paulo`.

    Read at call time (never cached) so a test or a deploy can set it without
    a re-import. An unknown zone name RAISES `ValueError` — a typo must fail
    the boot loudly, never silently run every cron in UTC.
    """
    name = (os.environ.get(PLATFORM_TIMEZONE_ENV) or "").strip() or DEFAULT_PLATFORM_TIMEZONE
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(
            f"{PLATFORM_TIMEZONE_ENV}={name!r} is not a known IANA timezone"
        ) from exc
    return name


def platform_tz() -> ZoneInfo:
    """`ZoneInfo` for `platform_timezone_name()`."""
    return ZoneInfo(platform_timezone_name())


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
