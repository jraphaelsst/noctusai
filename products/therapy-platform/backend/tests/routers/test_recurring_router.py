"""
Tests for the Recurring Schedules Router.

Covers: create, list, get, modify, approve, deny, pause, resume,
end, skip, and auth/permission checks.
"""
import pytest
from datetime import date, timedelta

SAMPLE_SCHEDULE = {
    "id": "sched-001",
    "therapist_id": "test-user-123",
    "patient_id": "patient-001",
    "frequency": "weekly",
    "day_of_week": 2,
    "start_time": "14:00",
    "duration_minutes": 50,
    "start_date": "2026-04-01",
    "end_condition": "indefinite",
    "status": "active",
    "clinic_id": None,
    "created_by_type": "therapist",
    "approved_by_user_id": None,
}

SAMPLE_SCHEDULE_PATIENT_REQ = {
    **SAMPLE_SCHEDULE,
    "status": "pending_approval",
    "created_by_type": "patient_request",
}

CREATE_PAYLOAD = {
    "therapist_id": "test-user-123",
    "patient_id": "patient-001",
    "frequency": "weekly",
    "day_of_week": 2,
    "start_time": "14:00",
    "duration_minutes": 50,
    "start_date": "2026-04-01",
    "end_condition": "indefinite",
}


class TestCreateRecurringSchedule:
    """POST /api/recurring"""

    def test_create_schedule_therapist(self, client):
        """Therapist creates a recurring schedule."""
        client._mock_supabase.set_table_data("recurring_schedules", [SAMPLE_SCHEDULE])
        client._mock_supabase.set_table_data("therapist_profiles", [])
        resp = client.post("/api/recurring", json=CREATE_PAYLOAD)
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body

    def test_create_schedule_patient(self, patient_client):
        """Patient creates a schedule request (requires approval)."""
        patient_client._mock_supabase.set_table_data("recurring_schedules", [
            SAMPLE_SCHEDULE_PATIENT_REQ,
        ])
        patient_client._mock_supabase.set_table_data("therapist_profiles", [])
        resp = patient_client.post("/api/recurring", json=CREATE_PAYLOAD)
        assert resp.status_code == 200

    def test_create_schedule_401(self, client):
        """No auth returns 401."""
        resp = client._tc.post("/api/recurring", json=CREATE_PAYLOAD)
        assert resp.status_code == 401


class TestListRecurringSchedules:
    """GET /api/recurring"""

    def test_list_schedules(self, client):
        """Therapist lists own recurring schedules."""
        client._mock_supabase.set_table_data("recurring_schedules", [SAMPLE_SCHEDULE])
        resp = client.get("/api/recurring")
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body

    def test_list_schedules_empty(self, client):
        """Empty list returns successfully."""
        client._mock_supabase.set_table_data("recurring_schedules", [])
        resp = client.get("/api/recurring")
        assert resp.status_code == 200


class TestGetRecurringSchedule:
    """GET /api/recurring/:id"""

    def test_get_schedule_detail(self, client):
        """Therapist gets schedule detail."""
        client._mock_supabase.set_table_data("recurring_schedules", [SAMPLE_SCHEDULE])
        client._mock_supabase.set_table_data("appointments", [])
        resp = client.get("/api/recurring/sched-001")
        assert resp.status_code == 200

    def test_get_schedule_not_found(self, client):
        """Non-existent schedule returns 404."""
        client._mock_supabase.set_table_data("recurring_schedules", [])
        resp = client.get("/api/recurring/nonexistent")
        assert resp.status_code in (404, 500)


class TestModifyRecurringSchedule:
    """PATCH /api/recurring/:id"""

    def test_modify_schedule(self, client):
        """Therapist modifies a recurring schedule."""
        client._mock_supabase.set_table_data("recurring_schedules", [SAMPLE_SCHEDULE])
        resp = client.patch("/api/recurring/sched-001", json={
            "day_of_week": 3,
            "start_time": "15:00",
        })
        assert resp.status_code == 200

    def test_modify_schedule_patient_forbidden(self, patient_client):
        """Patient cannot modify schedules."""
        resp = patient_client.patch("/api/recurring/sched-001", json={
            "day_of_week": 3,
        })
        assert resp.status_code == 403


class TestApproveRecurringSchedule:
    """POST /api/recurring/:id/approve"""

    def test_approve_schedule(self, client):
        """Therapist approves a patient-requested schedule."""
        client._mock_supabase.set_table_data("recurring_schedules", [
            SAMPLE_SCHEDULE_PATIENT_REQ,
        ])
        resp = client.post("/api/recurring/sched-001/approve")
        assert resp.status_code == 200

    def test_approve_patient_forbidden(self, patient_client):
        """Patient cannot approve schedules."""
        resp = patient_client.post("/api/recurring/sched-001/approve")
        assert resp.status_code == 403


class TestDenyRecurringSchedule:
    """POST /api/recurring/:id/deny"""

    def test_deny_schedule_with_reason(self, client):
        """Therapist denies a schedule with reason."""
        client._mock_supabase.set_table_data("recurring_schedules", [
            SAMPLE_SCHEDULE_PATIENT_REQ,
        ])
        resp = client.post("/api/recurring/sched-001/deny?reason=Horario%20indisponivel")
        assert resp.status_code == 200

    def test_deny_patient_forbidden(self, patient_client):
        """Patient cannot deny schedules."""
        resp = patient_client.post("/api/recurring/sched-001/deny?reason=test")
        assert resp.status_code == 403


class TestPauseRecurringSchedule:
    """POST /api/recurring/:id/pause"""

    def test_pause_schedule(self, client):
        """Pause an active recurring schedule."""
        client._mock_supabase.set_table_data("recurring_schedules", [SAMPLE_SCHEDULE])
        resp = client.post("/api/recurring/sched-001/pause")
        assert resp.status_code == 200


class TestResumeRecurringSchedule:
    """POST /api/recurring/:id/resume"""

    def test_resume_schedule(self, client):
        """Resume a paused recurring schedule."""
        client._mock_supabase.set_table_data("recurring_schedules", [
            {**SAMPLE_SCHEDULE, "status": "paused"},
        ])
        resp = client.post("/api/recurring/sched-001/resume")
        assert resp.status_code == 200


class TestEndRecurringSchedule:
    """POST /api/recurring/:id/end"""

    def test_end_schedule(self, client):
        """End a recurring schedule."""
        client._mock_supabase.set_table_data("recurring_schedules", [SAMPLE_SCHEDULE])
        client._mock_supabase.set_table_data("appointments", [])
        client._mock_supabase.set_table_data("platform_settings", [])
        resp = client.post("/api/recurring/sched-001/end")
        assert resp.status_code == 200


class TestSkipOccurrence:
    """POST /api/recurring/:id/skip"""

    def test_skip_occurrence(self, client):
        """Skip a specific occurrence date by cancelling the appointment."""
        future_date = (date.today() + timedelta(days=7)).isoformat()
        future_start = f"{future_date}T14:00:00+00:00"
        client._mock_supabase.set_table_data("recurring_schedules", [SAMPLE_SCHEDULE])
        client._mock_supabase.set_table_data("appointments", [{
            "id": "appt-skip-001",
            "recurring_schedule_id": "sched-001",
            "scheduled_start": future_start,
            "status": "scheduled",
        }])
        client._mock_supabase.set_table_data("platform_settings", [])
        client._mock_supabase.set_table_data("video_rooms", [])
        resp = client.post(f"/api/recurring/sched-001/skip?date={future_date}")
        assert resp.status_code == 200

    def test_skip_occurrence_401(self, client):
        """No auth returns 401."""
        resp = client._tc.post("/api/recurring/sched-001/skip?date=2026-04-08")
        assert resp.status_code == 401
