"""
Team Management Router — Employee invitations and member management.

Uses the shared invitation system (noctusai_shared.invitations) for token
generation, validation, and lifecycle.  Admin operations (invite, remove,
role change) require platform_admin or ERP admin role.
"""
from __future__ import annotations

import logging
from typing import Literal, Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, EmailStr, Field

from app.dependencies import (
    get_current_user,
    get_admin_client,
    get_org_id,
    get_user_role,
    log_action,
)
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

# Valid ERP roles for invitations
ERP_ROLES = ("admin", "coordenador", "dev", "corretor")

ERP_ROLE_LABELS = {
    "admin": "Administrador",
    "coordenador": "Coordenador",
    "dev": "Desenvolvedor",
    "corretor": "Corretor",
}

# Frontend base URL for invitation links
ERP_FRONTEND_URL = "http://localhost:8080"

INVITATIONS_TABLE = "invitations"


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class InviteBody(BaseModel):
    email: EmailStr
    role: Literal["admin", "coordenador", "dev", "corretor"]


class AcceptInviteBody(BaseModel):
    token: str
    nome: str = Field(..., min_length=2, max_length=120)
    password: str = Field(..., min_length=6, max_length=128)


class ChangeRoleBody(BaseModel):
    role: Literal["admin", "coordenador", "dev", "corretor"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _require_erp_admin(user) -> None:
    """Raise 403 if the user is neither a platform_admin nor an ERP admin."""
    role = get_user_role(user)
    if role == "platform_admin":
        return

    # Check ERP-native admin role in user_roles table
    db = get_admin_client()
    check = (
        db.table("user_roles")
        .select("role")
        .eq("user_id", str(user.id))
        .eq("role", "admin")
        .execute()
    )
    if not check.data:
        raise HTTPException(status_code=403, detail="Acesso restrito a administradores")


def _get_org_name(db, org_id: str) -> str:
    """Fetch organization name from the core public schema."""
    from app.database import get_core_client

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
    """List all organization members (profiles with auth user info)."""
    user, token = await get_current_user(authorization)
    org_id = get_org_id(user, required=True)
    db = get_admin_client()

    # Fetch profiles scoped to org
    profiles = (
        db.table("profiles")
        .select("id, nome, email, telefone, cargo, avatar_url, created_at")
        .eq("org_id", org_id)
        .order("created_at", desc=True)
        .execute()
    )
    members = profiles.data or []

    if not members:
        return success_response([], total=0)

    # Batch-fetch roles for all members
    member_ids = [m["id"] for m in members]
    roles_result = (
        db.table("user_roles")
        .select("user_id, role")
        .in_("user_id", member_ids)
        .execute()
    )
    role_map = {r["user_id"]: r["role"] for r in (roles_result.data or [])}

    # Enrich members with their role
    for member in members:
        member["role"] = role_map.get(member["id"], "corretor")

    return success_response(members, total=len(members))


@router.post("/invite")
async def convidar_membro(body: InviteBody, authorization: Optional[str] = Header(None)):
    """Invite a new employee to the organization (admin only)."""
    user, token = await get_current_user(authorization)
    _require_erp_admin(user)
    org_id = get_org_id(user, required=True)
    db = get_admin_client()

    # Check if email is already a member
    existing = (
        db.table("profiles")
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
    org_name = _get_org_name(db, org_id)
    inviter_name = _get_user_display_name(user)
    role_label = ERP_ROLE_LABELS.get(body.role, body.role.capitalize())

    send_product_invitation_email(
        to=body.email,
        product_name="ERP Imobiliario",
        org_name=org_name,
        role_label=role_label,
        invite_token=invite["token"],
        invited_by=inviter_name,
        base_url=ERP_FRONTEND_URL,
    )

    log_action(
        str(user.id), "convidar", "membro", invite["id"],
        f"Convidou {body.email} como {role_label}",
        {"email": body.email, "role": body.role},
    )

    return success_response(invite)


@router.get("/accept/validate")
async def validar_convite(token: str):
    """Validate an invitation token and return invite info for the form.

    Public endpoint — no auth required.
    """
    db = get_admin_client()
    invite = validate_invitation(db, INVITATIONS_TABLE, token)

    # Look up org name
    org_name = "Organizacao"
    try:
        core_db = get_core_client()
        org = core_db.table("organizations").select("nome").eq(
            "id", invite["org_id"]
        ).single().execute()
        if org.data:
            org_name = org.data["nome"]
    except Exception:
        pass

    role_labels = {
        "admin": "Administrador", "coordenador": "Coordenador",
        "dev": "Desenvolvedor", "corretor": "Corretor",
    }

    return {
        "email": invite["email"],
        "role": invite["role"],
        "role_label": role_labels.get(invite["role"], invite["role"]),
        "org_name": org_name,
    }


@router.post("/accept")
async def aceitar_convite(body: AcceptInviteBody):
    """Accept an invitation — public endpoint (no auth required).

    Creates:
    1. Supabase auth user (with org_id in metadata)
    2. erp.profiles record
    3. erp.user_roles record
    4. Marks invitation as accepted
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

    # 2. Create erp.profiles record
    try:
        db.table("profiles").insert({
            "id": new_user_id,
            "nome": nome_formatado,
            "email": email,
            "org_id": org_id,
        }).execute()
    except Exception as e:
        logger.error("Failed to create ERP profile for %s: %s", new_user_id, e)
        # Clean up auth user on failure
        try:
            db.auth.admin.delete_user(new_user_id)
        except Exception:
            pass
        raise HTTPException(status_code=500, detail="Erro ao criar perfil")

    # 3. Create erp.user_roles record
    try:
        db.table("user_roles").insert({
            "user_id": new_user_id,
            "role": role,
        }).execute()
    except Exception as e:
        logger.error("Failed to assign role for %s: %s", new_user_id, e)
        # Profile and auth user already exist — log but don't fail
        # The user can still log in, and an admin can fix the role later

    # 4. Mark invitation as accepted
    accept_invitation(db, INVITATIONS_TABLE, invite["id"])

    log_action(
        new_user_id, "aceitar_convite", "membro", invite["id"],
        f"{nome_formatado} aceitou convite como {ERP_ROLE_LABELS.get(role, role)}",
        {"email": email, "role": role, "invited_by": invite.get("invited_by")},
    )

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
    _require_erp_admin(user)
    org_id = get_org_id(user, required=True)
    db = get_admin_client()

    invitations = list_pending_invitations(db, INVITATIONS_TABLE, org_id)
    return success_response(invitations, total=len(invitations))


@router.delete("/invitations/{invitation_id}")
async def cancelar_convite(invitation_id: str, authorization: Optional[str] = Header(None)):
    """Cancel a pending invitation (admin only)."""
    user, token = await get_current_user(authorization)
    _require_erp_admin(user)
    org_id = get_org_id(user, required=True)
    db = get_admin_client()

    cancel_invitation(db, INVITATIONS_TABLE, invitation_id, org_id)

    log_action(
        str(user.id), "cancelar_convite", "convite", invitation_id,
        f"Cancelou convite {invitation_id}",
    )

    return ok_response("Convite cancelado")


@router.delete("/{user_id}")
async def remover_membro(user_id: str, authorization: Optional[str] = Header(None)):
    """Remove a member from the organization (admin only). Cannot remove self or org owner."""
    user, token = await get_current_user(authorization)
    _require_erp_admin(user)
    org_id = get_org_id(user, required=True)
    db = get_admin_client()

    # Cannot remove self
    if str(user.id) == user_id:
        raise HTTPException(status_code=400, detail="Voce nao pode remover a si mesmo")

    # Verify member exists in this org
    member = (
        db.table("profiles")
        .select("id, nome, email, org_id")
        .eq("id", user_id)
        .eq("org_id", org_id)
        .execute()
    )
    if not member.data:
        raise HTTPException(status_code=404, detail="Membro nao encontrado")

    member_data = member.data[0]

    # Check if target is org owner (cannot be removed)
    from app.database import get_core_client

    core = get_core_client()
    org = core.table("organizations").select("owner_id").eq("id", org_id).execute()
    if org.data and org.data[0].get("owner_id") == user_id:
        raise HTTPException(status_code=400, detail="Nao e possivel remover o proprietario da organizacao")

    # Remove user_roles entry
    db.table("user_roles").delete().eq("user_id", user_id).execute()

    # Remove profile
    db.table("profiles").delete().eq("id", user_id).eq("org_id", org_id).execute()

    log_action(
        str(user.id), "remover", "membro", user_id,
        f"Removeu membro {member_data.get('nome', user_id)}",
        {"email": member_data.get("email"), "removed_user_id": user_id},
    )

    return ok_response("Membro removido")


@router.patch("/{user_id}/role")
async def alterar_role(user_id: str, body: ChangeRoleBody, authorization: Optional[str] = Header(None)):
    """Change a member's role (admin only)."""
    user, token = await get_current_user(authorization)
    _require_erp_admin(user)
    org_id = get_org_id(user, required=True)
    db = get_admin_client()

    # Cannot change own role
    if str(user.id) == user_id:
        raise HTTPException(status_code=400, detail="Voce nao pode alterar seu proprio cargo")

    # Verify member belongs to org
    member = (
        db.table("profiles")
        .select("id, nome")
        .eq("id", user_id)
        .eq("org_id", org_id)
        .execute()
    )
    if not member.data:
        raise HTTPException(status_code=404, detail="Membro nao encontrado")

    # Upsert role (some members might not have a user_roles record yet)
    existing_role = (
        db.table("user_roles")
        .select("id")
        .eq("user_id", user_id)
        .execute()
    )

    if existing_role.data:
        db.table("user_roles").update({"role": body.role}).eq("user_id", user_id).execute()
    else:
        db.table("user_roles").insert({"user_id": user_id, "role": body.role}).execute()

    member_nome = member.data[0].get("nome", user_id)
    role_label = ERP_ROLE_LABELS.get(body.role, body.role)

    log_action(
        str(user.id), "alterar_role", "membro", user_id,
        f"Alterou cargo de {member_nome} para {role_label}",
        {"new_role": body.role, "target_user_id": user_id},
    )

    return success_response({"user_id": user_id, "role": body.role})
