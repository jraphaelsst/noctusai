"""Admin list + detail on `media_scheduling.appointments`.

Frontend contract (Phase 5 hooks `useAppointments.ts`):
  - GET /api/appointments?start_date=&end_date=&status=&condominium_id=
  - GET /api/appointments/{id}

Wire-shape note (Phase 3 improvement candidate): the frontend hook surfaces
`starts_at` / `ends_at` while the schema column names are `start_at` /
`end_at`. We translate both directions so the hook gets the fields it
wires; surface in Phase 3 improvements for a Phase 6 alignment pass
(rename hook OR rename column — keep one source of truth).
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Header, HTTPException, Query

from app.database import get_supabase_client
from app.dependencies import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/appointments", tags=["Appointments"])


_VALID_STATUSES = {
    "scheduled",
    "pending",
    "confirmed",
    "in_progress",
    "completed",
    "cancelled",
    "canceled",
}


def _wire(row: dict[str, Any]) -> dict[str, Any]:
    """Map DB shape → frontend hook shape (start_at→starts_at, end_at→ends_at)."""
    out = dict(row)
    if "start_at" in out:
        out["starts_at"] = out.pop("start_at")
    if "end_at" in out:
        out["ends_at"] = out.pop("end_at")
    return out


@router.get("")
async def list_appointments(
    authorization: Optional[str] = Header(None),
    start_date: Optional[str] = Query(None, description="ISO date YYYY-MM-DD inclusive"),
    end_date: Optional[str] = Query(None, description="ISO date YYYY-MM-DD inclusive"),
    status: Optional[str] = Query(None),
    condominium_id: Optional[str] = Query(None),
) -> dict[str, Any]:
    await get_current_user(authorization)

    if status and status not in _VALID_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Allowed: {sorted(_VALID_STATUSES)}",
        )

    db = get_supabase_client()
    q = db.table("appointments").select("*")

    if start_date:
        # `start_at >= start_date 00:00 UTC`. Caller responsible for tz semantics.
        q = q.gte("start_at", f"{start_date}T00:00:00+00:00")
    if end_date:
        q = q.lte("start_at", f"{end_date}T23:59:59+00:00")
    if status:
        q = q.eq("status", status)
    if condominium_id:
        q = q.eq("condominium_id", condominium_id)

    q = q.order("start_at", desc=True).limit(500)
    try:
        result = q.execute()
    except Exception as exc:
        logger.warning("appointments list failed: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    rows = [_wire(r) for r in (result.data or [])]
    return {"data": rows, "total": len(rows)}


@router.get("/{appointment_id}")
async def get_appointment(
    appointment_id: str,
    authorization: Optional[str] = Header(None),
) -> dict[str, Any]:
    await get_current_user(authorization)
    db = get_supabase_client()
    result = (
        db.table("appointments")
        .select("*")
        .eq("id", appointment_id)
        .limit(1)
        .execute()
    )
    rows = result.data or []
    if not rows:
        raise HTTPException(status_code=404, detail="Appointment not found")
    return _wire(rows[0])
