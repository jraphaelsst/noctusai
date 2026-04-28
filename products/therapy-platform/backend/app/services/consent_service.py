"""Consent Service — auditable per-session consent records (compliance-audit-
reconciliation Phase 5, Q5).

Q5 locks: one consent row per (appointment, scope); each scope granted and
revoked independently. `recording` is the minimum scope required to start
a session — enforced by `sessions.py` start endpoint.

Writers: the patient (self-grant) or the therapist-of-session (attesting
to verbal in-room consent — `actor_user_id` records who logged it). RLS
enforces both paths via `consent_records_policy` on the session's
appointment.

LGPD Art. 8: the `policy_version` + `purpose_text` fields retain the exact
wording the patient agreed to — revoking does not delete the historical
record, it sets `revoked_at`.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from app.dependencies import first_or_none

logger = logging.getLogger(__name__)

ALLOWED_SCOPES = ("recording", "transcription", "ai_summary", "longitudinal")

SP_TZ = timezone(timedelta(hours=-3))


def _now_iso() -> str:
    return datetime.now(SP_TZ).isoformat()


def _load_appointment(appointment_id: str, db: Any) -> Dict:
    result = (
        db.table("appointments")
        .select("id, therapist_id, patient_id, clinic_id")
        .eq("id", appointment_id)
        .execute()
    )
    appt = first_or_none(result)
    if not appt:
        raise HTTPException(status_code=404, detail="Agendamento não encontrado")
    return appt


async def grant_consent(
    appointment_id: str,
    scope: str,
    policy_version: str,
    purpose_text: str,
    actor_user_id: str,
    db: Any,
) -> Dict:
    """Grant consent for a specific scope on an appointment.

    If a prior consent row exists for this (appointment, scope), it is
    "re-granted": `revoked_at` is cleared and `granted_at` updated to now.
    Otherwise a new row is inserted.
    """
    if scope not in ALLOWED_SCOPES:
        raise HTTPException(status_code=422, detail=f"Escopo inválido: {scope}")

    appt = _load_appointment(appointment_id, db)

    # Actor must be a participant (therapist or patient of the session).
    if actor_user_id not in (appt["therapist_id"], appt["patient_id"]):
        raise HTTPException(
            status_code=403,
            detail="Apenas o terapeuta ou paciente da sessão pode registrar consentimento",
        )

    existing = first_or_none(
        db.table("consent_records")
        .select("id")
        .eq("appointment_id", appointment_id)
        .eq("scope", scope)
        .execute()
    )

    now_iso = _now_iso()

    if existing:
        result = (
            db.table("consent_records")
            .update({
                "granted_at": now_iso,
                "revoked_at": None,
                "policy_version": policy_version,
                "purpose_text": purpose_text,
                "actor_user_id": actor_user_id,
            })
            .eq("id", existing["id"])
            .execute()
        )
        return first_or_none(result) or {"id": existing["id"], "appointment_id": appointment_id, "scope": scope}

    payload = {
        "appointment_id": appointment_id,
        "patient_id": appt["patient_id"],
        "therapist_id": appt["therapist_id"],
        "clinic_id": appt.get("clinic_id"),
        "scope": scope,
        "policy_version": policy_version,
        "purpose_text": purpose_text,
        "actor_user_id": actor_user_id,
        "granted_at": now_iso,
    }
    result = db.table("consent_records").insert(payload).execute()
    return first_or_none(result) or payload


async def revoke_consent(
    appointment_id: str,
    scope: str,
    actor_user_id: str,
    db: Any,
) -> Dict:
    """Revoke an active consent for a scope. Sets `revoked_at`; does NOT
    delete the historical row (LGPD Art. 8 retention)."""
    if scope not in ALLOWED_SCOPES:
        raise HTTPException(status_code=422, detail=f"Escopo inválido: {scope}")

    appt = _load_appointment(appointment_id, db)

    if actor_user_id not in (appt["therapist_id"], appt["patient_id"]):
        raise HTTPException(
            status_code=403,
            detail="Apenas o terapeuta ou paciente da sessão pode revogar consentimento",
        )

    existing = first_or_none(
        db.table("consent_records")
        .select("id, revoked_at")
        .eq("appointment_id", appointment_id)
        .eq("scope", scope)
        .execute()
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Registro de consentimento não encontrado")
    if existing.get("revoked_at"):
        raise HTTPException(status_code=400, detail="Consentimento já revogado")

    result = (
        db.table("consent_records")
        .update({"revoked_at": _now_iso()})
        .eq("id", existing["id"])
        .execute()
    )
    return first_or_none(result) or {"id": existing["id"], "revoked": True}


async def check_active_consent(
    appointment_id: str,
    scope: str,
    db: Any,
) -> bool:
    """Return True iff there is an active (not-revoked) consent row for
    this (appointment, scope)."""
    if scope not in ALLOWED_SCOPES:
        return False

    result = (
        db.table("consent_records")
        .select("id, revoked_at")
        .eq("appointment_id", appointment_id)
        .eq("scope", scope)
        .execute()
    )
    row = first_or_none(result)
    if not row:
        return False
    return row.get("revoked_at") is None


async def list_consents(appointment_id: str, db: Any) -> List[Dict]:
    """List all consent records (active + revoked) for an appointment."""
    result = (
        db.table("consent_records")
        .select("*")
        .eq("appointment_id", appointment_id)
        .execute()
    )
    return result.data or []
