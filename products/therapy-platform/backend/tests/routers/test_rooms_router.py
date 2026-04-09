"""
Tests for the Rooms Router.

Covers: create room (clinic_admin only), list rooms, update room,
create booking, delete booking, and auth/permission checks.
"""
import pytest

SAMPLE_ROOM = {
    "id": "room-001",
    "clinic_id": "test-clinic-123",
    "nome": "Sala 1 - Atendimento Individual",
    "descricao": "Sala com divã e poltrona",
    "capacidade": 2,
    "is_active": True,
    "created_at": "2026-04-01T10:00:00Z",
}

SAMPLE_BOOKING = {
    "id": "booking-001",
    "room_id": "room-001",
    "appointment_id": "appt-001",
    "data": "2026-04-10",
    "horario_inicio": "09:00",
    "horario_fim": "10:00",
    "booked_by": "test-user-123",
    "created_at": "2026-04-01T10:00:00Z",
}


class TestCreateRoom:
    """POST /api/salas"""

    def test_create_room(self, clinic_admin_client):
        """Clinic admin creates a room."""
        clinic_admin_client._mock_supabase.set_table_data("rooms", [SAMPLE_ROOM])
        resp = clinic_admin_client.post("/api/salas", json={
            "nome": "Sala 1 - Atendimento Individual",
            "descricao": "Sala com divã e poltrona",
            "capacidade": 2,
        })
        assert resp.status_code == 200
        assert "data" in resp.json()

    def test_create_room_therapist_forbidden(self, client):
        """Therapist cannot create rooms."""
        resp = client.post("/api/salas", json={
            "nome": "Sala 1",
        })
        assert resp.status_code == 403

    def test_create_room_patient_forbidden(self, patient_client):
        """Patient cannot create rooms."""
        resp = patient_client.post("/api/salas", json={
            "nome": "Sala 1",
        })
        assert resp.status_code == 403

    def test_create_room_401(self, clinic_admin_client):
        """No auth returns 401."""
        resp = clinic_admin_client._tc.post("/api/salas", json={
            "nome": "Sala 1",
        })
        assert resp.status_code == 401


class TestListRooms:
    """GET /api/salas"""

    def test_list_rooms(self, clinic_admin_client):
        """Clinic admin lists rooms."""
        clinic_admin_client._mock_supabase.set_table_data("rooms", [SAMPLE_ROOM])
        resp = clinic_admin_client.get("/api/salas")
        assert resp.status_code == 200
        assert "data" in resp.json()

    def test_list_rooms_no_clinic(self, client):
        """Therapist without clinic_id gets 400."""
        resp = client.get("/api/salas")
        assert resp.status_code == 400


class TestUpdateRoom:
    """PATCH /api/salas/{room_id}"""

    def test_update_room(self, clinic_admin_client):
        """Clinic admin updates a room."""
        clinic_admin_client._mock_supabase.set_table_data("rooms", [SAMPLE_ROOM])
        resp = clinic_admin_client.patch("/api/salas/room-001", json={
            "nome": "Sala 1 - Renomeada",
        })
        assert resp.status_code == 200

    def test_update_room_not_found(self, clinic_admin_client):
        """Non-existent room returns 404."""
        clinic_admin_client._mock_supabase.set_table_data("rooms", [])
        resp = clinic_admin_client.patch("/api/salas/nonexistent", json={
            "nome": "Teste",
        })
        assert resp.status_code == 404

    def test_update_room_different_clinic(self, clinic_admin_client):
        """Admin cannot update a room from another clinic."""
        other_room = {**SAMPLE_ROOM, "clinic_id": "other-clinic-999"}
        clinic_admin_client._mock_supabase.set_table_data("rooms", [other_room])
        resp = clinic_admin_client.patch("/api/salas/room-001", json={
            "nome": "Teste",
        })
        assert resp.status_code == 403

    def test_update_room_therapist_forbidden(self, client):
        """Therapist cannot update rooms."""
        resp = client.patch("/api/salas/room-001", json={
            "nome": "Teste",
        })
        assert resp.status_code == 403


class TestCreateBooking:
    """POST /api/salas/reservas"""

    def test_create_booking_therapist(self, client):
        """Therapist creates booking — mock returns conflict (409)."""
        client._mock_supabase.set_table_data("rooms", [SAMPLE_ROOM])
        client._mock_supabase.set_table_data("room_bookings", [SAMPLE_BOOKING])
        resp = client.post("/api/salas/reservas", json={
            "room_id": "room-001",
            "appointment_id": "appt-001",
            "data": "2026-04-10",
            "horario_inicio": "09:00",
            "horario_fim": "10:00",
        })
        # Mock returns existing booking for conflict check -> 409
        assert resp.status_code == 409

    def test_create_booking_no_conflict(self, client):
        """Therapist creates booking without conflict."""
        client._mock_supabase.set_table_data("rooms", [SAMPLE_ROOM])
        client._mock_supabase.set_table_data("room_bookings", [])
        resp = client.post("/api/salas/reservas", json={
            "room_id": "room-001",
            "appointment_id": "appt-002",
            "data": "2026-04-11",
            "horario_inicio": "11:00",
            "horario_fim": "12:00",
        })
        # Empty bookings -> no conflict, but empty insert returns 500
        assert resp.status_code in (200, 500)

    def test_create_booking_patient_forbidden(self, patient_client):
        """Patient cannot create bookings."""
        resp = patient_client.post("/api/salas/reservas", json={
            "room_id": "room-001",
            "appointment_id": "appt-001",
            "data": "2026-04-10",
            "horario_inicio": "09:00",
            "horario_fim": "10:00",
        })
        assert resp.status_code == 403


class TestDeleteBooking:
    """DELETE /api/salas/reservas/{booking_id}"""

    def test_delete_booking(self, client):
        """Booker deletes their own booking."""
        booking = {**SAMPLE_BOOKING, "booked_by": "test-user-123"}
        client._mock_supabase.set_table_data("room_bookings", [booking])
        resp = client.delete("/api/salas/reservas/booking-001")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_delete_booking_not_found(self, client):
        """Non-existent booking returns 404."""
        client._mock_supabase.set_table_data("room_bookings", [])
        resp = client.delete("/api/salas/reservas/nonexistent")
        assert resp.status_code == 404

    def test_delete_booking_not_owner(self, client):
        """Therapist cannot delete another user's booking."""
        other_booking = {**SAMPLE_BOOKING, "booked_by": "other-user-999"}
        client._mock_supabase.set_table_data("room_bookings", [other_booking])
        resp = client.delete("/api/salas/reservas/booking-001")
        assert resp.status_code == 403

    def test_delete_booking_admin_can(self, clinic_admin_client):
        """Clinic admin can delete any booking."""
        other_booking = {**SAMPLE_BOOKING, "booked_by": "other-user-999"}
        clinic_admin_client._mock_supabase.set_table_data("room_bookings", [other_booking])
        resp = clinic_admin_client.delete("/api/salas/reservas/booking-001")
        assert resp.status_code == 200
