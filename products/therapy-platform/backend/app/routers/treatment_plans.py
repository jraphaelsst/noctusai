"""
Treatment Plans Router — Therapeutic treatment plans with goals.

Therapists create and manage treatment plans for their patients.
Each plan can have multiple goals (metas) that track progress.
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
from app.responses import ok_response, paginated_response, success_response
from app.services import clinical_records_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/planos-tratamento", tags=["Treatment Plans"])


@router.post("")
async def create_treatment_plan(
    body: dict,
    authorization: Optional[str] = Header(None),
):
    """Create a treatment plan for a patient (therapist only)."""
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    if role != "therapist":
        raise HTTPException(status_code=403, detail="Apenas terapeutas podem criar planos de tratamento")

    db = get_user_client(token)
    data = await clinical_records_service.create_treatment_plan(
        patient_id=body.get("patient_id", ""),
        therapist_id=user.id,
        data=body,
        db=db,
    )
    return success_response(data)


@router.get("/paciente/{patient_id}")
async def list_plans_for_patient(
    patient_id: str,
    authorization: Optional[str] = Header(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List treatment plans for a specific patient."""
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    if role not in ("therapist", "patient", "clinic_admin", "platform_admin"):
        raise HTTPException(status_code=403, detail="Sem permissão")

    db = get_user_client(token)
    raw = await clinical_records_service.list_treatment_plans(
        patient_id=patient_id,
        db=db,
    )
    total = len(raw)
    start = (page - 1) * page_size
    data = raw[start:start + page_size]
    return paginated_response(data, total, page, page_size)


@router.get("/{plan_id}")
async def get_treatment_plan(
    plan_id: str,
    authorization: Optional[str] = Header(None),
):
    """Get a treatment plan with its goals."""
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    db = get_user_client(token)

    existing = first_or_none(
        db.table("treatment_plans").select("*").eq("id", plan_id).execute()
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Plano de tratamento não encontrado")
    if role == "therapist" and existing.get("therapist_id") != user.id:
        raise HTTPException(status_code=403, detail="Sem permissão para visualizar este plano")
    data = existing
    return success_response(data)


@router.patch("/{plan_id}")
async def update_treatment_plan(
    plan_id: str,
    body: dict,
    authorization: Optional[str] = Header(None),
):
    """Update a treatment plan (therapist only)."""
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    if role != "therapist":
        raise HTTPException(status_code=403, detail="Apenas terapeutas podem editar planos de tratamento")

    db = get_user_client(token)

    # Verify existence and ownership
    existing = first_or_none(
        db.table("treatment_plans")
        .select("id, therapist_id")
        .eq("id", plan_id)
        .execute()
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Plano de tratamento não encontrado")
    if existing["therapist_id"] != user.id:
        raise HTTPException(status_code=403, detail="Sem permissão para editar este plano")

    data = await clinical_records_service.update_treatment_plan(
        plan_id=plan_id,
        data=body,
        db=db,
    )
    return success_response(data)


@router.post("/{plan_id}/metas")
async def add_goal(
    plan_id: str,
    body: dict,
    authorization: Optional[str] = Header(None),
):
    """Add a goal (meta) to a treatment plan (therapist only)."""
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    if role != "therapist":
        raise HTTPException(status_code=403, detail="Apenas terapeutas podem adicionar metas")

    db = get_user_client(token)

    # Verify plan exists and belongs to therapist
    existing = first_or_none(
        db.table("treatment_plans")
        .select("id, therapist_id")
        .eq("id", plan_id)
        .execute()
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Plano de tratamento não encontrado")
    if existing["therapist_id"] != user.id:
        raise HTTPException(status_code=403, detail="Sem permissão para este plano")

    data = await clinical_records_service.create_goal(
        plan_id=plan_id,
        data=body,
        db=db,
    )
    return success_response(data)


@router.patch("/metas/{goal_id}")
async def update_goal(
    goal_id: str,
    body: dict,
    authorization: Optional[str] = Header(None),
):
    """Update a goal (therapist only)."""
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    if role != "therapist":
        raise HTTPException(status_code=403, detail="Apenas terapeutas podem editar metas")

    db = get_user_client(token)

    # Verify goal exists and belongs to therapist's plan
    existing = first_or_none(
        db.table("treatment_plan_goals")
        .select("id, treatment_plan_id")
        .eq("id", goal_id)
        .execute()
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Meta não encontrada")

    plan = first_or_none(
        db.table("treatment_plans")
        .select("therapist_id")
        .eq("id", existing["treatment_plan_id"])
        .execute()
    )
    if not plan or plan["therapist_id"] != user.id:
        raise HTTPException(status_code=403, detail="Sem permissão para editar esta meta")

    data = await clinical_records_service.update_goal(
        goal_id=goal_id,
        data=body,
        db=db,
    )
    return success_response(data)


@router.delete("/metas/{goal_id}")
async def delete_goal(
    goal_id: str,
    authorization: Optional[str] = Header(None),
):
    """Delete a goal (therapist only)."""
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    if role != "therapist":
        raise HTTPException(status_code=403, detail="Apenas terapeutas podem excluir metas")

    db = get_user_client(token)

    # Verify goal exists and belongs to therapist's plan
    existing = first_or_none(
        db.table("treatment_plan_goals")
        .select("id, treatment_plan_id")
        .eq("id", goal_id)
        .execute()
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Meta não encontrada")

    plan = first_or_none(
        db.table("treatment_plans")
        .select("therapist_id")
        .eq("id", existing["treatment_plan_id"])
        .execute()
    )
    if not plan or plan["therapist_id"] != user.id:
        raise HTTPException(status_code=403, detail="Sem permissão para excluir esta meta")

    await clinical_records_service.delete_goal(goal_id=goal_id, db=db)
    return ok_response("Meta excluída com sucesso")
