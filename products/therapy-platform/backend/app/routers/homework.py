"""
Homework Router — Therapist-assigned tasks for patients.

Therapists assign homework to patients. Patients submit responses.
Therapists review submissions.
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
from app.services import homework_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/homework", tags=["Homework"])


@router.post("")
async def assign_homework(
    body: dict,
    authorization: Optional[str] = Header(None),
):
    """Assign homework to a patient (therapist only)."""
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    if role != "therapist":
        raise HTTPException(status_code=403, detail="Apenas terapeutas podem atribuir tarefas")

    db = get_user_client(token)
    data = await homework_service.assign(
        therapist_id=user.id,
        data=body,
        db=db,
    )
    return success_response(data)


@router.get("")
async def list_homework(
    authorization: Optional[str] = Header(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None),
):
    """List homework assignments.

    - Therapist: sees homework they assigned
    - Patient: sees homework assigned to them
    """
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    db = get_user_client(token)

    if role == "therapist":
        raw = await homework_service.list_for_therapist(
            therapist_id=user.id, db=db, status_filter=status,
        )
    else:
        raw = await homework_service.list_for_patient(
            patient_id=user.id, db=db, status_filter=status,
        )
    total = len(raw)
    start = (page - 1) * page_size
    data = raw[start:start + page_size]
    return paginated_response(data, total, page, page_size)


@router.get("/{homework_id}")
async def get_homework(
    homework_id: str,
    authorization: Optional[str] = Header(None),
):
    """Get a single homework assignment."""
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    db = get_user_client(token)

    existing = first_or_none(
        db.table("homework_assignments")
        .select("*")
        .eq("id", homework_id)
        .execute()
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")

    # Authorization: must be the therapist or the patient
    if role == "therapist" and existing["therapist_id"] != user.id:
        raise HTTPException(status_code=403, detail="Sem permissão para visualizar esta tarefa")
    if role == "patient" and existing["patient_id"] != user.id:
        raise HTTPException(status_code=403, detail="Sem permissão para visualizar esta tarefa")

    return success_response(existing)


@router.post("/{homework_id}/submit")
async def submit_homework(
    homework_id: str,
    body: dict,
    authorization: Optional[str] = Header(None),
):
    """Patient submits a response to a homework assignment."""
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    if role != "patient":
        raise HTTPException(status_code=403, detail="Apenas pacientes podem enviar respostas de tarefas")

    db = get_user_client(token)

    # Verify existence and that patient is the assignee
    existing = first_or_none(
        db.table("homework_assignments")
        .select("id, patient_id")
        .eq("id", homework_id)
        .execute()
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")
    if existing["patient_id"] != user.id:
        raise HTTPException(status_code=403, detail="Sem permissão para responder esta tarefa")

    data = await homework_service.submit(
        assignment_id=homework_id,
        data=body,
        db=db,
    )
    return success_response(data)


@router.post("/{homework_id}/review")
async def review_homework(
    homework_id: str,
    body: dict,
    authorization: Optional[str] = Header(None),
):
    """Therapist reviews a homework submission."""
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    if role != "therapist":
        raise HTTPException(status_code=403, detail="Apenas terapeutas podem revisar tarefas")

    db = get_user_client(token)

    # Verify existence and that therapist is the assigner
    existing = first_or_none(
        db.table("homework_assignments")
        .select("id, therapist_id")
        .eq("id", homework_id)
        .execute()
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")
    if existing["therapist_id"] != user.id:
        raise HTTPException(status_code=403, detail="Sem permissão para revisar esta tarefa")

    data = await homework_service.review(
        assignment_id=homework_id,
        data=body,
        db=db,
    )
    return success_response(data)
