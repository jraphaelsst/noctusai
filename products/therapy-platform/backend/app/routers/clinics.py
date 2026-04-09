"""
Clinics Router — Directory, profile, settings, therapist management.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query

from app.dependencies import (
    get_current_user,
    get_user_client,
    get_admin_client,
    get_user_role,
    get_clinic_id_for_user,
)
from app.responses import paginated_response, success_response
from app.schemas.clinic import (
    ClinicUpdate,
    ClinicSettingsUpdate,
    ClinicTherapistConfigUpdate,
    TherapistInvite,
)
from app.services import clinic_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/clinics", tags=["Clinics"])


# ── Directory ────────────────────────────────────────────────────────

@router.get("")
async def list_clinics(
    authorization: Optional[str] = Header(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    busca: Optional[str] = Query(None),
    specialty: Optional[str] = Query(None),
    min_rating: Optional[float] = Query(None, ge=1, le=5),
    sort: Optional[str] = Query("relevance"),
):
    """Clinic directory — public to all authenticated users."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    filters = {
        "busca": busca,
        "specialty": specialty,
        "min_rating": min_rating,
        "sort": sort,
    }
    data, total = await clinic_service.list_clinics_directory(
        filters=filters,
        page=page,
        page_size=page_size,
        db=db,
    )
    return paginated_response(data, total, page, page_size)


@router.get("/settings")
async def get_settings(authorization: Optional[str] = Header(None)):
    """Get clinic settings (clinic admin only)."""
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    if role != "clinic_admin":
        raise HTTPException(status_code=403, detail="Acesso restrito a administradores de clínica")

    clinic_id = get_clinic_id_for_user(user)
    if not clinic_id:
        raise HTTPException(status_code=400, detail="Clínica não configurada")

    db = get_user_client(token)
    result = await clinic_service.get_clinic_settings(clinic_id, db)
    return success_response(result)


@router.patch("/settings")
async def update_settings(
    body: ClinicSettingsUpdate,
    authorization: Optional[str] = Header(None),
):
    """Update clinic settings (clinic admin only)."""
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    if role != "clinic_admin":
        raise HTTPException(status_code=403, detail="Acesso restrito a administradores de clínica")

    clinic_id = get_clinic_id_for_user(user)
    if not clinic_id:
        raise HTTPException(status_code=400, detail="Clínica não configurada")

    db = get_user_client(token)
    result = await clinic_service.update_clinic_settings(
        clinic_id=clinic_id,
        data=body.model_dump(exclude_unset=True),
        db=db,
    )
    return success_response(result)


@router.get("/therapists/{therapist_id}/config")
async def get_therapist_config(
    therapist_id: str,
    authorization: Optional[str] = Header(None),
):
    """Get per-therapist configuration within the clinic (clinic admin only)."""
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    if role != "clinic_admin":
        raise HTTPException(status_code=403, detail="Acesso restrito a administradores de clínica")

    clinic_id = get_clinic_id_for_user(user)
    if not clinic_id:
        raise HTTPException(status_code=400, detail="Clínica não configurada")

    db = get_user_client(token)
    result = await clinic_service.get_therapist_config(clinic_id, therapist_id, db)
    return success_response(result)


@router.patch("/therapists/{therapist_id}/config")
async def update_therapist_config(
    therapist_id: str,
    body: ClinicTherapistConfigUpdate,
    authorization: Optional[str] = Header(None),
):
    """Update per-therapist configuration within the clinic (clinic admin only)."""
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    if role != "clinic_admin":
        raise HTTPException(status_code=403, detail="Acesso restrito a administradores de clínica")

    clinic_id = get_clinic_id_for_user(user)
    if not clinic_id:
        raise HTTPException(status_code=400, detail="Clínica não configurada")

    db = get_user_client(token)
    result = await clinic_service.update_therapist_config(
        clinic_id=clinic_id,
        therapist_id=therapist_id,
        data=body.model_dump(exclude_unset=True),
        db=db,
    )
    return success_response(result)


# ── Profile ──────────────────────────────────────────────────────────

@router.get("/{clinic_id}")
async def get_clinic(
    clinic_id: str,
    authorization: Optional[str] = Header(None),
):
    """Get clinic profile detail with stats."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)
    result = await clinic_service.get_clinic_with_stats(clinic_id, db)
    return success_response(result)


@router.patch("/{clinic_id}")
async def update_clinic(
    clinic_id: str,
    body: ClinicUpdate,
    authorization: Optional[str] = Header(None),
):
    """Update clinic profile (clinic admin only, own clinic)."""
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    if role != "clinic_admin":
        raise HTTPException(status_code=403, detail="Acesso restrito a administradores de clínica")

    user_clinic_id = get_clinic_id_for_user(user)
    if user_clinic_id != clinic_id:
        raise HTTPException(status_code=403, detail="Você só pode editar sua própria clínica")

    db = get_user_client(token)
    result = await clinic_service.update_clinic(
        clinic_id=clinic_id,
        data=body.model_dump(exclude_unset=True),
        db=db,
    )
    return success_response(result)


@router.get("/{clinic_id}/therapists")
async def list_clinic_therapists(
    clinic_id: str,
    authorization: Optional[str] = Header(None),
):
    """List all therapists in a clinic (public)."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)
    data = await clinic_service.list_clinic_therapists(clinic_id, db)
    return success_response(data)


@router.post("/{clinic_id}/invite")
async def invite_therapist(
    clinic_id: str,
    body: TherapistInvite,
    authorization: Optional[str] = Header(None),
):
    """Invite a therapist to join the clinic (clinic admin only)."""
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    if role != "clinic_admin":
        raise HTTPException(status_code=403, detail="Acesso restrito a administradores de clínica")

    user_clinic_id = get_clinic_id_for_user(user)
    if user_clinic_id != clinic_id:
        raise HTTPException(status_code=403, detail="Você só pode convidar para sua própria clínica")

    db = get_user_client(token)
    admin_db = get_admin_client()
    result = await clinic_service.invite_therapist(
        clinic_id=clinic_id,
        email=body.email,
        nome=body.nome,
        db=db,
        admin_db=admin_db,
    )
    return success_response(result)
