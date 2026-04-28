"""
Admin Router — Approvals, commission overrides, patient assignments, listing.

All endpoints require platform_admin role.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query

from app.dependencies import get_current_user, get_admin_client, get_user_role
from app.responses import paginated_response, success_response
from app.schemas.admin import ApprovalAction, CommissionOverrideCreate, PatientAssignment
from app.services import admin_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin", tags=["Admin"])


def _require_admin(user) -> str:
    """Enforce platform_admin role. Returns user.id."""
    role = get_user_role(user)
    if role != "platform_admin":
        raise HTTPException(status_code=403, detail="Acesso restrito a administradores da plataforma")
    return user.id


# ── Approvals ────────────────────────────────────────────────────────

@router.get("/pending")
async def list_pending(authorization: Optional[str] = Header(None)):
    """List all pending therapist and clinic approvals."""
    user, _ = await get_current_user(authorization)
    _require_admin(user)
    db = get_admin_client()
    result = await admin_service.list_pending_approvals(db)
    return success_response(result)


@router.post("/approve/{entity_type}/{entity_id}")
async def approve_entity(
    entity_type: str,
    entity_id: str,
    authorization: Optional[str] = Header(None),
):
    """Approve a therapist or clinic."""
    user, _ = await get_current_user(authorization)
    admin_id = _require_admin(user)
    db = get_admin_client()
    result = await admin_service.approve_entity(
        entity_type=entity_type,
        entity_id=entity_id,
        admin_id=admin_id,
        db=db,
    )
    return success_response(result)


@router.post("/reject/{entity_type}/{entity_id}")
async def reject_entity(
    entity_type: str,
    entity_id: str,
    body: ApprovalAction,
    authorization: Optional[str] = Header(None),
):
    """Reject a therapist or clinic with a reason."""
    user, _ = await get_current_user(authorization)
    admin_id = _require_admin(user)

    if body.action != "reject":
        raise HTTPException(status_code=400, detail="Use o endpoint /approve para aprovações")

    if not body.reason:
        raise HTTPException(status_code=422, detail="Motivo é obrigatório para rejeição")

    db = get_admin_client()
    result = await admin_service.reject_entity(
        entity_type=entity_type,
        entity_id=entity_id,
        admin_id=admin_id,
        reason=body.reason,
        db=db,
    )
    return success_response(result)


# ── Commission Overrides ─────────────────────────────────────────────

@router.post("/commissions")
async def set_commission(
    body: CommissionOverrideCreate,
    authorization: Optional[str] = Header(None),
):
    """Set a platform-level commission override for a clinic or therapist."""
    user, _ = await get_current_user(authorization)
    admin_id = _require_admin(user)
    db = get_admin_client()
    result = await admin_service.set_commission_override(
        target_type=body.target_type,
        target_id=body.target_id,
        custom_commission_pct=body.custom_commission_pct,
        admin_id=admin_id,
        db=db,
    )
    return success_response(result)


# ── Patient Assignment ───────────────────────────────────────────────

@router.post("/assign-patient")
async def assign_patient(
    body: PatientAssignment,
    authorization: Optional[str] = Header(None),
):
    """Admin-assign a patient to a therapist and/or clinic."""
    user, _ = await get_current_user(authorization)
    admin_id = _require_admin(user)
    db = get_admin_client()
    result = await admin_service.assign_patient(
        patient_id=body.patient_id,
        therapist_id=body.therapist_id,
        clinic_id=body.clinic_id,
        custom_price=body.custom_price,
        admin_id=admin_id,
        db=db,
    )
    return success_response(result)


# ── Listing (Admin views) ───────────────────────────────────────────

@router.get("/therapists")
async def list_all_therapists(
    authorization: Optional[str] = Header(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None, description="Filtrar por status: pendente | aprovado | rejeitado | suspenso"),
):
    """List all therapists for the admin console, shaped as the frontend ``Terapeuta`` DTO."""
    user, _ = await get_current_user(authorization)
    _require_admin(user)
    db = get_admin_client()

    data, total = await admin_service.list_therapists_for_admin(
        db=db,
        page=page,
        page_size=page_size,
        status=status,
    )
    return paginated_response(data, total, page, page_size)


@router.get("/clinics")
async def list_all_clinics(
    authorization: Optional[str] = Header(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List all clinics (admin only)."""
    user, _ = await get_current_user(authorization)
    _require_admin(user)
    db = get_admin_client()

    query = (
        db.table("clinics")
        .select("*", count="exact")
        .order("created_at", desc=True)
    )
    offset = (page - 1) * page_size
    result = query.range(offset, offset + page_size - 1).execute()
    return paginated_response(result.data or [], result.count or 0, page, page_size)


@router.get("/patients")
async def list_all_patients(
    authorization: Optional[str] = Header(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List all patients (admin only)."""
    user, _ = await get_current_user(authorization)
    _require_admin(user)
    db = get_admin_client()

    query = (
        db.table("patient_profiles")
        .select("*", count="exact")
        .order("created_at", desc=True)
    )
    offset = (page - 1) * page_size
    result = query.range(offset, offset + page_size - 1).execute()
    return paginated_response(result.data or [], result.count or 0, page, page_size)
