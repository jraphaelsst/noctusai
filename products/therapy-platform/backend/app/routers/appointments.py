"""
Appointments Router — Book, list, get, cancel appointments.
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
from app.responses import paginated_response, success_response
from app.schemas.scheduling import AppointmentCancel, AppointmentCreate
from app.services import appointment_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/appointments", tags=["Appointments"])


@router.post("")
async def create_appointment(
    body: AppointmentCreate,
    authorization: Optional[str] = Header(None),
):
    """Create an appointment (patient books).

    Validates slot availability, creates video room, resolves session price.
    """
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    if role != "patient":
        raise HTTPException(
            status_code=403,
            detail="Apenas pacientes podem agendar sessões",
        )

    db = get_user_client(token)
    data = await appointment_service.create_appointment(
        therapist_id=body.therapist_id,
        patient_id=user.id,
        data=body.model_dump(),
        db=db,
    )
    return success_response(data)


@router.get("")
async def list_appointments(
    authorization: Optional[str] = Header(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None),
    date_start: Optional[str] = Query(None),
    date_end: Optional[str] = Query(None),
    therapist_id: Optional[str] = Query(None),
    patient_id: Optional[str] = Query(None),
):
    """List appointments. Role-scoped:

    - patient: sees own appointments
    - therapist: sees own appointments
    - clinic_admin: sees clinic's appointments
    - platform_admin: sees all
    """
    user, token = await get_current_user(authorization)
    db = get_user_client(token)
    role = get_user_role(user)

    filters: dict = {
        "status": status,
        "date_start": date_start,
        "date_end": date_end,
    }

    if role == "patient":
        filters["patient_id"] = user.id
    elif role == "therapist":
        filters["therapist_id"] = user.id
    elif role == "clinic_admin":
        clinic_id = get_clinic_id_for_user(user)
        if clinic_id:
            filters["clinic_id"] = clinic_id
    # platform_admin: no scope restriction

    # Allow explicit therapist_id/patient_id override for admins
    if role in ("platform_admin", "clinic_admin"):
        if therapist_id:
            filters["therapist_id"] = therapist_id
        if patient_id:
            filters["patient_id"] = patient_id

    data, total = await appointment_service.list_appointments(
        filters=filters,
        page=page,
        page_size=page_size,
        db=db,
    )
    return paginated_response(data, total, page, page_size)


@router.get("/{appointment_id}")
async def get_appointment(
    appointment_id: str,
    authorization: Optional[str] = Header(None),
):
    """Get appointment detail with video room info."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)
    role = get_user_role(user)

    appointment = await appointment_service.get_appointment(appointment_id, db)

    # Authorization check: involved party or admin
    if role not in ("platform_admin", "clinic_admin"):
        if user.id not in (appointment["therapist_id"], appointment["patient_id"]):
            raise HTTPException(status_code=403, detail="Sem permissão para visualizar este agendamento")

    return success_response(appointment)


@router.post("/{appointment_id}/cancel")
async def cancel_appointment(
    appointment_id: str,
    body: AppointmentCancel = AppointmentCancel(),
    authorization: Optional[str] = Header(None),
):
    """Cancel an appointment. Applies 24h cancellation policy.

    >24h before: free cancellation.
    <24h before: late cancellation (50% charge).
    """
    user, token = await get_current_user(authorization)
    db = get_user_client(token)
    role = get_user_role(user)

    result = await appointment_service.cancel_appointment(
        appointment_id=appointment_id,
        user_id=user.id,
        user_role=role,
        db=db,
    )
    return success_response(result)
