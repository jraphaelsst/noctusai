"""
Room Service — Physical room management and booking for clinics.

Handles room CRUD and time-conflict detection for bookings.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from fastapi import HTTPException

from app.dependencies import first_or_none

logger = logging.getLogger(__name__)


async def create_room(
    clinic_id: str,
    data: Dict,
    db: Any,
) -> Dict:
    """Create a physical room in a clinic."""
    record = {
        "clinic_id": clinic_id,
        "nome": data["nome"],
        "descricao": data.get("descricao"),
        "capacidade": data.get("capacidade", 1),
        "is_active": True,
    }
    result = db.table("rooms").insert(record).execute()
    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=500, detail="Erro ao criar sala")
    logger.info("Room '%s' created for clinic %s", data["nome"], clinic_id)
    return row


async def update_room(
    room_id: str,
    data: Dict,
    db: Any,
) -> Dict:
    """Update a room."""
    check = db.table("rooms").select("id").eq("id", room_id).execute()
    if not check.data:
        raise HTTPException(status_code=404, detail="Sala não encontrada")

    update_fields = {k: v for k, v in data.items() if v is not None}
    if not update_fields:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

    result = db.table("rooms").update(update_fields).eq("id", room_id).execute()
    return first_or_none(result) or {}


async def list_rooms(
    clinic_id: str,
    db: Any,
) -> List[Dict]:
    """List all rooms for a clinic."""
    result = (
        db.table("rooms")
        .select("*")
        .eq("clinic_id", clinic_id)
        .order("nome")
        .execute()
    )
    return result.data or []


async def create_booking(
    data: Dict,
    db: Any,
) -> Dict:
    """Book a room for an appointment time slot.

    Validates that no other booking exists for the same room,
    date, and overlapping time range.
    """
    room_id = str(data["room_id"])
    booking_date = data["data"]
    horario_inicio = data["horario_inicio"]
    horario_fim = data["horario_fim"]

    # Check room exists
    room_check = db.table("rooms").select("id, is_active").eq("id", room_id).execute()
    room = first_or_none(room_check)
    if not room:
        raise HTTPException(status_code=404, detail="Sala não encontrada")
    if not room.get("is_active", True):
        raise HTTPException(status_code=400, detail="Sala está desativada")

    # Check for time conflicts on the same room and date
    conflicts = (
        db.table("room_bookings")
        .select("id")
        .eq("room_id", room_id)
        .eq("data", str(booking_date))
        .lt("horario_inicio", str(horario_fim))
        .gt("horario_fim", str(horario_inicio))
        .execute()
    )
    if conflicts.data:
        raise HTTPException(
            status_code=409,
            detail="Sala já reservada neste horário",
        )

    record = {
        "room_id": room_id,
        "appointment_id": str(data["appointment_id"]),
        "data": str(booking_date),
        "horario_inicio": str(horario_inicio),
        "horario_fim": str(horario_fim),
    }
    result = db.table("room_bookings").insert(record).execute()
    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=500, detail="Erro ao reservar sala")
    logger.info("Room %s booked for date %s (%s-%s)", room_id, booking_date, horario_inicio, horario_fim)
    return row


async def delete_booking(
    booking_id: str,
    db: Any,
) -> None:
    """Delete a room booking."""
    check = db.table("room_bookings").select("id").eq("id", booking_id).execute()
    if not check.data:
        raise HTTPException(status_code=404, detail="Reserva não encontrada")

    db.table("room_bookings").delete().eq("id", booking_id).execute()
    logger.info("Room booking %s deleted", booking_id)
