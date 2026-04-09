"""
Recurring Schedule Service — Create, approve, pause, resume, end, modify, skip, generate.
"""
from __future__ import annotations

import logging
from calendar import monthrange
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from fastapi import HTTPException

from app.dependencies import first_or_none
from app.responses import calculate_pagination
from app.services.appointment_service import (
    SP_TZ,
    _get_cancellation_cutoff_hours,
    _get_post_access_minutes,
    _get_pre_access_minutes,
    resolve_session_price,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _next_occurrence(
    from_date: date,
    target_dow: int,
) -> date:
    """Find the next date (>= from_date) that falls on target_dow (0=Sun)."""
    # Convert target_dow (0=Sun) to Python weekday (0=Mon)
    py_target = (target_dow - 1) % 7  # 0=Sun→6, 1=Mon→0, …
    days_ahead = (py_target - from_date.weekday()) % 7
    return from_date + timedelta(days=days_ahead)


def _compute_occurrences(
    start_date: date,
    end_date: date,
    day_of_week: int,
    frequency: str,
    custom_interval_weeks: Optional[int] = None,
) -> List[date]:
    """Generate occurrence dates for a recurring schedule within a date range."""
    first = _next_occurrence(start_date, day_of_week)
    if first < start_date:
        first += timedelta(weeks=1)

    if frequency == "weekly":
        step = timedelta(weeks=1)
    elif frequency == "biweekly":
        step = timedelta(weeks=2)
    elif frequency == "monthly":
        step = timedelta(weeks=4)
    elif frequency == "custom" and custom_interval_weeks:
        step = timedelta(weeks=custom_interval_weeks)
    else:
        step = timedelta(weeks=1)

    occurrences: List[date] = []
    current = first
    while current <= end_date:
        if current >= start_date:
            occurrences.append(current)
        current += step

    return occurrences


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

async def create_schedule(
    data: Dict,
    created_by_user_id: str,
    created_by_type: str,
    db: Any,
) -> Dict:
    """Create a recurring schedule.

    If created_by_type='patient_request', status starts as 'active' only
    after approval (initially 'paused' until approved).
    """
    # Determine initial status
    if created_by_type == "patient_request":
        initial_status = "paused"
    else:
        initial_status = "active"

    insert_data = {
        "therapist_id": data["therapist_id"],
        "patient_id": data["patient_id"],
        "frequency": data["frequency"],
        "custom_interval_weeks": data.get("custom_interval_weeks"),
        "day_of_week": data["day_of_week"],
        "start_time": data["start_time"],
        "duration_minutes": data.get("duration_minutes", 50),
        "start_date": data["start_date"],
        "end_condition": data["end_condition"],
        "end_after_n": data.get("end_after_n"),
        "end_on_date": data.get("end_on_date"),
        "status": initial_status,
        "created_by_type": created_by_type,
        "created_by_user_id": created_by_user_id,
    }

    # Resolve clinic_id from therapist
    tp = (
        db.table("therapist_profiles")
        .select("clinic_id")
        .eq("user_id", data["therapist_id"])
        .execute()
    )
    tp_row = first_or_none(tp)
    if tp_row and tp_row.get("clinic_id"):
        insert_data["clinic_id"] = tp_row["clinic_id"]

    result = db.table("recurring_schedules").insert(insert_data).execute()
    schedule = first_or_none(result)
    if not schedule:
        raise HTTPException(status_code=500, detail="Erro ao criar agendamento recorrente")

    return schedule


# ---------------------------------------------------------------------------
# Approve / Deny
# ---------------------------------------------------------------------------

async def approve_schedule(schedule_id: str, approver_id: str, db: Any) -> Dict:
    """Therapist/clinic approves a patient-requested schedule."""
    schedule = await _get_schedule_or_404(schedule_id, db)

    if schedule.get("created_by_type") != "patient_request":
        raise HTTPException(status_code=400, detail="Este agendamento não requer aprovação")

    if schedule.get("approved_by_user_id"):
        raise HTTPException(status_code=400, detail="Agendamento já aprovado")

    result = (
        db.table("recurring_schedules")
        .update({
            "status": "active",
            "approved_by_user_id": approver_id,
        })
        .eq("id", schedule_id)
        .execute()
    )
    return first_or_none(result) or schedule


async def deny_schedule(schedule_id: str, denier_id: str, reason: str, db: Any) -> Dict:
    """Therapist/clinic denies a patient request."""
    schedule = await _get_schedule_or_404(schedule_id, db)

    if schedule.get("created_by_type") != "patient_request":
        raise HTTPException(status_code=400, detail="Este agendamento não requer aprovação")

    result = (
        db.table("recurring_schedules")
        .update({"status": "ended", "ended_at": datetime.now(SP_TZ).isoformat()})
        .eq("id", schedule_id)
        .execute()
    )
    return first_or_none(result) or schedule


# ---------------------------------------------------------------------------
# Pause / Resume / End
# ---------------------------------------------------------------------------

async def pause_schedule(schedule_id: str, user_id: str, db: Any) -> Dict:
    """Pause an active recurring schedule."""
    schedule = await _get_schedule_or_404(schedule_id, db)
    _assert_involved(schedule, user_id)

    if schedule["status"] != "active":
        raise HTTPException(status_code=400, detail="Só é possível pausar agendamentos ativos")

    result = (
        db.table("recurring_schedules")
        .update({
            "status": "paused",
            "paused_at": datetime.now(SP_TZ).isoformat(),
        })
        .eq("id", schedule_id)
        .execute()
    )
    return first_or_none(result) or schedule


async def resume_schedule(schedule_id: str, user_id: str, db: Any) -> Dict:
    """Resume a paused recurring schedule."""
    schedule = await _get_schedule_or_404(schedule_id, db)
    _assert_involved(schedule, user_id)

    if schedule["status"] != "paused":
        raise HTTPException(status_code=400, detail="Só é possível retomar agendamentos pausados")

    result = (
        db.table("recurring_schedules")
        .update({
            "status": "active",
            "resumed_at": datetime.now(SP_TZ).isoformat(),
        })
        .eq("id", schedule_id)
        .execute()
    )
    return first_or_none(result) or schedule


async def end_schedule(schedule_id: str, user_id: str, db: Any) -> Dict:
    """End a recurring schedule. Cancels all future auto-generated appointments."""
    schedule = await _get_schedule_or_404(schedule_id, db)
    _assert_involved(schedule, user_id)

    if schedule["status"] == "ended":
        raise HTTPException(status_code=400, detail="Agendamento já finalizado")

    now = datetime.now(SP_TZ)
    cutoff_hours = _get_cancellation_cutoff_hours(db)
    cutoff = now + timedelta(hours=cutoff_hours)

    # Cancel future auto-generated appointments
    future_appts = (
        db.table("appointments")
        .select("id, scheduled_start")
        .eq("recurring_schedule_id", schedule_id)
        .eq("is_auto_generated", True)
        .in_("status", ["waiting"])
        .gt("scheduled_start", now.isoformat())
        .execute()
    )

    free_cancel_ids: List[str] = []
    late_cancel_ids: List[str] = []
    for appt in future_appts.data or []:
        appt_start = datetime.fromisoformat(appt["scheduled_start"].replace("Z", "+00:00"))
        if appt_start > cutoff:
            free_cancel_ids.append(appt["id"])
        else:
            late_cancel_ids.append(appt["id"])

    if free_cancel_ids:
        db.table("appointments").update({"status": "cancelled"}).in_("id", free_cancel_ids).execute()
    if late_cancel_ids:
        db.table("appointments").update({"status": "late_cancelled"}).in_("id", late_cancel_ids).execute()

    # Close video rooms for cancelled appointments
    all_cancelled = free_cancel_ids + late_cancel_ids
    if all_cancelled:
        db.table("video_rooms").update({"status": "closed"}).in_(
            "appointment_id", all_cancelled
        ).execute()

    result = (
        db.table("recurring_schedules")
        .update({
            "status": "ended",
            "ended_at": now.isoformat(),
        })
        .eq("id", schedule_id)
        .execute()
    )
    return first_or_none(result) or schedule


# ---------------------------------------------------------------------------
# Modify
# ---------------------------------------------------------------------------

async def modify_schedule(
    schedule_id: str,
    data: Dict,
    user_id: str,
    db: Any,
) -> Dict:
    """Modify a recurring schedule. Changes apply to future occurrences only."""
    schedule = await _get_schedule_or_404(schedule_id, db)
    _assert_involved(schedule, user_id)

    update_data = {k: v for k, v in data.items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

    result = (
        db.table("recurring_schedules")
        .update(update_data)
        .eq("id", schedule_id)
        .execute()
    )
    return first_or_none(result) or schedule


# ---------------------------------------------------------------------------
# Skip Occurrence
# ---------------------------------------------------------------------------

async def skip_occurrence(
    schedule_id: str,
    occurrence_date: str,
    user_id: str,
    db: Any,
) -> Dict:
    """Skip a specific occurrence of a recurring schedule.

    >24h before = free skip (cancel). <24h = charged (late_cancel).
    """
    schedule = await _get_schedule_or_404(schedule_id, db)
    _assert_involved(schedule, user_id)

    # Find the appointment for this specific date
    search_start = f"{occurrence_date}T00:00:00"
    search_end = f"{occurrence_date}T23:59:59"
    appt_result = (
        db.table("appointments")
        .select("id, scheduled_start, status")
        .eq("recurring_schedule_id", schedule_id)
        .gte("scheduled_start", search_start)
        .lte("scheduled_start", search_end)
        .execute()
    )
    appt = first_or_none(appt_result)
    if not appt:
        raise HTTPException(
            status_code=404,
            detail="Nenhum agendamento encontrado para esta data",
        )

    if appt["status"] in ("cancelled", "late_cancelled"):
        raise HTTPException(status_code=400, detail="Este agendamento já foi cancelado")

    now = datetime.now(SP_TZ)
    scheduled_start = datetime.fromisoformat(appt["scheduled_start"].replace("Z", "+00:00"))
    cutoff_hours = _get_cancellation_cutoff_hours(db)
    cutoff = scheduled_start - timedelta(hours=cutoff_hours)

    new_status = "cancelled" if now < cutoff else "late_cancelled"

    db.table("appointments").update({"status": new_status}).eq("id", appt["id"]).execute()
    db.table("video_rooms").update({"status": "closed"}).eq("appointment_id", appt["id"]).execute()

    # Increment total_absences
    db.table("recurring_schedules").update({
        "total_absences": (schedule.get("total_absences") or 0) + 1,
    }).eq("id", schedule_id).execute()

    return {"appointment_id": appt["id"], "status": new_status, "date": occurrence_date}


# ---------------------------------------------------------------------------
# Generate Monthly Appointments
# ---------------------------------------------------------------------------

async def generate_monthly_appointments(db: Any) -> int:
    """Background job: generate appointments for active recurring schedules.

    Runs at start of each month. Creates appointments + video rooms for the
    entire month. Handles mid-month creation for new schedules.

    Returns count of appointments generated.
    """
    now = datetime.now(SP_TZ)
    month_start = date(now.year, now.month, 1)
    _, days_in_month = monthrange(now.year, now.month)
    month_end = date(now.year, now.month, days_in_month)

    # Fetch all active recurring schedules
    schedules_result = (
        db.table("recurring_schedules")
        .select("*")
        .eq("status", "active")
        .execute()
    )
    schedules = schedules_result.data or []

    total_created = 0

    for schedule in schedules:
        schedule_start = date.fromisoformat(schedule["start_date"])
        effective_start = max(schedule_start, month_start)

        # Check end conditions
        end_condition = schedule["end_condition"]
        if end_condition == "on_date" and schedule.get("end_on_date"):
            end_on = date.fromisoformat(schedule["end_on_date"])
            if end_on < effective_start:
                continue
            effective_end = min(month_end, end_on)
        else:
            effective_end = month_end

        if end_condition == "after_n_occurrences" and schedule.get("end_after_n"):
            max_total = schedule["end_after_n"]
            completed = schedule.get("total_completed") or 0
            remaining = max_total - completed
            if remaining <= 0:
                continue

        occurrences = _compute_occurrences(
            start_date=effective_start,
            end_date=effective_end,
            day_of_week=schedule["day_of_week"],
            frequency=schedule["frequency"],
            custom_interval_weeks=schedule.get("custom_interval_weeks"),
        )

        # Limit by remaining occurrences
        if end_condition == "after_n_occurrences" and schedule.get("end_after_n"):
            completed = schedule.get("total_completed") or 0
            remaining = schedule["end_after_n"] - completed
            occurrences = occurrences[:remaining]

        for occ_date in occurrences:
            # Parse start_time
            start_time_parts = schedule["start_time"].split(":")
            occ_start = datetime(
                occ_date.year, occ_date.month, occ_date.day,
                int(start_time_parts[0]), int(start_time_parts[1]),
                tzinfo=SP_TZ,
            )
            duration = schedule.get("duration_minutes") or 50
            occ_end = occ_start + timedelta(minutes=duration)

            # Check if appointment already exists for this date
            existing = (
                db.table("appointments")
                .select("id")
                .eq("recurring_schedule_id", schedule["id"])
                .gte("scheduled_start", f"{occ_date.isoformat()}T00:00:00")
                .lte("scheduled_start", f"{occ_date.isoformat()}T23:59:59")
                .execute()
            )
            if existing.data:
                continue

            # Check therapist conflict
            conflict = (
                db.table("appointments")
                .select("id")
                .eq("therapist_id", schedule["therapist_id"])
                .lt("scheduled_start", occ_end.isoformat())
                .gt("scheduled_end", occ_start.isoformat())
                .not_.in_("status", ["cancelled", "late_cancelled"])
                .execute()
            )
            if conflict.data:
                logger.warning(
                    "Conflict for schedule %s on %s — skipping",
                    schedule["id"], occ_date,
                )
                continue

            # Resolve price
            price, fee_pct, comm_pct = await resolve_session_price(
                schedule["therapist_id"], schedule["patient_id"], db,
            )

            appt_data = {
                "therapist_id": schedule["therapist_id"],
                "patient_id": schedule["patient_id"],
                "recurring_schedule_id": schedule["id"],
                "scheduled_start": occ_start.isoformat(),
                "scheduled_end": occ_end.isoformat(),
                "status": "waiting",
                "session_price_applied": price,
                "platform_fee_pct_applied": fee_pct,
                "clinic_commission_pct_applied": comm_pct,
                "is_auto_generated": True,
            }
            if schedule.get("clinic_id"):
                appt_data["clinic_id"] = schedule["clinic_id"]

            appt_result = db.table("appointments").insert(appt_data).execute()
            appt = first_or_none(appt_result)
            if not appt:
                continue

            # Create video room
            pre_access = _get_pre_access_minutes(db)
            post_access = _get_post_access_minutes(db)
            room_name = f"session-{uuid4()}"
            meeting_link = f"/session/{uuid4()}"

            vr_data = {
                "appointment_id": appt["id"],
                "livekit_room_name": room_name,
                "meeting_url": meeting_link,
                "accessible_from": (occ_start - timedelta(minutes=pre_access)).isoformat(),
                "accessible_until": (occ_end + timedelta(minutes=post_access)).isoformat(),
                "status": "pending",
            }
            vr_result = db.table("video_rooms").insert(vr_data).execute()
            vr = first_or_none(vr_result)

            if vr:
                db.table("appointments").update({
                    "meeting_link": meeting_link,
                    "video_room_id": vr["id"],
                }).eq("id", appt["id"]).execute()

            total_created += 1

    logger.info("Generated %d monthly appointments", total_created)
    return total_created


# ---------------------------------------------------------------------------
# List & Get
# ---------------------------------------------------------------------------

async def list_schedules(
    filters: Dict,
    page: int,
    page_size: int,
    db: Any,
) -> Tuple[List[Dict], int]:
    """List recurring schedules with filters, paginated."""
    page, page_size, offset = calculate_pagination(page, page_size)

    query = db.table("recurring_schedules").select("*", count="exact")

    therapist_id = filters.get("therapist_id")
    if therapist_id:
        query = query.eq("therapist_id", therapist_id)

    patient_id = filters.get("patient_id")
    if patient_id:
        query = query.eq("patient_id", patient_id)

    status = filters.get("status")
    if status:
        query = query.eq("status", status)

    query = query.order("created_at", desc=True)
    result = query.range(offset, offset + page_size - 1).execute()

    return result.data or [], result.count or 0


async def get_schedule(schedule_id: str, db: Any) -> Dict:
    """Get a single recurring schedule with upcoming appointments."""
    schedule = await _get_schedule_or_404(schedule_id, db)

    now = datetime.now(SP_TZ).isoformat()
    upcoming = (
        db.table("appointments")
        .select("id, scheduled_start, scheduled_end, status, meeting_link")
        .eq("recurring_schedule_id", schedule_id)
        .gte("scheduled_start", now)
        .not_.in_("status", ["cancelled", "late_cancelled"])
        .order("scheduled_start")
        .limit(10)
        .execute()
    )
    schedule["upcoming_appointments"] = upcoming.data or []

    return schedule


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _get_schedule_or_404(schedule_id: str, db: Any) -> Dict:
    """Fetch a recurring schedule by ID or raise 404."""
    result = (
        db.table("recurring_schedules")
        .select("*")
        .eq("id", schedule_id)
        .execute()
    )
    schedule = first_or_none(result)
    if not schedule:
        raise HTTPException(status_code=404, detail="Agendamento recorrente não encontrado")
    return schedule


def _assert_involved(schedule: Dict, user_id: str) -> None:
    """Assert user is the therapist or patient of the schedule."""
    if user_id not in (schedule["therapist_id"], schedule["patient_id"]):
        raise HTTPException(
            status_code=403,
            detail="Sem permissão para modificar este agendamento",
        )
