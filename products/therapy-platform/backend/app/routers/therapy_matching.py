"""
Therapy Matching Router — AI-powered therapist-patient matching.

Uses embeddings to match patients with compatible therapists based on
specialties, approaches, preferences, and availability.
"""
import logging
from typing import Literal, Optional

from fastapi import APIRouter, Body, Header, HTTPException, Query, Request
from pydantic import BaseModel

from app.dependencies import (
    get_current_user,
    get_user_client,
    get_user_role,
)
from app.rate_limit import limiter
from app.responses import success_response
from app.services import matching_service, therapy_embedding_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/matching", tags=["Therapy Matching"])


class EmbedProfileBody(BaseModel):
    """Body for the unified ``POST /api/matching/embed`` endpoint.

    ``role`` is optional — when omitted the endpoint infers it from the
    caller's auth role. Explicit ``role`` is required only for admin
    invocations that act on behalf of another role (e.g. platform_admin
    re-embedding a therapist profile).
    """

    role: Optional[Literal["terapeuta", "paciente"]] = None


@router.post("/embed")
@limiter.limit("30/minute")
async def embed_profile(
    request: Request,
    body: EmbedProfileBody = Body(default_factory=EmbedProfileBody),
    authorization: Optional[str] = Header(None),
):
    """Generate an embedding for the caller's matching profile (unified).

    Unified endpoint that replaces ``/embed-terapeuta`` + ``/embed-paciente``.
    The split routes remain registered for backwards compatibility and are
    documented as deprecated (see §7.c of the therapy-platform-wiring
    project). New consumers MUST call ``POST /api/matching/embed``.

    Resolution:
      * ``role="terapeuta"`` → embed therapist profile (role must be one of
        ``therapist``, ``clinic_admin``, ``platform_admin``).
      * ``role="paciente"``  → embed patient profile (role must be one of
        ``patient``, ``clinic_admin``, ``platform_admin``).
      * ``role`` omitted     → infer from caller's auth role
        (``therapist`` → terapeuta, ``patient`` → paciente; admins MUST
        send an explicit ``role``).
    """
    user, token = await get_current_user(authorization)
    caller_role = get_user_role(user)

    target = body.role
    if target is None:
        if caller_role == "therapist":
            target = "terapeuta"
        elif caller_role == "patient":
            target = "paciente"
        else:
            raise HTTPException(
                status_code=400,
                detail="Admins devem informar 'role' no corpo da requisição",
            )

    db = get_user_client(token)
    if target == "terapeuta":
        if caller_role not in ("therapist", "clinic_admin", "platform_admin"):
            raise HTTPException(
                status_code=403,
                detail="Sem permissão para gerar embedding de terapeuta",
            )
        data = await therapy_embedding_service.embed_therapist(
            therapist_id=user.id,
            db=db,
        )
    else:  # target == "paciente"
        if caller_role not in ("patient", "clinic_admin", "platform_admin"):
            raise HTTPException(
                status_code=403,
                detail="Sem permissão para gerar embedding de paciente",
            )
        data = await therapy_embedding_service.embed_patient(
            patient_id=user.id,
            db=db,
        )
    return success_response(data)


@router.post("/embed-terapeuta", deprecated=True)
@limiter.limit("30/minute")
async def embed_therapist_profile(
    request: Request,
    authorization: Optional[str] = Header(None),
):
    """Deprecated — use ``POST /api/matching/embed`` with ``{"role":"terapeuta"}``.

    Kept registered for backwards compatibility with existing therapist
    onboarding flows; new consumers MUST use the unified ``/embed`` route.
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


@router.post("/embed-paciente", deprecated=True)
@limiter.limit("30/minute")
async def embed_patient_profile(
    request: Request,
    authorization: Optional[str] = Header(None),
):
    """Deprecated — use ``POST /api/matching/embed`` with ``{"role":"paciente"}``.

    Kept registered for backwards compatibility with existing patient
    onboarding flows; new consumers MUST use the unified ``/embed`` route.
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
