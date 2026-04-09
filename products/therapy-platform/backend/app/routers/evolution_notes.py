"""
Evolution Notes Router — Session evolution notes (notas de evolução).

Therapists record structured evolution notes after each session,
tracking patient progress over time.
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
router = APIRouter(prefix="/api/evolucao", tags=["Evolution Notes"])


@router.post("")
async def create_evolution_note(
    body: dict,
    authorization: Optional[str] = Header(None),
):
    """Create an evolution note for a patient (therapist only)."""
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    if role != "therapist":
        raise HTTPException(status_code=403, detail="Apenas terapeutas podem criar notas de evolução")

    db = get_user_client(token)
    data = await clinical_records_service.create_evolution_note(
        patient_id=body.get("patient_id", ""),
        therapist_id=user.id,
        data=body,
        db=db,
    )
    return success_response(data)


@router.get("/paciente/{patient_id}")
async def list_evolution_notes(
    patient_id: str,
    authorization: Optional[str] = Header(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List evolution notes for a patient (paginated)."""
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    if role not in ("therapist", "clinic_admin", "platform_admin"):
        raise HTTPException(status_code=403, detail="Sem permissão para visualizar notas de evolução")

    db = get_user_client(token)
    data, total = await clinical_records_service.list_evolution_notes(
        patient_id=patient_id,
        therapist_id=user.id,
        db=db,
        page=page,
        page_size=page_size,
    )
    return paginated_response(data, total, page, page_size)


@router.get("/{note_id}")
async def get_evolution_note(
    note_id: str,
    authorization: Optional[str] = Header(None),
):
    """Get a single evolution note."""
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    db = get_user_client(token)

    existing = first_or_none(
        db.table("evolution_notes")
        .select("*")
        .eq("id", note_id)
        .execute()
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Nota de evolução não encontrada")

    # Authorization: therapist must own, admin can view all
    if role == "therapist" and existing["therapist_id"] != user.id:
        raise HTTPException(status_code=403, detail="Sem permissão para visualizar esta nota")

    return success_response(existing)


@router.patch("/{note_id}")
async def update_evolution_note(
    note_id: str,
    body: dict,
    authorization: Optional[str] = Header(None),
):
    """Update an evolution note (therapist only)."""
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    if role != "therapist":
        raise HTTPException(status_code=403, detail="Apenas terapeutas podem editar notas de evolução")

    db = get_user_client(token)

    # Verify existence and ownership
    existing = first_or_none(
        db.table("evolution_notes")
        .select("id, therapist_id")
        .eq("id", note_id)
        .execute()
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Nota de evolução não encontrada")
    if existing["therapist_id"] != user.id:
        raise HTTPException(status_code=403, detail="Sem permissão para editar esta nota")

    data = await clinical_records_service.update_evolution_note(
        note_id=note_id,
        data=body,
        db=db,
    )
    return success_response(data)
