"""Tests for `app.services.scheduling` — Phase 7 SchedulingEngine wiring.

Verifies:
  * `build_rules(settings)` maps imobi config → `SchedulingRules` with
    the brief's defaults (morning 09:00-12:00, afternoon 13:30-16:30,
    lunch 12:00-13:30 implicit, travel buffer 10 min, standard 90 min,
    same-condo 60 min).
  * `SchedulingEngine` candidate generation:
      - lunch gap is unschedulable (12:00-13:30 windowed-out),
      - same-condo back-to-back uses 60-min duration shortcut,
      - travel buffer rejects too-close cross-location bookings.
  * `SchedulingService.lookup_property` returns the right shape.
  * `SchedulingService.propose_appointment` calls the engine + paginates.
  * `SchedulingService.confirm_appointment` inserts the row +
    re-validates the slot is still free.

Per the rule "No monkey-patching of our own code" — all patches target
the Supabase boundary via `MockSupabaseClient`. The engine itself runs
unmodified (it's pure logic — same-process import; the seed test suite
already covers its math).
"""
from __future__ import annotations

from datetime import date, datetime, time, timezone
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from noctusai_lib.testing import MockSupabaseClient, MockSupabaseResponse


# ---------------------------------------------------------------------------
# Shared fixtures + helpers
# ---------------------------------------------------------------------------

ORG_ID = "00000000-0000-0000-0000-000000000001"
TZ_BR = ZoneInfo("America/Sao_Paulo")


def _settings_stub():
    """Return a stand-in settings object exposing the imobi_scheduling_*
    attributes the rules-builder reads. We use a plain dataclass rather
    than the real `ImobiSchedulingSettings` to keep the unit tests
    decoupled from env / Supabase resolution."""
    from dataclasses import dataclass

    @dataclass
    class _S:
        imobi_scheduling_timezone: str = "America/Sao_Paulo"
        imobi_scheduling_morning_start: str = "09:00"
        imobi_scheduling_morning_end: str = "12:00"
        imobi_scheduling_afternoon_start: str = "13:30"
        imobi_scheduling_afternoon_end: str = "16:30"
        imobi_scheduling_travel_buffer_minutes: int = 10
        imobi_scheduling_standard_duration_minutes: int = 90
        imobi_scheduling_same_condo_duration_minutes: int = 60
        imobi_scheduling_slot_grid_minutes: int = 30

    return _S()


def _condo_id() -> str:
    return "ccccccc1-0000-0000-0000-000000000001"


def _other_condo_id() -> str:
    return "ccccccc2-0000-0000-0000-000000000002"


def _property_row(
    *,
    prop_id: str = "ppppppp1-0000-0000-0000-000000000001",
    code: str = "AP-2034",
    condo: str | None = None,
    active: bool = True,
) -> dict:
    return {
        "id": prop_id,
        "org_id": ORG_ID,
        "code": code,
        "condominium_id": condo or _condo_id(),
        "active": active,
    }


def _condo_row(name: str = "Edifício Aurora", condo_id: str | None = None) -> dict:
    return {
        "id": condo_id or _condo_id(),
        "org_id": ORG_ID,
        "name": name,
    }


def _appt_row(
    *,
    start: datetime,
    end: datetime,
    condominium_id: str | None = None,
    crew: str | None = None,
    status: str = "scheduled",
    appt_id: str = "aaaaaaa1-0000-0000-0000-000000000001",
) -> dict:
    return {
        "id": appt_id,
        "org_id": ORG_ID,
        "start_at": start.isoformat(),
        "end_at": end.isoformat(),
        "condominium_id": condominium_id or _condo_id(),
        "media_crew_user_id": crew,
        "status": status,
    }


# ---------------------------------------------------------------------------
# `build_rules`
# ---------------------------------------------------------------------------

class TestBuildRules:
    def test_imobi_defaults(self):
        from app.services.scheduling import build_rules

        rules = build_rules(_settings_stub())

        assert rules.timezone == TZ_BR
        assert rules.transition_buffer_minutes == 10
        assert rules.default_duration_minutes == 90
        assert rules.same_location_duration_minutes == 60
        assert rules.slot_grid_minutes == 30
        names = [w.name for w in rules.working_windows]
        assert names == ["morning", "afternoon"]

    def test_morning_window_is_9_to_12(self):
        from app.services.scheduling import build_rules

        rules = build_rules(_settings_stub())
        morning = next(w for w in rules.working_windows if w.name == "morning")
        assert morning.start == time(9, 0)
        assert morning.end == time(12, 0)

    def test_afternoon_window_is_1330_to_1630(self):
        from app.services.scheduling import build_rules

        rules = build_rules(_settings_stub())
        afternoon = next(w for w in rules.working_windows if w.name == "afternoon")
        assert afternoon.start == time(13, 30)
        assert afternoon.end == time(16, 30)

    def test_lunch_gap_is_implicit_between_windows(self):
        """The 12:00-13:30 lunch interval is NOT a `BlockedInterval`;
        it's the gap between two named WorkingWindows. No engine
        configuration is needed to enforce it."""
        from app.services.scheduling import build_rules

        rules = build_rules(_settings_stub())
        morning_end = next(w for w in rules.working_windows if w.name == "morning").end
        afternoon_start = next(w for w in rules.working_windows if w.name == "afternoon").start
        # Lunch = the time between morning_end (12:00) and afternoon_start (13:30).
        assert morning_end == time(12, 0)
        assert afternoon_start == time(13, 30)

    def test_raises_on_malformed_time(self):
        """The rules dataclass is a startup-time construct — surface
        a malformed `HH:MM` loud, don't silently degrade."""
        from app.services.scheduling import build_rules

        bad = _settings_stub()
        bad.imobi_scheduling_morning_start = "9:00am"  # invalid

        with pytest.raises(ValueError):
            build_rules(bad)


# ---------------------------------------------------------------------------
# Engine math via `build_engine` — quick sanity (full math in seed tests)
# ---------------------------------------------------------------------------

class TestEngineSlotGeneration:
    """Spot-check the engine math under imobi defaults.

    The seed `tests/domain/scheduling/test_engine.py` covers the math
    in depth. These tests confirm imobi's specific config produces the
    expected behavior under realistic inputs.
    """

    def test_empty_day_returns_morning_and_afternoon_candidates(self):
        from app.services.scheduling import build_engine, build_rules

        rules = build_rules(_settings_stub())
        engine = build_engine(rules)
        slots = engine.candidate_slots(
            requested_date=date(2026, 5, 15),
            target_location_id=_condo_id(),
            existing_intervals=[],
        )
        # Engine returns slots whose duration (90 min) fits in each window.
        # Morning (09:00-12:00): starts at 09:00 fit (ends 10:30) — 10:30
        # doesn't fit (would end 12:00 ok, but 90-min from 10:30 → 12:00
        # is the boundary), but cursor stride is 30 min so 09:00, 09:30,
        # 10:00, 10:30 are candidates. 10:30 ends at 12:00 — boundary fits
        # (`end_at <= window_end`). Afternoon analog.
        assert len(slots) > 0
        # Every slot ends inside a working window — none cross lunch.
        for slot in slots:
            assert slot.start_at.time() < time(12, 0) or slot.start_at.time() >= time(13, 30)
            assert slot.end_at.time() <= time(12, 0) or slot.end_at.time() <= time(16, 30)

    def test_lunch_window_unschedulable(self):
        from app.services.scheduling import build_engine, build_rules

        rules = build_rules(_settings_stub())
        engine = build_engine(rules)
        slots = engine.candidate_slots(
            requested_date=date(2026, 5, 15),
            target_location_id=_condo_id(),
            existing_intervals=[],
        )
        # No slot may start during lunch (12:00-13:30) nor cross into it.
        for slot in slots:
            assert not (time(12, 0) <= slot.start_at.time() < time(13, 30)), (
                f"slot starts in lunch window: {slot}"
            )
            # And no morning slot ends after 12:00.
            if slot.start_at.time() < time(12, 0):
                assert slot.end_at.time() <= time(12, 0), (
                    f"morning slot bleeds into lunch: {slot}"
                )

    def test_morning_filter_excludes_afternoon_slots(self):
        from app.services.scheduling import build_engine, build_rules

        rules = build_rules(_settings_stub())
        engine = build_engine(rules)
        slots = engine.candidate_slots(
            requested_date=date(2026, 5, 15),
            target_location_id=_condo_id(),
            existing_intervals=[],
            window_name="morning",
        )
        for slot in slots:
            assert slot.start_at.time() < time(12, 0)

    def test_same_condo_back_to_back_uses_60_min_duration(self):
        """Per the seed's same-location-shortcut: if the previous
        interval ends exactly at the candidate start AND shares the same
        location, the duration drops to 60 min (vs. the default 90)."""
        from app.services.scheduling import build_engine, build_rules

        rules = build_rules(_settings_stub())
        engine = build_engine(rules)

        # Existing interval ends precisely at 10:00 in the same condo.
        existing = [
            _make_blocked(
                start=datetime(2026, 5, 15, 9, 0, tzinfo=TZ_BR),
                end=datetime(2026, 5, 15, 10, 0, tzinfo=TZ_BR),
                location_id=_condo_id(),
            ),
        ]
        slots = engine.candidate_slots(
            requested_date=date(2026, 5, 15),
            target_location_id=_condo_id(),
            existing_intervals=existing,
        )
        # The 10:00 candidate should have duration 60 (same-location
        # shortcut), not 90.
        ten_am_candidates = [s for s in slots if s.start_at.hour == 10 and s.start_at.minute == 0]
        assert ten_am_candidates, "expected a 10:00 candidate"
        assert ten_am_candidates[0].duration_minutes == 60

    def test_travel_buffer_rejects_too_close_cross_location_booking(self):
        """When previous interval is at a different condo, the engine
        must respect both the travel time + the 10-min transition
        buffer."""
        from app.services.scheduling import build_engine, build_rules

        rules = build_rules(_settings_stub())

        class _FixedTravel:
            def travel_minutes(self, origin, destination) -> int:
                # 25 min between the two condos in this test.
                if origin == destination:
                    return 0
                return 25

        engine = build_engine(rules, travel_lookup=_FixedTravel())

        # Previous interval at the other condo ends at 09:00. Travel 25 min
        # + buffer 10 min = 35 min required gap. Earliest valid start at
        # target condo: 09:35.
        existing = [
            _make_blocked(
                start=datetime(2026, 5, 15, 8, 30, tzinfo=TZ_BR),
                end=datetime(2026, 5, 15, 9, 0, tzinfo=TZ_BR),
                location_id=_other_condo_id(),
            ),
        ]
        slots = engine.candidate_slots(
            requested_date=date(2026, 5, 15),
            target_location_id=_condo_id(),
            existing_intervals=existing,
        )
        # No slot earlier than 09:35.
        early_slots = [s for s in slots if s.start_at.time() < time(9, 30)]
        assert early_slots == [], (
            f"expected no slots before 09:30 (travel+buffer), got: {early_slots}"
        )


def _make_blocked(*, start, end, location_id, assignee_id=None):
    from noctusai_lib.domain.scheduling import BlockedInterval

    return BlockedInterval(
        start=start, end=end, location_id=location_id, assignee_id=assignee_id
    )


# ---------------------------------------------------------------------------
# SchedulingService — DB orchestration
# ---------------------------------------------------------------------------

class TestServiceLookupProperty:
    """`SchedulingService.lookup_property` glues properties + condos."""

    def test_returns_property_and_condo_name(self):
        from app.services.scheduling import (
            PropertyLookupResult,
            SchedulingService,
            build_rules,
        )

        db = MockSupabaseClient(data=[])
        svc = SchedulingService(
            admin_client=db,
            org_id=ORG_ID,
            rules=build_rules(_settings_stub()),
        )
        # Sequence: properties select hit → condominiums select hit.
        svc._scoped.set_sequential_responses(
            "properties",
            [MockSupabaseResponse(data=[_property_row()])],
        )
        svc._scoped.set_sequential_responses(
            "condominiums",
            [MockSupabaseResponse(data=[_condo_row(name="Edifício Aurora")])],
        )

        result = svc.lookup_property("AP-2034")

        assert isinstance(result, PropertyLookupResult)
        assert result.found is True
        assert result.code == "AP-2034"
        assert result.condominium_name == "Edifício Aurora"

    def test_returns_not_found_when_missing(self):
        from app.services.scheduling import SchedulingService, build_rules

        db = MockSupabaseClient(data=[])
        svc = SchedulingService(
            admin_client=db,
            org_id=ORG_ID,
            rules=build_rules(_settings_stub()),
        )
        svc._scoped.set_sequential_responses(
            "properties", [MockSupabaseResponse(data=[])],
        )

        result = svc.lookup_property("AP-NOT-FOUND")
        assert result.found is False
        assert result.code == "AP-NOT-FOUND"
        assert result.property_id is None


class TestServiceProposeAppointment:
    """`SchedulingService.propose_appointment` calls the engine."""

    def test_returns_slots_when_property_known_and_day_empty(self):
        from app.services.scheduling import SchedulingService, build_rules

        db = MockSupabaseClient(data=[])
        svc = SchedulingService(
            admin_client=db,
            org_id=ORG_ID,
            rules=build_rules(_settings_stub()),
        )
        # Multiple lookups during propose: properties (lookup_property),
        # condominiums (lookup), appointments (existing intervals).
        # Each subsequent ".execute()" pops from the queue.
        svc._scoped.set_sequential_responses(
            "properties", [MockSupabaseResponse(data=[_property_row()])],
        )
        svc._scoped.set_sequential_responses(
            "condominiums", [MockSupabaseResponse(data=[_condo_row()])],
        )
        svc._scoped.set_sequential_responses(
            "appointments", [MockSupabaseResponse(data=[])],
        )

        slots = svc.propose_appointment(
            property_code="AP-2034",
            requested_date="2026-05-15",
            time_window="morning",
            limit=3,
        )
        assert len(slots) > 0
        # Top-3 — at most 3 entries.
        assert len(slots) <= 3
        # All proposed slots are in the morning (window filter respected).
        for slot in slots:
            parsed_start = datetime.fromisoformat(slot.start_at)
            assert parsed_start.time() < time(12, 0)

    def test_raises_when_property_unknown(self):
        from app.services.scheduling import SchedulingService, build_rules

        db = MockSupabaseClient(data=[])
        svc = SchedulingService(
            admin_client=db,
            org_id=ORG_ID,
            rules=build_rules(_settings_stub()),
        )
        svc._scoped.set_sequential_responses(
            "properties", [MockSupabaseResponse(data=[])],
        )

        with pytest.raises(ValueError, match="Property code not found"):
            svc.propose_appointment(
                property_code="AP-MISSING",
                requested_date="2026-05-15",
                time_window="any",
            )

    def test_raises_on_malformed_date(self):
        from app.services.scheduling import SchedulingService, build_rules

        db = MockSupabaseClient(data=[])
        svc = SchedulingService(
            admin_client=db,
            org_id=ORG_ID,
            rules=build_rules(_settings_stub()),
        )
        with pytest.raises(ValueError, match="ISO-formatted"):
            svc.propose_appointment(
                property_code="AP-2034",
                requested_date="15/05/2026",  # not ISO
                time_window="any",
            )

    def test_skips_slots_overlapping_existing_appointments(self):
        from app.services.scheduling import SchedulingService, build_rules

        db = MockSupabaseClient(data=[])
        svc = SchedulingService(
            admin_client=db,
            org_id=ORG_ID,
            rules=build_rules(_settings_stub()),
        )
        # Existing morning booking 09:00-10:30 at the same condo.
        appt_start = datetime(2026, 5, 15, 9, 0, tzinfo=TZ_BR)
        appt_end = datetime(2026, 5, 15, 10, 30, tzinfo=TZ_BR)
        svc._scoped.set_sequential_responses(
            "properties", [MockSupabaseResponse(data=[_property_row()])],
        )
        svc._scoped.set_sequential_responses(
            "condominiums", [MockSupabaseResponse(data=[_condo_row()])],
        )
        svc._scoped.set_sequential_responses(
            "appointments",
            [
                MockSupabaseResponse(
                    data=[_appt_row(start=appt_start, end=appt_end)]
                ),
            ],
        )

        slots = svc.propose_appointment(
            property_code="AP-2034",
            requested_date="2026-05-15",
            time_window="morning",
            limit=5,
        )
        # No slot may overlap [09:00, 10:30) on this same condo. The
        # 10:30 slot (same-condo back-to-back) is allowed.
        for slot in slots:
            parsed_start = datetime.fromisoformat(slot.start_at)
            assert not (
                time(9, 0) <= parsed_start.time() < time(10, 30)
            ), f"slot overlaps existing: {slot}"


class TestServiceConfirmAppointment:
    """`SchedulingService.confirm_appointment` inserts a row + revalidates."""

    def test_returns_created_with_appointment_id_on_success(self):
        from app.services.scheduling import (
            ConfirmationResult,
            SchedulingService,
            build_rules,
        )

        db = MockSupabaseClient(data=[])
        svc = SchedulingService(
            admin_client=db,
            org_id=ORG_ID,
            rules=build_rules(_settings_stub()),
        )
        new_id = "aaaaaaa9-0000-0000-0000-000000000099"
        svc._scoped.set_sequential_responses(
            "properties", [MockSupabaseResponse(data=[_property_row()])],
        )
        svc._scoped.set_sequential_responses(
            "condominiums", [MockSupabaseResponse(data=[_condo_row()])],
        )
        svc._scoped.set_sequential_responses(
            "appointments",
            [
                MockSupabaseResponse(data=[]),                     # re-validation fetch
                MockSupabaseResponse(data=[{"id": new_id}]),       # insert returning row
            ],
        )

        result = svc.confirm_appointment(
            property_code="AP-2034",
            start_at="2026-05-15T10:00:00-03:00",
            end_at="2026-05-15T11:30:00-03:00",
            services=["photos", "videos"],
        )

        assert isinstance(result, ConfirmationResult)
        assert result.created is True
        assert result.appointment_id == new_id

    def test_rejects_when_end_before_start(self):
        from app.services.scheduling import SchedulingService, build_rules

        db = MockSupabaseClient(data=[])
        svc = SchedulingService(
            admin_client=db,
            org_id=ORG_ID,
            rules=build_rules(_settings_stub()),
        )
        result = svc.confirm_appointment(
            property_code="AP-2034",
            start_at="2026-05-15T11:30:00-03:00",
            end_at="2026-05-15T10:00:00-03:00",
        )
        assert result.created is False
        assert "strictly after" in (result.reason or "")

    def test_rejects_when_property_unknown(self):
        from app.services.scheduling import SchedulingService, build_rules

        db = MockSupabaseClient(data=[])
        svc = SchedulingService(
            admin_client=db,
            org_id=ORG_ID,
            rules=build_rules(_settings_stub()),
        )
        svc._scoped.set_sequential_responses(
            "properties", [MockSupabaseResponse(data=[])],
        )
        result = svc.confirm_appointment(
            property_code="AP-MISSING",
            start_at="2026-05-15T10:00:00-03:00",
            end_at="2026-05-15T11:30:00-03:00",
        )
        assert result.created is False
        assert "property code not found" in (result.reason or "")

    def test_conflict_revalidation_rejects_taken_slot(self):
        """Race between propose+confirm: another booking landed in the
        same slot. Confirmation MUST detect via final re-check, even
        though propose returned it earlier."""
        from app.services.scheduling import SchedulingService, build_rules

        db = MockSupabaseClient(data=[])
        svc = SchedulingService(
            admin_client=db,
            org_id=ORG_ID,
            rules=build_rules(_settings_stub()),
        )
        # Overlapping existing booking 10:00-11:30 at the same condo.
        existing_start = datetime(2026, 5, 15, 10, 0, tzinfo=TZ_BR)
        existing_end = datetime(2026, 5, 15, 11, 30, tzinfo=TZ_BR)
        svc._scoped.set_sequential_responses(
            "properties", [MockSupabaseResponse(data=[_property_row()])],
        )
        svc._scoped.set_sequential_responses(
            "condominiums", [MockSupabaseResponse(data=[_condo_row()])],
        )
        svc._scoped.set_sequential_responses(
            "appointments",
            [
                MockSupabaseResponse(
                    data=[_appt_row(start=existing_start, end=existing_end)]
                ),
            ],
        )

        result = svc.confirm_appointment(
            property_code="AP-2034",
            start_at="2026-05-15T10:00:00-03:00",
            end_at="2026-05-15T11:30:00-03:00",
        )
        assert result.created is False
        assert "slot conflicts" in (result.reason or "")


class TestServiceConfirmAppointmentCalendarFactory:
    """Phase 8 — `SchedulingService.confirm_appointment` composes the
    Calendar `create_event` BEFORE the DB insert when a
    ``calendar_event_factory`` is injected at construction time."""

    def test_calendar_event_id_stamped_onto_db_payload(self):
        """Successful Calendar create → event_id flows into the
        ``google_calendar_event_id`` column of the inserted row."""
        from app.services.scheduling import SchedulingService, build_rules

        calls: list[dict] = []

        def _fake_factory(**kwargs) -> str:
            calls.append(kwargs)
            return "evt-google-abc-001"

        db = MockSupabaseClient(data=[])
        svc = SchedulingService(
            admin_client=db,
            org_id=ORG_ID,
            rules=build_rules(_settings_stub()),
            calendar_event_factory=_fake_factory,
        )
        new_id = "aaaaaaa9-0000-0000-0000-000000000099"
        svc._scoped.set_sequential_responses(
            "properties", [MockSupabaseResponse(data=[_property_row()])],
        )
        svc._scoped.set_sequential_responses(
            "condominiums", [MockSupabaseResponse(data=[_condo_row()])],
        )
        svc._scoped.set_sequential_responses(
            "appointments",
            [
                MockSupabaseResponse(data=[]),                     # re-validation
                MockSupabaseResponse(data=[{"id": new_id}]),       # insert
            ],
        )

        result = svc.confirm_appointment(
            property_code="AP-2034",
            start_at="2026-05-15T10:00:00-03:00",
            end_at="2026-05-15T11:30:00-03:00",
            services=["photos"],
            appointment_request_id="req-xyz",
        )
        assert result.created is True

        # Factory was invoked once with the expected logical inputs.
        assert len(calls) == 1
        assert calls[0]["appointment_request_id"] == "req-xyz"
        assert "Visita técnica" in calls[0]["summary"]

        # The DB insert payload carried the event id.
        inserted = svc._scoped.table("appointments").inserted_payloads
        assert any(
            p.get("google_calendar_event_id") == "evt-google-abc-001"
            for p in inserted
        )

    def test_calendar_create_failure_aborts_db_insert(self):
        """Calendar create raises → no DB insert → ConfirmationResult is
        ``created=False`` with a reason that surfaces the failure."""
        from app.services.scheduling import SchedulingService, build_rules

        def _raises(**kwargs) -> str:
            raise RuntimeError("calendar quota exceeded")

        db = MockSupabaseClient(data=[])
        svc = SchedulingService(
            admin_client=db,
            org_id=ORG_ID,
            rules=build_rules(_settings_stub()),
            calendar_event_factory=_raises,
        )
        svc._scoped.set_sequential_responses(
            "properties", [MockSupabaseResponse(data=[_property_row()])],
        )
        svc._scoped.set_sequential_responses(
            "condominiums", [MockSupabaseResponse(data=[_condo_row()])],
        )
        svc._scoped.set_sequential_responses(
            "appointments",
            [MockSupabaseResponse(data=[])],  # re-validation only — no insert
        )

        result = svc.confirm_appointment(
            property_code="AP-2034",
            start_at="2026-05-15T10:00:00-03:00",
            end_at="2026-05-15T11:30:00-03:00",
        )
        assert result.created is False
        assert "calendar event creation failed" in (result.reason or "")
        # No DB insert landed — appointments table received no inserts.
        inserted = svc._scoped.table("appointments").inserted_payloads
        assert inserted == []

    def test_caller_supplied_event_id_skips_factory(self):
        """When the caller passes ``google_calendar_event_id`` directly
        (because they pre-created the event), the factory is skipped —
        the caller has already taken responsibility for idempotency."""
        from app.services.scheduling import SchedulingService, build_rules

        called = []

        def _factory(**kwargs) -> str:
            called.append(kwargs)
            return "should-not-be-used"

        db = MockSupabaseClient(data=[])
        svc = SchedulingService(
            admin_client=db,
            org_id=ORG_ID,
            rules=build_rules(_settings_stub()),
            calendar_event_factory=_factory,
        )
        svc._scoped.set_sequential_responses(
            "properties", [MockSupabaseResponse(data=[_property_row()])],
        )
        svc._scoped.set_sequential_responses(
            "condominiums", [MockSupabaseResponse(data=[_condo_row()])],
        )
        new_id = "aaaaaaa9-0000-0000-0000-000000000099"
        svc._scoped.set_sequential_responses(
            "appointments",
            [
                MockSupabaseResponse(data=[]),
                MockSupabaseResponse(data=[{"id": new_id}]),
            ],
        )

        result = svc.confirm_appointment(
            property_code="AP-2034",
            start_at="2026-05-15T10:00:00-03:00",
            end_at="2026-05-15T11:30:00-03:00",
            google_calendar_event_id="caller-supplied-event-id",
        )
        assert result.created is True
        assert called == []  # factory skipped

        inserted = svc._scoped.table("appointments").inserted_payloads
        assert any(
            p.get("google_calendar_event_id") == "caller-supplied-event-id"
            for p in inserted
        )


# ---------------------------------------------------------------------------
# Phase 9 — cancel_appointment
# ---------------------------------------------------------------------------


def _scheduled_appt_row(
    *,
    appt_id: str = "aaaaaaa1-0000-0000-0000-000000000001",
    google_event_id: str | None = "evt-google-001",
    start: datetime | None = None,
    end: datetime | None = None,
    status: str = "scheduled",
) -> dict:
    """Stand-in for an existing `appointments` row used by cancel/reschedule fetches."""
    start = start or datetime(2026, 5, 15, 10, 0, tzinfo=TZ_BR)
    end = end or datetime(2026, 5, 15, 11, 30, tzinfo=TZ_BR)
    return {
        "id": appt_id,
        "org_id": ORG_ID,
        "status": status,
        "google_calendar_event_id": google_event_id,
        "condominium_id": _condo_id(),
        "property_id": "ppppppp1-0000-0000-0000-000000000001",
        "start_at": start.isoformat(),
        "end_at": end.isoformat(),
        "appointment_request_id": None,
        "media_crew_user_id": None,
    }


class TestServiceCancelAppointment:
    """`SchedulingService.cancel_appointment` Phase 9 flow:

      - flips ``status`` to ``cancelled`` + writes audit columns;
      - calls the ``calendar_event_canceler`` for rows with a Calendar id;
      - tolerates Calendar-side failures (DB flip still lands);
      - idempotent on already-cancelled rows.
    """

    def test_returns_cancelled_true_and_updates_audit_columns(self):
        from app.services.scheduling import (
            CancellationResult,
            SchedulingService,
            build_rules,
        )

        db = MockSupabaseClient(data=[])
        svc = SchedulingService(
            admin_client=db,
            org_id=ORG_ID,
            rules=build_rules(_settings_stub()),
        )
        appt_id = "aaaaaaa1-0000-0000-0000-000000000001"
        svc._scoped.set_sequential_responses(
            "appointments",
            [
                MockSupabaseResponse(data=[_scheduled_appt_row(appt_id=appt_id)]),  # fetch
                MockSupabaseResponse(data=[]),                                       # update
            ],
        )

        result = svc.cancel_appointment(
            appointment_id=appt_id,
            reason="cliente desistiu",
        )
        assert isinstance(result, CancellationResult)
        assert result.cancelled is True
        assert result.appointment_id == appt_id

        updated = svc._scoped.table("appointments").updated_payloads
        assert len(updated) == 1
        assert updated[0]["status"] == "cancelled"
        assert updated[0]["cancellation_reason"] == "cliente desistiu"
        assert updated[0]["cancelled_at"]  # truthy ISO string

    def test_returns_not_found_when_row_missing(self):
        from app.services.scheduling import SchedulingService, build_rules

        db = MockSupabaseClient(data=[])
        svc = SchedulingService(
            admin_client=db,
            org_id=ORG_ID,
            rules=build_rules(_settings_stub()),
        )
        svc._scoped.set_sequential_responses(
            "appointments",
            [MockSupabaseResponse(data=[])],
        )
        result = svc.cancel_appointment(
            appointment_id="missing-uuid",
            reason="whatever",
        )
        assert result.cancelled is False
        assert "appointment not found" in (result.reason or "")
        # No update fired.
        updated = svc._scoped.table("appointments").updated_payloads
        assert updated == []

    def test_idempotent_when_already_cancelled(self):
        """Calling cancel on an already-cancelled row returns cancelled=False
        with a stable reason (not an exception, not a second flip)."""
        from app.services.scheduling import SchedulingService, build_rules

        db = MockSupabaseClient(data=[])
        svc = SchedulingService(
            admin_client=db,
            org_id=ORG_ID,
            rules=build_rules(_settings_stub()),
        )
        appt_id = "aaaaaaa1-0000-0000-0000-000000000001"
        svc._scoped.set_sequential_responses(
            "appointments",
            [MockSupabaseResponse(
                data=[_scheduled_appt_row(appt_id=appt_id, status="cancelled")]
            )],
        )
        result = svc.cancel_appointment(
            appointment_id=appt_id,
            reason="re-cancel",
        )
        assert result.cancelled is False
        assert "'cancelled'" in (result.reason or "")
        # No update fired (second cancel is a no-op).
        updated = svc._scoped.table("appointments").updated_payloads
        assert updated == []

    def test_calls_calendar_canceler_when_wired(self):
        """Successful DB cancel + a wired canceler → canceler invoked with event_id."""
        from app.services.scheduling import SchedulingService, build_rules

        calls: list[dict] = []

        def _canceler(*, event_id: str) -> None:
            calls.append({"event_id": event_id})

        db = MockSupabaseClient(data=[])
        svc = SchedulingService(
            admin_client=db,
            org_id=ORG_ID,
            rules=build_rules(_settings_stub()),
            calendar_event_canceler=_canceler,
        )
        appt_id = "aaaaaaa1-0000-0000-0000-000000000001"
        svc._scoped.set_sequential_responses(
            "appointments",
            [
                MockSupabaseResponse(
                    data=[_scheduled_appt_row(appt_id=appt_id, google_event_id="evt-zzz")]
                ),
                MockSupabaseResponse(data=[]),
            ],
        )
        result = svc.cancel_appointment(
            appointment_id=appt_id,
            reason=None,
        )
        assert result.cancelled is True
        assert result.calendar_deleted is True
        assert calls == [{"event_id": "evt-zzz"}]

    def test_tolerates_calendar_delete_failure(self):
        """Calendar delete raises → DB cancellation still lands; ``calendar_deleted=False``."""
        from app.services.scheduling import SchedulingService, build_rules

        def _failing_canceler(*, event_id: str) -> None:
            raise RuntimeError("calendar API down")

        db = MockSupabaseClient(data=[])
        svc = SchedulingService(
            admin_client=db,
            org_id=ORG_ID,
            rules=build_rules(_settings_stub()),
            calendar_event_canceler=_failing_canceler,
        )
        appt_id = "aaaaaaa1-0000-0000-0000-000000000001"
        svc._scoped.set_sequential_responses(
            "appointments",
            [
                MockSupabaseResponse(
                    data=[_scheduled_appt_row(appt_id=appt_id, google_event_id="evt-xxx")]
                ),
                MockSupabaseResponse(data=[]),
            ],
        )
        result = svc.cancel_appointment(
            appointment_id=appt_id,
            reason=None,
        )
        assert result.cancelled is True
        assert result.calendar_deleted is False
        # DB update still landed.
        updated = svc._scoped.table("appointments").updated_payloads
        assert len(updated) == 1
        assert updated[0]["status"] == "cancelled"

    def test_skips_calendar_when_event_id_absent(self):
        """Row without a ``google_calendar_event_id`` → canceler is NOT called."""
        from app.services.scheduling import SchedulingService, build_rules

        calls: list[dict] = []

        def _canceler(*, event_id: str) -> None:
            calls.append({"event_id": event_id})

        db = MockSupabaseClient(data=[])
        svc = SchedulingService(
            admin_client=db,
            org_id=ORG_ID,
            rules=build_rules(_settings_stub()),
            calendar_event_canceler=_canceler,
        )
        appt_id = "aaaaaaa1-0000-0000-0000-000000000001"
        svc._scoped.set_sequential_responses(
            "appointments",
            [
                MockSupabaseResponse(
                    data=[_scheduled_appt_row(appt_id=appt_id, google_event_id=None)]
                ),
                MockSupabaseResponse(data=[]),
            ],
        )
        result = svc.cancel_appointment(appointment_id=appt_id)
        assert result.cancelled is True
        assert result.calendar_deleted is False
        assert calls == []


# ---------------------------------------------------------------------------
# Phase 9 — reschedule_appointment
# ---------------------------------------------------------------------------


class TestServiceRescheduleAppointment:
    """`SchedulingService.reschedule_appointment` Phase 9 flow:

      - re-validates the new slot against current bookings (excluding the
        row being moved);
      - flips ``start_at`` / ``end_at`` + writes audit columns (previous_*,
        rescheduled_at);
      - calls the ``calendar_event_updater`` when wired;
      - rejects conflicts + not-found + invalid state.
    """

    def test_returns_rescheduled_true_and_audit_columns(self):
        from app.services.scheduling import (
            RescheduleResult,
            SchedulingService,
            build_rules,
        )

        db = MockSupabaseClient(data=[])
        svc = SchedulingService(
            admin_client=db,
            org_id=ORG_ID,
            rules=build_rules(_settings_stub()),
        )
        appt_id = "aaaaaaa1-0000-0000-0000-000000000001"
        old_start = datetime(2026, 5, 15, 10, 0, tzinfo=TZ_BR)
        old_end = datetime(2026, 5, 15, 11, 30, tzinfo=TZ_BR)
        svc._scoped.set_sequential_responses(
            "appointments",
            [
                MockSupabaseResponse(
                    data=[_scheduled_appt_row(
                        appt_id=appt_id, start=old_start, end=old_end,
                    )]
                ),
                # The conflict-revalidation fetches the day's existing rows.
                # Only the row being moved is in the day; the service filters
                # it out before applying conflict rules.
                MockSupabaseResponse(data=[_appt_row(
                    start=old_start, end=old_end, appt_id=appt_id,
                )]),
                MockSupabaseResponse(data=[]),  # update
            ],
        )

        result = svc.reschedule_appointment(
            appointment_id=appt_id,
            new_start_at="2026-05-15T14:00:00-03:00",
            new_end_at="2026-05-15T15:30:00-03:00",
        )
        assert isinstance(result, RescheduleResult)
        assert result.rescheduled is True
        assert result.appointment_id == appt_id

        updated = svc._scoped.table("appointments").updated_payloads
        assert len(updated) == 1
        payload = updated[0]
        assert payload["start_at"] == "2026-05-15T14:00:00-03:00"
        assert payload["end_at"] == "2026-05-15T15:30:00-03:00"
        # Previous-slot audit columns capture the old times.
        assert payload["previous_start_at"] == old_start.isoformat()
        assert payload["previous_end_at"] == old_end.isoformat()
        assert payload["rescheduled_at"]  # truthy ISO string

    def test_rejects_new_slot_conflict(self):
        """A different appointment overlaps the new slot → rescheduled=False."""
        from app.services.scheduling import SchedulingService, build_rules

        db = MockSupabaseClient(data=[])
        svc = SchedulingService(
            admin_client=db,
            org_id=ORG_ID,
            rules=build_rules(_settings_stub()),
        )
        appt_id = "aaaaaaa1-0000-0000-0000-000000000001"
        old_start = datetime(2026, 5, 15, 10, 0, tzinfo=TZ_BR)
        old_end = datetime(2026, 5, 15, 11, 30, tzinfo=TZ_BR)
        # Another booking blocks the new slot.
        blocker_start = datetime(2026, 5, 15, 14, 0, tzinfo=TZ_BR)
        blocker_end = datetime(2026, 5, 15, 15, 30, tzinfo=TZ_BR)
        svc._scoped.set_sequential_responses(
            "appointments",
            [
                MockSupabaseResponse(
                    data=[_scheduled_appt_row(
                        appt_id=appt_id, start=old_start, end=old_end,
                    )]
                ),
                MockSupabaseResponse(data=[
                    _appt_row(start=old_start, end=old_end, appt_id=appt_id),
                    _appt_row(
                        start=blocker_start, end=blocker_end,
                        appt_id="aaaaaaa2-0000-0000-0000-000000000002",
                    ),
                ]),
            ],
        )
        result = svc.reschedule_appointment(
            appointment_id=appt_id,
            new_start_at="2026-05-15T14:00:00-03:00",
            new_end_at="2026-05-15T15:30:00-03:00",
        )
        assert result.rescheduled is False
        assert "conflicts" in (result.reason or "")
        # No DB update fired.
        updated = svc._scoped.table("appointments").updated_payloads
        assert updated == []

    def test_returns_not_found_when_row_missing(self):
        from app.services.scheduling import SchedulingService, build_rules

        db = MockSupabaseClient(data=[])
        svc = SchedulingService(
            admin_client=db,
            org_id=ORG_ID,
            rules=build_rules(_settings_stub()),
        )
        svc._scoped.set_sequential_responses(
            "appointments",
            [MockSupabaseResponse(data=[])],
        )
        result = svc.reschedule_appointment(
            appointment_id="missing-uuid",
            new_start_at="2026-05-15T14:00:00-03:00",
            new_end_at="2026-05-15T15:30:00-03:00",
        )
        assert result.rescheduled is False
        assert "appointment not found" in (result.reason or "")

    def test_rejects_end_before_start(self):
        from app.services.scheduling import SchedulingService, build_rules

        db = MockSupabaseClient(data=[])
        svc = SchedulingService(
            admin_client=db,
            org_id=ORG_ID,
            rules=build_rules(_settings_stub()),
        )
        result = svc.reschedule_appointment(
            appointment_id="any-uuid",
            new_start_at="2026-05-15T15:30:00-03:00",
            new_end_at="2026-05-15T14:00:00-03:00",
        )
        assert result.rescheduled is False
        assert "strictly after" in (result.reason or "")

    def test_calls_calendar_updater_when_wired(self):
        """Successful reschedule + wired updater → updater invoked with event_id + new slot."""
        from app.services.scheduling import SchedulingService, build_rules

        calls: list[dict] = []

        def _updater(**kwargs) -> Any:  # noqa: ANN401 — flexible kwargs accepted.
            calls.append(kwargs)
            return {"event_id": kwargs.get("event_id"), "ok": True}

        db = MockSupabaseClient(data=[])
        svc = SchedulingService(
            admin_client=db,
            org_id=ORG_ID,
            rules=build_rules(_settings_stub()),
            calendar_event_updater=_updater,
        )
        appt_id = "aaaaaaa1-0000-0000-0000-000000000001"
        old_start = datetime(2026, 5, 15, 10, 0, tzinfo=TZ_BR)
        old_end = datetime(2026, 5, 15, 11, 30, tzinfo=TZ_BR)
        svc._scoped.set_sequential_responses(
            "appointments",
            [
                MockSupabaseResponse(
                    data=[_scheduled_appt_row(
                        appt_id=appt_id,
                        start=old_start, end=old_end,
                        google_event_id="evt-rsv-001",
                    )]
                ),
                MockSupabaseResponse(data=[_appt_row(
                    start=old_start, end=old_end, appt_id=appt_id,
                )]),
                MockSupabaseResponse(data=[]),  # update
            ],
        )
        # The reschedule helper looks up condo + property names for the summary refresh.
        svc._scoped.set_sequential_responses(
            "condominiums",
            [MockSupabaseResponse(data=[_condo_row()])],
        )
        svc._scoped.set_sequential_responses(
            "properties",
            [MockSupabaseResponse(data=[_property_row()])],
        )

        result = svc.reschedule_appointment(
            appointment_id=appt_id,
            new_start_at="2026-05-15T14:00:00-03:00",
            new_end_at="2026-05-15T15:30:00-03:00",
        )
        assert result.rescheduled is True
        assert result.calendar_updated is True
        assert len(calls) == 1
        assert calls[0]["event_id"] == "evt-rsv-001"

    def test_tolerates_calendar_update_failure(self):
        """Calendar updater raises → DB-side reschedule still lands; ``calendar_updated=False``."""
        from app.services.scheduling import SchedulingService, build_rules

        def _failing_updater(**kwargs) -> Any:  # noqa: ANN401 — flexible kwargs accepted.
            raise RuntimeError("calendar quota exhausted")

        db = MockSupabaseClient(data=[])
        svc = SchedulingService(
            admin_client=db,
            org_id=ORG_ID,
            rules=build_rules(_settings_stub()),
            calendar_event_updater=_failing_updater,
        )
        appt_id = "aaaaaaa1-0000-0000-0000-000000000001"
        old_start = datetime(2026, 5, 15, 10, 0, tzinfo=TZ_BR)
        old_end = datetime(2026, 5, 15, 11, 30, tzinfo=TZ_BR)
        svc._scoped.set_sequential_responses(
            "appointments",
            [
                MockSupabaseResponse(
                    data=[_scheduled_appt_row(
                        appt_id=appt_id,
                        start=old_start, end=old_end,
                        google_event_id="evt-fail-001",
                    )]
                ),
                MockSupabaseResponse(data=[_appt_row(
                    start=old_start, end=old_end, appt_id=appt_id,
                )]),
                MockSupabaseResponse(data=[]),
            ],
        )
        svc._scoped.set_sequential_responses(
            "condominiums",
            [MockSupabaseResponse(data=[_condo_row()])],
        )
        svc._scoped.set_sequential_responses(
            "properties",
            [MockSupabaseResponse(data=[_property_row()])],
        )

        result = svc.reschedule_appointment(
            appointment_id=appt_id,
            new_start_at="2026-05-15T14:00:00-03:00",
            new_end_at="2026-05-15T15:30:00-03:00",
        )
        assert result.rescheduled is True
        assert result.calendar_updated is False
        # DB update still landed.
        updated = svc._scoped.table("appointments").updated_payloads
        assert len(updated) == 1


# ---------------------------------------------------------------------------
# Phase 9 — calendar wrappers (cancel + update)
# ---------------------------------------------------------------------------


class TestCalendarCancelAndUpdateWrappers:
    """`app.services.calendar.cancel_calendar_event` + `update_calendar_event`
    route through the configured adapter's `delete_event` / `update_event`."""

    def _wire_fake_module(self):
        from noctusai_lib.integrations.google_calendar import FakeCalendarAdapter

        from app.services import calendar as calendar_module

        calendar_module._reset_for_tests()
        adapter = FakeCalendarAdapter(supports_attendees=True)
        calendar_module.configure_calendar_module(
            admin_client=None,
            org_id=ORG_ID,
            default_calendar_id="primary",
            adapter=adapter,
        )
        return adapter, calendar_module

    def test_cancel_calendar_event_removes_from_fake(self):
        from app.services.calendar import (
            cancel_calendar_event,
            create_calendar_event,
        )

        adapter, calendar_module = self._wire_fake_module()
        start = datetime(2026, 5, 15, 10, 0, tzinfo=TZ_BR)
        end = datetime(2026, 5, 15, 11, 30, tzinfo=TZ_BR)
        created = create_calendar_event(
            summary="Visita técnica",
            start_at=start,
            end_at=end,
            timezone="America/Sao_Paulo",
            appointment_request_id="req-c-1",
        )
        # Event is on the fake before cancellation.
        assert adapter.get_event("primary", created.event_id) is not None

        cancel_calendar_event(event_id=created.event_id)

        # After deletion, the fake no longer has the event.
        assert adapter.get_event("primary", created.event_id) is None
        calendar_module._reset_for_tests()

    def test_update_calendar_event_mutates_start_and_end(self):
        from app.services.calendar import (
            create_calendar_event,
            update_calendar_event,
        )

        adapter, calendar_module = self._wire_fake_module()
        old_start = datetime(2026, 5, 15, 10, 0, tzinfo=TZ_BR)
        old_end = datetime(2026, 5, 15, 11, 30, tzinfo=TZ_BR)
        created = create_calendar_event(
            summary="Visita técnica — Aurora — AP-2034",
            start_at=old_start,
            end_at=old_end,
            timezone="America/Sao_Paulo",
            appointment_request_id="req-u-1",
        )

        new_start = datetime(2026, 5, 15, 14, 0, tzinfo=TZ_BR)
        new_end = datetime(2026, 5, 15, 15, 30, tzinfo=TZ_BR)
        updated = update_calendar_event(
            event_id=created.event_id,
            summary="Visita técnica — Aurora — AP-2034",
            start_at=new_start,
            end_at=new_end,
            timezone="America/Sao_Paulo",
            appointment_request_id="req-u-1",
        )
        # Event id is preserved across the update.
        assert updated.event_id == created.event_id

        # The fake's stored body reflects the new times.
        latest = adapter.get_event("primary", created.event_id)
        assert latest is not None
        assert latest.raw["start"]["dateTime"].startswith("2026-05-15T14:00:00")
        assert latest.raw["end"]["dateTime"].startswith("2026-05-15T15:30:00")
        calendar_module._reset_for_tests()
