"""
Homework Service — Assignment, submission, and review workflow.

Workflow: therapist assigns → patient submits → therapist reviews.
Status transitions: pendente → em_andamento → concluido → revisado.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from app.dependencies import first_or_none

logger = logging.getLogger(__name__)


async def assign(
    therapist_id: str,
    data: Dict,
    db: Any,
) -> Dict:
    """Therapist assigns homework to a patient."""
    record = {
        "therapist_id": therapist_id,
        "patient_id": str(data["patient_id"]),
        "titulo": data["titulo"],
        "descricao": data["descricao"],
        "data_limite": data.get("data_limite"),
        "status": "pendente",
    }
    result = db.table("homework_assignments").insert(record).execute()
    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=500, detail="Erro ao criar tarefa")
    logger.info(
        "Homework assigned by therapist %s to patient %s",
        therapist_id,
        data["patient_id"],
    )
    return row


async def submit(
    assignment_id: str,
    data: Dict,
    db: Any,
) -> Dict:
    """Patient submits their homework response."""
    check = (
        db.table("homework_assignments")
        .select("id, status")
        .eq("id", assignment_id)
        .execute()
    )
    assignment = first_or_none(check)
    if not assignment:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")

    if assignment["status"] == "revisado":
        raise HTTPException(status_code=400, detail="Tarefa já foi revisada")

    update_data = {
        "resposta_paciente": data["resposta_paciente"],
        "status": "concluido",
    }
    result = (
        db.table("homework_assignments")
        .update(update_data)
        .eq("id", assignment_id)
        .execute()
    )
    row = first_or_none(result)
    logger.info("Homework %s submitted by patient", assignment_id)
    return row or {**assignment, **update_data}


async def review(
    assignment_id: str,
    data: Dict,
    db: Any,
) -> Dict:
    """Therapist reviews submitted homework."""
    check = (
        db.table("homework_assignments")
        .select("id, status")
        .eq("id", assignment_id)
        .execute()
    )
    assignment = first_or_none(check)
    if not assignment:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")

    if assignment["status"] not in ("concluido", "em_andamento"):
        raise HTTPException(
            status_code=400,
            detail="Tarefa precisa estar concluída ou em andamento para ser revisada",
        )

    update_data = {
        "feedback_terapeuta": data["feedback_terapeuta"],
        "status": "revisado",
    }
    result = (
        db.table("homework_assignments")
        .update(update_data)
        .eq("id", assignment_id)
        .execute()
    )
    row = first_or_none(result)
    logger.info("Homework %s reviewed by therapist", assignment_id)
    return row or {**assignment, **update_data}


async def list_for_patient(
    patient_id: str,
    db: Any,
    status_filter: Optional[str] = None,
) -> List[Dict]:
    """List homework assignments for a patient, optionally filtered by status."""
    query = (
        db.table("homework_assignments")
        .select("*")
        .eq("patient_id", patient_id)
    )
    if status_filter:
        query = query.eq("status", status_filter)

    result = query.order("created_at", desc=True).execute()
    return result.data or []


async def list_for_therapist(
    therapist_id: str,
    db: Any,
    status_filter: Optional[str] = None,
) -> List[Dict]:
    """List homework assignments created by a therapist, optionally filtered by status."""
    query = (
        db.table("homework_assignments")
        .select("*")
        .eq("therapist_id", therapist_id)
    )
    if status_filter:
        query = query.eq("status", status_filter)

    result = query.order("created_at", desc=True).execute()
    return result.data or []
