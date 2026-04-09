"""
Tests for the No-Show Service.

Covers: no-show detection and charging, recurring schedule absence
tracking, error handling for individual appointments, and edge cases
(no waiting appointments, already-past cutoff, with/without recurring).
"""
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

from tests.conftest import MockSupabaseClient
from app.services import no_show_service


# Use dynamic dates relative to now so tests never go stale.
_now = datetime.now(timezone.utc)
_past_cutoff = (_now - timedelta(minutes=45)).isoformat()  # well past the 30-min grace
_recent = (_now - timedelta(minutes=10)).isoformat()  # within grace period

SAMPLE_APPOINTMENT_NO_SHOW = {
    "id": "appt-no-show-001",
    "therapist_id": "therapist-001",
    "patient_id": "patient-001",
    "scheduled_start": (_now - timedelta(hours=1, minutes=45)).isoformat(),
    "scheduled_end": _past_cutoff,
    "status": "waiting",
    "clinic_id": None,
    "recurring_schedule_id": None,
    "session_price": "150.00",
}

SAMPLE_APPOINTMENT_WITH_RECURRING = {
    **SAMPLE_APPOINTMENT_NO_SHOW,
    "id": "appt-no-show-002",
    "recurring_schedule_id": "recurring-001",
}

SAMPLE_RECURRING_SCHEDULE = {
    "id": "recurring-001",
    "total_absences": 2,
}


class TestDetectAndChargeNoShows:
    @pytest.mark.asyncio
    async def test_no_waiting_appointments(self):
        """No appointments in 'waiting' status returns zero processed."""
        db = MockSupabaseClient()
        db.set_table_data("appointments", [])

        result = await no_show_service.detect_and_charge_no_shows(db)
        assert result["processed"] == 0
        assert result["charged"] == 0

    @pytest.mark.asyncio
    async def test_single_no_show_processed(self):
        """Detects a single no-show and processes it."""
        db = MockSupabaseClient()
        db.set_table_data("appointments", [SAMPLE_APPOINTMENT_NO_SHOW])

        with patch.object(
            no_show_service.commission_engine,
            "process_no_show_charge",
            new_callable=AsyncMock,
            return_value={"id": "tx-001", "amount": "75.00"},
        ):
            result = await no_show_service.detect_and_charge_no_shows(db)

        assert result["processed"] == 1
        assert result["charged"] == 1

    @pytest.mark.asyncio
    async def test_no_show_charge_returns_none(self):
        """Processed but not charged when commission engine returns None."""
        db = MockSupabaseClient()
        db.set_table_data("appointments", [SAMPLE_APPOINTMENT_NO_SHOW])

        with patch.object(
            no_show_service.commission_engine,
            "process_no_show_charge",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await no_show_service.detect_and_charge_no_shows(db)

        assert result["processed"] == 1
        assert result["charged"] == 0

    @pytest.mark.asyncio
    async def test_updates_recurring_schedule_absences(self):
        """Increments total_absences on recurring schedule when applicable."""
        db = MockSupabaseClient()
        db.set_table_data("appointments", [SAMPLE_APPOINTMENT_WITH_RECURRING])
        db.set_table_data("recurring_schedules", [SAMPLE_RECURRING_SCHEDULE])

        with patch.object(
            no_show_service.commission_engine,
            "process_no_show_charge",
            new_callable=AsyncMock,
            return_value={"id": "tx-002"},
        ):
            result = await no_show_service.detect_and_charge_no_shows(db)

        assert result["processed"] == 1

    @pytest.mark.asyncio
    async def test_skips_recurring_update_when_no_schedule(self):
        """Does not crash when recurring_schedule_id is set but schedule not found."""
        db = MockSupabaseClient()
        appt_with_missing_schedule = {
            **SAMPLE_APPOINTMENT_WITH_RECURRING,
            "recurring_schedule_id": "nonexistent-schedule",
        }
        db.set_table_data("appointments", [appt_with_missing_schedule])
        db.set_table_data("recurring_schedules", [])

        with patch.object(
            no_show_service.commission_engine,
            "process_no_show_charge",
            new_callable=AsyncMock,
            return_value={"id": "tx-003"},
        ):
            result = await no_show_service.detect_and_charge_no_shows(db)

        assert result["processed"] == 1

    @pytest.mark.asyncio
    async def test_multiple_no_shows(self):
        """Processes multiple no-show appointments."""
        db = MockSupabaseClient()
        appt2 = {
            **SAMPLE_APPOINTMENT_NO_SHOW,
            "id": "appt-no-show-003",
            "patient_id": "patient-002",
        }
        db.set_table_data("appointments", [SAMPLE_APPOINTMENT_NO_SHOW, appt2])

        with patch.object(
            no_show_service.commission_engine,
            "process_no_show_charge",
            new_callable=AsyncMock,
            return_value={"id": "tx-004"},
        ):
            result = await no_show_service.detect_and_charge_no_shows(db)

        assert result["processed"] == 2
        assert result["charged"] == 2

    @pytest.mark.asyncio
    async def test_error_in_one_appointment_continues_others(self):
        """An error processing one appointment does not stop others."""
        db = MockSupabaseClient()
        appt2 = {
            **SAMPLE_APPOINTMENT_NO_SHOW,
            "id": "appt-no-show-fail",
            "patient_id": "patient-003",
        }
        db.set_table_data("appointments", [SAMPLE_APPOINTMENT_NO_SHOW, appt2])

        call_count = 0

        async def mock_charge(appt_id, db_arg):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Payment gateway error")
            return {"id": "tx-005"}

        with patch.object(
            no_show_service.commission_engine,
            "process_no_show_charge",
            side_effect=mock_charge,
        ):
            result = await no_show_service.detect_and_charge_no_shows(db)

        # First one failed (error caught), second processed successfully
        assert result["processed"] == 1
        assert result["charged"] == 1


class TestGetPlatformSetting:
    def test_returns_setting_value(self):
        db = MockSupabaseClient()
        db.set_table_data("platform_settings", [{"value": "50"}])
        result = no_show_service._get_platform_setting(db, "no_show_charge_pct", "30")
        assert result == "50"

    def test_returns_default_when_not_found(self):
        db = MockSupabaseClient()
        db.set_table_data("platform_settings", [])
        result = no_show_service._get_platform_setting(db, "no_show_charge_pct", "30")
        assert result == "30"
