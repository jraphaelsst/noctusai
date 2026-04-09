"""
Availability Service — Manage therapist availability slots, blocking, and bookable windows.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException

from app.dependencies import first_or_none

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_time(t: str) -> time:
    """Parse HH:MM string to a time object."""
    parts = t.split(":")
    return time(int(parts[0]), int(parts[1]))


def _times_overlap(
    s1: str, e1: str,
    s2: str, e2: str,
) -> bool:
    """Check if two time ranges overlap."""
    start1, end1 = _parse_time(s1), _parse_time(e1)
    start2, end2 = _parse_time(s2), _parse_time(e2)
    return start1 < end2 and start2 < end1


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

async def list_slots(therapist_id: str, db: Any) -> List[Dict]:
    """Return all availability slots for a therapist."""
    result = (
        db.table("availability_slots")
        .select("*")
        .eq("therapist_id", therapist_id)
        .order("day_of_week")
        .order("start_time")
        .execute()
    )
    return result.data or []


async def create_slot(
    therapist_id: str,
    data: Dict,
    clinic_id: Optional[str],
    db: Any,
) -> Dict:
    """Create an availability slot. Validates no overlap with existing slots."""
    # Validate start < end
    if _parse_time(data["start_time"]) >= _parse_time(data["end_time"]):
        raise HTTPException(
            status_code=400,
            detail="Horário de início deve ser anterior ao horário de término",
        )

    # Check overlap with existing slots for the same day
    existing = (
        db.table("availability_slots")
        .select("id, start_time, end_time")
        .eq("therapist_id", therapist_id)
        .eq("day_of_week", data["day_of_week"])
        .execute()
    )
    for slot in existing.data or []:
        if _times_overlap(
            data["start_time"], data["end_time"],
            slot["start_time"], slot["end_time"],
        ):
            raise HTTPException(
                status_code=409,
                detail="Este horário se sobrepõe a um slot existente",
            )

    insert_data = {
        "therapist_id": therapist_id,
        "day_of_week": data["day_of_week"],
        "start_time": data["start_time"],
        "end_time": data["end_time"],
        "is_recurring": data.get("is_recurring", True),
        "specific_date": data.get("specific_date"),
        "is_blocked": data.get("is_blocked", False),
    }
    if clinic_id:
        insert_data["clinic_id"] = clinic_id

    result = db.table("availability_slots").insert(insert_data).execute()
    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=500, detail="Erro ao criar slot de disponibilidade")
    return row


async def update_slot(
    slot_id: str,
    therapist_id: str,
    data: Dict,
    db: Any,
) -> Dict:
    """Update an availability slot. Only the owning therapist can update."""
    # Verify ownership
    check = (
        db.table("availability_slots")
        .select("id, day_of_week, start_time, end_time")
        .eq("id", slot_id)
        .eq("therapist_id", therapist_id)
        .execute()
    )
    existing = first_or_none(check)
    if not existing:
        raise HTTPException(status_code=404, detail="Slot não encontrado")

    update_data = {k: v for k, v in data.items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

    # Validate time order if either time field changed
    new_start = update_data.get("start_time", existing["start_time"])
    new_end = update_data.get("end_time", existing["end_time"])
    if _parse_time(new_start) >= _parse_time(new_end):
        raise HTTPException(
            status_code=400,
            detail="Horário de início deve ser anterior ao horário de término",
        )

    # Check overlap with other slots (excluding current)
    others = (
        db.table("availability_slots")
        .select("id, start_time, end_time")
        .eq("therapist_id", therapist_id)
        .eq("day_of_week", existing["day_of_week"])
        .neq("id", slot_id)
        .execute()
    )
    for s in others.data or []:
        if _times_overlap(new_start, new_end, s["start_time"], s["end_time"]):
            raise HTTPException(
                status_code=409,
                detail="Este horário se sobrepõe a um slot existente",
            )

    result = (
        db.table("availability_slots")
        .update(update_data)
        .eq("id", slot_id)
        .execute()
    )
    return first_or_none(result) or existing


async def delete_slot(slot_id: str, therapist_id: str, db: Any) -> None:
    """Delete an availability slot. Verifies ownership first."""
    check = (
        db.table("availability_slots")
        .select("id")
        .eq("id", slot_id)
        .eq("therapist_id", therapist_id)
        .execute()
    )
    if not check.data:
        raise HTTPException(status_code=404, detail="Slot não encontrado")

    db.table("availability_slots").delete().eq("id", slot_id).execute()


async def block_dates(
    therapist_id: str,
    start_date: str,
    end_date: str,
    clinic_id: Optional[str],
    db: Any,
) -> List[Dict]:
    """Block a date range by creating blocked slots for each day."""
    d_start = date.fromisoformat(start_date)
    d_end = date.fromisoformat(end_date)

    if d_start > d_end:
        raise HTTPException(status_code=400, detail="Data de início deve ser anterior à data de término")

    blocked_slots: List[Dict] = []
    current = d_start
    while current <= d_end:
        insert_data = {
            "therapist_id": therapist_id,
            "day_of_week": current.isoweekday() % 7,  # Python isoweekday 1=Mon, convert to 0=Sun
            "start_time": "00:00",
            "end_time": "23:59",
            "is_recurring": False,
            "specific_date": current.isoformat(),
            "is_blocked": True,
        }
        if clinic_id:
            insert_data["clinic_id"] = clinic_id
        result = db.table("availability_slots").insert(insert_data).execute()
        row = first_or_none(result)
        if row:
            blocked_slots.append(row)
        current += timedelta(days=1)

    return blocked_slots


async def get_available_slots_for_booking(
    therapist_id: str,
    start_date: str,
    end_date: str,
    db: Any,
) -> List[Dict]:
    """Return non-booked, non-blocked time windows for a therapist in a date range.

    Cross-references availability_slots with existing appointments to exclude
    already-booked times. Returns list of {date, start_time, end_time} dicts.
    """
    d_start = date.fromisoformat(start_date)
    d_end = date.fromisoformat(end_date)

    # Fetch all availability slots for the therapist
    slots_result = (
        db.table("availability_slots")
        .select("*")
        .eq("therapist_id", therapist_id)
        .eq("is_blocked", False)
        .execute()
    )
    all_slots = slots_result.data or []

    # Fetch existing appointments in the date range
    iso_start = datetime.combine(d_start, time.min).isoformat()
    iso_end = datetime.combine(d_end, time(23, 59, 59)).isoformat()
    appts_result = (
        db.table("appointments")
        .select("scheduled_start, scheduled_end")
        .eq("therapist_id", therapist_id)
        .gte("scheduled_start", iso_start)
        .lte("scheduled_start", iso_end)
        .not_.in_("status", ["cancelled", "late_cancelled"])
        .execute()
    )
    booked_appointments = appts_result.data or []

    # Fetch blocked dates in range
    blocked_result = (
        db.table("availability_slots")
        .select("specific_date")
        .eq("therapist_id", therapist_id)
        .eq("is_blocked", True)
        .execute()
    )
    blocked_dates = {
        b["specific_date"]
        for b in (blocked_result.data or [])
        if b.get("specific_date")
    }

    # Build booked set: {(date_str, start_time)} for quick lookup
    booked_set: set[Tuple[str, str]] = set()
    for appt in booked_appointments:
        appt_start = datetime.fromisoformat(appt["scheduled_start"].replace("Z", "+00:00"))
        appt_date = appt_start.date().isoformat()
        appt_time = appt_start.strftime("%H:%M")
        booked_set.add((appt_date, appt_time))

    available: List[Dict] = []
    current = d_start
    while current <= d_end:
        date_str = current.isoformat()
        dow = current.isoweekday() % 7  # 0=Sun

        # Skip blocked dates
        if date_str in blocked_dates:
            current += timedelta(days=1)
            continue

        for slot in all_slots:
            # Match by day_of_week (recurring) or specific_date
            is_match = False
            if slot.get("is_recurring") and slot["day_of_week"] == dow:
                is_match = True
            elif slot.get("specific_date") == date_str:
                is_match = True

            if not is_match:
                continue

            # Check if this slot/time is already booked
            if (date_str, slot["start_time"]) not in booked_set:
                available.append({
                    "date": date_str,
                    "start_time": slot["start_time"],
                    "end_time": slot["end_time"],
                })

        current += timedelta(days=1)

    # Sort by date then start_time
    available.sort(key=lambda x: (x["date"], x["start_time"]))
    return available
