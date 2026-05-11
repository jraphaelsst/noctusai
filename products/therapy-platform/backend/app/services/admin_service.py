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


# ---------------------------------------------------------------------------
# Admin appointment listing (DTO-shaped for the admin Appointments page)
# ---------------------------------------------------------------------------


def _resolve_clinic_names(db: Any, clinic_ids: List[str]) -> Dict[str, str]:
    """Bulk-resolve clinic names. Returns ``{clinic_id: name}``.

    Empty list returns empty dict. Mirrors
    :func:`noctusai_lib.integrations.supabase_identity.fetch_user_identities`
    in shape but reads from the product-owned ``clinics`` table — clinic
    names live in our schema, not in ``auth.users``.
    """
    if not clinic_ids:
        return {}
    unique_ids = list({cid for cid in clinic_ids if cid})
    if not unique_ids:
        return {}
    result = (
        db.table("clinics")
        .select("id, name")
        .in_("id", unique_ids)
        .execute()
    )
    rows = result.data or []
    return {row["id"]: (row.get("name") or "") for row in rows if row.get("id")}


def _appointment_row_to_dto(
    row: Dict[str, Any],
    identities: Dict[str, UserIdentity],
    clinic_names: Dict[str, str],
) -> Dict[str, Any]:
    """Map an ``appointments`` row → admin DTO with resolved names.

    The frontend ``AdminAppointment`` interface
    (``pages/admin/Appointments.tsx``) reads ``patient_name``,
    ``therapist_name``, ``clinic_name``, ``scheduled_start``,
    ``scheduled_end``, ``status`` — those are the load-bearing fields.
    """
    patient_id = row.get("patient_id") or ""
    therapist_id = row.get("therapist_id") or ""
    clinic_id = row.get("clinic_id") or ""

    patient_identity = identities.get(patient_id, UserIdentity(user_id=patient_id))
    therapist_identity = identities.get(therapist_id, UserIdentity(user_id=therapist_id))

    return {
        "id": row.get("id"),
        "patient_id": patient_id,
        "therapist_id": therapist_id,
        "clinic_id": clinic_id or None,
        "patient_name": patient_identity.nome,
        "therapist_name": therapist_identity.nome,
        "clinic_name": clinic_names.get(clinic_id) if clinic_id else None,
        "scheduled_start": row.get("scheduled_start"),
        "scheduled_end": row.get("scheduled_end"),
        "status": row.get("status"),
        "patient_origin": row.get("patient_origin"),
        "session_price_applied": row.get("session_price_applied"),
        "created_at": row.get("created_at"),
    }


async def list_appointments_for_admin(
    db: Any,
    page: int,
    page_size: int,
    status: str | None = None,
    date_start: str | None = None,
    date_end: str | None = None,
) -> Tuple[List[Dict[str, Any]], int]:
    """List appointments for the admin console, DTO-shaped.

    Returns ``(data, total)``. Bulk-resolves patient/therapist identities
    via :func:`fetch_user_identities` and clinic names via
    :func:`_resolve_clinic_names` to avoid the N+1 trap (Phase 1 lesson).
    """
    query = db.table("appointments").select("*", count="exact")

    if status:
        query = query.eq("status", status)
    if date_start:
        query = query.gte("scheduled_start", date_start)
    if date_end:
        query = query.lte("scheduled_start", date_end)

    query = query.order("scheduled_start", desc=True)
    offset = (page - 1) * page_size
    result = query.range(offset, offset + page_size - 1).execute()
    rows = result.data or []
    total = result.count or 0

    user_ids: List[str] = []
    clinic_ids: List[str] = []
    for row in rows:
        if row.get("patient_id"):
            user_ids.append(row["patient_id"])
        if row.get("therapist_id"):
            user_ids.append(row["therapist_id"])
        if row.get("clinic_id"):
            clinic_ids.append(row["clinic_id"])

    identities = fetch_user_identities(db, user_ids)
    clinic_names = _resolve_clinic_names(db, clinic_ids)

    dtos = [_appointment_row_to_dto(row, identities, clinic_names) for row in rows]
    return dtos, total


# ---------------------------------------------------------------------------
# Admin dashboard metrics
# ---------------------------------------------------------------------------


async def admin_dashboard_metrics(db: Any) -> Dict[str, Any]:
    """Snapshot metrics for the admin dashboard landing page.

    Returns counts the UI surfaces as headline cards: pending therapists,
    pending clinics, sessions today (count of appointments scheduled today),
    total platform revenue (sum of captured platform fees).
    """
    from datetime import datetime, timedelta, timezone

    pending_therapists = (
        db.table("therapist_profiles")
        .select("user_id", count="exact")
        .eq("is_approved", False)
        .eq("is_active", True)
        .execute()
    )
    pending_clinics = (
        db.table("clinics")
        .select("id", count="exact")
        .eq("is_approved", False)
        .eq("is_active", True)
        .execute()
    )

    today = datetime.now(timezone.utc).date()
    tomorrow = today + timedelta(days=1)
    sessions_today = (
        db.table("appointments")
        .select("id", count="exact")
        .gte("scheduled_start", today.isoformat())
        .lt("scheduled_start", tomorrow.isoformat())
        .execute()
    )

    tx_result = (
        db.table("transactions")
        .select("gross_amount, platform_fee_amount, status")
        .eq("status", "captured")
        .execute()
    )
    txs = tx_result.data or []
    total_revenue = sum(float(t.get("gross_amount", 0) or 0) for t in txs)
    platform_fees = sum(float(t.get("platform_fee_amount", 0) or 0) for t in txs)

    return {
        "pending_therapists": pending_therapists.count or 0,
        "pending_clinics": pending_clinics.count or 0,
        "sessions_today": sessions_today.count or 0,
        "total_revenue": total_revenue,
        "platform_fees": platform_fees,
    }


# ---------------------------------------------------------------------------
# Suspend a therapist or clinic (admin action)
# ---------------------------------------------------------------------------


async def suspend_entity(
    entity_type: str,
    entity_id: str,
    admin_id: str,
    db: Any,
) -> Dict[str, Any]:
    """Suspend a therapist or clinic (sets ``is_active=False``).

    Mirror of :func:`approve_entity` for the suspension half of the
    admin lifecycle. The list endpoint's ``status=suspenso`` filter and
    :func:`_derive_therapist_status` already read ``is_active`` — flipping
    it here closes the loop.
    """
    if entity_type == "therapist":
        table = "therapist_profiles"
        id_col = "user_id"
    elif entity_type == "clinic":
        table = "clinics"
        id_col = "id"
    else:
        raise HTTPException(
            status_code=400,
            detail="Tipo de entidade inválido. Use 'therapist' ou 'clinic'",
        )

    check = db.table(table).select(id_col).eq(id_col, entity_id).execute()
    if not check.data:
        raise HTTPException(
            status_code=404,
            detail=f"{entity_type.capitalize()} não encontrado(a)",
        )

    result = (
        db.table(table)
        .update({"is_active": False})
        .eq(id_col, entity_id)
        .execute()
    )
    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=500, detail="Erro ao suspender entidade")

    logger.info(
        "Entity suspended: type=%s id=%s by_admin=%s",
        entity_type, entity_id, admin_id,
    )
    return row


# ---------------------------------------------------------------------------
# Admin clinic listing (DTO-shaped for the admin Clinics page) — Phase 3
# ---------------------------------------------------------------------------

_VALID_CLINIC_STATUSES = {"pendente", "aprovada", "rejeitada", "suspensa"}


def _derive_clinic_status(row: Dict[str, Any]) -> str:
    """Lifecycle status for a clinic row.

    Frontend ``Clinica`` type expects feminine spellings
    (``pendente`` / ``aprovada`` / ``rejeitada`` / ``suspensa``) — keep them.
    """
    if not row.get("is_active", True):
        return "suspensa"
    if row.get("is_approved"):
        return "aprovada"
    if row.get("rejection_reason"):
        return "rejeitada"
    return "pendente"


def _clinic_row_to_dto(row: Dict[str, Any], identity: UserIdentity) -> Dict[str, Any]:
    """Map a ``clinics`` row + responsible-person identity → admin DTO.

    Mirrors the ``Clinica`` shape declared in
    ``frontend/src/types/index.ts``. ``user_id`` is the clinic's
    responsible-person ``approved_by`` for now — there's no
    ``responsible_user_id`` column in the migration. Email comes from the
    same identity lookup when present, else falls back to
    ``contact_email`` on the row. ``cidade`` / ``estado`` are not yet
    persisted; the page treats them as optional.
    """
    return {
        "id": row.get("id"),
        "user_id": identity.user_id or row.get("approved_by") or "",
        "nome": row.get("name") or "",
        "cnpj": row.get("cnpj") or "",
        "responsavel": row.get("responsible_person") or identity.nome or "",
        "email": row.get("contact_email") or identity.email or "",
        "telefone": row.get("phone") or "",
        "endereco": row.get("address"),
        "cidade": row.get("city"),
        "estado": row.get("state"),
        "logo_url": row.get("logo_url"),
        "status": _derive_clinic_status(row),
        "nota_media": row.get("avg_rating"),
        "total_avaliacoes": row.get("review_count"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


async def list_clinics_for_admin(
    db: Any,
    page: int,
    page_size: int,
    status: str | None = None,
    busca: str | None = None,
) -> Tuple[List[Dict[str, Any]], int]:
    """List clinics for the admin console as the frontend ``Clinica`` DTO.

    ``status`` accepts ``pendente`` | ``aprovada`` | ``rejeitada`` |
    ``suspensa`` and is translated to DB predicates here.
    ``busca`` matches ``name`` or ``cnpj`` via ``ilike``.
    Identities resolve the responsible-person's email/name from
    ``auth.users`` when present.
    """
    query = (
        db.table("clinics")
        .select("*", count="exact")
        .order("created_at", desc=True)
    )

    if status and status in _VALID_CLINIC_STATUSES:
        if status == "aprovada":
            query = query.eq("is_approved", True).eq("is_active", True)
        elif status == "pendente":
            query = query.eq("is_approved", False).eq("is_active", True)
        elif status == "suspensa":
            query = query.eq("is_active", False)
        elif status == "rejeitada":
            # Reject-audit columns land in Phase 5; until then, the
            # rejeitada bucket is empty.
            return [], 0

    if busca:
        # PostgREST ``or`` with ``ilike`` — matches name or cnpj.
        query = query.or_(f"name.ilike.%{busca}%,cnpj.ilike.%{busca}%")

    offset = (page - 1) * page_size
    result = query.range(offset, offset + page_size - 1).execute()
    rows = result.data or []
    total = result.count or 0

    user_ids = [
        row.get("approved_by") for row in rows
        if row.get("approved_by")
    ]
    identities = fetch_user_identities(db, user_ids)

    dtos: List[Dict[str, Any]] = []
    for row in rows:
        uid = row.get("approved_by") or ""
        identity = identities.get(uid, UserIdentity(user_id=uid))
        dtos.append(_clinic_row_to_dto(row, identity))
    return dtos, total


# ---------------------------------------------------------------------------
# Admin patient listing (DTO-shaped for the admin Patients page) — Phase 3
# ---------------------------------------------------------------------------


def _patient_row_to_dto(
    row: Dict[str, Any],
    identity: UserIdentity,
    therapist_identities: Dict[str, UserIdentity],
    session_counts: Dict[str, int],
) -> Dict[str, Any]:
    """Map a ``patient_profiles`` row → admin Patient DTO.

    Shape mirrors the locally-declared ``AdminPatient`` interface in
    ``frontend/src/pages/admin/Patients.tsx``: ``id``, ``nome``, ``email``,
    ``terapeuta_nome``, ``origin``, ``session_count``.
    """
    therapist_id = row.get("current_therapist_id") or ""
    terapeuta_identity = (
        therapist_identities.get(therapist_id)
        if therapist_id
        else None
    )
    return {
        "id": row.get("user_id"),
        "user_id": row.get("user_id"),
        "nome": identity.nome,
        "email": identity.email,
        "telefone": row.get("phone"),
        "foto_url": identity.foto_url or row.get("photo_url"),
        "terapeuta_id": therapist_id or None,
        "terapeuta_nome": (
            terapeuta_identity.nome if terapeuta_identity else None
        ),
        "clinic_id": row.get("clinic_id"),
        "origin": row.get("origin"),
        "session_count": session_counts.get(row.get("user_id") or "", 0),
        "is_active": row.get("is_active", True),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


def _resolve_session_counts(db: Any, patient_ids: List[str]) -> Dict[str, int]:
    """Bulk-fetch session counts per patient from ``appointments``.

    Returns ``{patient_id: count}`` for completed appointments. Empty
    input → empty dict. Mirrors ``_resolve_clinic_names`` in shape —
    one query, no N+1.
    """
    if not patient_ids:
        return {}
    unique_ids = list({pid for pid in patient_ids if pid})
    if not unique_ids:
        return {}
    result = (
        db.table("appointments")
        .select("patient_id, status")
        .in_("patient_id", unique_ids)
        .eq("status", "completed")
        .execute()
    )
    rows = result.data or []
    counts: Dict[str, int] = {}
    for r in rows:
        pid = r.get("patient_id")
        if pid:
            counts[pid] = counts.get(pid, 0) + 1
    return counts


async def list_patients_for_admin(
    db: Any,
    page: int,
    page_size: int,
    busca: str | None = None,
) -> Tuple[List[Dict[str, Any]], int]:
    """List patients for the admin console, DTO-shaped.

    Bulk-resolves: (a) patient nome/email via the Phase 1 identity
    resolver; (b) current-therapist nome via the same resolver; (c)
    session_count per patient via :func:`_resolve_session_counts`.
    """
    query = (
        db.table("patient_profiles")
        .select("*", count="exact")
        .order("created_at", desc=True)
    )

    if busca:
        # Search hits ``phone`` only at the DB level — name/email live in
        # ``auth.users`` and aren't reachable via PostgREST ``ilike``.
        # The frontend already runs a client-side filter for name/email
        # on the returned page; this DB ``ilike`` keeps phone-search
        # working server-side.
        query = query.or_(f"phone.ilike.%{busca}%")

    offset = (page - 1) * page_size
    result = query.range(offset, offset + page_size - 1).execute()
    rows = result.data or []
    total = result.count or 0

    patient_ids = [row.get("user_id") for row in rows if row.get("user_id")]
    therapist_ids = [
        row.get("current_therapist_id") for row in rows
        if row.get("current_therapist_id")
    ]

    patient_identities = fetch_user_identities(db, patient_ids)
    therapist_identities = fetch_user_identities(db, therapist_ids)
    session_counts = _resolve_session_counts(db, patient_ids)

    dtos: List[Dict[str, Any]] = []
    for row in rows:
        uid = row.get("user_id") or ""
        identity = patient_identities.get(uid, UserIdentity(user_id=uid))
        dtos.append(
            _patient_row_to_dto(
                row, identity, therapist_identities, session_counts,
            )
        )
    return dtos, total


# ---------------------------------------------------------------------------
# Admin reports listing (DTO-shaped for the admin Moderation page) — Phase 3
# ---------------------------------------------------------------------------


_VALID_REPORT_STATUSES = {"pending", "reviewed", "resolved", "dismissed"}


def _resolve_message_previews(
    db: Any,
    message_ids: List[str],
) -> Dict[str, str]:
    """Bulk-resolve message previews keyed by message_id.

    Returns ``{message_id: content_preview}`` where preview is the first
    ~120 chars of ``content`` (system/AI messages fall back to a tag).
    Empty input → empty dict.
    """
    if not message_ids:
        return {}
    unique_ids = list({mid for mid in message_ids if mid})
    if not unique_ids:
        return {}
    result = (
        db.table("messages")
        .select("id, content, message_type")
        .in_("id", unique_ids)
        .execute()
    )
    rows = result.data or []
    previews: Dict[str, str] = {}
    for r in rows:
        mid = r.get("id")
        if not mid:
            continue
        content = (r.get("content") or "").strip()
        if content:
            previews[mid] = content[:120]
        else:
            previews[mid] = f"[{r.get('message_type') or 'system'}]"
    return previews


def _report_row_to_dto(
    row: Dict[str, Any],
    reporter_identity: UserIdentity,
    message_preview: str,
) -> Dict[str, Any]:
    """Map a ``message_reports`` row → admin Report DTO.

    Shape mirrors the locally-declared ``Report`` interface in
    ``frontend/src/pages/admin/Moderation.tsx``: ``id``,
    ``reporter_name``, ``reported_message_preview``, ``reason``,
    ``status``, ``created_at``, ``conversation_id``.
    """
    return {
        "id": row.get("id"),
        "reporter_name": reporter_identity.nome,
        "reporter_user_id": row.get("reported_by_user_id"),
        "reported_message_preview": message_preview,
        "message_id": row.get("message_id"),
        "reason": row.get("reason") or "",
        "status": row.get("status") or "pending",
        "resolution": row.get("resolution"),
        "conversation_id": row.get("conversation_id"),
        "reviewed_by_admin_id": row.get("reviewed_by_admin_id"),
        "created_at": row.get("created_at"),
        "resolved_at": row.get("resolved_at"),
    }


async def list_reports_for_admin(
    db: Any,
    page: int,
    page_size: int,
    status: str | None = None,
) -> Tuple[List[Dict[str, Any]], int]:
    """List message reports for admin moderation, DTO-shaped.

    Bulk-resolves reporter identity + message preview. ``status`` filter
    narrows by report lifecycle (``pending`` / ``reviewed`` / ``resolved``
    / ``dismissed``).
    """
    query = (
        db.table("message_reports")
        .select("*", count="exact")
        .order("created_at", desc=True)
    )
    if status and status in _VALID_REPORT_STATUSES:
        query = query.eq("status", status)

    offset = (page - 1) * page_size
    result = query.range(offset, offset + page_size - 1).execute()
    rows = result.data or []
    total = result.count or 0

    reporter_ids = [
        row.get("reported_by_user_id") for row in rows
        if row.get("reported_by_user_id")
    ]
    message_ids = [row.get("message_id") for row in rows if row.get("message_id")]

    identities = fetch_user_identities(db, reporter_ids)
    previews = _resolve_message_previews(db, message_ids)

    dtos: List[Dict[str, Any]] = []
    for row in rows:
        uid = row.get("reported_by_user_id") or ""
        mid = row.get("message_id") or ""
        identity = identities.get(uid, UserIdentity(user_id=uid))
        dtos.append(
            _report_row_to_dto(row, identity, previews.get(mid, ""))
        )
    return dtos, total


async def resolve_report(
    report_id: str,
    admin_id: str,
    resolution: str,
    db: Any,
) -> Dict[str, Any]:
    """Resolve a message report — sets ``status='resolved'`` + audit cols.

    Mirror of :func:`messaging_service.review_report` but rooted in the
    admin namespace so the frontend's ``POST /api/admin/reports/:id/resolve``
    has a service-layer entry point.
    """
    from datetime import datetime, timezone

    check = (
        db.table("message_reports")
        .select("id")
        .eq("id", report_id)
        .execute()
    )
    if not check.data:
        raise HTTPException(status_code=404, detail="Denúncia não encontrada")

    result = (
        db.table("message_reports")
        .update({
            "status": "resolved",
            "reviewed_by_admin_id": admin_id,
            "resolution": resolution,
            "resolved_at": datetime.now(timezone.utc).isoformat(),
        })
        .eq("id", report_id)
        .execute()
    )
    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=500, detail="Erro ao resolver denúncia")

    logger.info(
        "Report resolved: id=%s by_admin=%s",
        report_id, admin_id,
    )
    return row


# ---------------------------------------------------------------------------
# Admin flagged reviews listing — Phase 3
# ---------------------------------------------------------------------------


def _flagged_review_row_to_dto(
    row: Dict[str, Any],
    entity_type: str,
    patient_identity: UserIdentity,
    entity_name: str,
) -> Dict[str, Any]:
    """Map a ``reviews`` / ``clinic_reviews`` row → admin FlaggedReview DTO.

    Shape mirrors the ``FlaggedReview`` interface declared in
    ``frontend/src/pages/admin/Reviews.tsx``.
    """
    return {
        "id": row.get("id"),
        "nota": row.get("star_rating"),
        "comentario": row.get("review_text") or "",
        "patient_id": row.get("patient_id"),
        "patient_name": patient_identity.nome,
        "entity_id": row.get("therapist_id") if entity_type == "therapist" else row.get("clinic_id"),
        "entity_name": entity_name,
        "entity_type": entity_type,
        "flag_reason": row.get("flagged_reason") or "",
        "flagged_by_id": (
            row.get("flagged_by_therapist_id")
            if entity_type == "therapist"
            else row.get("flagged_by_clinic_admin_id")
        ),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


async def list_flagged_reviews_for_admin(
    db: Any,
    page: int,
    page_size: int,
    entity_type: str | None = None,
) -> Tuple[List[Dict[str, Any]], int]:
    """List flagged (and not hidden) therapist + clinic reviews, DTO-shaped.

    Reads both ``reviews`` (therapist) and ``clinic_reviews`` tables,
    bulk-resolves patient identities + therapist identities + clinic
    names. ``entity_type`` filter restricts to one of
    ``therapist`` | ``clinic``; absent → both.

    Pagination spans the combined sorted list.

    .. note::
       This is the **N=2 consumer** of :func:`_resolve_clinic_names`
       (first was ``list_appointments_for_admin``). Per the recurrence
       rule it stays in-product for now; if a third consumer lands the
       helper graduates to seed.
    """
    therapist_rows: List[Dict[str, Any]] = []
    clinic_rows: List[Dict[str, Any]] = []
    t_total = 0
    c_total = 0

    if entity_type in (None, "therapist"):
        t_query = (
            db.table("reviews")
            .select("*", count="exact")
            .eq("is_flagged", True)
            .eq("is_hidden", False)
            .order("created_at", desc=True)
        )
        t_result = t_query.execute()
        therapist_rows = t_result.data or []
        t_total = t_result.count or 0

    if entity_type in (None, "clinic"):
        c_query = (
            db.table("clinic_reviews")
            .select("*", count="exact")
            .eq("is_flagged", True)
            .eq("is_hidden", False)
            .order("created_at", desc=True)
        )
        c_result = c_query.execute()
        clinic_rows = c_result.data or []
        c_total = c_result.count or 0

    # Bulk identity / name resolution across the combined set.
    patient_ids: List[str] = [
        r.get("patient_id") for r in therapist_rows + clinic_rows
        if r.get("patient_id")
    ]
    therapist_ids: List[str] = [
        r.get("therapist_id") for r in therapist_rows
        if r.get("therapist_id")
    ]
    clinic_ids: List[str] = [
        r.get("clinic_id") for r in clinic_rows
        if r.get("clinic_id")
    ]

    patient_identities = fetch_user_identities(db, patient_ids)
    therapist_identities = fetch_user_identities(db, therapist_ids)
    clinic_names = _resolve_clinic_names(db, clinic_ids)

    dtos: List[Dict[str, Any]] = []
    for row in therapist_rows:
        pid = row.get("patient_id") or ""
        tid = row.get("therapist_id") or ""
        p_identity = patient_identities.get(pid, UserIdentity(user_id=pid))
        t_identity = therapist_identities.get(tid, UserIdentity(user_id=tid))
        dtos.append(
            _flagged_review_row_to_dto(row, "therapist", p_identity, t_identity.nome)
        )
    for row in clinic_rows:
        pid = row.get("patient_id") or ""
        cid = row.get("clinic_id") or ""
        p_identity = patient_identities.get(pid, UserIdentity(user_id=pid))
        c_name = clinic_names.get(cid) or ""
        dtos.append(
            _flagged_review_row_to_dto(row, "clinic", p_identity, c_name)
        )

    # Stable sort: newest first across both tables.
    dtos.sort(key=lambda d: d.get("created_at") or "", reverse=True)

    total = t_total + c_total
    offset = (page - 1) * page_size
    return dtos[offset:offset + page_size], total


async def moderate_review(
    review_id: str,
    action: str,
    admin_id: str,
    db: Any,
) -> Dict[str, Any]:
    """Admin moderation action on a flagged review.

    ``action`` ∈ {``dismiss``, ``hide``}. ``dismiss`` clears the flag
    (review goes back to visible); ``hide`` sets ``is_hidden=True`` and
    stamps ``hidden_by_admin_id``. Looks in both ``reviews`` and
    ``clinic_reviews`` tables — review IDs are UUIDs from one of the
    two; the lookup checks both.
    """
    if action not in ("dismiss", "hide"):
        raise HTTPException(
            status_code=400,
            detail="Ação deve ser 'dismiss' ou 'hide'",
        )

    # Try therapist reviews first.
    table = "reviews"
    check = db.table(table).select("id").eq("id", review_id).execute()
    if not check.data:
        table = "clinic_reviews"
        check = db.table(table).select("id").eq("id", review_id).execute()
        if not check.data:
            raise HTTPException(status_code=404, detail="Avaliação não encontrada")

    if action == "dismiss":
        update_data = {
            "is_flagged": False,
            "flagged_reason": None,
        }
    else:  # hide
        update_data = {
            "is_hidden": True,
            "hidden_by_admin_id": admin_id,
        }

    result = (
        db.table(table)
        .update(update_data)
        .eq("id", review_id)
        .execute()
    )
    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=500, detail="Erro ao moderar avaliação")

    logger.info(
        "Review moderated: id=%s action=%s table=%s by_admin=%s",
        review_id, action, table, admin_id,
    )
    return row


# ---------------------------------------------------------------------------
# Admin user-blocks listing — Phase 3
# ---------------------------------------------------------------------------


def _block_row_to_dto(
    row: Dict[str, Any],
    blocker_identity: UserIdentity,
    blocked_identity: UserIdentity,
) -> Dict[str, Any]:
    """Map a ``user_blocks`` row → admin Block DTO.

    Mirrors the ``Block`` interface declared in
    ``frontend/src/pages/admin/Moderation.tsx``: ``id``,
    ``blocker_name``, ``blocked_name``, ``created_at``.
    """
    return {
        "id": row.get("id"),
        "blocker_user_id": row.get("blocker_user_id"),
        "blocker_name": blocker_identity.nome,
        "blocked_user_id": row.get("blocked_user_id"),
        "blocked_name": blocked_identity.nome,
        "created_at": row.get("created_at"),
    }


async def list_blocks_for_admin(
    db: Any,
    page: int,
    page_size: int,
) -> Tuple[List[Dict[str, Any]], int]:
    """List user-blocks for admin review, DTO-shaped.

    Bulk-resolves blocker + blocked names via the Phase 1 identity
    resolver. Each block row needs TWO identity lookups, so the bulk
    fetch dedupes via the resolver's existing dedup behavior.
    """
    query = (
        db.table("user_blocks")
        .select("*", count="exact")
        .order("created_at", desc=True)
    )

    offset = (page - 1) * page_size
    result = query.range(offset, offset + page_size - 1).execute()
    rows = result.data or []
    total = result.count or 0

    all_user_ids: List[str] = []
    for r in rows:
        if r.get("blocker_user_id"):
            all_user_ids.append(r["blocker_user_id"])
        if r.get("blocked_user_id"):
            all_user_ids.append(r["blocked_user_id"])

    identities = fetch_user_identities(db, all_user_ids)

    dtos: List[Dict[str, Any]] = []
    for row in rows:
        bk = row.get("blocker_user_id") or ""
        bd = row.get("blocked_user_id") or ""
        bk_identity = identities.get(bk, UserIdentity(user_id=bk))
        bd_identity = identities.get(bd, UserIdentity(user_id=bd))
        dtos.append(_block_row_to_dto(row, bk_identity, bd_identity))
    return dtos, total


# ---------------------------------------------------------------------------
# Admin support-conversations listing — Phase 3
# ---------------------------------------------------------------------------


def _support_conversation_row_to_dto(
    row: Dict[str, Any],
    other_identity: UserIdentity | None,
    other_participant_type: str,
) -> Dict[str, Any]:
    """Map a support ``conversations`` row → frontend ``Conversation`` DTO.

    Mirrors the ``Conversation`` shape declared in
    ``frontend/src/types/messaging.ts`` — ``id``, ``mode``,
    ``last_message_at``, ``created_at``, ``other_participant_name``,
    ``other_participant_avatar``, ``other_participant_type``,
    ``last_message_preview``, ``unread_count``, ``is_muted``,
    ``is_support``.

    The "other participant" is the platform-side user the support
    operator is talking to (patient / therapist / clinic admin). Name
    falls back to "Suporte" when the identity isn't resolvable.
    """
    return {
        "id": row.get("id"),
        "mode": row.get("mode") or "human",
        "last_message_at": row.get("last_message_at"),
        "created_at": row.get("created_at"),
        "other_participant_name": (
            other_identity.nome if other_identity else "Suporte"
        ),
        "other_participant_avatar": (
            other_identity.foto_url if other_identity else None
        ),
        "other_participant_type": other_participant_type,
        "last_message_preview": row.get("last_message_preview"),
        "unread_count": row.get("unread_count", 0) or 0,
        "is_muted": bool(row.get("is_muted", False)),
        "is_support": True,
    }


async def list_support_conversations_for_admin(
    db: Any,
    page: int,
    page_size: int,
    busca: str | None = None,
) -> Tuple[List[Dict[str, Any]], int]:
    """List support conversations for the admin inbox, DTO-shaped.

    Finds every conversation with a ``platform_support`` participant,
    then bulk-resolves the OTHER side's identity (the user the support
    operator is talking to). ``busca`` filters by ``conversations.id``
    via ``ilike``.
    """
    support_parts = (
        db.table("conversation_participants")
        .select("conversation_id")
        .eq("participant_type", "platform_support")
        .execute()
    )
    if not support_parts.data:
        return [], 0

    conv_ids = [p["conversation_id"] for p in support_parts.data]

    query = (
        db.table("conversations")
        .select("*", count="exact")
        .in_("id", conv_ids)
        .order("last_message_at", desc=True)
    )
    if busca:
        query = query.or_(f"id.ilike.%{busca}%")

    offset = (page - 1) * page_size
    result = query.range(offset, offset + page_size - 1).execute()
    rows = result.data or []
    total = result.count or 0

    # Resolve the "other" participant per conversation: the non-support
    # user-type participant. We fetch the full participant set for the
    # selected conversations and pick the first non-support entry.
    selected_ids = [r.get("id") for r in rows if r.get("id")]
    other_by_conv: Dict[str, Tuple[str | None, str]] = {}
    if selected_ids:
        parts_result = (
            db.table("conversation_participants")
            .select("conversation_id, participant_type, participant_id, clinic_id")
            .in_("conversation_id", selected_ids)
            .execute()
        )
        for part in parts_result.data or []:
            ptype = part.get("participant_type")
            if ptype == "platform_support":
                continue
            cid = part.get("conversation_id")
            if not cid or cid in other_by_conv:
                continue
            # ``participant_type`` for users is ``"user"`` per messaging.ts;
            # clinic-entity participants use ``"clinic"``.
            if ptype == "clinic":
                other_by_conv[cid] = (None, "clinic")
            else:
                other_by_conv[cid] = (part.get("participant_id"), "user")

    user_ids = [
        uid for uid, _ in other_by_conv.values() if uid
    ]
    identities = fetch_user_identities(db, user_ids)

    dtos: List[Dict[str, Any]] = []
    for row in rows:
        cid = row.get("id") or ""
        other_uid, other_type = other_by_conv.get(cid, (None, "platform_support"))
        identity = (
            identities.get(other_uid)
            if other_uid
            else None
        )
        dtos.append(
            _support_conversation_row_to_dto(row, identity, other_type)
        )
    return dtos, total
