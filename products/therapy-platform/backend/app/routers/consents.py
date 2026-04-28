"""Consents Router — auditable consent records per (appointment, scope).

Prefix: /api/consents

compliance-audit-reconciliation Phase 5 (Q5, 2026-04-22): replaces the
ephemeral `consent_given: bool` flag on session-start with a persistent,
revocable, per-scope consent. Scopes: recording, transcription, ai_summary,
longitudinal. Recording is the minimum required for `POST /api/sessions/
:appointment_id/start` to succeed.

Writers: the patient of the session, OR the therapist-of-session attesting
to verbal in-room consent (`actor_user_id` records who logged it). RLS
policy `consent_records_policy` enforces the same restriction at the DB.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException

from app.dependencies import get_current_user, get_user_client, get_user_role
from app.responses import success_response
from app.schemas.consent import ConsentGrantRequest, ConsentRevokeRequest
from app.services import consent_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/consents", tags=["Consents"])


@router.post("/grant")
async def grant_consent(
    body: ConsentGrantRequest,
    authorization: Optional[str] = Header(None),
):
    """Grant consent for one scope on one appointment.

    Allowed actors: the session's patient, or its therapist (attesting).
    Other roles are refused — consent is a clinical-audit artifact.
    """
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    if role not in ("therapist", "patient"):
        raise HTTPException(
            status_code=403,
            detail="Apenas terapeuta ou paciente da sessão podem registrar consentimento",
        )

    db = get_user_client(token)
    data = await consent_service.grant_consent(
        appointment_id=body.appointment_id,
        scope=body.scope,
        policy_version=body.policy_version,
        purpose_text=body.purpose_text,
        actor_user_id=str(user.id),
        db=db,
    )
    return success_response(data)


@router.post("/revoke")
async def revoke_consent(
    body: ConsentRevokeRequest,
    authorization: Optional[str] = Header(None),
):
    """Revoke an active consent. Historical row is preserved (LGPD Art. 8)."""
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    if role not in ("therapist", "patient"):
        raise HTTPException(
            status_code=403,
            detail="Apenas terapeuta ou paciente da sessão podem revogar consentimento",
        )

    db = get_user_client(token)
    data = await consent_service.revoke_consent(
        appointment_id=body.appointment_id,
        scope=body.scope,
        actor_user_id=str(user.id),
        db=db,
    )
    return success_response(data)


@router.get("/{appointment_id}")
async def list_consents(
    appointment_id: str,
    authorization: Optional[str] = Header(None),
):
    """List all consent records (active + revoked) for an appointment.

    RLS restricts results to participants of the appointment. platform_admin
    / clinic_admin get empty results (consent is clinical audit data).
    """
    user, token = await get_current_user(authorization)
    db = get_user_client(token)
    data = await consent_service.list_consents(appointment_id, db)
    return success_response(data)
