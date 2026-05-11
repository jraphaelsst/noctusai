"""
WhatsApp Therapy Service — Appointment reminders and messaging via WAHA.

Sends WhatsApp messages for appointment reminders, confirmations,
and cancellation notices through a WAHA (WhatsApp HTTP API) instance.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from app.dependencies import first_or_none

logger = logging.getLogger(__name__)

WAHA_TIMEOUT = 15.0


# ---------------------------------------------------------------------------
# Message formatting
# ---------------------------------------------------------------------------

def _format_reminder_message(appointment: dict) -> str:
    """Format a reminder message for an appointment."""
    scheduled_start = appointment.get("scheduled_start", "")
    # Extract date and time from ISO string
    date_part = scheduled_start[:10] if len(scheduled_start) >= 10 else ""
    time_part = scheduled_start[11:16] if len(scheduled_start) >= 16 else ""

    return (
        f"Olá! Lembrete da sua sessão de terapia.\n\n"
        f"Data: {date_part}\n"
        f"Horário: {time_part}\n\n"
        f"Caso precise reagendar, entre em contato com antecedência."
    )


# ---------------------------------------------------------------------------
# WAHA integration
# ---------------------------------------------------------------------------

async def send_via_waha(
    waha_url: str,
    session_name: str,
    phone: str,
    message: str,
) -> Dict:
    """Send a WhatsApp message via WAHA HTTP API.

    Thin product wrapper around `noctusai_lib.integrations.whatsapp.WahaClient.send_text`
    (consumed via `get_whatsapp_client(...)` factory). Therapy assumes `phone`
    arrives already in international format (`5511999998888`), as enforced
    upstream by `patient_profiles.phone` collection. The return shape is the
    raw WAHA response (`{id, ...}`) for backward compatibility with
    `send_reminder`'s `waha_response` field.

    Raises:
        ValueError: when the WAHA HTTP call returns a non-2xx status. The
        seed `WahaClient.send_text` raises `httpx.HTTPStatusError`; we wrap
        it as `ValueError` to preserve the therapy-product contract that
        `send_reminder` catches.
    """
    from noctusai_lib.integrations.whatsapp import get_whatsapp_client

    client = get_whatsapp_client(
        base_url=waha_url,
        api_key=None,
        session=session_name,
    )
    chat_id = f"{phone}@c.us"
    try:
        result = await client.send_text(chat_id, message)
    except Exception as exc:
        logger.error("WAHA send failed for phone=%s: %s", phone, exc)
        raise ValueError(f"Erro ao enviar mensagem via WAHA: {exc}") from exc

    logger.info("WhatsApp message sent to %s via WAHA", phone)
    return result


# ---------------------------------------------------------------------------
# High-level operations
# ---------------------------------------------------------------------------

async def send_reminder(
    appointment: dict,
    db: Any,
    waha_url: Optional[str] = None,
    session_name: str = "default",
) -> Dict:
    """Send an appointment reminder via WhatsApp.

    Fetches patient phone, formats message, sends via WAHA, logs to DB.
    """
    patient_id = appointment.get("patient_id")
    if not patient_id:
        raise ValueError("Agendamento sem paciente associado")

    # Fetch patient phone
    patient_result = (
        db.table("patient_profiles")
        .select("phone, nome")
        .eq("user_id", patient_id)
        .execute()
    )
    patient = first_or_none(patient_result)
    if not patient or not patient.get("phone"):
        logger.warning("Patient %s has no phone number for WhatsApp reminder", patient_id)
        return {"status": "skipped", "reason": "Paciente sem telefone cadastrado"}

    phone = patient["phone"]
    message = _format_reminder_message(appointment)

    # Send via WAHA if configured
    waha_response = None
    if waha_url:
        try:
            waha_response = await send_via_waha(waha_url, session_name, phone, message)
        except Exception as e:
            logger.error("Failed to send WhatsApp reminder: %s", e)
            waha_response = {"error": str(e)}
    else:
        logger.info("WAHA URL not configured — dry-run reminder for %s", phone)

    # Log message
    log_data = {
        "appointment_id": appointment.get("id"),
        "destinatario_telefone": phone,
        "tipo": "lembrete",
        "conteudo": message,
        "status": "enviado" if waha_url and not (waha_response or {}).get("error") else "erro",
    }
    await log_message(log_data, db)

    return {
        "status": "sent" if waha_url else "dry_run",
        "phone": phone,
        "waha_response": waha_response,
    }


async def log_message(
    data: Dict,
    db: Any,
) -> Optional[Dict]:
    """Log a WhatsApp message to the database."""
    try:
        result = db.table("whatsapp_messages").insert(data).execute()
        return first_or_none(result)
    except Exception as e:
        logger.warning("Failed to log WhatsApp message: %s", e)
        return None


# ---------------------------------------------------------------------------
# Router-facing operations
# ---------------------------------------------------------------------------

async def send_message(
    therapist_id: str,
    body: Dict,
    db: Any,
) -> Dict:
    """Send a WhatsApp message to a patient (therapist-facing)."""
    patient_id = body.get("patient_id")
    message_text = body.get("message", "")

    patient_result = (
        db.table("patient_profiles")
        .select("phone, nome")
        .eq("user_id", patient_id)
        .execute()
    )
    patient = first_or_none(patient_result)
    if not patient or not patient.get("phone"):
        return {"status": "skipped", "reason": "Paciente sem telefone cadastrado"}

    log_data = {
        "therapist_id": therapist_id,
        "destinatario_telefone": patient["phone"],
        "tipo": "mensagem",
        "conteudo": message_text,
        "status": "enviado",
    }
    await log_message(log_data, db)
    return {"status": "sent", "phone": patient["phone"]}


async def get_message_history(
    user_id: str,
    role: str,
    patient_id: Optional[str],
    page: int,
    page_size: int,
    db: Any,
) -> tuple:
    """Get paginated WhatsApp message history."""
    from app.responses import calculate_pagination
    page, page_size, offset = calculate_pagination(page, page_size)

    query = db.table("whatsapp_messages").select("*", count="exact")
    if role == "therapist":
        query = query.eq("therapist_id", user_id)
    if patient_id:
        query = query.eq("patient_id", patient_id)

    result = query.order("created_at", desc=True).range(offset, offset + page_size - 1).execute()
    return result.data or [], result.count or 0


async def configure_reminders(
    therapist_id: str,
    body: Dict,
    db: Any,
) -> Dict:
    """Configure automated reminder settings for a therapist."""
    record = {
        "therapist_id": therapist_id,
        "antecedencia_horas": body.get("antecedencia_horas", 24),
        "is_active": body.get("is_active", True),
    }
    result = db.table("reminder_configs").upsert(record).execute()
    return first_or_none(result) or record


async def list_reminder_configs(
    therapist_id: str,
    db: Any,
) -> list:
    """List reminder configurations for a therapist."""
    result = (
        db.table("reminder_configs")
        .select("*")
        .eq("therapist_id", therapist_id)
        .execute()
    )
    return result.data or []
