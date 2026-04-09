"""
Availability Router — Manage therapist availability slots and bookable windows.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query

from app.dependencies import (
    get_clinic_id_for_user,
    get_current_user,
    get_user_client,
    get_user_role,
)
from app.responses import ok_response, success_response
from app.schemas.scheduling import AvailabilitySlotCreate, AvailabilitySlotUpdate, BlockDatesRequest
from app.services import availability_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/availability", tags=["Availability"])


@router.get("")
async def list_availability(
    authorization: Optional[str] = Header(None),
    therapist_id: Optional[str] = Query(None),
):
    """List availability slots.

    Therapists see their own by default. Any authenticated user can query
    a specific therapist's availability via the therapist_id query param.
    """
    user, token = await get_current_user(authorization)
    db = get_user_client(token)
    role = get_user_role(user)

    target_id = therapist_id
    if not target_id:
        if role != "therapist":
            raise HTTPException(
                status_code=400,
                detail="Informe o therapist_id para consultar a disponibilidade",
            )
        target_id = user.id

    data = await availability_service.list_slots(target_id, db)
    return success_response(data)


@router.post("")
async def create_availability(
    body: AvailabilitySlotCreate,
    authorization: Optional[str] = Header(None),
):
    """Create an availability slot (therapist only)."""
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    if role != "therapist":
        raise HTTPException(status_code=403, detail="Apenas terapeutas podem criar slots de disponibilidade")

    db = get_user_client(token)
    clinic_id = get_clinic_id_for_user(user)
    data = await availability_service.create_slot(
        therapist_id=user.id,
        data=body.model_dump(),
        clinic_id=clinic_id,
        db=db,
    )
    return success_response(data)


@router.patch("/{slot_id}")
async def update_availability(
    slot_id: str,
    body: AvailabilitySlotUpdate,
    authorization: Optional[str] = Header(None),
):
    """Update an availability slot (therapist only, own slot)."""
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    if role != "therapist":
        raise HTTPException(status_code=403, detail="Apenas terapeutas podem editar slots de disponibilidade")

    db = get_user_client(token)
    data = await availability_service.update_slot(
        slot_id=slot_id,
        therapist_id=user.id,
        data=body.model_dump(exclude_unset=True),
        db=db,
    )
    return success_response(data)


@router.delete("/{slot_id}")
async def delete_availability(
    slot_id: str,
    authorization: Optional[str] = Header(None),
):
    """Delete an availability slot (therapist only, own slot)."""
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    if role != "therapist":
        raise HTTPException(status_code=403, detail="Apenas terapeutas podem excluir slots de disponibilidade")

    db = get_user_client(token)
    await availability_service.delete_slot(slot_id, user.id, db)
    return ok_response("Slot de disponibilidade excluído com sucesso")


@router.post("/block")
async def block_dates(
    body: BlockDatesRequest,
    authorization: Optional[str] = Header(None),
):
    """Block a date range (therapist only)."""
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    if role != "therapist":
        raise HTTPException(status_code=403, detail="Apenas terapeutas podem bloquear datas")

    db = get_user_client(token)
    clinic_id = get_clinic_id_for_user(user)
    data = await availability_service.block_dates(
        therapist_id=user.id,
        start_date=body.start_date,
        end_date=body.end_date,
        clinic_id=clinic_id,
        db=db,
    )
    return success_response(data)


@router.get("/bookable/{therapist_id}")
async def get_bookable_slots(
    therapist_id: str,
    authorization: Optional[str] = Header(None),
    start_date: str = Query(..., description="YYYY-MM-DD"),
    end_date: str = Query(..., description="YYYY-MM-DD"),
):
    """Get available booking slots for a therapist within a date range.

    Any authenticated user can call this to see where they can book.
    """
    user, token = await get_current_user(authorization)
    db = get_user_client(token)
    data = await availability_service.get_available_slots_for_booking(
        therapist_id=therapist_id,
        start_date=start_date,
        end_date=end_date,
        db=db,
    )
    return success_response(data)
