"""Tests for `app/services/scheduling/conflicts.py`.

Covers `ProfessionalAvailabilityConflict.applies` against fabricated
availability windows. Engine integration is covered upstream in
`seed/lib/backend/tests/domain/scheduling/`.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Iterable

import pytest

from app.services.scheduling import (
    AvailabilityWindow,
    ProfessionalAvailabilityConflict,
)
from noctusai_lib.domain.scheduling.engine import (
    SchedulingContext,
    SchedulingRules,
    Slot,
    ZeroTravelLookup,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _dt(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=timezone.utc)


def _slot(day: date, start_hour: int, duration_minutes: int = 50) -> Slot:
    start = _dt(day, start_hour)
    return Slot(
        start_at=start,
        end_at=start + timedelta(minutes=duration_minutes),
        duration_minutes=duration_minutes,
    )


def _context(rules: SchedulingRules | None = None) -> SchedulingContext:
    rules = rules or SchedulingRules(timezone=timezone.utc)
    return SchedulingContext(
        target_location_id="clinic-1",
        existing_intervals_sorted=[],
        travel_lookup=ZeroTravelLookup(),
        rules=rules,
    )


def _lookup(windows_by_date: dict[date, Iterable[AvailabilityWindow]]):
    def _resolve(d: date) -> list[AvailabilityWindow]:
        return list(windows_by_date.get(d, []))
    return _resolve


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestProfessionalAvailabilityConflict:
    def test_slot_inside_available_window_is_accepted(self):
        """Happy path — slot fits inside an available window → applies()=False."""
        d = date(2026, 6, 1)
        windows = {d: [AvailabilityWindow(_dt(d, 9), _dt(d, 17))]}
        conflict = ProfessionalAvailabilityConflict(_lookup(windows))

        assert conflict.applies(_slot(d, 10), _context()) is False

    def test_slot_with_no_window_for_date_is_rejected(self):
        """No availability for the slot's date → applies()=True (REJECT)."""
        d = date(2026, 6, 1)
        conflict = ProfessionalAvailabilityConflict(_lookup({}))

        assert conflict.applies(_slot(d, 10), _context()) is True

    def test_blocked_window_overlapping_slot_rejects(self):
        """Block beats availability — even if a wider available window
        exists, an overlapping block rejects the slot."""
        d = date(2026, 6, 1)
        windows = {
            d: [
                AvailabilityWindow(_dt(d, 9), _dt(d, 17)),
                AvailabilityWindow(_dt(d, 10), _dt(d, 11), is_blocked=True),
            ]
        }
        conflict = ProfessionalAvailabilityConflict(_lookup(windows))

        assert conflict.applies(_slot(d, 10, duration_minutes=30), _context()) is True

    def test_specific_date_block_overrides_recurring_window(self):
        """One-off block on a specific date rejects, even though a
        recurring window would otherwise cover the slot. Mirrors the
        therapy.availability_slots semantics where is_blocked=true rows
        override the recurring set for their specific_date."""
        d = date(2026, 6, 1)
        windows = {
            d: [
                AvailabilityWindow(_dt(d, 9), _dt(d, 17)),
                AvailabilityWindow(_dt(d, 9), _dt(d, 17), is_blocked=True),
            ]
        }
        conflict = ProfessionalAvailabilityConflict(_lookup(windows))

        assert conflict.applies(_slot(d, 14), _context()) is True

    def test_slot_ending_exactly_at_window_end_is_accepted(self):
        """Half-open interval — slot.end_at == window.end_at must fit."""
        d = date(2026, 6, 1)
        windows = {d: [AvailabilityWindow(_dt(d, 9), _dt(d, 10))]}
        conflict = ProfessionalAvailabilityConflict(_lookup(windows))

        slot = Slot(
            start_at=_dt(d, 9),
            end_at=_dt(d, 10),
            duration_minutes=60,
        )
        assert conflict.applies(slot, _context()) is False

    def test_slot_extending_past_window_end_is_rejected(self):
        """Slot must be FULLY contained — partial overlap doesn't count
        as available."""
        d = date(2026, 6, 1)
        windows = {d: [AvailabilityWindow(_dt(d, 9), _dt(d, 10))]}
        conflict = ProfessionalAvailabilityConflict(_lookup(windows))

        slot = Slot(
            start_at=_dt(d, 9, 30),
            end_at=_dt(d, 10, 30),
            duration_minutes=60,
        )
        assert conflict.applies(slot, _context()) is True

    def test_lookup_called_with_slot_date_only(self):
        """The lookup callable receives a date, not a datetime —
        confirms the contract for service-layer implementations."""
        seen: list[date] = []

        def lookup(d: date) -> list[AvailabilityWindow]:
            seen.append(d)
            return [AvailabilityWindow(_dt(d, 0), _dt(d + timedelta(days=1), 0))]

        conflict = ProfessionalAvailabilityConflict(lookup)
        d = date(2026, 6, 1)
        conflict.applies(_slot(d, 14), _context())

        assert seen == [d]
        assert all(isinstance(item, date) and not isinstance(item, datetime) for item in seen)

    def test_empty_window_list_for_date_rejects(self):
        """Lookup returning [] for the slot's date → no available window → REJECT."""
        d = date(2026, 6, 1)
        conflict = ProfessionalAvailabilityConflict(_lookup({d: []}))

        assert conflict.applies(_slot(d, 10), _context()) is True
