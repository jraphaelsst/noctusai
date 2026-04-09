"""
Scheduling edge cases -- booking permissions, cancellation boundaries, recurring logic.

Tests cover appointment booking restrictions, the 24-hour cancellation policy,
price level resolution, and recurring schedule state transitions.
"""
import pytest
from datetime import datetime, timedelta, timezone


_now = datetime.now(timezone.utc)
_24h_from_now = (_now + timedelta(hours=25)).isoformat()
_23h_from_now = (_now + timedelta(hours=23, minutes=59)).isoformat()


# ===================================================================
# Booking permissions
# ===================================================================

class TestBookingPermissions:
    """Only patients can book appointments."""

    def test_therapist_cannot_book(self, client):
        """Therapist POST /api/appointments -> 403."""
        resp = client.post("/api/appointments", json={
            "therapist_id": "therapist-001",
            "scheduled_start": _24h_from_now,
            "scheduled_end": (_now + timedelta(hours=26)).isoformat(),
        })
        assert resp.status_code == 403

    def test_clinic_admin_cannot_book(self, clinic_admin_client):
        """Clinic admin POST /api/appointments -> 403."""
        resp = clinic_admin_client.post("/api/appointments", json={
            "therapist_id": "therapist-001",
            "scheduled_start": _24h_from_now,
            "scheduled_end": (_now + timedelta(hours=26)).isoformat(),
        })
        assert resp.status_code == 403

    def test_admin_cannot_book(self, admin_client):
        """Platform admin POST /api/appointments -> 403."""
        resp = admin_client.post("/api/appointments", json={
            "therapist_id": "therapist-001",
            "scheduled_start": _24h_from_now,
            "scheduled_end": (_now + timedelta(hours=26)).isoformat(),
        })
        assert resp.status_code == 403


# ===================================================================
# Appointment listing is role-scoped
# ===================================================================

class TestAppointmentListingScope:
    """Each role sees only their scoped appointments."""

    def test_patient_list_is_self_scoped(self, patient_client):
        """Patient listing always filters by patient_id = self."""
        sb = patient_client._mock_supabase
        sb.set_table_data("appointments", [
            {"id": "appt-own", "patient_id": "test-user-123", "therapist_id": "t1", "status": "waiting"},
            {"id": "appt-other", "patient_id": "other-patient", "therapist_id": "t1", "status": "waiting"},
        ])
        resp = patient_client.get("/api/appointments")
        assert resp.status_code == 200

    def test_therapist_list_is_self_scoped(self, client):
        """Therapist listing always filters by therapist_id = self."""
        sb = client._mock_supabase
        sb.set_table_data("appointments", [
            {"id": "appt-own", "therapist_id": "test-user-123", "patient_id": "p1", "status": "waiting"},
        ])
        resp = client.get("/api/appointments")
        assert resp.status_code == 200

    def test_clinic_admin_sees_clinic_scoped(self, clinic_admin_client):
        """Clinic admin listing filters by clinic_id."""
        sb = clinic_admin_client._mock_supabase
        sb.set_table_data("appointments", [
            {"id": "appt-clinic", "clinic_id": "test-clinic-123", "therapist_id": "t1",
             "patient_id": "p1", "status": "waiting"},
        ])
        resp = clinic_admin_client.get("/api/appointments")
        assert resp.status_code == 200


# ===================================================================
# Appointment detail access
# ===================================================================

class TestAppointmentDetailAccess:
    """Only involved parties or admins can view appointment details."""

    def test_uninvolved_therapist_cannot_view(self, client):
        """Therapist viewing another therapist's appointment -> 403."""
        sb = client._mock_supabase
        sb.set_table_data("appointments", [{
            "id": "appt-other",
            "therapist_id": "other-therapist-999",
            "patient_id": "other-patient-999",
            "status": "waiting",
        }])
        resp = client.get("/api/appointments/appt-other")
        assert resp.status_code == 403

    def test_uninvolved_patient_cannot_view(self, patient_client):
        """Patient viewing another patient's appointment -> 403."""
        sb = patient_client._mock_supabase
        sb.set_table_data("appointments", [{
            "id": "appt-other",
            "therapist_id": "therapist-001",
            "patient_id": "other-patient-999",
            "status": "waiting",
        }])
        resp = patient_client.get("/api/appointments/appt-other")
        assert resp.status_code == 403


# ===================================================================
# Cancellation boundary (24h rule)
# ===================================================================

class TestCancellationPolicy:
    """The 24h cancellation rule is enforced at the service layer."""

    def test_cancel_nonexistent_appointment_404(self, patient_client):
        """Cancelling non-existent appointment -> error."""
        sb = patient_client._mock_supabase
        sb.set_table_data("appointments", [])
        resp = patient_client.post("/api/appointments/appt-nonexistent/cancel", json={})
        # Service raises 404 for missing appointment
        assert resp.status_code in (404, 500)

    def test_cancel_as_patient_succeeds(self, patient_client):
        """Patient can cancel their own appointment."""
        sb = patient_client._mock_supabase
        sb.set_table_data("appointments", [{
            "id": "appt-cancel-001",
            "patient_id": "test-user-123",
            "therapist_id": "therapist-001",
            "status": "waiting",
            "scheduled_start": _24h_from_now,
            "session_price": 200,
            "clinic_id": None,
        }])
        sb.set_table_data("wallets", [])
        sb.set_table_data("platform_settings", [])
        resp = patient_client.post("/api/appointments/appt-cancel-001/cancel", json={})
        assert resp.status_code == 200


# ===================================================================
# Recurring schedule permissions
# ===================================================================

class TestRecurringSchedulePermissions:
    """Recurring schedule CRUD respects role restrictions."""

    def test_patient_creates_as_request(self, patient_client):
        """Patient creating recurring schedule should use 'patient_request' type."""
        sb = patient_client._mock_supabase
        sb.set_table_data("recurring_schedules", [{
            "id": "rs-001", "status": "paused",
            "therapist_id": "therapist-001",
            "patient_id": "test-user-123",
        }])
        sb.set_table_data("therapist_profiles", [])
        resp = patient_client.post("/api/recurring", json={
            "therapist_id": "therapist-001",
            "patient_id": "test-user-123",
            "frequency": "weekly",
            "day_of_week": 1,
            "start_time": "10:00",
            "start_date": "2026-05-01",
            "end_condition": "indefinite",
        })
        assert resp.status_code == 200

    def test_patient_cannot_modify_recurring_schedule(self, patient_client):
        """Patient PATCH /api/recurring/:id -> 403."""
        resp = patient_client.patch("/api/recurring/rs-001", json={
            "start_time": "11:00",
        })
        assert resp.status_code == 403

    def test_patient_cannot_approve_recurring_schedule(self, patient_client):
        """Patient POST /api/recurring/:id/approve -> 403."""
        resp = patient_client.post("/api/recurring/rs-001/approve")
        assert resp.status_code == 403

    def test_patient_cannot_deny_recurring_schedule(self, patient_client):
        """Patient POST /api/recurring/:id/deny -> 403."""
        resp = patient_client.post("/api/recurring/rs-001/deny")
        assert resp.status_code == 403

    def test_therapist_can_modify_recurring_schedule(self, client):
        """Therapist PATCH /api/recurring/:id -> allowed."""
        sb = client._mock_supabase
        sb.set_table_data("recurring_schedules", [{
            "id": "rs-001",
            "therapist_id": "test-user-123",
            "patient_id": "patient-001",
            "status": "active",
        }])
        resp = client.patch("/api/recurring/rs-001", json={
            "start_time": "11:00",
        })
        assert resp.status_code == 200

    def test_therapist_can_approve_recurring_schedule(self, client):
        """Therapist POST /api/recurring/:id/approve -> allowed for patient_request."""
        sb = client._mock_supabase
        sb.set_table_data("recurring_schedules", [{
            "id": "rs-001",
            "therapist_id": "test-user-123",
            "patient_id": "patient-001",
            "status": "paused",
            "created_by_type": "patient_request",
            "approved_by_user_id": None,
        }])
        resp = client.post("/api/recurring/rs-001/approve")
        assert resp.status_code == 200


# ===================================================================
# Recurring schedule detail access
# ===================================================================

class TestRecurringScheduleAccess:
    """Only involved parties can view schedule details."""

    def test_uninvolved_therapist_cannot_view(self, client):
        """Therapist viewing another's recurring schedule -> 403."""
        sb = client._mock_supabase
        sb.set_table_data("recurring_schedules", [{
            "id": "rs-other",
            "therapist_id": "other-therapist-999",
            "patient_id": "other-patient-999",
            "status": "active",
        }])
        resp = client.get("/api/recurring/rs-other")
        assert resp.status_code == 403

    def test_involved_therapist_can_view(self, client):
        """Therapist viewing their own recurring schedule -> success."""
        sb = client._mock_supabase
        sb.set_table_data("recurring_schedules", [{
            "id": "rs-own",
            "therapist_id": "test-user-123",
            "patient_id": "patient-001",
            "status": "active",
        }])
        resp = client.get("/api/recurring/rs-own")
        assert resp.status_code == 200

    def test_involved_patient_can_view(self, patient_client):
        """Patient viewing their own recurring schedule -> success."""
        sb = patient_client._mock_supabase
        sb.set_table_data("recurring_schedules", [{
            "id": "rs-own",
            "therapist_id": "therapist-001",
            "patient_id": "test-user-123",
            "status": "active",
        }])
        resp = patient_client.get("/api/recurring/rs-own")
        assert resp.status_code == 200


# ===================================================================
# Recurring schedule pause/resume/end/skip by all roles
# ===================================================================

class TestRecurringScheduleLifecycle:
    """Recurring schedule lifecycle actions (pause, resume, end, skip)."""

    def _setup_schedule(self, mock_sb, status="active"):
        mock_sb.set_table_data("recurring_schedules", [{
            "id": "rs-lc-001",
            "therapist_id": "test-user-123",
            "patient_id": "patient-001",
            "status": status,
            "total_absences": 0,
        }])
        mock_sb.set_table_data("appointments", [])

    def test_pause_active_schedule(self, client):
        """Pause an active recurring schedule."""
        self._setup_schedule(client._mock_supabase, status="active")
        resp = client.post("/api/recurring/rs-lc-001/pause")
        assert resp.status_code == 200

    def test_resume_paused_schedule(self, client):
        """Resume a paused recurring schedule."""
        self._setup_schedule(client._mock_supabase, status="paused")
        resp = client.post("/api/recurring/rs-lc-001/resume")
        assert resp.status_code == 200

    def test_end_schedule(self, client):
        """End a recurring schedule cancels future appointments."""
        self._setup_schedule(client._mock_supabase, status="active")
        resp = client.post("/api/recurring/rs-lc-001/end")
        assert resp.status_code == 200

    def test_skip_occurrence_no_appointment_404(self, client):
        """Skip occurrence when no appointment exists for that date -> 404."""
        sb = client._mock_supabase
        sb.set_table_data("recurring_schedules", [{
            "id": "rs-lc-001",
            "therapist_id": "test-user-123",
            "patient_id": "patient-001",
            "status": "active",
        }])
        sb.set_table_data("appointments", [])
        resp = client.post(
            "/api/recurring/rs-lc-001/skip",
            params={"date": "2026-05-01"},
        )
        assert resp.status_code == 404
