"""
WhatsApp Therapy Router — WhatsApp messaging and appointment reminders.

Therapists send messages to patients, configure automated reminders
for upcoming appointments, and view message history.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query, Request

from app.dependencies import (
    get_current_user,
    get_user_client,
    get_user_role,
)
from app.rate_limit import limiter
from app.responses import paginated_response, success_response
from app.services import whatsapp_therapy_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/whatsapp", tags=["WhatsApp"])


@router.post("/enviar")
@limiter.limit("30/minute")
async def send_message(
    request: Request,
    body: dict,
    authorization: Optional[str] = Header(None),
):
    """Send a WhatsApp message to a patient (therapist only)."""
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    if role != "therapist":
        raise HTTPException(status_code=403, detail="Apenas terapeutas podem enviar mensagens")

    db = get_user_client(token)
    data = await whatsapp_therapy_service.send_message(
        therapist_id=user.id,
        body=body,
        db=db,
    )
    return success_response(data)


@router.post("/lembrete")
@limiter.limit("30/minute")
async def send_reminder(
    request: Request,
    body: dict,
    authorization: Optional[str] = Header(None),
):
    """Send an appointment reminder via WhatsApp."""
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    if role != "therapist":
        raise HTTPException(status_code=403, detail="Apenas terapeutas podem enviar lembretes")

    db = get_user_client(token)
    # Fetch appointment for the reminder
    appointment_id = body.get("appointment_id")
    appt = None
    if appointment_id:
        from app.dependencies import first_or_none
        appt = first_or_none(
            db.table("appointments").select("*").eq("id", appointment_id).execute()
        )
    if not appt:
        appt = body  # Fallback: use body as appointment data
    data = await whatsapp_therapy_service.send_reminder(
        appointment=appt,
        db=db,
    )
    return success_response(data)


@router.get("/historico")
async def message_history(
    authorization: Optional[str] = Header(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    patient_id: Optional[str] = Query(None),
):
    """Get WhatsApp message history."""
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    if role not in ("therapist", "clinic_admin", "platform_admin"):
        raise HTTPException(status_code=403, detail="Sem permissão para visualizar histórico de mensagens")

    db = get_user_client(token)
    data, total = await whatsapp_therapy_service.get_message_history(
        user_id=user.id,
        role=role,
        patient_id=patient_id,
        page=page,
        page_size=page_size,
        db=db,
    )
    return paginated_response(data, total, page, page_size)


@router.post("/configurar-lembretes")
async def configure_reminders(
    body: dict,
    authorization: Optional[str] = Header(None),
):
    """Configure automated reminder schedules (therapist only)."""
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    if role != "therapist":
        raise HTTPException(status_code=403, detail="Apenas terapeutas podem configurar lembretes")

    db = get_user_client(token)
    data = await whatsapp_therapy_service.configure_reminders(
        therapist_id=user.id,
        body=body,
        db=db,
    )
    return success_response(data)


@router.get("/lembretes")
async def list_reminder_configs(
    authorization: Optional[str] = Header(None),
):
    """List reminder configurations for the current therapist."""
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    if role != "therapist":
        raise HTTPException(status_code=403, detail="Apenas terapeutas podem visualizar configurações de lembretes")

    db = get_user_client(token)
    data = await whatsapp_therapy_service.list_reminder_configs(
        therapist_id=user.id,
        db=db,
    )
    return success_response(data)
