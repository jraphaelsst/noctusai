"""
Rooms Router — Physical room management and booking for clinics.

Clinic admins create and manage rooms. Therapists book rooms
for in-person sessions.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query

from app.dependencies import (
    first_or_none,
    get_clinic_id_for_user,
    get_current_user,
    get_user_client,
    get_user_role,
)
from app.responses import ok_response, success_response
from app.services import room_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/rooms", tags=["Rooms"])


@router.post("")
async def create_room(
    body: dict,
    authorization: Optional[str] = Header(None),
):
    """Create a room (clinic_admin only)."""
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    if role != "clinic_admin":
        raise HTTPException(status_code=403, detail="Apenas administradores de clínica podem criar salas")

    clinic_id = get_clinic_id_for_user(user)
    if not clinic_id:
        raise HTTPException(status_code=400, detail="Usuário não associado a uma clínica")

    db = get_user_client(token)
    data = await room_service.create_room(
        clinic_id=clinic_id,
        data=body,
        db=db,
    )
    return success_response(data)


@router.get("")
async def list_rooms(
    authorization: Optional[str] = Header(None),
):
    """List rooms for the user's clinic."""
    user, token = await get_current_user(authorization)
    role = get_user_role(user)

    clinic_id = get_clinic_id_for_user(user)
    if not clinic_id:
        raise HTTPException(status_code=400, detail="Usuário não associado a uma clínica")

    db = get_user_client(token)
    data = await room_service.list_rooms(
        clinic_id=clinic_id,
        db=db,
    )
    return success_response(data)


@router.patch("/{room_id}")
async def update_room(
    room_id: str,
    body: dict,
    authorization: Optional[str] = Header(None),
):
    """Update a room (clinic_admin only)."""
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    if role != "clinic_admin":
        raise HTTPException(status_code=403, detail="Apenas administradores de clínica podem editar salas")

    clinic_id = get_clinic_id_for_user(user)
    if not clinic_id:
        raise HTTPException(status_code=400, detail="Usuário não associado a uma clínica")

    db = get_user_client(token)

    # Verify room exists and belongs to the clinic
    existing = first_or_none(
        db.table("rooms")
        .select("id, clinic_id")
        .eq("id", room_id)
        .execute()
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Sala não encontrada")
    if existing["clinic_id"] != clinic_id:
        raise HTTPException(status_code=403, detail="Sem permissão para editar esta sala")

    data = await room_service.update_room(
        room_id=room_id,
        data=body,
        db=db,
    )
    return success_response(data)


@router.post("/bookings")
async def create_booking(
    body: dict,
    authorization: Optional[str] = Header(None),
):
    """Create a room booking."""
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    if role not in ("therapist", "clinic_admin"):
        raise HTTPException(status_code=403, detail="Apenas terapeutas e admins podem reservar salas")

    db = get_user_client(token)
    data = await room_service.create_booking(
        data=body,
        db=db,
    )
    return success_response(data)


@router.delete("/bookings/{booking_id}")
async def delete_booking(
    booking_id: str,
    authorization: Optional[str] = Header(None),
):
    """Delete a room booking."""
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    db = get_user_client(token)

    # Verify booking exists
    existing = first_or_none(
        db.table("room_bookings")
        .select("id, booked_by")
        .eq("id", booking_id)
        .execute()
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Reserva não encontrada")

    # Only the booker or clinic_admin can delete
    if role not in ("clinic_admin", "platform_admin") and existing["booked_by"] != user.id:
        raise HTTPException(status_code=403, detail="Sem permissão para cancelar esta reserva")

    await room_service.delete_booking(booking_id=booking_id, db=db)
    return ok_response("Reserva cancelada com sucesso")
