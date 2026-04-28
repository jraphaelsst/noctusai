"""
Longitudinal Router — AI-generated longitudinal analyses across sessions.

Clinical longitudinal: therapist/clinic_admin sees progress over time.
Personal longitudinal ("Minha Jornada"): patient's own perspective.
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
from app.responses import success_response

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/longitudinal", tags=["Longitudinal"])


# ---------------------------------------------------------------------------
# Clinical Longitudinal (therapist / clinic_admin)
# ---------------------------------------------------------------------------

@router.get("/clinical/{patient_id}")
async def get_clinical_longitudinal(
    patient_id: str,
    authorization: Optional[str] = Header(None),
    include_versions: bool = Query(False),
):
    """Get the latest clinical longitudinal analysis for a patient.

    Therapist only (clinical content — Q2 of `compliance-audit-reconciliation`
    2026-04-22 dropped clinic_admin/platform_admin from clinical-longitudinal
    access at both router + RLS layer). Optionally includes version history.
    """
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    if role != "therapist":
        raise HTTPException(
            status_code=403,
            detail="Apenas o terapeuta responsável pode acessar análises clínicas longitudinais",
        )

    db = get_user_client(token)

    # For therapists: only show analyses where they are the therapist
    query = (
        db.table("clinical_longitudinal_analyses")
        .select("*")
        .eq("patient_id", patient_id)
    )
    if role == "therapist":
        query = query.eq("therapist_id", user.id)

    query = query.order("version_number", desc=True)
    result = query.execute()

    latest = first_or_none(result)
    if not latest:
        raise HTTPException(
            status_code=404,
            detail="Nenhuma análise longitudinal encontrada para este paciente",
        )

    response: dict = {"analysis": latest}

    if include_versions:
        response["versions"] = result.data or []

    return success_response(response)


@router.get("/clinical/{patient_id}/versions")
async def list_clinical_longitudinal_versions(
    patient_id: str,
    authorization: Optional[str] = Header(None),
):
    """List all clinical longitudinal versions for a patient.

    Therapist only (clinical content — Q2 of `compliance-audit-reconciliation`
    2026-04-22 dropped clinic_admin/platform_admin).
    """
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    if role != "therapist":
        raise HTTPException(
            status_code=403,
            detail="Apenas o terapeuta responsável pode acessar análises clínicas longitudinais",
        )

    db = get_user_client(token)

    query = (
        db.table("clinical_longitudinal_analyses")
        .select("*")
        .eq("patient_id", patient_id)
    )
    if role == "therapist":
        query = query.eq("therapist_id", user.id)

    result = query.order("version_number", desc=True).execute()
    return success_response(result.data or [])


# ---------------------------------------------------------------------------
# Personal Longitudinal ("Minha Jornada" — patient only)
# ---------------------------------------------------------------------------

@router.get("/personal")
async def get_personal_longitudinal(
    authorization: Optional[str] = Header(None),
    therapist_id: Optional[str] = Query(
        None,
        description="Filtrar por terapeuta. Se omitido, retorna a mais recente.",
    ),
):
    """Get the patient's personal longitudinal analysis ("Minha Jornada").

    Patient only. Shows their own journey and reflections.
    """
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    if role != "patient":
        raise HTTPException(
            status_code=403,
            detail="Apenas pacientes podem acessar sua jornada pessoal",
        )

    db = get_user_client(token)

    query = (
        db.table("patient_longitudinal_analyses")
        .select("*")
        .eq("patient_id", user.id)
    )
    if therapist_id:
        query = query.eq("therapist_id", therapist_id)

    result = query.order("version_number", desc=True).execute()
    latest = first_or_none(result)

    if not latest:
        raise HTTPException(
            status_code=404,
            detail="Nenhuma análise de jornada encontrada. "
            "A análise é gerada automaticamente após as primeiras sessões.",
        )

    return success_response(latest)


@router.get("/personal/versions")
async def list_personal_longitudinal_versions(
    authorization: Optional[str] = Header(None),
    therapist_id: Optional[str] = Query(None),
):
    """List all personal longitudinal versions (patient only).

    Allows the patient to review the evolution of their journey analysis.
    """
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    if role != "patient":
        raise HTTPException(
            status_code=403,
            detail="Apenas pacientes podem acessar versões de sua jornada pessoal",
        )

    db = get_user_client(token)

    query = (
        db.table("patient_longitudinal_analyses")
        .select("*")
        .eq("patient_id", user.id)
    )
    if therapist_id:
        query = query.eq("therapist_id", therapist_id)

    result = query.order("version_number", desc=True).execute()
    return success_response(result.data or [])
