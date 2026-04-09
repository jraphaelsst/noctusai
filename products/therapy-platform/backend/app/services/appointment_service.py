"""
Appointment Service — Create, cancel, list, no-show detection, price resolution.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from fastapi import HTTPException

from app.dependencies import first_or_none
from app.responses import calculate_pagination

logger = logging.getLogger(__name__)

# São Paulo timezone offset (UTC-3). For production use pytz/ZoneInfo,
# but keeping stdlib-only for simplicity.
SP_TZ = timezone(timedelta(hours=-3))


# ---------------------------------------------------------------------------
# Platform settings helpers
# ---------------------------------------------------------------------------

def _get_platform_setting(db: Any, key: str, default: str) -> str:
    """Read a single value from therapy.platform_settings."""
    result = (
        db.table("platform_settings")
        .select("value")
        .eq("key", key)
        .execute()
    )
    row = first_or_none(result)
    return row["value"] if row else default


def _get_cancellation_cutoff_hours(db: Any) -> int:
    return int(_get_platform_setting(db, "cancellation_cutoff_hours", "24"))


def _get_no_show_charge_pct(db: Any) -> float:
    return float(_get_platform_setting(db, "no_show_charge_pct", "50"))


def _get_pre_access_minutes(db: Any) -> int:
    return int(_get_platform_setting(db, "session_pre_access_minutes", "15"))


def _get_post_access_minutes(db: Any) -> int:
    return int(_get_platform_setting(db, "session_post_access_minutes", "10"))


# ---------------------------------------------------------------------------
# Price Resolution
# ---------------------------------------------------------------------------

async def resolve_session_price(
    therapist_id: str,
    patient_id: str,
    db: Any,
) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """Resolve session price following the priority chain.

    Priority (highest → lowest):
    1. platform_admin patient_pricing (set_by='platform_admin')
    2. clinic_admin/therapist patient_pricing (set_by='clinic_admin' or 'therapist')
    3. clinic_set_default_price from clinic_therapist_config
    4. therapist default_session_price from therapist_profiles

    Returns (session_price, platform_fee_pct, clinic_commission_pct).
    """
    # 1. Check patient_pricing set by platform_admin
    pp_admin = (
        db.table("patient_pricing")
        .select("custom_price")
        .eq("therapist_id", therapist_id)
        .eq("patient_id", patient_id)
        .eq("set_by", "platform_admin")
        .execute()
    )
    admin_row = first_or_none(pp_admin)
    if admin_row and admin_row.get("custom_price") is not None:
        price = float(admin_row["custom_price"])
        fee_pct, comm_pct = await _get_fee_and_commission(therapist_id, db)
        return price, fee_pct, comm_pct

    # 2. Check patient_pricing set by clinic_admin or therapist
    pp_other = (
        db.table("patient_pricing")
        .select("custom_price")
        .eq("therapist_id", therapist_id)
        .eq("patient_id", patient_id)
        .in_("set_by", ["clinic_admin", "therapist"])
        .execute()
    )
    other_row = first_or_none(pp_other)
    if other_row and other_row.get("custom_price") is not None:
        price = float(other_row["custom_price"])
        fee_pct, comm_pct = await _get_fee_and_commission(therapist_id, db)
        return price, fee_pct, comm_pct

    # 3. Check clinic_set_default_price from clinic_therapist_config
    ctc = (
        db.table("clinic_therapist_config")
        .select("clinic_set_default_price, clinic_commission_pct")
        .eq("therapist_id", therapist_id)
        .execute()
    )
    ctc_row = first_or_none(ctc)
    if ctc_row and ctc_row.get("clinic_set_default_price") is not None:
        price = float(ctc_row["clinic_set_default_price"])
        comm = float(ctc_row.get("clinic_commission_pct") or 0)
        fee_pct = await _get_platform_fee_pct(db)
        return price, fee_pct, comm

    # 4. Therapist default_session_price
    tp = (
        db.table("therapist_profiles")
        .select("default_session_price")
        .eq("user_id", therapist_id)
        .execute()
    )
    tp_row = first_or_none(tp)
    price = float(tp_row["default_session_price"]) if tp_row and tp_row.get("default_session_price") else None
    fee_pct, comm_pct = await _get_fee_and_commission(therapist_id, db)
    return price, fee_pct, comm_pct


async def _get_platform_fee_pct(db: Any) -> float:
    return float(_get_platform_setting(db, "platform_fee_pct", "10"))


async def _get_fee_and_commission(
    therapist_id: str,
    db: Any,
) -> Tuple[float, float]:
    """Get platform fee pct and clinic commission pct for a therapist."""
    fee_pct = await _get_platform_fee_pct(db)
    ctc = (
        db.table("clinic_therapist_config")
        .select("clinic_commission_pct")
        .eq("therapist_id", therapist_id)
        .execute()
    )
    ctc_row = first_or_none(ctc)
    comm_pct = float(ctc_row["clinic_commission_pct"]) if ctc_row and ctc_row.get("clinic_commission_pct") else 0.0
    return fee_pct, comm_pct


# ---------------------------------------------------------------------------
# Create Appointment
# ---------------------------------------------------------------------------

async def create_appointment(
    therapist_id: str,
    patient_id: str,
    data: Dict,
    db: Any,
) -> Dict:
    """Create an appointment + video room.

    Validates:
    - Slot is available (no blocking, no conflict)
    - Patient has no conflicting appointment at the same time

    Resolves session price, creates video_room with accessibility window.
    """
    scheduled_start_str = data["scheduled_start"]
    scheduled_start = datetime.fromisoformat(scheduled_start_str.replace("Z", "+00:00"))

    # Determine scheduled_end
    if data.get("scheduled_end"):
        scheduled_end = datetime.fromisoformat(data["scheduled_end"].replace("Z", "+00:00"))
    else:
        # Default to therapist's session duration (50 min fallback)
        tp = (
            db.table("therapist_profiles")
            .select("session_duration_minutes")
            .eq("user_id", therapist_id)
            .execute()
        )
        tp_row = first_or_none(tp)
        duration = int(tp_row["session_duration_minutes"]) if tp_row and tp_row.get("session_duration_minutes") else 50
        scheduled_end = scheduled_start + timedelta(minutes=duration)

    # Validate: no conflicting appointment for this therapist
    conflict_therapist = (
        db.table("appointments")
        .select("id")
        .eq("therapist_id", therapist_id)
        .lt("scheduled_start", scheduled_end.isoformat())
        .gt("scheduled_end", scheduled_start.isoformat())
        .not_.in_("status", ["cancelled", "late_cancelled"])
        .execute()
    )
    if conflict_therapist.data:
        raise HTTPException(
            status_code=409,
            detail="O terapeuta já tem uma sessão neste horário",
        )

    # Validate: no conflicting appointment for this patient
    conflict_patient = (
        db.table("appointments")
        .select("id")
        .eq("patient_id", patient_id)
        .lt("scheduled_start", scheduled_end.isoformat())
        .gt("scheduled_end", scheduled_start.isoformat())
        .not_.in_("status", ["cancelled", "late_cancelled"])
        .execute()
    )
    if conflict_patient.data:
        raise HTTPException(
            status_code=409,
            detail="Você já tem uma sessão agendada neste horário",
        )

    # Resolve price
    price, fee_pct, comm_pct = await resolve_session_price(therapist_id, patient_id, db)

    # Resolve therapist clinic_id
    tp_full = (
        db.table("therapist_profiles")
        .select("clinic_id")
        .eq("user_id", therapist_id)
        .execute()
    )
    tp_full_row = first_or_none(tp_full)
    clinic_id = tp_full_row.get("clinic_id") if tp_full_row else None

    # Create appointment
    appointment_data = {
        "therapist_id": therapist_id,
        "patient_id": patient_id,
        "scheduled_start": scheduled_start.isoformat(),
        "scheduled_end": scheduled_end.isoformat(),
        "status": "waiting",
        "session_price_applied": price,
        "platform_fee_pct_applied": fee_pct,
        "clinic_commission_pct_applied": comm_pct,
        "is_auto_generated": False,
    }
    if clinic_id:
        appointment_data["clinic_id"] = clinic_id

    appt_result = db.table("appointments").insert(appointment_data).execute()
    appointment = first_or_none(appt_result)
    if not appointment:
        raise HTTPException(status_code=500, detail="Erro ao criar agendamento")

    # Create video room
    pre_access = _get_pre_access_minutes(db)
    post_access = _get_post_access_minutes(db)
    room_name = f"session-{uuid4()}"
    meeting_link = f"/session/{uuid4()}"

    video_room_data = {
        "appointment_id": appointment["id"],
        "livekit_room_name": room_name,
        "meeting_url": meeting_link,
        "accessible_from": (scheduled_start - timedelta(minutes=pre_access)).isoformat(),
        "accessible_until": (scheduled_end + timedelta(minutes=post_access)).isoformat(),
        "status": "pending",
    }
    vr_result = db.table("video_rooms").insert(video_room_data).execute()
    video_room = first_or_none(vr_result)

    # Attach meeting_link to appointment for convenience
    if video_room:
        db.table("appointments").update({
            "meeting_link": meeting_link,
            "video_room_id": video_room["id"],
        }).eq("id", appointment["id"]).execute()
        appointment["meeting_link"] = meeting_link
        appointment["video_room_id"] = video_room["id"]
        appointment["video_room"] = video_room

    return appointment


# ---------------------------------------------------------------------------
# Cancel Appointment
# ---------------------------------------------------------------------------

async def cancel_appointment(
    appointment_id: str,
    user_id: str,
    user_role: str,
    db: Any,
) -> Dict:
    """Cancel an appointment with 24h policy.

    >24h before: free cancellation (status='cancelled').
    <24h before: late cancellation (status='late_cancelled', 50% charge).
    """
    result = (
        db.table("appointments")
        .select("*")
        .eq("id", appointment_id)
        .execute()
    )
    appointment = first_or_none(result)
    if not appointment:
        raise HTTPException(status_code=404, detail="Agendamento não encontrado")

    # Authorization: patient or therapist involved, or admin
    if user_role not in ("platform_admin", "clinic_admin"):
        if user_id not in (appointment["therapist_id"], appointment["patient_id"]):
            raise HTTPException(status_code=403, detail="Sem permissão para cancelar este agendamento")

    if appointment["status"] in ("cancelled", "late_cancelled"):
        raise HTTPException(status_code=400, detail="Agendamento já cancelado")

    if appointment["status"] == "completed":
        raise HTTPException(status_code=400, detail="Não é possível cancelar um agendamento concluído")

    now = datetime.now(SP_TZ)
    scheduled_start = datetime.fromisoformat(
        appointment["scheduled_start"].replace("Z", "+00:00")
    )
    cutoff_hours = _get_cancellation_cutoff_hours(db)
    cutoff = scheduled_start - timedelta(hours=cutoff_hours)

    if now < cutoff:
        # Free cancellation
        new_status = "cancelled"
    else:
        # Late cancellation — charge applies
        new_status = "late_cancelled"

    update_data = {"status": new_status}
    updated = (
        db.table("appointments")
        .update(update_data)
        .eq("id", appointment_id)
        .execute()
    )

    # Close associated video room
    db.table("video_rooms").update({"status": "closed"}).eq(
        "appointment_id", appointment_id
    ).execute()

    return first_or_none(updated) or {**appointment, **update_data}


# ---------------------------------------------------------------------------
# List & Get
# ---------------------------------------------------------------------------

async def list_appointments(
    filters: Dict,
    page: int,
    page_size: int,
    db: Any,
) -> Tuple[List[Dict], int]:
    """List appointments with role-based filters, paginated."""
    page, page_size, offset = calculate_pagination(page, page_size)

    query = db.table("appointments").select("*", count="exact")

    therapist_id = filters.get("therapist_id")
    if therapist_id:
        query = query.eq("therapist_id", therapist_id)

    patient_id = filters.get("patient_id")
    if patient_id:
        query = query.eq("patient_id", patient_id)

    clinic_id = filters.get("clinic_id")
    if clinic_id:
        query = query.eq("clinic_id", clinic_id)

    status = filters.get("status")
    if status:
        query = query.eq("status", status)

    date_start = filters.get("date_start")
    if date_start:
        query = query.gte("scheduled_start", date_start)

    date_end = filters.get("date_end")
    if date_end:
        query = query.lte("scheduled_start", date_end)

    query = query.order("scheduled_start", desc=True)
    result = query.range(offset, offset + page_size - 1).execute()

    return result.data or [], result.count or 0


async def get_appointment(appointment_id: str, db: Any) -> Dict:
    """Get a single appointment with video room info."""
    result = (
        db.table("appointments")
        .select("*")
        .eq("id", appointment_id)
        .execute()
    )
    appointment = first_or_none(result)
    if not appointment:
        raise HTTPException(status_code=404, detail="Agendamento não encontrado")

    # Fetch video room
    vr_result = (
        db.table("video_rooms")
        .select("*")
        .eq("appointment_id", appointment_id)
        .execute()
    )
    appointment["video_room"] = first_or_none(vr_result)

    return appointment


# ---------------------------------------------------------------------------
# No-Show Detection
# ---------------------------------------------------------------------------

async def detect_no_shows(db: Any) -> int:
    """Background job: detect no-shows and mark them.

    Finds appointments where scheduled_end has passed, status='waiting',
    and neither party attended. Marks as 'no_show'.

    Returns count of newly detected no-shows.
    """
    now = datetime.now(SP_TZ).isoformat()

    # Find overdue appointments still in 'waiting'
    overdue = (
        db.table("appointments")
        .select("id")
        .eq("status", "waiting")
        .lt("scheduled_end", now)
        .execute()
    )
    overdue_ids = [a["id"] for a in (overdue.data or [])]
    if not overdue_ids:
        return 0

    # Batch update to no_show
    db.table("appointments").update({
        "status": "no_show",
    }).in_("id", overdue_ids).execute()

    logger.info("Detected %d no-shows", len(overdue_ids))
    return len(overdue_ids)
