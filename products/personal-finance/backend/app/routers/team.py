"""
Team Management Router — Invitations and member management for Personal Finance.

Uses the shared invitation system (noctusai_shared.invitations) for token
generation, validation, and lifecycle.  Admin operations (invite, cancel)
require platform_admin or org admin/owner role.

PF has only two roles: admin and member.  There is no product-specific
profiles table — members are tracked in the core ``noctus_users`` table
(public schema) and auth user metadata carries the org_id.
"""
from __future__ import annotations

import logging
from typing import Literal, Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, EmailStr, Field

from app.dependencies import get_current_user, get_admin_client, get_user_role
from app.database import get_core_client
from app.responses import success_response, ok_response
from noctusai_shared.invitations import (
    create_invitation,
    validate_invitation,
    accept_invitation,
    cancel_invitation,
    list_pending_invitations,
)
from noctusai_shared.email_templates import send_product_invitation_email

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/team", tags=["Team"])

# Valid PF roles
PF_ROLES = ("admin", "member")

PF_ROLE_LABELS = {
    "admin": "Administrador",
    "member": "Membro",
}

# Frontend base URL for invitation links
PF_FRONTEND_URL = "http://localhost:8090"

INVITATIONS_TABLE = "invitations"


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class InviteBody(BaseModel):
    email: EmailStr
    role: Literal["admin", "member"] = "member"


class AcceptInviteBody(BaseModel):
    token: str
    nome: str = Field(..., min_length=2, max_length=120)
    password: str = Field(..., min_length=6, max_length=128)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_org_id(user) -> str:
    """Extract org_id from user metadata. Raises 403 if missing."""
    org_id = (user.user_metadata or {}).get("org_id")
    if not org_id:
        raise HTTPException(status_code=403, detail="Usuário sem organização associada")
    return org_id


def _require_pf_admin(user) -> None:
    """Raise 403 if the user is neither a platform_admin nor an org admin/owner."""
    role = get_user_role(user)
    if role == "platform_admin":
        return

    # Check org_role from core noctus_users
    core = get_core_client()
    check = (
        core.table("noctus_users")
        .select("org_role")
        .eq("id", str(user.id))
        .execute()
    )
    if check.data:
        org_role = check.data[0].get("org_role")
        if org_role in ("owner", "admin"):
            return

    raise HTTPException(status_code=403, detail="Acesso restrito a administradores")


def _get_org_name(org_id: str) -> str:
    """Fetch organization name from the core public schema."""
    core = get_core_client()
    result = core.table("organizations").select("name").eq("id", org_id).execute()
    if result.data:
        return result.data[0].get("name", "Organização")
    return "Organização"


def _get_user_display_name(user) -> str:
    """Extract a display name from user metadata."""
    metadata = getattr(user, "user_metadata", None) or {}
    return metadata.get("nome") or metadata.get("name") or metadata.get("email", "Administrador")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("")
async def listar_membros(authorization: Optional[str] = Header(None)):
    """List all organization members from the core noctus_users table."""
    user, token = await get_current_user(authorization)
    org_id = _get_org_id(user)
    core = get_core_client()

    result = (
        core.table("noctus_users")
        .select("id, nome, email, org_role, avatar_url, created_at")
        .eq("org_id", org_id)
        .order("created_at", desc=True)
        .execute()
    )
    members = result.data or []

    # Map org_role to PF role labels for display
    for member in members:
        org_role = member.get("org_role", "member")
        if org_role in ("owner", "admin"):
            member["role"] = "admin"
        else:
            member["role"] = "member"

    return success_response(members, total=len(members))


@router.post("/invite")
async def convidar_membro(body: InviteBody, authorization: Optional[str] = Header(None)):
    """Invite a new member to the organization (admin only)."""
    user, token = await get_current_user(authorization)
    _require_pf_admin(user)
    org_id = _get_org_id(user)
    db = get_admin_client()

    # Check if email is already a member
    core = get_core_client()
    existing = (
        core.table("noctus_users")
        .select("id")
        .eq("org_id", org_id)
        .eq("email", body.email)
        .execute()
    )
    if existing.data:
        raise HTTPException(status_code=409, detail="Este email ja e membro da organizacao")

    # Create invitation via shared helper
    invite = create_invitation(
        db,
        INVITATIONS_TABLE,
        org_id,
        body.email,
        body.role,
        str(user.id),
    )

    # Send invitation email
    org_name = _get_org_name(org_id)
    inviter_name = _get_user_display_name(user)
    role_label = PF_ROLE_LABELS.get(body.role, body.role.capitalize())

    send_product_invitation_email(
        to=body.email,
        product_name="Financas Pessoais",
        org_name=org_name,
        role_label=role_label,
        invite_token=invite["token"],
        invited_by=inviter_name,
        base_url=PF_FRONTEND_URL,
    )

    logger.info(
        "Invitation sent: email=%s org=%s role=%s invited_by=%s",
        body.email, org_id, body.role, str(user.id),
    )

    return success_response(invite)


@router.get("/accept/validate")
async def validar_convite(token: str):
    """Validate an invitation token — public endpoint (no auth required).

    Returns the invitation email and role so the frontend can pre-fill the form.
    """
    db = get_admin_client()
    invite = validate_invitation(db, INVITATIONS_TABLE, token)

    org_name = _get_org_name(invite["org_id"])

    return success_response({
        "email": invite["email"],
        "role": PF_ROLE_LABELS.get(invite["role"], invite["role"]),
        "org_name": org_name,
    })


@router.post("/accept")
async def aceitar_convite(body: AcceptInviteBody):
    """Accept an invitation — public endpoint (no auth required).

    Creates:
    1. Supabase auth user (with org_id + role in metadata)
    2. Core noctus_users record
    3. Marks invitation as accepted
    """
    db = get_admin_client()

    # Validate token
    invite = validate_invitation(db, INVITATIONS_TABLE, body.token)

    org_id = invite["org_id"]
    email = invite["email"]
    role = invite["role"]

    # Format name
    nome_formatado = " ".join(
        word.capitalize() for word in body.nome.strip().split()
    )

    # Map PF role to org_role
    org_role = "admin" if role == "admin" else "member"

    # 1. Create auth user
    try:
        auth_result = db.auth.admin.create_user({
            "email": email,
            "password": body.password,
            "email_confirm": True,
            "user_metadata": {
                "nome": nome_formatado,
                "org_id": org_id,
            },
        })
    except Exception as e:
        error_msg = str(e).lower()
        if "already" in error_msg or "duplicate" in error_msg:
            raise HTTPException(status_code=409, detail="Este email ja esta cadastrado")
        logger.error("Failed to create auth user for invitation: %s", e)
        raise HTTPException(status_code=400, detail="Erro ao criar usuario")

    new_user_id = str(auth_result.user.id) if auth_result.user else None
    if not new_user_id:
        raise HTTPException(status_code=500, detail="Erro ao criar usuario — ID nao retornado")

    # 2. Create noctus_users record in public schema
    core = get_core_client()
    try:
        core.table("noctus_users").insert({
            "id": new_user_id,
            "nome": nome_formatado,
            "email": email,
            "org_id": org_id,
            "role": "user",
            "org_role": org_role,
        }).execute()
    except Exception as e:
        logger.error("Failed to create noctus_users record for %s: %s", new_user_id, e)
        # Clean up auth user on failure
        try:
            db.auth.admin.delete_user(new_user_id)
        except Exception:
            pass
        raise HTTPException(status_code=500, detail="Erro ao criar registro de usuario")

    # 3. Mark invitation as accepted
    accept_invitation(db, INVITATIONS_TABLE, invite["id"])

    logger.info(
        "Invitation accepted: user=%s email=%s org=%s role=%s",
        new_user_id, email, org_id, role,
    )

    return success_response({
        "user_id": new_user_id,
        "email": email,
        "nome": nome_formatado,
        "role": role,
    })


@router.get("/invitations")
async def listar_convites(authorization: Optional[str] = Header(None)):
    """List all pending invitations for the organization (admin only)."""
    user, token = await get_current_user(authorization)
    _require_pf_admin(user)
    org_id = _get_org_id(user)
    db = get_admin_client()

    invitations = list_pending_invitations(db, INVITATIONS_TABLE, org_id)
    return success_response(invitations, total=len(invitations))


@router.delete("/invitations/{invitation_id}")
async def cancelar_convite(invitation_id: str, authorization: Optional[str] = Header(None)):
    """Cancel a pending invitation (admin only)."""
    user, token = await get_current_user(authorization)
    _require_pf_admin(user)
    org_id = _get_org_id(user)
    db = get_admin_client()

    cancel_invitation(db, INVITATIONS_TABLE, invitation_id, org_id)

    logger.info("Invitation %s canceled by user %s", invitation_id, str(user.id))

    return ok_response("Convite cancelado")


@router.delete("/{user_id}")
async def remover_membro(user_id: str, authorization: Optional[str] = Header(None)):
    """Remove a member from the organization (admin only). Cannot remove self or org owner."""
    user, token = await get_current_user(authorization)
    _require_pf_admin(user)
    org_id = _get_org_id(user)
    core = get_core_client()

    # Cannot remove self
    if str(user.id) == user_id:
        raise HTTPException(status_code=400, detail="Voce nao pode remover a si mesmo")

    # Verify member exists in this org
    member = (
        core.table("noctus_users")
        .select("id, nome, email, org_id")
        .eq("id", user_id)
        .eq("org_id", org_id)
        .execute()
    )
    if not member.data:
        raise HTTPException(status_code=404, detail="Membro nao encontrado")

    # Check if target is org owner (cannot be removed)
    org = core.table("organizations").select("owner_id").eq("id", org_id).execute()
    if org.data and org.data[0].get("owner_id") == user_id:
        raise HTTPException(status_code=400, detail="Nao e possivel remover o proprietario da organizacao")

    # Remove from noctus_users
    core.table("noctus_users").delete().eq("id", user_id).eq("org_id", org_id).execute()

    logger.info("Member %s removed from org %s by user %s", user_id, org_id, str(user.id))

    return ok_response("Membro removido")
