"""
Admin Router — Approvals, commission overrides, patient assignments, listing.

All endpoints require platform_admin role.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from app.dependencies import get_current_user, get_admin_client, get_user_role
from app.responses import paginated_response, success_response
from app.schemas.admin import ApprovalAction, CommissionOverrideCreate, PatientAssignment
from app.services import admin_service


class _ReportResolution(BaseModel):
    """Body for ``POST /api/admin/reports/{id}/resolve``."""

    resolution: str = Field(..., min_length=1, max_length=2000)

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
    status: Optional[str] = Query(None, description="pendente | aprovada | rejeitada | suspensa"),
    busca: Optional[str] = Query(None, description="Buscar por nome ou CNPJ"),
):
    """List all clinics for the admin console, shaped as the frontend ``Clinica`` DTO."""
    user, _ = await get_current_user(authorization)
    _require_admin(user)
    db = get_admin_client()

    data, total = await admin_service.list_clinics_for_admin(
        db=db,
        page=page,
        page_size=page_size,
        status=status,
        busca=busca,
    )
    return paginated_response(data, total, page, page_size)


@router.get("/patients")
async def list_all_patients(
    authorization: Optional[str] = Header(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    busca: Optional[str] = Query(None, description="Buscar por telefone (server-side); name/email filter on client"),
):
    """List all patients for the admin console, shaped as the ``AdminPatient`` DTO."""
    user, _ = await get_current_user(authorization)
    _require_admin(user)
    db = get_admin_client()

    data, total = await admin_service.list_patients_for_admin(
        db=db,
        page=page,
        page_size=page_size,
        busca=busca,
    )
    return paginated_response(data, total, page, page_size)


@router.get("/appointments")
async def list_all_appointments(
    authorization: Optional[str] = Header(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None, description="Filtrar por status da sessão"),
    date_start: Optional[str] = Query(None, description="ISO date (yyyy-mm-dd)"),
    date_end: Optional[str] = Query(None, description="ISO date (yyyy-mm-dd)"),
):
    """List all appointments for the admin console.

    Resolves ``patient_name`` / ``therapist_name`` / ``clinic_name`` via the
    Phase 1 identity resolver and a bulk clinic-name lookup.
    """
    user, _ = await get_current_user(authorization)
    _require_admin(user)
    db = get_admin_client()

    data, total = await admin_service.list_appointments_for_admin(
        db=db,
        page=page,
        page_size=page_size,
        status=status,
        date_start=date_start,
        date_end=date_end,
    )
    return paginated_response(data, total, page, page_size)


# ── Dashboard ────────────────────────────────────────────────────────


@router.get("/dashboard")
async def admin_dashboard(
    authorization: Optional[str] = Header(None),
):
    """Snapshot metrics for the admin landing page."""
    user, _ = await get_current_user(authorization)
    _require_admin(user)
    db = get_admin_client()
    metrics = await admin_service.admin_dashboard_metrics(db)
    return success_response(metrics)


# ── Suspend ─────────────────────────────────────────────────────────


@router.post("/suspend/{entity_type}/{entity_id}")
async def suspend_entity(
    entity_type: str,
    entity_id: str,
    authorization: Optional[str] = Header(None),
):
    """Suspend a therapist or clinic (``is_active=False``).

    Mirror of :func:`approve_entity`. Re-approval clears the suspension.
    """
    user, _ = await get_current_user(authorization)
    admin_id = _require_admin(user)
    db = get_admin_client()
    result = await admin_service.suspend_entity(
        entity_type=entity_type,
        entity_id=entity_id,
        admin_id=admin_id,
        db=db,
    )
    return success_response(result)


# ── Moderation: Reports ──────────────────────────────────────────────


@router.get("/reports")
async def list_admin_reports(
    authorization: Optional[str] = Header(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None, description="pending | reviewed | resolved | dismissed"),
):
    """List message-reports for the admin Moderation page, DTO-shaped."""
    user, _ = await get_current_user(authorization)
    _require_admin(user)
    db = get_admin_client()

    data, total = await admin_service.list_reports_for_admin(
        db=db,
        page=page,
        page_size=page_size,
        status=status,
    )
    return paginated_response(data, total, page, page_size)


@router.post("/reports/{report_id}/resolve")
async def resolve_admin_report(
    report_id: str,
    body: _ReportResolution,
    authorization: Optional[str] = Header(None),
):
    """Admin resolves a message report."""
    user, _ = await get_current_user(authorization)
    admin_id = _require_admin(user)
    db = get_admin_client()

    result = await admin_service.resolve_report(
        report_id=report_id,
        admin_id=admin_id,
        resolution=body.resolution,
        db=db,
    )
    return success_response(result)


# ── Moderation: Flagged reviews ──────────────────────────────────────


@router.get("/reviews/flagged")
async def list_admin_flagged_reviews(
    authorization: Optional[str] = Header(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    entity_type: Optional[str] = Query(None, description="therapist | clinic"),
):
    """List flagged (and not hidden) reviews across therapists + clinics."""
    user, _ = await get_current_user(authorization)
    _require_admin(user)
    db = get_admin_client()

    data, total = await admin_service.list_flagged_reviews_for_admin(
        db=db,
        page=page,
        page_size=page_size,
        entity_type=entity_type,
    )
    return paginated_response(data, total, page, page_size)


@router.post("/reviews/{review_id}/dismiss")
async def dismiss_review_flag(
    review_id: str,
    authorization: Optional[str] = Header(None),
):
    """Admin dismisses a review flag — review goes back to visible."""
    user, _ = await get_current_user(authorization)
    admin_id = _require_admin(user)
    db = get_admin_client()

    result = await admin_service.moderate_review(
        review_id=review_id,
        action="dismiss",
        admin_id=admin_id,
        db=db,
    )
    return success_response(result)


@router.post("/reviews/{review_id}/hide")
async def hide_review(
    review_id: str,
    authorization: Optional[str] = Header(None),
):
    """Admin hides a flagged review — sets ``is_hidden=True``."""
    user, _ = await get_current_user(authorization)
    admin_id = _require_admin(user)
    db = get_admin_client()

    result = await admin_service.moderate_review(
        review_id=review_id,
        action="hide",
        admin_id=admin_id,
        db=db,
    )
    return success_response(result)


# ── Moderation: Blocks ───────────────────────────────────────────────


@router.get("/blocks")
async def list_admin_blocks(
    authorization: Optional[str] = Header(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List user-blocks for the admin Moderation page, DTO-shaped."""
    user, _ = await get_current_user(authorization)
    _require_admin(user)
    db = get_admin_client()

    data, total = await admin_service.list_blocks_for_admin(
        db=db,
        page=page,
        page_size=page_size,
    )
    return paginated_response(data, total, page, page_size)


# ── Support inbox ────────────────────────────────────────────────────


@router.get("/support/conversations")
async def list_admin_support_conversations(
    authorization: Optional[str] = Header(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    busca: Optional[str] = Query(None, description="Buscar por id da conversa"),
):
    """List support conversations for the admin inbox, ``Conversation`` DTO."""
    user, _ = await get_current_user(authorization)
    _require_admin(user)
    db = get_admin_client()

    data, total = await admin_service.list_support_conversations_for_admin(
        db=db,
        page=page,
        page_size=page_size,
        busca=busca,
    )
    return paginated_response(data, total, page, page_size)
