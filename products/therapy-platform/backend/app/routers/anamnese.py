"""
Anamnese Router — Clinical anamnesis (intake assessment) per patient-therapist pair.

Therapists create and update anamneses for their patients. Each patient has
one anamnese per therapist relationship.
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
from app.services import clinical_records_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/anamnese", tags=["Anamnese"])


@router.post("")
async def create_anamnese(
    body: dict,
    authorization: Optional[str] = Header(None),
):
    """Create an anamnese for a patient (therapist only)."""
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    if role != "therapist":
        raise HTTPException(status_code=403, detail="Apenas terapeutas podem criar anamneses")

    db = get_user_client(token)
    data = await clinical_records_service.create_anamnese(
        patient_id=body.get("patient_id", ""),
        therapist_id=user.id,
        data=body,
        db=db,
    )
    return success_response(data)


@router.get("")
async def list_anamneses(
    authorization: Optional[str] = Header(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List all anamneses for the current therapist (therapist only)."""
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    if role != "therapist":
        raise HTTPException(status_code=403, detail="Apenas terapeutas podem listar anamneses")

    db = get_user_client(token)
    raw = await clinical_records_service.list_anamnese_by_therapist(
        therapist_id=user.id,
        db=db,
    )
    total = len(raw)
    start = (page - 1) * page_size
    data = raw[start:start + page_size]
    return paginated_response(data, total, page, page_size)


@router.get("/paciente/{patient_id}")
async def get_anamnese_for_patient(
    patient_id: str,
    authorization: Optional[str] = Header(None),
):
    """Get anamnese for a specific patient-therapist pair.

    Anamnese is clinical intake content — therapist only per Q2 of
    `compliance-audit-reconciliation` 2026-04-22 (clinic_admin/platform_admin
    dropped from clinical content platform-wide).
    """
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    if role != "therapist":
        raise HTTPException(status_code=403, detail="Sem permissão para visualizar anamneses")

    db = get_user_client(token)
    data = await clinical_records_service.get_anamnese(
        therapist_id=user.id,
        patient_id=patient_id,
        db=db,
    )
    return success_response(data)


@router.patch("/{anamnese_id}")
async def update_anamnese(
    anamnese_id: str,
    body: dict,
    authorization: Optional[str] = Header(None),
):
    """Update an existing anamnese (therapist only)."""
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    if role != "therapist":
        raise HTTPException(status_code=403, detail="Apenas terapeutas podem editar anamneses")

    db = get_user_client(token)

    # Verify existence and ownership
    existing = first_or_none(
        db.table("anamnese")
        .select("id, therapist_id")
        .eq("id", anamnese_id)
        .execute()
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Anamnese não encontrada")
    if existing["therapist_id"] != user.id:
        raise HTTPException(status_code=403, detail="Sem permissão para editar esta anamnese")

    data = await clinical_records_service.update_anamnese(
        anamnese_id=anamnese_id,
        data=body,
        db=db,
    )
    return success_response(data)
