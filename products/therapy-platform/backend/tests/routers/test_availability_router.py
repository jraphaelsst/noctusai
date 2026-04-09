"""
Tests for the Availability Router.

Covers: list slots, create slot, update slot, delete slot,
block dates, get bookable slots, and auth/permission checks.
"""
import pytest

SAMPLE_SLOT = {
    "id": "slot-001",
    "therapist_id": "test-user-123",
    "day_of_week": 1,
    "start_time": "09:00",
    "end_time": "10:00",
    "is_recurring": True,
    "is_blocked": False,
    "specific_date": None,
    "clinic_id": None,
}


class TestListAvailability:
    """GET /api/availability"""

    def test_list_slots_therapist(self, client):
        """Therapist lists own slots by default."""
        client._mock_supabase.set_table_data("availability_slots", [SAMPLE_SLOT])
        resp = client.get("/api/availability")
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body

    def test_list_slots_empty(self, client):
        """Therapist with no slots gets empty list."""
        client._mock_supabase.set_table_data("availability_slots", [])
        resp = client.get("/api/availability")
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body

    def test_list_slots_with_therapist_id(self, patient_client):
        """Patient can query a specific therapist's availability."""
        patient_client._mock_supabase.set_table_data("availability_slots", [SAMPLE_SLOT])
        resp = patient_client.get("/api/availability?therapist_id=test-user-123")
        assert resp.status_code == 200

    def test_list_slots_patient_no_therapist_id(self, patient_client):
        """Patient without therapist_id query param gets 400."""
        resp = patient_client.get("/api/availability")
        assert resp.status_code == 400

    def test_list_slots_401(self, client):
        """No auth returns 401."""
        resp = client._tc.get("/api/availability")
        assert resp.status_code == 401


class TestCreateAvailability:
    """POST /api/availability"""

    def test_create_slot(self, client):
        """Therapist creates an availability slot."""
        # Empty table so overlap check passes; insert returns the slot
        client._mock_supabase.set_table_data("availability_slots", [SAMPLE_SLOT])
        resp = client.post("/api/availability", json={
            "day_of_week": 3,
            "start_time": "14:00",
            "end_time": "15:00",
        })
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body

    def test_create_slot_invalid_day(self, client):
        """Invalid day_of_week returns 422."""
        resp = client.post("/api/availability", json={
            "day_of_week": 9,
            "start_time": "09:00",
            "end_time": "10:00",
        })
        assert resp.status_code == 422

    def test_create_slot_patient_forbidden(self, patient_client):
        """Patient cannot create availability slots."""
        resp = patient_client.post("/api/availability", json={
            "day_of_week": 1,
            "start_time": "09:00",
            "end_time": "10:00",
        })
        assert resp.status_code == 403


class TestUpdateAvailability:
    """PATCH /api/availability/:id"""

    def test_update_slot(self, client):
        """Therapist updates own slot."""
        client._mock_supabase.set_table_data("availability_slots", [SAMPLE_SLOT])
        resp = client.patch("/api/availability/slot-001", json={
            "start_time": "10:00",
            "end_time": "11:00",
        })
        assert resp.status_code == 200

    def test_update_slot_patient_forbidden(self, patient_client):
        """Patient cannot update availability slots."""
        resp = patient_client.patch("/api/availability/slot-001", json={
            "start_time": "10:00",
        })
        assert resp.status_code == 403


class TestDeleteAvailability:
    """DELETE /api/availability/:id"""

    def test_delete_slot(self, client):
        """Therapist deletes own slot."""
        client._mock_supabase.set_table_data("availability_slots", [SAMPLE_SLOT])
        resp = client.delete("/api/availability/slot-001")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True

    def test_delete_slot_patient_forbidden(self, patient_client):
        """Patient cannot delete availability slots."""
        resp = patient_client.delete("/api/availability/slot-001")
        assert resp.status_code == 403


class TestBlockDates:
    """POST /api/availability/block"""

    def test_block_dates(self, client):
        """Therapist blocks a date range."""
        client._mock_supabase.set_table_data("availability_slots", [
            {**SAMPLE_SLOT, "is_blocked": True},
        ])
        resp = client.post("/api/availability/block", json={
            "start_date": "2026-04-15",
            "end_date": "2026-04-20",
        })
        assert resp.status_code == 200

    def test_block_dates_patient_forbidden(self, patient_client):
        """Patient cannot block dates."""
        resp = patient_client.post("/api/availability/block", json={
            "start_date": "2026-04-15",
            "end_date": "2026-04-20",
        })
        assert resp.status_code == 403


class TestGetBookableSlots:
    """GET /api/availability/bookable/:therapist_id"""

    def test_get_bookable_slots(self, patient_client):
        """Any authenticated user can get bookable slots."""
        patient_client._mock_supabase.set_table_data("availability_slots", [SAMPLE_SLOT])
        patient_client._mock_supabase.set_table_data("appointments", [])
        resp = patient_client.get(
            "/api/availability/bookable/test-user-123"
            "?start_date=2026-04-01&end_date=2026-04-07"
        )
        assert resp.status_code == 200

    def test_get_bookable_slots_401(self, client):
        """No auth returns 401."""
        resp = client._tc.get(
            "/api/availability/bookable/test-user-123"
            "?start_date=2026-04-01&end_date=2026-04-07"
        )
        assert resp.status_code == 401
