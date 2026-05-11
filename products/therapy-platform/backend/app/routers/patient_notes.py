"""
Patient Notes Router — Strictly private patient session notes.

Only patients can create, view, and edit their own notes. Therapists
and clinic admins have no access to patient notes.
"""
import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request

from app.dependencies import (
    first_or_none,
    get_admin_client,
    get_current_user,
    get_user_client,
    get_user_role,
)
from app.rate_limit import limiter
from app.responses import success_response
from app.schemas.session import PatientNoteCreate, PatientNoteUpdate
from app.services import ai_pipeline

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/patient-notes", tags=["Patient Notes"])


@router.post("")
@limiter.limit("30/minute")
async def create_patient_note(
    request: Request,
    body: PatientNoteCreate,
    background_tasks: BackgroundTasks,
    authorization: Optional[str] = Header(None),
):
    """Create a private session note (patient only).

    Triggers patient longitudinal regeneration in the background.
    """
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    if role != "patient":
        raise HTTPException(status_code=403, detail="Apenas pacientes podem criar anotações pessoais")

    db = get_user_client(token)

    # Verify session record exists and patient is involved
    sr = (
        db.table("session_records")
        .select("id, patient_id, therapist_id")
        .eq("id", body.session_record_id)
        .execute()
    )
    record = first_or_none(sr)
    if not record:
        raise HTTPException(status_code=404, detail="Registro de sessão não encontrado")
    if record["patient_id"] != user.id:
        raise HTTPException(status_code=403, detail="Sem permissão para este registro de sessão")

    # Create note
    note_data = {
        "session_record_id": body.session_record_id,
        "patient_id": user.id,
        "note_text": body.note_text,
    }
    result = db.table("patient_session_notes").insert(note_data).execute()
    note = first_or_none(result)
    if not note:
        raise HTTPException(status_code=500, detail="Erro ao criar anotação")

    # Trigger patient longitudinal regeneration in background
    admin_db = get_admin_client()
    background_tasks.add_task(
        ai_pipeline.on_patient_note_change,
        session_record_id=body.session_record_id,
        patient_id=user.id,
        therapist_id=record["therapist_id"],
        db=admin_db,
    )

    return success_response(note)


@router.get("/session/{session_record_id}")
async def get_patient_notes(
    session_record_id: str,
    authorization: Optional[str] = Header(None),
):
    """Get patient's notes for a session. Patient sees own notes only."""
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    if role != "patient":
        raise HTTPException(status_code=403, detail="Apenas pacientes podem acessar anotações pessoais")

    db = get_user_client(token)

    result = (
        db.table("patient_session_notes")
        .select("*")
        .eq("session_record_id", session_record_id)
        .eq("patient_id", user.id)
        .order("created_at")
        .execute()
    )
    return success_response(result.data or [])


@router.patch("/{note_id}")
@limiter.limit("30/minute")
async def update_patient_note(
    request: Request,
    note_id: str,
    body: PatientNoteUpdate,
    background_tasks: BackgroundTasks,
    authorization: Optional[str] = Header(None),
):
    """Update a patient note. Triggers patient longitudinal regeneration."""
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    if role != "patient":
        raise HTTPException(status_code=403, detail="Apenas pacientes podem editar anotações pessoais")

    db = get_user_client(token)

    # Verify ownership
    existing = (
        db.table("patient_session_notes")
        .select("*")
        .eq("id", note_id)
        .eq("patient_id", user.id)
        .execute()
    )
    note = first_or_none(existing)
    if not note:
        raise HTTPException(status_code=404, detail="Anotação não encontrada")

    # Update
    result = (
        db.table("patient_session_notes")
        .update({"note_text": body.note_text})
        .eq("id", note_id)
        .execute()
    )
    updated = first_or_none(result)

    # Fetch therapist_id for longitudinal regeneration
    sr = (
        db.table("session_records")
        .select("therapist_id")
        .eq("id", note["session_record_id"])
        .execute()
    )
    record = first_or_none(sr)
    therapist_id = record["therapist_id"] if record else None

    if therapist_id:
        admin_db = get_admin_client()
        background_tasks.add_task(
            ai_pipeline.on_patient_note_change,
            session_record_id=note["session_record_id"],
            patient_id=user.id,
            therapist_id=therapist_id,
            db=admin_db,
        )

    return success_response(updated or {**note, "note_text": body.note_text})
