"""
Review Service — Therapist reviews, clinic reviews, responses, flags, rating stats.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Tuple

from fastapi import HTTPException

from noctusai_lib.integrations.supabase_identity import (
    UserIdentity,
    fetch_user_identities,
)

from app.dependencies import first_or_none
from app.services._bulk import bulk_lookup

logger = logging.getLogger(__name__)


async def create_review(
    patient_id: str,
    data: Dict,
    db: Any,
) -> Dict:
    """Create a therapist review.

    Validates that the patient has at least one completed session with the therapist.
    """
    therapist_id = data["therapist_id"]

    # Verify patient has completed session with therapist
    session_check = (
        db.table("appointments")
        .select("id")
        .eq("patient_id", patient_id)
        .eq("therapist_id", therapist_id)
        .eq("status", "completed")
        .limit(1)
        .execute()
    )
    if not session_check.data:
        raise HTTPException(
            status_code=403,
            detail="Você precisa ter pelo menos uma sessão concluída com este terapeuta para avaliá-lo",
        )

    # Check for existing review
    existing = (
        db.table("reviews")
        .select("id")
        .eq("patient_id", patient_id)
        .eq("therapist_id", therapist_id)
        .execute()
    )
    if existing.data:
        raise HTTPException(
            status_code=409,
            detail="Você já avaliou este terapeuta. Use a edição para alterar.",
        )

    review_data = {
        "patient_id": patient_id,
        "therapist_id": therapist_id,
        "star_rating": data["star_rating"],
        "review_text": data.get("review_text"),
        "tags": data.get("tags", []),
    }
    result = db.table("reviews").insert(review_data).execute()
    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=500, detail="Erro ao criar avaliação")

    logger.info(
        "Review created: patient=%s therapist=%s rating=%s",
        patient_id, therapist_id, data["star_rating"],
    )
    return row


async def update_review(
    review_id: str,
    patient_id: str,
    data: Dict,
    db: Any,
) -> Dict:
    """Update an existing review. Only the review author can update."""
    update_data = {k: v for k, v in data.items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

    result = (
        db.table("reviews")
        .update(update_data)
        .eq("id", review_id)
        .eq("patient_id", patient_id)
        .execute()
    )
    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=404, detail="Avaliação não encontrada")
    return row


async def list_therapist_reviews(
    therapist_id: str,
    page: int,
    page_size: int,
    db: Any,
) -> Tuple[List[Dict], int]:
    """List reviews for a therapist, newest first."""
    query = (
        db.table("reviews")
        .select("*", count="exact")
        .eq("therapist_id", therapist_id)
        .order("created_at", desc=True)
    )
    offset = (page - 1) * page_size
    result = query.range(offset, offset + page_size - 1).execute()
    return result.data or [], result.count or 0


async def create_clinic_review(
    patient_id: str,
    data: Dict,
    db: Any,
) -> Dict:
    """Create a clinic review.

    Validates that the patient has a completed session with a therapist from this clinic.
    """
    clinic_id = data["clinic_id"]

    # Find therapists in this clinic
    therapists_result = (
        db.table("therapist_profiles")
        .select("user_id")
        .eq("clinic_id", clinic_id)
        .execute()
    )
    therapist_ids = [t["user_id"] for t in (therapists_result.data or [])]

    if not therapist_ids:
        raise HTTPException(
            status_code=403,
            detail="Esta clínica não possui terapeutas cadastrados",
        )

    # Check if patient has completed session with any clinic therapist
    session_check = (
        db.table("appointments")
        .select("id")
        .eq("patient_id", patient_id)
        .in_("therapist_id", therapist_ids)
        .eq("status", "completed")
        .limit(1)
        .execute()
    )
    if not session_check.data:
        raise HTTPException(
            status_code=403,
            detail="Você precisa ter pelo menos uma sessão concluída com um terapeuta desta clínica para avaliá-la",
        )

    # Check for existing review
    existing = (
        db.table("clinic_reviews")
        .select("id")
        .eq("patient_id", patient_id)
        .eq("clinic_id", clinic_id)
        .execute()
    )
    if existing.data:
        raise HTTPException(
            status_code=409,
            detail="Você já avaliou esta clínica. Use a edição para alterar.",
        )

    review_data = {
        "patient_id": patient_id,
        "clinic_id": clinic_id,
        "star_rating": data["star_rating"],
        "review_text": data.get("review_text"),
        "tags": data.get("tags", []),
    }
    result = db.table("clinic_reviews").insert(review_data).execute()
    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=500, detail="Erro ao criar avaliação")

    logger.info(
        "Clinic review created: patient=%s clinic=%s rating=%s",
        patient_id, clinic_id, data["star_rating"],
    )
    return row


async def list_clinic_reviews(
    clinic_id: str,
    page: int,
    page_size: int,
    db: Any,
) -> Tuple[List[Dict], int]:
    """List reviews for a clinic, newest first."""
    query = (
        db.table("clinic_reviews")
        .select("*", count="exact")
        .eq("clinic_id", clinic_id)
        .order("created_at", desc=True)
    )
    offset = (page - 1) * page_size
    result = query.range(offset, offset + page_size - 1).execute()
    return result.data or [], result.count or 0


async def create_review_response(
    review_id: str,
    responder_id: str,
    response_text: str,
    db: Any,
) -> Dict:
    """Therapist responds to a review on their profile.

    Validates that the review belongs to the therapist.
    """
    # Verify the review exists and belongs to this therapist
    review = (
        db.table("reviews")
        .select("id, therapist_id")
        .eq("id", review_id)
        .execute()
    )
    review_row = first_or_none(review)
    if not review_row:
        raise HTTPException(status_code=404, detail="Avaliação não encontrada")

    if review_row["therapist_id"] != responder_id:
        raise HTTPException(
            status_code=403,
            detail="Você só pode responder avaliações do seu próprio perfil",
        )

    # Update the review with the response
    result = (
        db.table("reviews")
        .update({
            "therapist_response": response_text,
        })
        .eq("id", review_id)
        .execute()
    )
    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=500, detail="Erro ao salvar resposta")

    logger.info("Review response created: review=%s therapist=%s", review_id, responder_id)
    return row


async def flag_review(
    review_id: str,
    flagged_by: str,
    reason: str,
    db: Any,
) -> Dict:
    """Flag a review for moderation.

    Therapists can flag reviews on their profiles.
    Clinic admins can flag clinic reviews.
    """
    # Try therapist reviews first (canonical table: `reviews`).
    review = (
        db.table("reviews")
        .select("id")
        .eq("id", review_id)
        .execute()
    )
    table_name = "reviews"

    if not review.data:
        # Try clinic_reviews
        review = (
            db.table("clinic_reviews")
            .select("id")
            .eq("id", review_id)
            .execute()
        )
        table_name = "clinic_reviews"

    if not review.data:
        raise HTTPException(status_code=404, detail="Avaliação não encontrada")

    result = (
        db.table(table_name)
        .update({
            "is_flagged": True,
            "flag_reason": reason,
            "flagged_by": flagged_by,
        })
        .eq("id", review_id)
        .execute()
    )
    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=500, detail="Erro ao sinalizar avaliação")

    logger.info("Review flagged: review=%s by=%s reason=%s", review_id, flagged_by, reason)
    return row


async def get_therapist_rating_stats(therapist_id: str, db: Any) -> Dict:
    """Get avg rating and review count for a therapist."""
    result = (
        db.table("reviews")
        .select("star_rating")
        .eq("therapist_id", therapist_id)
        .execute()
    )
    reviews = result.data or []
    count = len(reviews)
    avg = sum(r["star_rating"] for r in reviews) / count if count > 0 else None
    return {
        "therapist_id": therapist_id,
        "avg_rating": round(avg, 2) if avg else None,
        "review_count": count,
    }


async def get_clinic_rating_stats(clinic_id: str, db: Any) -> Dict:
    """Get avg rating, review count, and therapist aggregate avg for a clinic."""
    # Direct clinic reviews
    clinic_result = (
        db.table("clinic_reviews")
        .select("star_rating")
        .eq("clinic_id", clinic_id)
        .execute()
    )
    clinic_reviews = clinic_result.data or []
    clinic_count = len(clinic_reviews)
    clinic_avg = (
        sum(r["star_rating"] for r in clinic_reviews) / clinic_count
        if clinic_count > 0
        else None
    )

    # Therapist aggregate avg (average of all therapist avg ratings in this clinic)
    therapists_result = (
        db.table("therapist_profiles")
        .select("user_id")
        .eq("clinic_id", clinic_id)
        .eq("is_active", True)
        .execute()
    )
    therapist_ids = [t["user_id"] for t in (therapists_result.data or [])]

    therapist_avg = None
    if therapist_ids:
        all_reviews = (
            db.table("reviews")
            .select("star_rating")
            .in_("therapist_id", therapist_ids)
            .execute()
        )
        t_reviews = all_reviews.data or []
        if t_reviews:
            therapist_avg = round(
                sum(r["star_rating"] for r in t_reviews) / len(t_reviews), 2
            )

    return {
        "clinic_id": clinic_id,
        "clinic_avg_rating": round(clinic_avg, 2) if clinic_avg else None,
        "clinic_review_count": clinic_count,
        "therapist_aggregate_avg": therapist_avg,
    }


async def list_patient_reviews(
    patient_id: str,
    db: Any,
    admin_db: Any,
) -> Dict[str, List[Dict]]:
    """List a patient's reviews + pending review CTAs.

    Returns a `{"data": [...], "pending": [...]}` shape consumed by
    ``usePatientReviews`` (see `frontend/src/hooks/usePatientReviews.ts`).

    `data` is the union of the patient's therapist-reviews and clinic-reviews,
    each enriched with `entity_name` + `entity_type` for direct rendering on
    the patient portal. Field renames (`star_rating` → `nota`,
    `review_text` → `comentario`) match the page's render contract.

    `pending` is the set of `completed` appointments without a corresponding
    therapist review, surfaced as a CTA on the patient portal Reviews tab.

    Args:
        patient_id: Owning patient user id.
        db: User-scoped Supabase client (RLS-respecting).
        admin_db: Admin-scoped Supabase client for `auth.users` identity
            lookups via :func:`fetch_user_identities`.
    """
    # ----- Patient's therapist reviews ------------------------------------
    therapist_reviews_q = (
        db.table("reviews")
        .select("*")
        .eq("patient_id", patient_id)
        .order("created_at", desc=True)
        .execute()
    )
    therapist_rows = therapist_reviews_q.data or []
    reviewed_therapist_ids = {r["therapist_id"] for r in therapist_rows if r.get("therapist_id")}

    # ----- Patient's clinic reviews ---------------------------------------
    clinic_reviews_q = (
        db.table("clinic_reviews")
        .select("*")
        .eq("patient_id", patient_id)
        .order("created_at", desc=True)
        .execute()
    )
    clinic_rows = clinic_reviews_q.data or []

    # ----- Bulk identity + clinic-name resolution -------------------------
    therapist_ids_for_lookup = [r["therapist_id"] for r in therapist_rows if r.get("therapist_id")]
    identities = fetch_user_identities(admin_db, therapist_ids_for_lookup) if therapist_ids_for_lookup else {}

    clinic_ids_for_lookup = [r["clinic_id"] for r in clinic_rows if r.get("clinic_id")]
    clinic_name_map: Dict[str, str] = {}
    if clinic_ids_for_lookup:
        raw_map = bulk_lookup(db, "clinics", clinic_ids_for_lookup, value_cols="name")
        clinic_name_map = {k: (v or "") for k, v in raw_map.items()}

    # ----- Shape the union list -------------------------------------------
    out: List[Dict] = []
    for r in therapist_rows:
        tid = r.get("therapist_id") or ""
        identity = identities.get(tid, UserIdentity(user_id=tid))
        out.append({
            "id": r.get("id"),
            "nota": r.get("star_rating"),
            "comentario": r.get("review_text"),
            "entity_name": identity.display_name,
            "entity_type": "therapist",
            "created_at": r.get("created_at"),
            "updated_at": r.get("updated_at") or r.get("created_at"),
        })
    for r in clinic_rows:
        cid = r.get("clinic_id") or ""
        out.append({
            "id": r.get("id"),
            "nota": r.get("star_rating"),
            "comentario": r.get("review_text"),
            "entity_name": clinic_name_map.get(cid, ""),
            "entity_type": "clinic",
            "created_at": r.get("created_at"),
            "updated_at": r.get("updated_at") or r.get("created_at"),
        })
    # Newest-first across both flavors (rows already individually ordered).
    out.sort(key=lambda x: x.get("created_at") or "", reverse=True)

    # ----- Pending: completed appointments lacking a therapist review -----
    appts_q = (
        db.table("appointments")
        .select("id, therapist_id, scheduled_at, status")
        .eq("patient_id", patient_id)
        .eq("status", "completed")
        .order("scheduled_at", desc=True)
        .execute()
    )
    appt_rows = appts_q.data or []

    pending_therapist_ids = [
        a["therapist_id"]
        for a in appt_rows
        if a.get("therapist_id") and a["therapist_id"] not in reviewed_therapist_ids
    ]
    pending_identities = (
        fetch_user_identities(admin_db, pending_therapist_ids) if pending_therapist_ids else {}
    )

    pending: List[Dict] = []
    seen_pending_therapists: set[str] = set()
    for appt in appt_rows:
        tid = appt.get("therapist_id") or ""
        if not tid or tid in reviewed_therapist_ids or tid in seen_pending_therapists:
            continue
        seen_pending_therapists.add(tid)
        identity = pending_identities.get(tid, UserIdentity(user_id=tid))
        pending.append({
            "appointment_id": appt.get("id"),
            "therapist_name": identity.display_name,
            "session_date": appt.get("scheduled_at"),
        })

    return {"data": out, "pending": pending}


async def delete_review(
    review_id: str,
    patient_id: str,
    db: Any,
) -> Dict:
    """Patient deletes one of their own reviews.

    Looks across `reviews` and `clinic_reviews` so the same endpoint serves
    both flavors (mirrors `flag_review` table-fallback). Patient ownership is
    enforced by filtering both the row id and `patient_id`. Returns the
    deleted row (or raises 404 if not found / not owned).
    """
    # Try therapist-reviews table first.
    target_table = "reviews"
    existing = (
        db.table("reviews")
        .select("id, patient_id")
        .eq("id", review_id)
        .eq("patient_id", patient_id)
        .execute()
    )
    if not existing.data:
        target_table = "clinic_reviews"
        existing = (
            db.table("clinic_reviews")
            .select("id, patient_id")
            .eq("id", review_id)
            .eq("patient_id", patient_id)
            .execute()
        )

    if not existing.data:
        raise HTTPException(status_code=404, detail="Avaliação não encontrada")

    result = (
        db.table(target_table)
        .delete()
        .eq("id", review_id)
        .eq("patient_id", patient_id)
        .execute()
    )
    row = first_or_none(result) or {"id": review_id, "patient_id": patient_id}
    logger.info("Review deleted: review=%s patient=%s table=%s", review_id, patient_id, target_table)
    return row
