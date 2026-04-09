"""
Patients Router — Patient listing, profile detail, profile update.
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
from app.schemas.patient import PatientProfileUpdate
from app.services import patient_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/patients", tags=["Patients"])


@router.get("")
async def list_patients(
    authorization: Optional[str] = Header(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    busca: Optional[str] = Query(None),
):
    """List patients with role-based scoping.

    - Therapist: sees their own patients
    - Clinic admin: sees clinic patients
    - Platform admin: sees all patients
    - Patient: forbidden
    """
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    db = get_user_client(token)

    filters = {"busca": busca}

    if role == "therapist":
        data, total = await patient_service.list_patients(
            filters=filters,
            page=page,
            page_size=page_size,
            db=db,
            therapist_id=user.id,
        )
    elif role == "clinic_admin":
        clinic_id = get_clinic_id_for_user(user)
        if not clinic_id:
            raise HTTPException(status_code=400, detail="Clínica não configurada")
        data, total = await patient_service.list_patients(
            filters=filters,
            page=page,
            page_size=page_size,
            db=db,
            clinic_id=clinic_id,
        )
    elif role == "platform_admin":
        admin_db = get_admin_client()
        data, total = await patient_service.list_patients(
            filters=filters,
            page=page,
            page_size=page_size,
            db=admin_db,
        )
    else:
        raise HTTPException(status_code=403, detail="Acesso negado")

    return paginated_response(data, total, page, page_size)


@router.get("/{patient_id}")
async def get_patient(
    patient_id: str,
    authorization: Optional[str] = Header(None),
):
    """Get patient profile detail.

    Accessible by: the patient themselves, their therapist, their clinic admin, platform admin.
    """
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    db = get_user_client(token)

    profile = await patient_service.get_patient_profile(patient_id, db)

    # Access control
    if role == "patient" and user.id != patient_id:
        raise HTTPException(status_code=403, detail="Acesso negado")
    elif role == "therapist" and profile.get("current_therapist_id") != user.id:
        raise HTTPException(status_code=403, detail="Acesso negado")
    elif role == "clinic_admin":
        clinic_id = get_clinic_id_for_user(user)
        if profile.get("clinic_id") != clinic_id:
            raise HTTPException(status_code=403, detail="Acesso negado")
    # platform_admin has full access

    return success_response(profile)


@router.patch("/{patient_id}")
async def update_patient(
    patient_id: str,
    body: PatientProfileUpdate,
    authorization: Optional[str] = Header(None),
):
    """Update own patient profile. Only the patient themselves can update."""
    user, token = await get_current_user(authorization)
    role = get_user_role(user)

    if role != "patient" or user.id != patient_id:
        raise HTTPException(
            status_code=403,
            detail="Você só pode editar seu próprio perfil",
        )

    db = get_user_client(token)
    result = await patient_service.update_patient_profile(
        user_id=patient_id,
        data=body.model_dump(exclude_unset=True),
        db=db,
    )
    return success_response(result)
