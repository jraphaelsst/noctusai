"""
Clinical Records Service — Anamnese, treatment plans, goals, evolution notes.

Manages structured clinical documentation for therapist-patient relationships.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException

from app.dependencies import first_or_none
from app.responses import calculate_pagination

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Anamnese
# ---------------------------------------------------------------------------

async def create_anamnese(
    patient_id: str,
    therapist_id: str,
    data: Dict,
    db: Any,
) -> Dict:
    """Create an anamnesis record. One per patient-therapist pair."""
    # Check uniqueness
    existing = (
        db.table("anamnese")
        .select("id")
        .eq("patient_id", patient_id)
        .eq("therapist_id", therapist_id)
        .execute()
    )
    if existing.data:
        raise HTTPException(
            status_code=409,
            detail="Anamnese já existe para este par paciente-terapeuta",
        )

    record = {
        "patient_id": patient_id,
        "therapist_id": therapist_id,
        "queixa_principal": data["queixa_principal"],
        "historia_pregressa": data.get("historia_pregressa"),
        "historico_familiar": data.get("historico_familiar"),
        "medicacoes": data.get("medicacoes"),
        "observacoes": data.get("observacoes"),
    }
    result = db.table("anamnese").insert(record).execute()
    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=500, detail="Erro ao criar anamnese")
    logger.info("Anamnese created for patient %s by therapist %s", patient_id, therapist_id)
    return row


async def update_anamnese(
    anamnese_id: str,
    data: Dict,
    db: Any,
) -> Dict:
    """Update an existing anamnesis record."""
    check = db.table("anamnese").select("id").eq("id", anamnese_id).execute()
    if not check.data:
        raise HTTPException(status_code=404, detail="Anamnese não encontrada")

    update_fields = {k: v for k, v in data.items() if v is not None}
    if not update_fields:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

    result = db.table("anamnese").update(update_fields).eq("id", anamnese_id).execute()
    return first_or_none(result) or {}


async def get_anamnese(
    patient_id: str,
    therapist_id: str,
    db: Any,
) -> Optional[Dict]:
    """Get anamnesis for a specific patient-therapist pair."""
    result = (
        db.table("anamnese")
        .select("*")
        .eq("patient_id", patient_id)
        .eq("therapist_id", therapist_id)
        .execute()
    )
    return first_or_none(result)


async def list_anamnese_by_therapist(
    therapist_id: str,
    db: Any,
) -> List[Dict]:
    """List all anamneses created by a therapist (all patients)."""
    result = (
        db.table("anamnese")
        .select("*")
        .eq("therapist_id", therapist_id)
        .order("created_at", desc=True)
        .execute()
    )
    return result.data or []


# ---------------------------------------------------------------------------
# Treatment Plans
# ---------------------------------------------------------------------------

async def create_treatment_plan(
    patient_id: str,
    therapist_id: str,
    data: Dict,
    db: Any,
) -> Dict:
    """Create a treatment plan for a patient."""
    record = {
        "patient_id": patient_id,
        "therapist_id": therapist_id,
        "titulo": data["titulo"],
        "descricao": data.get("descricao"),
        "data_inicio": data["data_inicio"],
        "data_revisao": data.get("data_revisao"),
        "status": "ativo",
    }
    result = db.table("treatment_plans").insert(record).execute()
    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=500, detail="Erro ao criar plano de tratamento")
    logger.info("Treatment plan created for patient %s", patient_id)
    return row


async def update_treatment_plan(
    plan_id: str,
    data: Dict,
    db: Any,
) -> Dict:
    """Update a treatment plan."""
    check = db.table("treatment_plans").select("id").eq("id", plan_id).execute()
    if not check.data:
        raise HTTPException(status_code=404, detail="Plano de tratamento não encontrado")

    update_fields = {k: v for k, v in data.items() if v is not None}
    if not update_fields:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

    result = db.table("treatment_plans").update(update_fields).eq("id", plan_id).execute()
    return first_or_none(result) or {}


async def list_treatment_plans(
    patient_id: str,
    db: Any,
) -> List[Dict]:
    """List all treatment plans for a patient."""
    result = (
        db.table("treatment_plans")
        .select("*")
        .eq("patient_id", patient_id)
        .order("created_at", desc=True)
        .execute()
    )
    return result.data or []


# ---------------------------------------------------------------------------
# Goals
# ---------------------------------------------------------------------------

async def create_goal(
    plan_id: str,
    data: Dict,
    db: Any,
) -> Dict:
    """Create a goal within a treatment plan."""
    # Verify plan exists
    check = db.table("treatment_plans").select("id").eq("id", plan_id).execute()
    if not check.data:
        raise HTTPException(status_code=404, detail="Plano de tratamento não encontrado")

    record = {
        "treatment_plan_id": plan_id,
        "descricao": data["descricao"],
        "prazo": data.get("prazo"),
        "status": "pendente",
    }
    result = db.table("treatment_plan_goals").insert(record).execute()
    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=500, detail="Erro ao criar meta")
    logger.info("Goal created for plan %s", plan_id)
    return row


async def update_goal(
    goal_id: str,
    data: Dict,
    db: Any,
) -> Dict:
    """Update a goal."""
    check = db.table("treatment_plan_goals").select("id").eq("id", goal_id).execute()
    if not check.data:
        raise HTTPException(status_code=404, detail="Meta não encontrada")

    update_fields = {k: v for k, v in data.items() if v is not None}
    if not update_fields:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

    result = db.table("treatment_plan_goals").update(update_fields).eq("id", goal_id).execute()
    return first_or_none(result) or {}


async def delete_goal(
    goal_id: str,
    db: Any,
) -> None:
    """Delete a goal."""
    check = db.table("treatment_plan_goals").select("id").eq("id", goal_id).execute()
    if not check.data:
        raise HTTPException(status_code=404, detail="Meta não encontrada")

    db.table("treatment_plan_goals").delete().eq("id", goal_id).execute()
    logger.info("Goal %s deleted", goal_id)


# ---------------------------------------------------------------------------
# Evolution Notes
# ---------------------------------------------------------------------------

async def create_evolution_note(
    patient_id: str,
    therapist_id: str,
    data: Dict,
    db: Any,
) -> Dict:
    """Create an evolution note (SOAP or free-form)."""
    record = {
        "patient_id": patient_id,
        "therapist_id": therapist_id,
        "appointment_id": data.get("appointment_id"),
        "formato": data["formato"],
        "subjetivo": data.get("subjetivo"),
        "objetivo": data.get("objetivo"),
        "avaliacao": data.get("avaliacao"),
        "plano": data.get("plano"),
        "conteudo_livre": data.get("conteudo_livre"),
    }
    result = db.table("evolution_notes").insert(record).execute()
    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=500, detail="Erro ao criar nota de evolução")
    logger.info("Evolution note created for patient %s by therapist %s", patient_id, therapist_id)
    return row


async def update_evolution_note(
    note_id: str,
    data: Dict,
    db: Any,
) -> Dict:
    """Update an evolution note."""
    check = db.table("evolution_notes").select("id").eq("id", note_id).execute()
    if not check.data:
        raise HTTPException(status_code=404, detail="Nota de evolução não encontrada")

    update_fields = {k: v for k, v in data.items() if v is not None}
    if not update_fields:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

    result = db.table("evolution_notes").update(update_fields).eq("id", note_id).execute()
    return first_or_none(result) or {}


async def list_evolution_notes(
    patient_id: str,
    therapist_id: str,
    db: Any,
    page: int = 1,
    page_size: int = 20,
) -> Tuple[List[Dict], int]:
    """List evolution notes for a patient-therapist pair, paginated."""
    page, page_size, offset = calculate_pagination(page, page_size)

    result = (
        db.table("evolution_notes")
        .select("*", count="exact")
        .eq("patient_id", patient_id)
        .eq("therapist_id", therapist_id)
        .order("created_at", desc=True)
        .range(offset, offset + page_size - 1)
        .execute()
    )
    return result.data or [], result.count or 0
