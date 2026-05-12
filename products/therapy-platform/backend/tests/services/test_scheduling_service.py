"""Service-layer tests for `app/services/scheduling/service.py`.

Covers materialize_availability_lookup, list_blocked_intervals,
_resolve_clinic_buffer (via generate_candidate_slots), book_appointment,
cancel_appointment, resolve_calendar_for_therapist. Engine internals are
covered upstream in `seed/lib/backend/tests/domain/scheduling/`.

DB shape: `MockSupabaseClient(validate_schema=False, schema="therapy")`.
GCal adapter: explicit `FakeCalendarAdapter()` injection (bypassing the
resolver path which is exercised in router tests).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from noctusai_lib.integrations.google_calendar import EventInput, FakeCalendarAdapter
from noctusai_lib.testing import MockSupabaseClient

from app.services.scheduling import (
    book_appointment,
    cancel_appointment,
    generate_candidate_slots,
    list_blocked_intervals,
    materialize_availability_lookup,
    resolve_calendar_for_therapist,
)
from app.services.scheduling.service import _THERAPY_TZ


THERAPIST_ID = "therapist-A"
CLINIC_ID = "clinic-1"
PATIENT_ID = "patient-X"


def _mock_db() -> MockSupabaseClient:
    return MockSupabaseClient(validate_schema=False, schema="therapy")


# ---------------------------------------------------------------------------
# materialize_availability_lookup
# ---------------------------------------------------------------------------


class TestMaterializeAvailabilityLookup:
    def test_recurring_window_matches_correct_weekday(self):
        # 2026-06-01 is a Monday → Postgres-style dow=1.
        db = _mock_db()
        db.set_table_data(
            "availability_slots",
            [
                {
                    "therapist_id": THERAPIST_ID,
                    "day_of_week": 1,
                    "start_time": "09:00",
                    "end_time": "12:00",
                    "is_recurring": True,
                    "specific_date": None,
                    "is_blocked": False,
                }
            ],
        )
        lookup = materialize_availability_lookup(
            therapist_id=THERAPIST_ID, db=db, rules_timezone=_THERAPY_TZ
        )
        windows = lookup(date(2026, 6, 1))
        assert len(windows) == 1
        assert not windows[0].is_blocked

    def test_recurring_window_skipped_for_other_weekdays(self):
        db = _mock_db()
        db.set_table_data(
            "availability_slots",
            [
                {
                    "day_of_week": 1,
                    "start_time": "09:00",
                    "end_time": "12:00",
                    "is_recurring": True,
                    "specific_date": None,
                    "is_blocked": False,
                }
            ],
        )
        lookup = materialize_availability_lookup(
            therapist_id=THERAPIST_ID, db=db, rules_timezone=_THERAPY_TZ
        )
        # 2026-06-02 = Tuesday.
        assert lookup(date(2026, 6, 2)) == []

    def test_specific_date_window_matches_only_that_date(self):
        db = _mock_db()
        db.set_table_data(
            "availability_slots",
            [
                {
                    "therapist_id": THERAPIST_ID,
                    "day_of_week": 0,
                    "start_time": "14:00",
                    "end_time": "16:00",
                    "is_recurring": False,
                    "specific_date": "2026-06-15",
                    "is_blocked": False,
                }
            ],
        )
        lookup = materialize_availability_lookup(
            therapist_id=THERAPIST_ID, db=db, rules_timezone=_THERAPY_TZ
        )
        assert len(lookup(date(2026, 6, 15))) == 1
        assert lookup(date(2026, 6, 14)) == []

    def test_blocked_flag_propagates(self):
        db = _mock_db()
        db.set_table_data(
            "availability_slots",
            [
                {
                    "therapist_id": THERAPIST_ID,
                    "day_of_week": 0,
                    "start_time": "14:00",
                    "end_time": "15:00",
                    "is_recurring": False,
                    "specific_date": "2026-06-15",
                    "is_blocked": True,
                }
            ],
        )
        lookup = materialize_availability_lookup(
            therapist_id=THERAPIST_ID, db=db, rules_timezone=_THERAPY_TZ
        )
        windows = lookup(date(2026, 6, 15))
        assert windows[0].is_blocked is True


# ---------------------------------------------------------------------------
# list_blocked_intervals
# ---------------------------------------------------------------------------


class TestListBlockedIntervals:
    def test_filters_out_cancelled_statuses(self):
        db = _mock_db()
        # `list_blocked_intervals` filters by `.eq("therapist_id", ...)
        # .gte("scheduled_end", window_start).lte("scheduled_start", window_end)`.
        # Seed rows carry `therapist_id` so MOCK-SELECT-PREDICATE-FIX keeps them.
        db.set_table_data(
            "appointments",
            [
                {
                    "therapist_id": THERAPIST_ID,
                    "scheduled_start": "2026-06-01T10:00:00+00:00",
                    "scheduled_end": "2026-06-01T11:00:00+00:00",
                    "status": "waiting",
                },
                {
                    "therapist_id": THERAPIST_ID,
                    "scheduled_start": "2026-06-01T12:00:00+00:00",
                    "scheduled_end": "2026-06-01T13:00:00+00:00",
                    "status": "cancelled",
                },
                {
                    "therapist_id": THERAPIST_ID,
                    "scheduled_start": "2026-06-01T14:00:00+00:00",
                    "scheduled_end": "2026-06-01T15:00:00+00:00",
                    "status": "no_show",
                },
            ],
        )
        intervals = list_blocked_intervals(
            therapist_id=THERAPIST_ID,
            location_id=CLINIC_ID,
            window_start=datetime(2026, 6, 1, tzinfo=timezone.utc),
            window_end=datetime(2026, 6, 2, tzinfo=timezone.utc),
            db=db,
            calendar_adapter=None,
            calendar_id=None,
        )
        assert len(intervals) == 1

    def test_includes_gcal_events_when_adapter_supplied(self):
        db = _mock_db()
        db.set_table_data("appointments", [])

        adapter = FakeCalendarAdapter()
        adapter.create_event(
            "primary",
            EventInput(
                summary="Dentist",
                start_at=datetime(2026, 6, 1, 16, tzinfo=timezone.utc),
                end_at=datetime(2026, 6, 1, 17, tzinfo=timezone.utc),
                timezone="UTC",
            ),
        )
        intervals = list_blocked_intervals(
            therapist_id=THERAPIST_ID,
            location_id=CLINIC_ID,
            window_start=datetime(2026, 6, 1, tzinfo=timezone.utc),
            window_end=datetime(2026, 6, 2, tzinfo=timezone.utc),
            db=db,
            calendar_adapter=adapter,
            calendar_id="primary",
        )
        assert len(intervals) == 1
        assert intervals[0].assignee_id == THERAPIST_ID


# ---------------------------------------------------------------------------
# generate_candidate_slots — integration through the engine
# ---------------------------------------------------------------------------


class TestGenerateCandidateSlots:
    def test_buffer_falls_back_to_default_when_clinic_settings_missing(self):
        db = _mock_db()
        db.set_table_data("clinic_settings", [])
        db.set_table_data(
            "availability_slots",
            [
                {
                    "therapist_id": THERAPIST_ID,
                    "day_of_week": 1,
                    "start_time": "09:00",
                    "end_time": "10:00",
                    "is_recurring": True,
                    "specific_date": None,
                    "is_blocked": False,
                }
            ],
        )
        db.set_table_data("appointments", [])
        slots = generate_candidate_slots(
            therapist_id=THERAPIST_ID,
            clinic_id=CLINIC_ID,
            window_start=datetime(2026, 6, 1, tzinfo=timezone.utc),
            window_end=datetime(2026, 6, 1, tzinfo=timezone.utc),
            duration_minutes=50,
            db=db,
        )
        assert len(slots) >= 1

    def test_buffer_reads_clinic_settings(self):
        db = _mock_db()
        db.set_table_data(
            "clinic_settings",
            [{"transition_buffer_minutes": 30}],
        )
        db.set_table_data(
            "availability_slots",
            [
                {
                    "day_of_week": 1,
                    "start_time": "09:00",
                    "end_time": "10:00",
                    "is_recurring": True,
                    "specific_date": None,
                    "is_blocked": False,
                }
            ],
        )
        db.set_table_data("appointments", [])
        # Just exercise the path; assertion is "doesn't error and returns a list".
        slots = generate_candidate_slots(
            therapist_id=THERAPIST_ID,
            clinic_id=CLINIC_ID,
            window_start=datetime(2026, 6, 1, tzinfo=timezone.utc),
            window_end=datetime(2026, 6, 1, tzinfo=timezone.utc),
            db=db,
        )
        assert isinstance(slots, list)


# ---------------------------------------------------------------------------
# book_appointment + cancel_appointment
# ---------------------------------------------------------------------------


class TestBookAppointment:
    def test_inserts_with_status_waiting(self):
        db = _mock_db()
        adapter = FakeCalendarAdapter()
        slot_start = datetime(2026, 6, 1, 10, tzinfo=timezone.utc)
        slot_end = slot_start + timedelta(minutes=50)

        result = book_appointment(
            therapist_id=THERAPIST_ID,
            patient_id=PATIENT_ID,
            clinic_id=CLINIC_ID,
            slot_start=slot_start,
            slot_end=slot_end,
            db=db,
            calendar_adapter=adapter,
            calendar_id="primary",
        )

        payloads = db.table("appointments").inserted_payloads
        assert len(payloads) == 1
        assert payloads[0]["status"] == "waiting"
        assert payloads[0]["therapist_id"] == THERAPIST_ID
        assert payloads[0]["patient_id"] == PATIENT_ID
        assert payloads[0]["google_event_id"] is not None
        # Result echoes the payload + auto-id.
        assert result.get("id", "").startswith("mock-appointments-")

    def test_appointment_persists_even_when_gcal_write_fails(self):
        db = _mock_db()
        adapter = FakeCalendarAdapter()
        # Force GCal create_event to fail.
        original = adapter.create_event
        def _boom(*a, **k):
            raise RuntimeError("simulated GCal outage")
        adapter.create_event = _boom  # type: ignore[method-assign]
        try:
            slot_start = datetime(2026, 6, 1, 10, tzinfo=timezone.utc)
            book_appointment(
                therapist_id=THERAPIST_ID,
                patient_id=PATIENT_ID,
                clinic_id=CLINIC_ID,
                slot_start=slot_start,
                slot_end=slot_start + timedelta(minutes=50),
                db=db,
                calendar_adapter=adapter,
                calendar_id="primary",
            )
        finally:
            adapter.create_event = original  # type: ignore[method-assign]
        payloads = db.table("appointments").inserted_payloads
        assert len(payloads) == 1
        assert payloads[0]["google_event_id"] is None


class TestCancelAppointment:
    def test_marks_cancelled(self):
        db = _mock_db()
        db.set_table_data(
            "appointments",
            [{"google_event_id": "ev-123"}],
        )
        adapter = FakeCalendarAdapter()
        # Pre-populate event so delete has something to delete.
        adapter.create_event(
            "primary",
            EventInput(
                summary="x",
                start_at=datetime(2026, 6, 1, 10, tzinfo=timezone.utc),
                end_at=datetime(2026, 6, 1, 11, tzinfo=timezone.utc),
                timezone="UTC",
            ),
        )
        result = cancel_appointment(
            appointment_id="appt-1",
            db=db,
            calendar_adapter=adapter,
            calendar_id="primary",
        )
        assert result.get("status") == "cancelled"


# ---------------------------------------------------------------------------
# resolve_calendar_for_therapist — Fake fallback path
# ---------------------------------------------------------------------------


class TestResolveCalendarForTherapist:
    def test_falls_back_to_fake_when_no_credentials(self):
        db = _mock_db()
        db.set_table_data("therapist_profiles", [{"gcal_calendar_id": None}])
        adapter, calendar_id = resolve_calendar_for_therapist(
            db=db,
            therapist_id=THERAPIST_ID,
            client_id=None,
            client_secret=None,
        )
        assert isinstance(adapter, FakeCalendarAdapter)
        assert calendar_id == "primary"
