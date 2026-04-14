"""
Tests for the Room Service.

Covers: room CRUD, booking creation, conflict detection, booking deletion.
"""
import pytest

from tests.conftest import MockRequestBuilder, MockSupabaseClient
from app.services import room_service


SAMPLE_ROOM = {
    "id": "room-001",
    "clinic_id": "clinic-001",
    "nome": "Sala 1",
    "descricao": "Sala de atendimento individual",
    "capacidade": 2,
    "is_active": True,
}

SAMPLE_BOOKING = {
    "id": "booking-001",
    "room_id": "room-001",
    "appointment_id": "appt-001",
    "data": "2026-04-10",
    "horario_inicio": "09:00",
    "horario_fim": "10:00",
}


class TestCreateRoom:
    @pytest.mark.asyncio
    async def test_create_room(self):
        db = MockSupabaseClient()
        db.set_table_data("rooms", [SAMPLE_ROOM])
        result = await room_service.create_room(
            clinic_id="clinic-001",
            data={"nome": "Sala 1", "descricao": "Atendimento individual"},
            db=db,
        )
        assert result is not None
        assert result["nome"] == "Sala 1"

    @pytest.mark.asyncio
    async def test_create_room_default_capacity(self):
        db = MockSupabaseClient()
        db.set_table_data("rooms", [SAMPLE_ROOM])
        result = await room_service.create_room(
            clinic_id="clinic-001",
            data={"nome": "Sala 2"},
            db=db,
        )
        assert result is not None


class TestUpdateRoom:
    @pytest.mark.asyncio
    async def test_update_room(self):
        db = MockSupabaseClient()
        db.set_table_data("rooms", [SAMPLE_ROOM])
        result = await room_service.update_room(
            room_id="room-001",
            data={"nome": "Sala 1 - Renomeada"},
            db=db,
        )
        assert result is not None

    @pytest.mark.asyncio
    async def test_update_room_not_found(self):
        db = MockSupabaseClient()
        db.set_table_data("rooms", [])
        with pytest.raises(Exception) as exc_info:
            await room_service.update_room(
                room_id="nonexistent",
                data={"nome": "Teste"},
                db=db,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_update_room_empty_data(self):
        db = MockSupabaseClient()
        db.set_table_data("rooms", [SAMPLE_ROOM])
        with pytest.raises(Exception) as exc_info:
            await room_service.update_room(
                room_id="room-001",
                data={},
                db=db,
            )
        assert exc_info.value.status_code == 400


class TestListRooms:
    @pytest.mark.asyncio
    async def test_list_rooms(self):
        db = MockSupabaseClient()
        db.set_table_data("rooms", [SAMPLE_ROOM])
        result = await room_service.list_rooms(clinic_id="clinic-001", db=db)
        assert isinstance(result, list)
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_list_rooms_empty(self):
        db = MockSupabaseClient()
        db.set_table_data("rooms", [])
        result = await room_service.list_rooms(clinic_id="clinic-001", db=db)
        assert result == []


class TestCreateBooking:
    @pytest.mark.asyncio
    async def test_create_booking(self):
        """Three-phase mock: room exists, no conflict, insert returns data."""
        db = MockSupabaseClient()
        call_count = {"n": 0}
        original_table = db.table

        def phased_table(name):
            call_count["n"] += 1
            if name == "rooms":
                return MockRequestBuilder([SAMPLE_ROOM])
            if name == "room_bookings":
                if call_count["n"] == 2:
                    # Conflict check: no existing booking
                    return MockRequestBuilder([])
                else:
                    # Insert: return new booking
                    return MockRequestBuilder([SAMPLE_BOOKING])
            return original_table(name)

        db.table = phased_table
        result = await room_service.create_booking(
            data={
                "room_id": "room-001",
                "appointment_id": "appt-001",
                "data": "2026-04-10",
                "horario_inicio": "09:00",
                "horario_fim": "10:00",
            },
            db=db,
        )
        assert result is not None

    @pytest.mark.asyncio
    async def test_create_booking_room_not_found(self):
        db = MockSupabaseClient()
        db.set_table_data("rooms", [])
        with pytest.raises(Exception) as exc_info:
            await room_service.create_booking(
                data={
                    "room_id": "nonexistent",
                    "appointment_id": "appt-001",
                    "data": "2026-04-10",
                    "horario_inicio": "09:00",
                    "horario_fim": "10:00",
                },
                db=db,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_create_booking_inactive_room(self):
        db = MockSupabaseClient()
        inactive_room = {**SAMPLE_ROOM, "is_active": False}
        db.set_table_data("rooms", [inactive_room])
        with pytest.raises(Exception) as exc_info:
            await room_service.create_booking(
                data={
                    "room_id": "room-001",
                    "appointment_id": "appt-001",
                    "data": "2026-04-10",
                    "horario_inicio": "09:00",
                    "horario_fim": "10:00",
                },
                db=db,
            )
        assert exc_info.value.status_code == 400


class TestDeleteBooking:
    @pytest.mark.asyncio
    async def test_delete_booking(self):
        db = MockSupabaseClient()
        db.set_table_data("room_bookings", [SAMPLE_BOOKING])
        await room_service.delete_booking(booking_id="booking-001", db=db)

    @pytest.mark.asyncio
    async def test_delete_booking_not_found(self):
        db = MockSupabaseClient()
        db.set_table_data("room_bookings", [])
        with pytest.raises(Exception) as exc_info:
            await room_service.delete_booking(booking_id="nonexistent", db=db)
        assert exc_info.value.status_code == 404
