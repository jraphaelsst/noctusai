"""Schedule window: tz-aware (America/Sao_Paulo), weekday-aware."""
from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.services.automation_engine import _apply_schedule_window

SP = ZoneInfo("America/Sao_Paulo")
WINDOW = {
    "days": ["mon", "tue", "wed", "thu", "fri"],
    "start": "08:00", "end": "17:00", "tz": "America/Sao_Paulo",
    "outside_window_behavior": "schedule_next_available",
}


def _utc(y, m, d, h, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=timezone.utc)


def _local(dt):
    return dt.astimezone(SP)


def test_inside_window_is_untouched():
    # Wed 2026-10-14 12:00 BRT = 15:00 UTC
    dt = _utc(2026, 10, 14, 15)
    assert _apply_schedule_window(dt, WINDOW) == dt


def test_utc_morning_hour_is_NOT_treated_as_local_morning():
    # 09:00 UTC = 06:00 BRT => before 08:00 local => pushed to 08:00 BRT same day.
    out = _apply_schedule_window(_utc(2026, 10, 14, 9), WINDOW)
    assert _local(out).hour == 8 and _local(out).day == 14


def test_after_close_goes_to_next_business_morning():
    # Wed 18:00 BRT (21:00 UTC) => Thu 08:00 BRT
    out = _apply_schedule_window(_utc(2026, 10, 14, 21), WINDOW)
    assert (_local(out).day, _local(out).hour) == (15, 8)


def test_friday_evening_skips_the_weekend():
    # Fri 2026-10-16 18:00 BRT => Mon 2026-10-19 08:00 BRT
    out = _apply_schedule_window(_utc(2026, 10, 16, 21), WINDOW)
    assert (_local(out).day, _local(out).hour, _local(out).weekday()) == (19, 8, 0)


def test_saturday_midday_goes_to_monday():
    out = _apply_schedule_window(_utc(2026, 10, 17, 15), WINDOW)
    assert _local(out).weekday() == 0 and _local(out).hour == 8


def test_other_behaviour_passes_through():
    dt = _utc(2026, 10, 17, 3)
    assert _apply_schedule_window(dt, {**WINDOW, "outside_window_behavior": "send_anyway"}) == dt


def test_malformed_window_passes_through():
    dt = _utc(2026, 10, 17, 3)
    assert _apply_schedule_window(dt, {**WINDOW, "start": "oito"}) == dt
    assert _apply_schedule_window(dt, {**WINDOW, "tz": "Mars/Base"}) == dt
