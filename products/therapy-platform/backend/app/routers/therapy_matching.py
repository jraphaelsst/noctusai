"""
Therapy Matching Router — AI-powered therapist-patient matching.

Uses embeddings to match patients with compatible therapists based on
specialties, approaches, preferences, and availability.
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
from app.services import matching_service, therapy_embedding_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/matching", tags=["Therapy Matching"])


@router.post("/embed-terapeuta")
async def embed_therapist_profile(
    authorization: Optional[str] = Header(None),
):
    """Generate embedding for the current therapist's profile.

    Accessible by therapists (own profile) and admins.
    """
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    if role not in ("therapist", "clinic_admin", "platform_admin"):
        raise HTTPException(status_code=403, detail="Sem permissão para gerar embedding de terapeuta")

    db = get_user_client(token)
    therapist_id = user.id if role == "therapist" else None

    data = await therapy_embedding_service.embed_therapist(
        therapist_id=therapist_id or user.id,
        db=db,
    )
    return success_response(data)


@router.post("/embed-paciente")
async def embed_patient_profile(
    authorization: Optional[str] = Header(None),
):
    """Generate embedding for the current patient's profile.

    Accessible by patients (own profile) and admins.
    """
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    if role not in ("patient", "clinic_admin", "platform_admin"):
        raise HTTPException(status_code=403, detail="Sem permissão para gerar embedding de paciente")

    db = get_user_client(token)
    patient_id = user.id if role == "patient" else None

    data = await therapy_embedding_service.embed_patient(
        patient_id=patient_id or user.id,
        db=db,
    )
    return success_response(data)


@router.get("/buscar/{patient_id}")
async def find_matching_therapists(
    patient_id: str,
    authorization: Optional[str] = Header(None),
    limit: int = Query(10, ge=1, le=50),
):
    """Find therapists matching a patient's profile.

    Accessible by the patient themselves or admins.
    """
    user, token = await get_current_user(authorization)
    role = get_user_role(user)

    # Patient can only search for themselves
    if role == "patient" and user.id != patient_id:
        raise HTTPException(status_code=403, detail="Sem permissão para buscar matching de outro paciente")
    if role not in ("patient", "clinic_admin", "platform_admin"):
        raise HTTPException(status_code=403, detail="Sem permissão para buscar matching")

    db = get_user_client(token)
    data = await matching_service.find_matches(
        patient_id=patient_id,
        limit=limit,
        db=db,
    )
    return success_response(data)


@router.get("/sugestoes")
async def get_match_suggestions(
    authorization: Optional[str] = Header(None),
):
    """Get match suggestions for the current patient."""
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    if role != "patient":
        raise HTTPException(status_code=403, detail="Apenas pacientes podem ver sugestões de matching")

    db = get_user_client(token)
    data = await matching_service.find_matches(
        patient_id=user.id,
        db=db,
    )
    return success_response(data)
