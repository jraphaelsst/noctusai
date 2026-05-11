"""
Therapist Service — Profile management, directory listing, stats.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException

from app.dependencies import first_or_none

logger = logging.getLogger(__name__)


async def get_therapist_profile(user_id: str, db: Any) -> Dict:
    """Get a therapist profile by user_id.

    Raises 404 if not found.
    """
    result = (
        db.table("therapist_profiles")
        .select("*")
        .eq("user_id", user_id)
        .execute()
    )
    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=404, detail="Perfil de terapeuta não encontrado")
    return row


async def update_therapist_profile(
    user_id: str,
    data: Dict,
    db: Any,
) -> Dict:
    """Update a therapist's own profile. Returns updated row."""
    # Filter out None values
    update_data = {k: v for k, v in data.items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

    # Handle session_duration_minutes → therapist_settings table
    duration = update_data.pop("session_duration_minutes", None)
    if duration is not None:
        db.table("therapist_settings").update(
            {"session_duration_minutes": duration}
        ).eq("therapist_id", user_id).execute()

    # Update main profile fields
    if update_data:
        result = (
            db.table("therapist_profiles")
            .update(update_data)
            .eq("user_id", user_id)
            .execute()
        )
        row = first_or_none(result)
        if not row:
            raise HTTPException(status_code=404, detail="Perfil de terapeuta não encontrado")
        return row

    # If only duration was updated, fetch the profile
    return await get_therapist_profile(user_id, db)


async def list_therapists_directory(
    filters: Dict,
    page: int,
    page_size: int,
    db: Any,
) -> Tuple[List[Dict], int]:
    """List therapists for public directory with filters.

    Only shows approved, active therapists. Supports:
    - busca: text search on bio, specialties
    - specialty: filter by specialty (array contains)
    - approach: filter by approach (array contains)
    - min_price / max_price: price range filter
    - min_rating: minimum average rating filter
    - clinic_id: filter by affiliated clinic
    - sort: relevance | highest_rated | most_reviewed | lowest_price

    Returns (data, total_count).
    """
    query = (
        db.table("therapist_profiles")
        .select("*", count="exact")
        .eq("is_approved", True)
        .eq("is_active", True)
    )

    # Apply filters
    busca = filters.get("busca")
    if busca:
        search_pattern = f"%{busca}%"
        query = query.or_(
            f"bio.ilike.{search_pattern},"
            f"crp.ilike.{search_pattern}"
        )

    specialty = filters.get("specialty")
    if specialty:
        query = query.contains("specialties", [specialty])

    approach = filters.get("approach")
    if approach:
        query = query.contains("approaches", [approach])

    min_price = filters.get("min_price")
    if min_price is not None:
        query = query.gte("default_session_price", min_price)

    max_price = filters.get("max_price")
    if max_price is not None:
        query = query.lte("default_session_price", max_price)

    clinic_id = filters.get("clinic_id")
    if clinic_id:
        query = query.eq("clinic_id", clinic_id)

    # Sort
    sort = filters.get("sort", "relevance")
    if sort == "lowest_price":
        query = query.order("default_session_price", desc=False)
    elif sort == "highest_rated":
        query = query.order("avg_rating", desc=True)
    elif sort == "most_reviewed":
        query = query.order("review_count", desc=True)
    else:
        query = query.order("created_at", desc=True)

    # Pagination
    offset = (page - 1) * page_size
    result = query.range(offset, offset + page_size - 1).execute()

    data = result.data or []
    total = result.count or 0

    # Post-filter min_rating if the column exists
    min_rating = filters.get("min_rating")
    if min_rating is not None:
        data = [t for t in data if (t.get("avg_rating") or 0) >= min_rating]

    return data, total


async def get_therapist_with_stats(user_id: str, db: Any) -> Dict:
    """Get therapist profile enriched with rating stats.

    Fetches profile + computes avg_rating and review_count from reviews table.
    """
    profile = await get_therapist_profile(user_id, db)

    # Fetch rating stats
    reviews_result = (
        db.table("reviews")
        .select("star_rating")
        .eq("therapist_id", user_id)
        .execute()
    )
    reviews = reviews_result.data or []
    review_count = len(reviews)
    avg_rating = (
        sum(r["star_rating"] for r in reviews) / review_count
        if review_count > 0
        else None
    )

    profile["avg_rating"] = round(avg_rating, 2) if avg_rating else None
    profile["review_count"] = review_count

    # Fetch settings for session_duration_minutes
    settings_result = (
        db.table("therapist_settings")
        .select("session_duration_minutes")
        .eq("therapist_id", user_id)
        .execute()
    )
    settings_row = first_or_none(settings_result)
    if settings_row:
        profile["session_duration_minutes"] = settings_row.get("session_duration_minutes", 50)

    return profile
