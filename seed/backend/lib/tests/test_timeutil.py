"""Unit tests for `noctusai_lib.primitives.timeutil`.

Exercises the freezable wallclock seam — the bug class this module
exists to prevent is fully reproducible here via `frozen_time(...)`.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from noctusai_lib.primitives.timeutil import (
    current_day_ref,
    current_month_ref,
    frozen_time,
    now_utc,
    today_utc,
)


class TestNowUtc:
    def test_returns_aware_utc_datetime(self):
        result = now_utc()
        assert isinstance(result, datetime)
        assert result.tzinfo is not None
        assert result.utcoffset().total_seconds() == 0

    def test_frozen_time_pins_now_utc(self):
        pinned = datetime(2026, 5, 1, 12, 34, 56, tzinfo=timezone.utc)
        with frozen_time(pinned):
            assert now_utc() == pinned

    def test_frozen_time_restores_provider_on_exit(self):
        pinned = datetime(2024, 1, 1, tzinfo=timezone.utc)
        with frozen_time(pinned):
            assert now_utc() == pinned
        # After the with-block, the real clock is back. We can't assert
        # an exact value, but it definitely isn't the pinned 2024 value
        # (today is 2026+).
        assert now_utc() != pinned
        assert now_utc().year >= 2026


class TestTodayUtc:
    def test_returns_date(self):
        result = today_utc()
        assert isinstance(result, date)
        assert not isinstance(result, datetime)

    def test_frozen_time_pins_today_utc(self):
        pinned = datetime(2026, 5, 1, 0, 47, tzinfo=timezone.utc)
        with frozen_time(pinned):
            assert today_utc() == date(2026, 5, 1)


class TestCurrentMonthRef:
    def test_returns_yyyy_mm_string(self):
        with frozen_time(datetime(2026, 4, 30, 21, 0, tzinfo=timezone.utc)):
            assert current_month_ref() == "2026-04"

    def test_after_utc_midnight_rolls_over(self):
        """The exact bug we caught 2026-04-30 → 2026-05-01."""
        with frozen_time(datetime(2026, 5, 1, 0, 47, tzinfo=timezone.utc)):
            assert current_month_ref() == "2026-05"

    def test_january_format(self):
        with frozen_time(datetime(2026, 1, 5, 12, 0, tzinfo=timezone.utc)):
            assert current_month_ref() == "2026-01"


class TestCurrentDayRef:
    def test_returns_yyyy_mm_dd_string(self):
        with frozen_time(datetime(2026, 4, 30, 23, 59, tzinfo=timezone.utc)):
            assert current_day_ref() == "2026-04-30"

    def test_after_utc_midnight(self):
        with frozen_time(datetime(2026, 5, 1, 0, 1, tzinfo=timezone.utc)):
            assert current_day_ref() == "2026-05-01"


class TestFrozenTimeRejectsNaiveDatetimes:
    def test_naive_datetime_raises(self):
        # The whole point of this module is to ban naive datetimes from
        # the wallclock seam. A `frozen_time(datetime(...))` (no tzinfo)
        # would let the bug class right back in.
        with pytest.raises(ValueError, match="aware UTC datetime"):
            with frozen_time(datetime(2026, 5, 1, 0, 0)):
                pass  # pragma: no cover — the with statement should raise

    def test_aware_non_utc_datetime_accepted(self):
        # An aware datetime in another zone is OK — `_now_provider` returns
        # it as-is; consumers like `current_month_ref` will format it
        # in its own zone, not UTC. This is intentional flexibility for
        # tests that want to pin "now is 21:00 in BRT" and verify the
        # downstream UTC-rendered string.
        from datetime import timedelta
        brt = timezone(timedelta(hours=-3))
        pinned = datetime(2026, 4, 30, 21, 47, tzinfo=brt)
        with frozen_time(pinned):
            assert now_utc() == pinned
