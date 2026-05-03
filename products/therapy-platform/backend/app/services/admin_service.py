"""
Admin Service — Approvals, commission overrides, patient assignments.

All operations require platform_admin role, enforced at the router level.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Tuple

from fastapi import HTTPException

from app.dependencies import first_or_none
from noctusai_lib.integrations.supabase_identity import (
    UserIdentity,
    fetch_user_identities,
)

logger = logging.getLogger(__name__)


async def approve_entity(
    entity_type: str,
    entity_id: str,
    admin_id: str,
    db: Any,
) -> Dict:
    """Approve a therapist or clinic.

    Sets is_approved=True on the corresponding table.
    """
    if entity_type == "therapist":
        table = "therapist_profiles"
        id_col = "user_id"
    elif entity_type == "clinic":
        table = "clinics"
        id_col = "id"
    else:
        raise HTTPException(status_code=400, detail="Tipo de entidade inválido. Use 'therapist' ou 'clinic'")

    # Verify entity exists
    check = db.table(table).select(id_col).eq(id_col, entity_id).execute()
    if not check.data:
        raise HTTPException(status_code=404, detail=f"{entity_type.capitalize()} não encontrado(a)")

    result = (
        db.table(table)
        .update({"is_approved": True})
        .eq(id_col, entity_id)
        .execute()
    )
    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=500, detail="Erro ao aprovar entidade")

    logger.info(
        "Entity approved: type=%s id=%s by_admin=%s",
        entity_type, entity_id, admin_id,
    )
    return row


async def reject_entity(
    entity_type: str,
    entity_id: str,
    admin_id: str,
    reason: str,
    db: Any,
) -> Dict:
    """Reject a therapist or clinic with a reason.

    Sets is_approved=False and stores the rejection reason.
    """
    if entity_type == "therapist":
        table = "therapist_profiles"
        id_col = "user_id"
    elif entity_type == "clinic":
        table = "clinics"
        id_col = "id"
    else:
        raise HTTPException(status_code=400, detail="Tipo de entidade inválido. Use 'therapist' ou 'clinic'")

    # Verify entity exists
    check = db.table(table).select(id_col).eq(id_col, entity_id).execute()
    if not check.data:
        raise HTTPException(status_code=404, detail=f"{entity_type.capitalize()} não encontrado(a)")

    result = (
        db.table(table)
        .update({
            "is_approved": False,
            "rejection_reason": reason,
        })
        .eq(id_col, entity_id)
        .execute()
    )
    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=500, detail="Erro ao rejeitar entidade")

    logger.info(
        "Entity rejected: type=%s id=%s by_admin=%s reason=%s",
        entity_type, entity_id, admin_id, reason,
    )
    return row


async def list_pending_approvals(db: Any) -> Dict:
    """List all pending (unapproved) therapists and clinics."""
    therapists = (
        db.table("therapist_profiles")
        .select("*")
        .eq("is_approved", False)
        .eq("is_active", True)
        .order("created_at", desc=True)
        .execute()
    )

    clinics = (
        db.table("clinics")
        .select("*")
        .eq("is_approved", False)
        .eq("is_active", True)
        .order("created_at", desc=True)
        .execute()
    )

    return {
        "therapists": therapists.data or [],
        "clinics": clinics.data or [],
        "total": len(therapists.data or []) + len(clinics.data or []),
    }


async def set_commission_override(
    target_type: str,
    target_id: str,
    custom_commission_pct: float,
    admin_id: str,
    db: Any,
) -> Dict:
    """Set a platform-level commission override for a clinic or therapist.

    Stored in the commission_overrides table.
    """
    if target_type not in ("clinic", "therapist"):
        raise HTTPException(status_code=400, detail="Tipo deve ser 'clinic' ou 'therapist'")

    override_data = {
        "target_type": target_type,
        "target_id": target_id,
        "custom_commission_pct": custom_commission_pct,
        "set_by": admin_id,
    }
    result = (
        db.table("commission_overrides")
        .upsert(override_data, on_conflict="target_type,target_id")
        .execute()
    )
    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=500, detail="Erro ao definir comissão")

    logger.info(
        "Commission override set: type=%s id=%s pct=%s by_admin=%s",
        target_type, target_id, custom_commission_pct, admin_id,
    )
    return row


async def assign_patient(
    patient_id: str,
    therapist_id: str | None,
    clinic_id: str | None,
    custom_price: float | None,
    admin_id: str,
    db: Any,
) -> Dict:
    """Admin-assign a patient to a therapist and/or clinic."""
    # Verify patient exists
    patient_check = (
        db.table("patient_profiles")
        .select("user_id")
        .eq("user_id", patient_id)
        .execute()
    )
    if not patient_check.data:
        raise HTTPException(status_code=404, detail="Paciente não encontrado")

    update_data: Dict[str, Any] = {}
    if therapist_id is not None:
        # Verify therapist exists
        t_check = (
            db.table("therapist_profiles")
            .select("user_id")
            .eq("user_id", therapist_id)
            .execute()
        )
        if not t_check.data:
            raise HTTPException(status_code=404, detail="Terapeuta não encontrado")
        update_data["current_therapist_id"] = therapist_id

    if clinic_id is not None:
        # Verify clinic exists
        c_check = db.table("clinics").select("id").eq("id", clinic_id).execute()
        if not c_check.data:
            raise HTTPException(status_code=404, detail="Clínica não encontrada")
        update_data["clinic_id"] = clinic_id

    if not update_data:
        raise HTTPException(status_code=400, detail="Informe therapist_id e/ou clinic_id")

    result = (
        db.table("patient_profiles")
        .update(update_data)
        .eq("user_id", patient_id)
        .execute()
    )
    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=500, detail="Erro ao atribuir paciente")

    # If custom price, store in a patient pricing config
    if custom_price is not None and therapist_id:
        db.table("patient_pricing").upsert({
            "patient_id": patient_id,
            "therapist_id": therapist_id,
            "custom_price": custom_price,
            "set_by": admin_id,
        }, on_conflict="patient_id,therapist_id").execute()

    logger.info(
        "Patient assigned: patient=%s therapist=%s clinic=%s by_admin=%s",
        patient_id, therapist_id, clinic_id, admin_id,
    )
    return row


# ---------------------------------------------------------------------------
# Admin therapist listing (DTO-shaped for the admin UI)
# ---------------------------------------------------------------------------

_VALID_THERAPIST_STATUSES = {"pendente", "aprovado", "rejeitado", "suspenso"}


def _derive_therapist_status(row: Dict[str, Any]) -> str:
    if not row.get("is_active", True):
        return "suspenso"
    if row.get("is_approved"):
        return "aprovado"
    if row.get("rejection_reason"):
        return "rejeitado"
    return "pendente"


def _therapist_row_to_dto(row: Dict[str, Any], identity: UserIdentity) -> Dict[str, Any]:
    """Map a `therapist_profiles` row + resolved auth identity → admin DTO.

    The frontend `Terapeuta` type (in `frontend/src/types/`) expects
    Portuguese-named fields. Avatar `foto_url` falls back to the
    profile's `photo_url` column when the auth-side `user_metadata.foto_url`
    is missing — keeps existing avatars rendering.
    """
    return {
        "id": row.get("user_id"),
        "user_id": row.get("user_id"),
        "nome": identity.nome,
        "email": identity.email,
        "crp": row.get("crp") or "",
        "bio": row.get("bio"),
        "foto_url": identity.foto_url or row.get("photo_url"),
        "especialidades": row.get("specialties") or [],
        "abordagens": row.get("approaches") or [],
        "valor_sessao": row.get("default_session_price"),
        "duracao_sessao": row.get("session_duration_minutes"),
        "status": _derive_therapist_status(row),
        "nota_media": row.get("avg_rating"),
        "total_avaliacoes": row.get("review_count"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


async def list_therapists_for_admin(
    db: Any,
    page: int,
    page_size: int,
    status: str | None = None,
) -> Tuple[List[Dict[str, Any]], int]:
    """List therapists for the admin console, shaped as the frontend ``Terapeuta`` DTO.

    Returns ``(data, total)``. ``status`` filters by derived lifecycle state
    (``pendente`` | ``aprovado`` | ``rejeitado`` | ``suspenso``).
    """
    query = (
        db.table("therapist_profiles")
        .select("*", count="exact")
        .order("created_at", desc=True)
    )

    if status and status in _VALID_THERAPIST_STATUSES:
        if status == "aprovado":
            query = query.eq("is_approved", True).eq("is_active", True)
        elif status == "pendente":
            query = query.eq("is_approved", False).eq("is_active", True)
        elif status == "suspenso":
            query = query.eq("is_active", False)
        elif status == "rejeitado":
            # Rejected state is captured in ``rejection_reason``, but that column is
            # not yet migrated into ``therapist_profiles``. Return nothing until the
            # reject flow is wired up end-to-end.
            return [], 0

    offset = (page - 1) * page_size
    result = query.range(offset, offset + page_size - 1).execute()
    rows = result.data or []
    total = result.count or 0

    user_ids = [row.get("user_id") for row in rows if row.get("user_id")]
    identities = fetch_user_identities(db, user_ids)

    dtos: List[Dict[str, Any]] = []
    for row in rows:
        uid = row.get("user_id") or ""
        identity = identities.get(uid, UserIdentity(user_id=uid))
        dtos.append(_therapist_row_to_dto(row, identity))
    return dtos, total
