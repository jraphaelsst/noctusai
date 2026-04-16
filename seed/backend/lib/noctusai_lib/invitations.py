"""
Shared invitation system for the NoctusAI platform.

Provides token generation, CRUD helpers, and validation for the
invitation workflow used across Core and all products.

Each product has its own ``invitations`` table (in its schema) with
the same structure.  All functions accept a ``table`` parameter so
products target the correct schema automatically via their Supabase
client's schema targeting.

Usage in a product's team router::

    from noctusai_lib.invitations import (
        generate_invite_token,
        create_invitation,
        validate_invitation,
        accept_invitation,
        cancel_invitation,
        list_pending_invitations,
    )

    @router.post("/invite")
    async def invite(body, authorization):
        user, token = await get_current_user(authorization)
        db = get_admin_client()
        invite = create_invitation(
            db, "invitations", org_id, body.email, body.role, user.id
        )
        send_product_invitation_email(...)
        return {"data": invite}
"""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException

logger = logging.getLogger(__name__)


def generate_invite_token() -> str:
    """Generate a cryptographically secure invitation token."""
    return secrets.token_urlsafe(32)


def create_invitation(
    db,
    table: str,
    org_id: str,
    email: str,
    role: str,
    invited_by: str,
    *,
    expires_days: int = 7,
    extra: Optional[dict] = None,
) -> dict:
    """Create an invitation record with a unique token.

    Args:
        db: Supabase client (schema-targeted).
        table: Table name (e.g. "invitations").
        org_id: Organization ID (or clinic_id for Therapy).
        email: Invitee email address.
        role: Pre-assigned role for the invitee.
        invited_by: User ID of the inviter.
        expires_days: Days until expiration (default 7).
        extra: Additional fields to store (e.g. invite_type for Therapy).

    Returns:
        The created invitation record dict.

    Raises:
        HTTPException(409) if email already has a pending invitation.
        HTTPException(500) if insert fails.
    """
    # Check for existing pending invitation
    pending = (
        db.table(table)
        .select("id")
        .eq("org_id", org_id)
        .eq("email", email)
        .eq("status", "pending")
        .execute()
    )
    if pending.data:
        raise HTTPException(
            status_code=409,
            detail="Ja existe um convite pendente para este email",
        )

    token = generate_invite_token()

    invite_data = {
        "org_id": org_id,
        "email": email,
        "role": role,
        "invited_by": invited_by,
        "token": token,
        "status": "pending",
    }
    if extra:
        invite_data.update(extra)

    result = db.table(table).insert(invite_data).execute()
    if not result.data:
        raise HTTPException(status_code=500, detail="Erro ao criar convite")

    logger.info("Invitation created for %s to org=%s role=%s", email, org_id, role)
    return result.data[0] if isinstance(result.data, list) else result.data


def validate_invitation(db, table: str, token: str) -> dict:
    """Validate an invitation token. Returns the invitation record.

    Checks:
    - Token exists
    - Status is 'pending'
    - Not expired (expires_at > now)

    Raises:
        HTTPException(404) if not found.
        HTTPException(400) if already used, canceled, or expired.
    """
    invite = (
        db.table(table)
        .select("*")
        .eq("token", token)
        .single()
        .execute()
    )
    if not invite.data:
        raise HTTPException(status_code=404, detail="Convite nao encontrado")

    data = invite.data

    if data["status"] != "pending":
        raise HTTPException(
            status_code=400,
            detail="Este convite ja foi utilizado ou cancelado",
        )

    # Check expiration
    expires_at = data.get("expires_at")
    if expires_at:
        try:
            exp_str = str(expires_at).replace("Z", "+00:00").replace(" ", "T")
            if not exp_str.endswith("+00:00") and "+" not in exp_str[-6:]:
                exp_str += "+00:00"
            exp_dt = datetime.fromisoformat(exp_str)
            if exp_dt < datetime.now(timezone.utc):
                # Auto-expire
                db.table(table).update({"status": "expired"}).eq("id", data["id"]).execute()
                raise HTTPException(status_code=400, detail="Convite expirado")
        except (ValueError, TypeError):
            pass  # If we can't parse, let it through

    return data


def accept_invitation(db, table: str, invitation_id: str) -> None:
    """Mark an invitation as accepted."""
    db.table(table).update({"status": "accepted"}).eq("id", invitation_id).execute()
    logger.info("Invitation %s accepted", invitation_id)


def cancel_invitation(db, table: str, invitation_id: str, org_id: str) -> None:
    """Cancel a pending invitation. Verifies it belongs to the org and is pending.

    Raises:
        HTTPException(404) if not found or not pending.
    """
    invite = (
        db.table(table)
        .select("id, status")
        .eq("id", invitation_id)
        .eq("org_id", org_id)
        .eq("status", "pending")
        .single()
        .execute()
    )
    if not invite.data:
        raise HTTPException(status_code=404, detail="Convite nao encontrado")

    db.table(table).update({"status": "canceled"}).eq("id", invitation_id).execute()
    logger.info("Invitation %s canceled", invitation_id)


def list_pending_invitations(db, table: str, org_id: str) -> list:
    """List all pending invitations for an organization."""
    result = (
        db.table(table)
        .select("id, email, role, status, invited_by, expires_at, created_at")
        .eq("org_id", org_id)
        .eq("status", "pending")
        .order("created_at", desc=True)
        .execute()
    )
    return result.data or []


def expire_old_invitations(db, table: str) -> int:
    """Expire all invitations past their expires_at. Returns count expired.

    Intended for periodic cleanup (e.g. scheduled task).
    """
    result = (
        db.table(table)
        .update({"status": "expired"})
        .eq("status", "pending")
        .lt("expires_at", datetime.now(timezone.utc).isoformat())
        .execute()
    )
    count = len(result.data) if result.data else 0
    if count:
        logger.info("Expired %d old invitations", count)
    return count
