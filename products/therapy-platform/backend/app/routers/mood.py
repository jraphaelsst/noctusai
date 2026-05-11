"""
Mood Router — Patient mood tracking and analytics.

Patients log daily mood entries with optional notes. Supports
date-range filtering and analytics aggregation.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query

from app.dependencies import (
    get_current_user,
    get_user_client,
    get_user_role,
)
from app.responses import success_response
from app.services import mood_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/mood", tags=["Mood"])


@router.post("")
async def create_mood_entry(
    body: dict,
    authorization: Optional[str] = Header(None),
):
    """Create a mood entry (patient only)."""
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    if role != "patient":
        raise HTTPException(status_code=403, detail="Apenas pacientes podem registrar humor")

    db = get_user_client(token)
    data = await mood_service.create_entry(
        patient_id=user.id,
        data=body,
        db=db,
    )
    return success_response(data)


@router.get("")
async def list_mood_entries(
    authorization: Optional[str] = Header(None),
    data_inicio: Optional[str] = Query(None, description="Data início (YYYY-MM-DD)"),
    data_fim: Optional[str] = Query(None, description="Data fim (YYYY-MM-DD)"),
):
    """List mood entries for the current patient (with date range filters)."""
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    if role != "patient":
        raise HTTPException(status_code=403, detail="Apenas pacientes podem visualizar seus registros de humor")

    db = get_user_client(token)
    data, total = await mood_service.list_entries(
        patient_id=user.id,
        data_inicio=data_inicio,
        data_fim=data_fim,
        db=db,
    )
    return success_response(data)


@router.get("/analytics")
async def mood_analytics(
    authorization: Optional[str] = Header(None),
    data_inicio: Optional[str] = Query(None, description="Data início (YYYY-MM-DD)"),
    data_fim: Optional[str] = Query(None, description="Data fim (YYYY-MM-DD)"),
):
    """Get mood analytics for the current patient."""
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    if role != "patient":
        raise HTTPException(status_code=403, detail="Apenas pacientes podem visualizar analytics de humor")

    db = get_user_client(token)
    data = await mood_service.get_analytics(
        patient_id=user.id,
        db=db,
    )
    return success_response(data)
