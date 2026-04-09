"""
Crisis Alerts Router — Crisis detection and alert management.

Monitors patient activity (mood entries, journal, session notes) for
crisis indicators. Therapists review alerts for their patients;
admins can view all and trigger manual scans.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query

from app.dependencies import (
    first_or_none,
    get_current_user,
    get_user_client,
    get_user_role,
)
from app.responses import paginated_response, success_response
from app.services import crisis_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/alertas-crise", tags=["Crisis Alerts"])


@router.get("")
async def list_alerts(
    authorization: Optional[str] = Header(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None),
):
    """List crisis alerts.

    - Therapist: sees alerts for their patients
    - Admin: sees all alerts
    """
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    if role not in ("therapist", "clinic_admin", "platform_admin"):
        raise HTTPException(status_code=403, detail="Sem permissão para visualizar alertas de crise")

    db = get_user_client(token)
    raw = await crisis_service.list_alerts(
        therapist_id=user.id,
        db=db,
        status_filter=status,
    )
    total = len(raw)
    start = (page - 1) * page_size
    data = raw[start:start + page_size]
    return paginated_response(data, total, page, page_size)


@router.get("/{alert_id}")
async def get_alert(
    alert_id: str,
    authorization: Optional[str] = Header(None),
):
    """Get crisis alert detail."""
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    if role not in ("therapist", "clinic_admin", "platform_admin"):
        raise HTTPException(status_code=403, detail="Sem permissão para visualizar alertas de crise")

    db = get_user_client(token)

    existing = first_or_none(
        db.table("crisis_alerts")
        .select("*")
        .eq("id", alert_id)
        .execute()
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Alerta de crise não encontrado")

    # Therapist can only see alerts for their patients
    if role == "therapist" and existing.get("therapist_id") != user.id:
        raise HTTPException(status_code=403, detail="Sem permissão para visualizar este alerta")

    return success_response(existing)


@router.patch("/{alert_id}/revisar")
async def review_alert(
    alert_id: str,
    body: dict,
    authorization: Optional[str] = Header(None),
):
    """Review a crisis alert (therapist or admin)."""
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    if role not in ("therapist", "clinic_admin", "platform_admin"):
        raise HTTPException(status_code=403, detail="Sem permissão para revisar alertas de crise")

    db = get_user_client(token)

    # Verify alert exists
    existing = first_or_none(
        db.table("crisis_alerts")
        .select("id, therapist_id")
        .eq("id", alert_id)
        .execute()
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Alerta de crise não encontrado")

    # Therapist can only review alerts for their patients
    if role == "therapist" and existing.get("therapist_id") != user.id:
        raise HTTPException(status_code=403, detail="Sem permissão para revisar este alerta")

    data = await crisis_service.review_alert(
        alert_id=alert_id,
        reviewer_id=user.id,
        data=body,
        db=db,
    )
    return success_response(data)


@router.post("/escanear")
async def manual_scan(
    authorization: Optional[str] = Header(None),
):
    """Trigger a manual crisis scan (admin only).

    Scans recent patient activity for crisis indicators.
    """
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    if role not in ("clinic_admin", "platform_admin"):
        raise HTTPException(status_code=403, detail="Apenas administradores podem acionar escaneamento manual")

    db = get_user_client(token)
    data = await crisis_service.manual_scan(db=db)
    return success_response(data)
