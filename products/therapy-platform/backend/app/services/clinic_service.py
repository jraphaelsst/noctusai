"""
Clinic Service — Profile, settings, therapist management, directory.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException
from gotrue.errors import AuthApiError

from app.dependencies import first_or_none

logger = logging.getLogger(__name__)


async def get_clinic(clinic_id: str, db: Any) -> Dict:
    """Get a clinic by ID. Raises 404 if not found."""
    result = (
        db.table("clinics")
        .select("*")
        .eq("id", clinic_id)
        .execute()
    )
    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=404, detail="Clínica não encontrada")
    return row


async def update_clinic(clinic_id: str, data: Dict, db: Any) -> Dict:
    """Update a clinic profile. Returns updated row."""
    update_data = {k: v for k, v in data.items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

    result = (
        db.table("clinics")
        .update(update_data)
        .eq("id", clinic_id)
        .execute()
    )
    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=404, detail="Clínica não encontrada")
    return row


async def list_clinics_directory(
    filters: Dict,
    page: int,
    page_size: int,
    db: Any,
) -> Tuple[List[Dict], int]:
    """List clinics for public directory.

    Only shows approved, active clinics. Supports:
    - busca: text search on name, description, tagline
    - specialty: filter by specialties_offered (array contains)
    - min_rating: minimum average rating
    - sort: relevance | highest_rated
    """
    query = (
        db.table("clinics")
        .select("*", count="exact")
        .eq("is_approved", True)
        .eq("is_active", True)
    )

    busca = filters.get("busca")
    if busca:
        search_pattern = f"%{busca}%"
        query = query.or_(
            f"name.ilike.{search_pattern},"
            f"description.ilike.{search_pattern},"
            f"tagline.ilike.{search_pattern}"
        )

    specialty = filters.get("specialty")
    if specialty:
        query = query.contains("specialties_offered", [specialty])

    sort = filters.get("sort", "relevance")
    if sort == "highest_rated":
        query = query.order("created_at", desc=True)  # TODO: order by avg_rating when materialized
    else:
        query = query.order("created_at", desc=True)

    offset = (page - 1) * page_size
    result = query.range(offset, offset + page_size - 1).execute()

    data = result.data or []
    total = result.count or 0

    # Post-filter min_rating
    min_rating = filters.get("min_rating")
    if min_rating is not None:
        data = [c for c in data if (c.get("avg_rating") or 0) >= min_rating]

    return data, total


async def get_clinic_with_stats(clinic_id: str, db: Any) -> Dict:
    """Get clinic profile enriched with therapist count and rating stats."""
    clinic = await get_clinic(clinic_id, db)

    # Therapist count
    therapists_result = (
        db.table("therapist_profiles")
        .select("user_id", count="exact")
        .eq("clinic_id", clinic_id)
        .eq("is_active", True)
        .execute()
    )
    clinic["therapist_count"] = therapists_result.count or 0

    # Clinic reviews
    reviews_result = (
        db.table("clinic_reviews")
        .select("star_rating")
        .eq("clinic_id", clinic_id)
        .execute()
    )
    reviews = reviews_result.data or []
    review_count = len(reviews)
    avg_rating = (
        sum(r["star_rating"] for r in reviews) / review_count
        if review_count > 0
        else None
    )
    clinic["avg_rating"] = round(avg_rating, 2) if avg_rating else None
    clinic["review_count"] = review_count

    return clinic


async def invite_therapist(
    clinic_id: str,
    email: str,
    nome: str,
    db: Any,
    admin_db: Any,
) -> Dict:
    """Invite a therapist to join the clinic.

    Creates a Supabase auth user + therapist_profiles row linked to this clinic.
    The therapist still needs admin approval to appear in the directory.
    """
    # Check clinic exists
    await get_clinic(clinic_id, db)

    # Check if email is already in use
    try:
        user_resp = admin_db.auth.admin.create_user({
            "email": email,
            "password": None,  # Will need to set password via invite email
            "email_confirm": False,
            "user_metadata": {
                "role": "therapist",
                "nome": nome,
                "clinic_id": clinic_id,
            },
        })
    except AuthApiError as e:
        if "already" in str(e).lower():
            raise HTTPException(status_code=409, detail="Email já cadastrado no sistema")
        raise HTTPException(status_code=400, detail=f"Erro ao convidar terapeuta: {e}")

    user = user_resp.user
    user_id = user.id

    # Create therapist profile linked to clinic
    admin_db.table("therapist_profiles").insert({
        "user_id": user_id,
        "clinic_id": clinic_id,
        "crp": "",  # To be filled by therapist
        "is_approved": False,
        "is_active": True,
    }).execute()

    # Create therapist settings
    admin_db.table("therapist_settings").insert({
        "therapist_id": user_id,
        "session_duration_minutes": 50,
    }).execute()

    # Create wallet
    admin_db.table("wallets").insert({
        "owner_type": "therapist",
        "owner_id": user_id,
        "balance": 0,
    }).execute()

    logger.info(
        "Therapist invited: user_id=%s clinic_id=%s email=%s",
        user_id, clinic_id, email,
    )
    return {
        "user_id": user_id,
        "email": email,
        "nome": nome,
        "clinic_id": clinic_id,
    }


async def list_clinic_therapists(clinic_id: str, db: Any) -> List[Dict]:
    """List all therapists affiliated with a clinic."""
    result = (
        db.table("therapist_profiles")
        .select("*")
        .eq("clinic_id", clinic_id)
        .order("created_at", desc=True)
        .execute()
    )
    return result.data or []


async def update_therapist_config(
    clinic_id: str,
    therapist_id: str,
    data: Dict,
    db: Any,
) -> Dict:
    """Update per-therapist configuration within a clinic.

    Manages pricing_policy, commission overrides, and clinic-set price
    in the clinic_therapist_configs table.
    """
    # Verify therapist belongs to clinic
    therapist_result = (
        db.table("therapist_profiles")
        .select("user_id")
        .eq("user_id", therapist_id)
        .eq("clinic_id", clinic_id)
        .execute()
    )
    if not therapist_result.data:
        raise HTTPException(
            status_code=404,
            detail="Terapeuta não encontrado nesta clínica",
        )

    update_data = {k: v for k, v in data.items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

    # Upsert config
    config_data = {
        "clinic_id": clinic_id,
        "therapist_id": therapist_id,
        **update_data,
    }
    result = (
        db.table("clinic_therapist_configs")
        .upsert(config_data, on_conflict="clinic_id,therapist_id")
        .execute()
    )
    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=500, detail="Erro ao atualizar configuração")
    return row


async def get_therapist_config(
    clinic_id: str,
    therapist_id: str,
    db: Any,
) -> Dict:
    """Get per-therapist configuration within a clinic."""
    result = (
        db.table("clinic_therapist_configs")
        .select("*")
        .eq("clinic_id", clinic_id)
        .eq("therapist_id", therapist_id)
        .execute()
    )
    row = first_or_none(result)
    if not row:
        # Return defaults
        return {
            "clinic_id": clinic_id,
            "therapist_id": therapist_id,
            "pricing_policy": "therapist_sets",
            "commission_override_clinic_sourced": None,
            "commission_override_therapist_sourced": None,
            "clinic_set_default_price": None,
        }
    return row


async def get_clinic_settings(clinic_id: str, db: Any) -> Dict:
    """Get clinic financial and notification settings."""
    result = (
        db.table("clinic_settings")
        .select("*")
        .eq("clinic_id", clinic_id)
        .execute()
    )
    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=404, detail="Configurações da clínica não encontradas")
    return row


async def update_clinic_settings(clinic_id: str, data: Dict, db: Any) -> Dict:
    """Update clinic financial and notification settings."""
    update_data = {k: v for k, v in data.items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

    result = (
        db.table("clinic_settings")
        .update(update_data)
        .eq("clinic_id", clinic_id)
        .execute()
    )
    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=404, detail="Configurações da clínica não encontradas")
    return row
