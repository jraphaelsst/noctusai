"""Real-estate scheduling rules — exercised against the seed `SchedulingEngine`.

Ported from `whatsapp-google-scheduling/tests/test_scheduling_service.py`.

Source-side rules lived in `app.services.scheduling_service.SchedulingService`.
The math has been lifted verbatim into `noctusai_lib.domain.scheduling.SchedulingEngine`
(see `KB § PATTERNS/scheduling-seed.md`); this product consumes it via
`app.services.scheduling_adapters.make_scheduling_engine` (built on top of the
condo-aware `RoutingLookup`). These tests assert the real-estate semantics
the source repo demanded — standard slots, lunch blocking, same-condo
duration shortcut, custom working hours, transition buffer between condos —
still hold against the seed-engine-backed product wrapper.

Vocabulary translated:
  - `target_condominium_id` (source kwarg)  → `target_location_id` (seed kwarg).
  - `condominium_id` on `ScheduledInterval` → `location_id` on `BlockedInterval`.
  - `time_window` (source kwarg)            → `window_name` (seed kwarg).
  - `travel_buffer_minutes` (source rule)   → `transition_buffer_minutes` (seed).
  - `same_condominium_duration_minutes`     → `same_location_duration_minutes`.
"""

from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from noctusai_lib.domain.scheduling import (
    BlockedInterval,
    SchedulingEngine,
    SchedulingRules,
    WorkingWindow,
)


TZ = ZoneInfo("America/Sao_Paulo")


class _StubTravelLookup:
    """Source: `_StubTravelService` — same/different condo branch.

    Same-id pair returns 0 (matches the seed convention of "no transition
    needed within one location"); distinct ids return a fixed minutes value.
    """

    def __init__(self, default_minutes: int = 20):
        self.default_minutes = default_minutes

    def travel_minutes(
        self,
        origin_location_id: int | str,
        destination_location_id: int | str,
    ) -> int:
        if origin_location_id == destination_location_id:
            return 0
        return self.default_minutes


def _at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 5, 12, hour, minute, tzinfo=TZ)


def _engine(default_travel_minutes: int = 20) -> SchedulingEngine:
    """Source-defaults engine: 90/60 standard/same-location duration, 10-min
    transition buffer, default morning/afternoon working windows."""
    return SchedulingEngine(
        SchedulingRules(timezone=TZ, transition_buffer_minutes=10),
        travel_lookup=_StubTravelLookup(default_minutes=default_travel_minutes),
    )


def test_generates_standard_morning_slots_without_existing_appointments() -> None:
    slots = _engine().candidate_slots(
        date(2026, 5, 12),
        target_location_id=1,
        existing_intervals=[],
        window_name="morning",
    )

    assert [
        (slot.start_at.time().isoformat(), slot.end_at.time().isoformat())
        for slot in slots
    ] == [
        ("09:00:00", "10:30:00"),
        ("09:30:00", "11:00:00"),
        ("10:00:00", "11:30:00"),
        ("10:30:00", "12:00:00"),
    ]


def test_blocks_lunch_by_using_fixed_working_windows() -> None:
    slots = _engine().candidate_slots(
        date(2026, 5, 12),
        target_location_id=1,
        existing_intervals=[],
    )

    # No slot may start at noon or end at 1pm — 12-13 is the lunch gap
    # between the two default working windows (09-12 morning, 13:30-16:30
    # afternoon).
    assert all(
        not (slot.start_at.time().hour == 12 or slot.end_at.time().hour == 13)
        for slot in slots
    )


def test_same_location_back_to_back_can_use_one_hour() -> None:
    """Source: `test_same_condominium_back_to_back_can_use_one_hour`.

    When the previous interval ends exactly at the candidate start AND
    they're at the same location, the engine packs the slot to
    `same_location_duration_minutes` (60) instead of the default 90.
    """
    existing = [
        BlockedInterval(start=_at(9), end=_at(10), location_id=7),
    ]

    slots = _engine().candidate_slots(
        date(2026, 5, 12),
        target_location_id=7,
        existing_intervals=existing,
        window_name="morning",
    )

    assert any(
        slot.start_at == _at(10)
        and slot.end_at == _at(11)
        and slot.duration_minutes == 60
        for slot in slots
    )


def test_custom_working_hours_from_rules_override_defaults() -> None:
    """Source-style: pass custom WorkingWindows into the rules and verify
    the engine honors the new bounds for both filters."""
    custom_rules = SchedulingRules(
        timezone=TZ,
        transition_buffer_minutes=10,
        working_windows=[
            WorkingWindow(name="morning", start=time(8, 0), end=time(11, 0)),
            WorkingWindow(name="afternoon", start=time(14, 0), end=time(17, 0)),
        ],
    )
    custom_engine = SchedulingEngine(custom_rules, travel_lookup=_StubTravelLookup())

    morning_slots = custom_engine.candidate_slots(
        date(2026, 5, 12),
        target_location_id=1,
        existing_intervals=[],
        window_name="morning",
    )
    assert morning_slots, "expected morning candidates within custom window"
    assert morning_slots[0].start_at.time() == time(8, 0)

    afternoon_slots = custom_engine.candidate_slots(
        date(2026, 5, 12),
        target_location_id=1,
        existing_intervals=[],
        window_name="afternoon",
    )
    assert any(slot.start_at.time() == time(14, 0) for slot in afternoon_slots)


def test_different_location_requires_travel_buffer_after_previous_appointment() -> None:
    """Source: `test_different_condominium_requires_travel_buffer_after_previous_appointment`.

    Previous appt at condo 1 ends at 10:00; target is condo 2.
    Travel = 20min, transition_buffer = 10min ⇒ 30-min required gap.
    A slot starting at 10:00 must be rejected; 10:30 must be allowed.
    """
    existing = [
        BlockedInterval(start=_at(9), end=_at(10), location_id=1),
    ]

    slots = _engine(default_travel_minutes=20).candidate_slots(
        date(2026, 5, 12),
        target_location_id=2,
        existing_intervals=existing,
        window_name="morning",
    )

    assert all(slot.start_at != _at(10) for slot in slots)
    assert any(slot.start_at == _at(10, 30) for slot in slots)
