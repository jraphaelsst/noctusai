"""
Recurring Schedules Router — Create, manage, approve/deny recurring therapy sessions.
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
from app.responses import ok_response, paginated_response, success_response
from app.schemas.scheduling import RecurringScheduleCreate, RecurringScheduleUpdate
from app.services import recurring_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/recurring", tags=["Recurring Schedules"])


@router.post("")
async def create_recurring_schedule(
    body: RecurringScheduleCreate,
    authorization: Optional[str] = Header(None),
):
    """Create a recurring schedule.

    - therapist/clinic_admin: creates directly (active).
    - patient: creates as request needing approval (paused until approved).
    """
    user, token = await get_current_user(authorization)
    db = get_user_client(token)
    role = get_user_role(user)

    if role == "patient":
        created_by_type = "patient_request"
    elif role == "therapist":
        created_by_type = "therapist"
    elif role == "clinic_admin":
        created_by_type = "clinic_admin"
    elif role == "platform_admin":
        created_by_type = "platform_admin"
    else:
        raise HTTPException(status_code=403, detail="Sem permissão para criar agendamento recorrente")

    data = await recurring_service.create_schedule(
        data=body.model_dump(),
        created_by_user_id=user.id,
        created_by_type=created_by_type,
        db=db,
    )
    return success_response(data)


@router.get("")
async def list_recurring_schedules(
    authorization: Optional[str] = Header(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None),
    therapist_id: Optional[str] = Query(None),
    patient_id: Optional[str] = Query(None),
):
    """List recurring schedules. Role-scoped (same as appointments)."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)
    role = get_user_role(user)

    filters: dict = {"status": status}

    if role == "patient":
        filters["patient_id"] = user.id
    elif role == "therapist":
        filters["therapist_id"] = user.id
    elif role == "clinic_admin":
        clinic_id = get_clinic_id_for_user(user)
        if clinic_id:
            filters["clinic_id"] = clinic_id
    # platform_admin: no scope restriction

    if role in ("platform_admin", "clinic_admin"):
        if therapist_id:
            filters["therapist_id"] = therapist_id
        if patient_id:
            filters["patient_id"] = patient_id

    data, total = await recurring_service.list_schedules(
        filters=filters,
        page=page,
        page_size=page_size,
        db=db,
    )
    return paginated_response(data, total, page, page_size)


@router.get("/{schedule_id}")
async def get_recurring_schedule(
    schedule_id: str,
    authorization: Optional[str] = Header(None),
):
    """Get schedule detail with upcoming appointments."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)
    role = get_user_role(user)

    schedule = await recurring_service.get_schedule(schedule_id, db)

    if role not in ("platform_admin", "clinic_admin"):
        if user.id not in (schedule["therapist_id"], schedule["patient_id"]):
            raise HTTPException(status_code=403, detail="Sem permissão para visualizar este agendamento")

    return success_response(schedule)


@router.patch("/{schedule_id}")
async def modify_recurring_schedule(
    schedule_id: str,
    body: RecurringScheduleUpdate,
    authorization: Optional[str] = Header(None),
):
    """Modify a recurring schedule. Changes apply to future occurrences only.

    Only therapist or clinic_admin can modify.
    """
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    if role not in ("therapist", "clinic_admin", "platform_admin"):
        raise HTTPException(status_code=403, detail="Apenas terapeutas ou administradores podem modificar")

    db = get_user_client(token)
    data = await recurring_service.modify_schedule(
        schedule_id=schedule_id,
        data=body.model_dump(exclude_unset=True),
        user_id=user.id,
        db=db,
    )
    return success_response(data)


@router.post("/{schedule_id}/approve")
async def approve_recurring_schedule(
    schedule_id: str,
    authorization: Optional[str] = Header(None),
):
    """Approve a patient-requested recurring schedule."""
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    if role not in ("therapist", "clinic_admin", "platform_admin"):
        raise HTTPException(status_code=403, detail="Apenas terapeutas ou administradores podem aprovar")

    db = get_user_client(token)
    data = await recurring_service.approve_schedule(schedule_id, user.id, db)
    return success_response(data)


@router.post("/{schedule_id}/deny")
async def deny_recurring_schedule(
    schedule_id: str,
    authorization: Optional[str] = Header(None),
    reason: str = Query("", description="Motivo da negação"),
):
    """Deny a patient-requested recurring schedule."""
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    if role not in ("therapist", "clinic_admin", "platform_admin"):
        raise HTTPException(status_code=403, detail="Apenas terapeutas ou administradores podem negar")

    db = get_user_client(token)
    data = await recurring_service.deny_schedule(schedule_id, user.id, reason, db)
    return success_response(data)


@router.post("/{schedule_id}/pause")
async def pause_recurring_schedule(
    schedule_id: str,
    authorization: Optional[str] = Header(None),
):
    """Pause an active recurring schedule."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)
    data = await recurring_service.pause_schedule(schedule_id, user.id, db)
    return success_response(data)


@router.post("/{schedule_id}/resume")
async def resume_recurring_schedule(
    schedule_id: str,
    authorization: Optional[str] = Header(None),
):
    """Resume a paused recurring schedule."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)
    data = await recurring_service.resume_schedule(schedule_id, user.id, db)
    return success_response(data)


@router.post("/{schedule_id}/end")
async def end_recurring_schedule(
    schedule_id: str,
    authorization: Optional[str] = Header(None),
):
    """End a recurring schedule. Cancels all future auto-generated appointments."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)
    data = await recurring_service.end_schedule(schedule_id, user.id, db)
    return success_response(data)


@router.post("/{schedule_id}/skip")
async def skip_occurrence(
    schedule_id: str,
    authorization: Optional[str] = Header(None),
    date: str = Query(..., description="YYYY-MM-DD date of the occurrence to skip"),
):
    """Skip a specific occurrence. >24h = free, <24h = charged."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)
    data = await recurring_service.skip_occurrence(
        schedule_id=schedule_id,
        occurrence_date=date,
        user_id=user.id,
        db=db,
    )
    return success_response(data)
