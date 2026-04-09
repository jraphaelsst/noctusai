"""
Patient Service — Profile management, patient listing.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException

from app.dependencies import first_or_none

logger = logging.getLogger(__name__)


async def get_patient_profile(user_id: str, db: Any) -> Dict:
    """Get a patient profile by user_id. Raises 404 if not found."""
    result = (
        db.table("patient_profiles")
        .select("*")
        .eq("user_id", user_id)
        .execute()
    )
    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=404, detail="Perfil de paciente não encontrado")
    return row


async def update_patient_profile(
    user_id: str,
    data: Dict,
    db: Any,
) -> Dict:
    """Update a patient's own profile. Returns updated row."""
    update_data = {k: v for k, v in data.items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

    result = (
        db.table("patient_profiles")
        .update(update_data)
        .eq("user_id", user_id)
        .execute()
    )
    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=404, detail="Perfil de paciente não encontrado")
    return row


async def list_patients(
    filters: Dict,
    page: int,
    page_size: int,
    db: Any,
    *,
    therapist_id: Optional[str] = None,
    clinic_id: Optional[str] = None,
) -> Tuple[List[Dict], int]:
    """List patients with role-based scoping.

    - Therapist: sees only their own patients (current_therapist_id match)
    - Clinic admin: sees patients linked to any therapist in their clinic
    - Platform admin: sees all patients

    Args:
        filters: busca, is_active
        page: page number
        page_size: items per page
        db: Supabase client
        therapist_id: if set, scope to this therapist's patients
        clinic_id: if set, scope to this clinic's patients
    """
    query = (
        db.table("patient_profiles")
        .select("*", count="exact")
    )

    # Role-based scoping
    if therapist_id:
        query = query.eq("current_therapist_id", therapist_id)
    elif clinic_id:
        query = query.eq("clinic_id", clinic_id)

    # Filters
    busca = filters.get("busca")
    if busca:
        search_pattern = f"%{busca}%"
        query = query.or_(
            f"phone.ilike.{search_pattern},"
            f"user_id.ilike.{search_pattern}"
        )

    is_active = filters.get("is_active")
    if is_active is not None:
        query = query.eq("is_active", is_active)

    query = query.order("created_at", desc=True)

    offset = (page - 1) * page_size
    result = query.range(offset, offset + page_size - 1).execute()

    return result.data or [], result.count or 0
