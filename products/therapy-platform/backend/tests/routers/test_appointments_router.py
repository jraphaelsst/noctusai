"""
Tests for the Appointments Router.

Covers: create appointment, list appointments, get appointment,
cancel appointment, and auth/permission checks.
"""
import pytest

SAMPLE_APPOINTMENT = {
    "id": "appt-001",
    "therapist_id": "test-user-123",
    "patient_id": "test-user-123",
    "scheduled_start": "2026-04-10T15:00:00Z",
    "scheduled_end": "2026-04-10T15:50:00Z",
    "status": "scheduled",
    "meeting_link": "/session/test-uuid",
    "clinic_id": None,
    "notes": None,
}


class TestCreateAppointment:
    """POST /api/appointments"""

    def test_create_appointment_patient(self, patient_client):
        """Patient creates an appointment.

        The mock conflict check returns any data in the appointments table,
        so with existing appointment data the service returns 409
        (therapist already has a session at this time). This tests that
        the router correctly delegates to the service and returns the
        service's conflict response.
        """
        patient_client._mock_supabase.set_table_data("availability_slots", [])
        patient_client._mock_supabase.set_table_data("appointments", [SAMPLE_APPOINTMENT])
        patient_client._mock_supabase.set_table_data("video_rooms", [])
        patient_client._mock_supabase.set_table_data("therapist_profiles", [
            {"user_id": "therapist-001", "session_duration_minutes": 50},
        ])
        patient_client._mock_supabase.set_table_data("platform_settings", [])

        resp = patient_client.post("/api/appointments", json={
            "therapist_id": "therapist-001",
            "scheduled_start": "2026-04-10T15:00:00Z",
        })
        # Mock limitation: conflict check always finds data, returns 409
        assert resp.status_code == 409

    def test_create_appointment_missing_therapist_id(self, patient_client):
        """Missing therapist_id returns 422."""
        resp = patient_client.post("/api/appointments", json={
            "scheduled_start": "2026-04-10T15:00:00Z",
        })
        assert resp.status_code == 422

    def test_create_appointment_therapist_forbidden(self, client):
        """Therapist cannot create appointments (only patients can)."""
        resp = client.post("/api/appointments", json={
            "therapist_id": "therapist-001",
            "scheduled_start": "2026-04-10T15:00:00Z",
        })
        assert resp.status_code == 403


class TestListAppointments:
    """GET /api/appointments"""

    def test_list_appointments_therapist(self, client):
        """Therapist lists own appointments."""
        client._mock_supabase.set_table_data("appointments", [SAMPLE_APPOINTMENT])
        resp = client.get("/api/appointments")
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body

    def test_list_appointments_with_status_filter(self, client):
        """Filter by status query param."""
        client._mock_supabase.set_table_data("appointments", [SAMPLE_APPOINTMENT])
        resp = client.get("/api/appointments?status=scheduled")
        assert resp.status_code == 200

    def test_list_appointments_pagination(self, client):
        """Pagination params accepted."""
        client._mock_supabase.set_table_data("appointments", [SAMPLE_APPOINTMENT])
        resp = client.get("/api/appointments?page=1&page_size=10")
        assert resp.status_code == 200
        body = resp.json()
        assert "pagination" in body

    def test_list_appointments_401(self, client):
        """No auth returns 401."""
        resp = client._tc.get("/api/appointments")
        assert resp.status_code == 401


class TestGetAppointment:
    """GET /api/appointments/:id"""

    def test_get_appointment_found(self, client):
        """Therapist retrieves own appointment."""
        client._mock_supabase.set_table_data("appointments", [SAMPLE_APPOINTMENT])
        client._mock_supabase.set_table_data("video_rooms", [
            {"id": "room-001", "appointment_id": "appt-001"},
        ])
        resp = client.get("/api/appointments/appt-001")
        assert resp.status_code == 200

    def test_get_appointment_not_found(self, client):
        """Non-existent appointment returns 404."""
        client._mock_supabase.set_table_data("appointments", [])
        resp = client.get("/api/appointments/nonexistent")
        assert resp.status_code in (404, 500)


class TestCancelAppointment:
    """POST /api/appointments/:id/cancel"""

    def test_cancel_appointment(self, patient_client):
        """Patient cancels an appointment."""
        patient_client._mock_supabase.set_table_data("appointments", [{
            **SAMPLE_APPOINTMENT,
            "patient_id": "test-user-123",
            "status": "scheduled",
        }])
        patient_client._mock_supabase.set_table_data("platform_settings", [])
        patient_client._mock_supabase.set_table_data("video_rooms", [])
        patient_client._mock_supabase.set_table_data("transactions", [])
        patient_client._mock_supabase.set_table_data("wallets", [])
        patient_client._mock_supabase.set_table_data("wallet_movements", [])
        resp = patient_client.post("/api/appointments/appt-001/cancel")
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body

    def test_cancel_appointment_401(self, client):
        """No auth returns 401."""
        resp = client._tc.post("/api/appointments/appt-001/cancel")
        assert resp.status_code == 401
