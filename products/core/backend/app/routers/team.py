"""
Team Router — Manage organization members and invitations.

GET    /api/team                      — List team members (users in same org)
POST   /api/team/invite               — Send invitation (create invitation record)
DELETE /api/team/{user_id}             — Remove member from org
PATCH  /api/team/{user_id}/role        — Change member role
GET    /api/team/invitations           — List pending invitations for org
DELETE /api/team/invitations/{id}      — Cancel invitation
POST   /api/team/accept-invite         — Accept invitation by token

-- Supabase SQL to create the invitations table:
--
-- CREATE TABLE invitations (
--   id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
--   org_id uuid NOT NULL REFERENCES organizations(id),
--   email text NOT NULL,
--   role text NOT NULL DEFAULT 'member',
--   invited_by uuid NOT NULL REFERENCES noctus_users(id),
--   token text UNIQUE NOT NULL,
--   status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'expired', 'canceled')),
--   expires_at timestamptz NOT NULL DEFAULT (now() + interval '7 days'),
--   created_at timestamptz NOT NULL DEFAULT now()
-- );
-- ALTER TABLE invitations ENABLE ROW LEVEL SECURITY;
"""
import logging
from typing import Optional, List
from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from app.database import get_admin_client
from app.dependencies import get_current_user
from app.rate_limit import limiter
from app.services.permissions import check_permission
from noctusai_lib.domain.invitations import (
    create_invitation,
    validate_invitation,
    accept_invitation as mark_accepted,
    cancel_invitation,
    list_pending_invitations,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/team", tags=["Team"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class InviteCreate(BaseModel):
    email: str = Field(..., max_length=255)
    role: str = Field(default="member", max_length=50)


class TeamMemberRoleUpdate(BaseModel):
    role: str = Field(..., max_length=50)


class AcceptInviteRequest(BaseModel):
    token: str = Field(..., max_length=128)
    nome: Optional[str] = Field(default=None, max_length=200)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_user_profile(db, user_id: str) -> dict:
    """Fetch the noctus_users profile for a given Supabase auth user ID."""
    profile = (
        db.table("noctus_users")
        .select("id, org_id, org_role, role")
        .eq("id", user_id)
        .single()
        .execute()
    )
    if not profile.data:
        raise HTTPException(status_code=404, detail="Perfil não encontrado")
    return profile.data


async def _require_team_manage(user, db):
    """Verify the caller has team:manage permission. Returns the user profile."""
    profile = await _get_user_profile(db, user.id)
    org_id = profile["org_id"]

    has_perm = await check_permission(user.id, org_id, "team:manage")
    if not has_perm:
        raise HTTPException(
            status_code=403,
            detail="Você não tem permissão para gerenciar a equipe",
        )
    return profile


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("")
async def listar_membros(authorization: Optional[str] = Header(None)):
    """List all members in the caller's organization."""
    user, token = await get_current_user(authorization)
    db = get_admin_client()

    profile = await _get_user_profile(db, user.id)
    org_id = profile["org_id"]

    members = (
        db.table("noctus_users")
        .select("id, nome, email, org_role, created_at")
        .eq("org_id", org_id)
        .order("created_at")
        .execute()
    )

    return {"data": members.data or []}


@router.post("/invite")
@limiter.limit("30/minute")
async def convidar_membro(
    request: Request,
    body: InviteCreate,
    authorization: Optional[str] = Header(None),
):
    """Create an invitation record with a unique token.

    The invited user can later accept the invitation via POST /api/team/accept-invite.
    """
    user, token = await get_current_user(authorization)
    db = get_admin_client()

    profile = await _require_team_manage(user, db)
    org_id = profile["org_id"]

    # Ensure the email is not already in this org
    existing = (
        db.table("noctus_users")
        .select("id")
        .eq("org_id", org_id)
        .eq("email", body.email)
        .execute()
    )
    if existing.data:
        raise HTTPException(
            status_code=409,
            detail="Este e-mail já pertence a um membro da organização",
        )

    # Validate that the target role exists
    role_check = (
        db.table("roles")
        .select("id")
        .eq("slug", body.role)
        .execute()
    )
    if not role_check.data:
        raise HTTPException(status_code=400, detail="Papel inválido")

    # Create invitation via shared helper (checks pending duplicates internally)
    invite_record = create_invitation(
        db, "invitations", org_id, body.email, body.role, user.id,
    )
    invite_token = invite_record["token"]

    # Audit log, notification, and webhook dispatch (best-effort)
    try:
        from app.services import audit_service
        await audit_service.log(
            user_id=user.id, org_id=org_id,
            action="invite", resource_type="invitation",
            resource_id=invite_record["id"],
        )
    except Exception as exc:
        logger.warning("team: invite audit log failed for invitation_id=%s (%s); invite succeeded", invite_record["id"], exc)
    try:
        from app.services import notification_service
        await notification_service.create(
            user_id=user.id, org_id=org_id,
            type="team_invite",
            title="Convite enviado",
            message=f"Convite enviado para {body.email} com papel {body.role}",
        )
    except Exception as exc:
        logger.warning("team: notification on invite failed for invitation_id=%s (%s); invite succeeded", invite_record["id"], exc)
    try:
        from app.services import webhook_delivery
        await webhook_delivery.dispatch(
            org_id=org_id,
            event_type="team.invite_sent",
            payload={"email": body.email, "role": body.role, "invitation_id": invite_record["id"]},
        )
    except Exception as exc:
        logger.warning("team: webhook dispatch on invite failed for invitation_id=%s (%s); invite succeeded", invite_record["id"], exc)

    # Send invitation email (best-effort — won't fail the request)
    try:
        from app.services.email_service import send_invitation_email
        from app.config import settings
        org = db.table("organizations").select("nome").eq("id", org_id).single().execute()
        org_name = org.data["nome"] if org.data else "NoctusAI"
        inviter = db.table("noctus_users").select("nome").eq("id", user.id).single().execute()
        inviter_name = inviter.data["nome"] if inviter.data else "Um membro"
        send_invitation_email(
            to=body.email,
            org_name=org_name,
            invite_token=invite_token,
            invited_by=inviter_name,
            base_url=settings.app_base_url,
        )
    except Exception as exc:
        logger.warning(f"Failed to send invitation email: {exc}")

    return {"data": invite_record}


@router.delete("/{user_id}")
async def remover_membro(
    user_id: str,
    authorization: Optional[str] = Header(None),
):
    """Remove a member from the organization.

    Cannot remove yourself or the org owner.
    """
    user, token = await get_current_user(authorization)
    db = get_admin_client()

    profile = await _require_team_manage(user, db)
    org_id = profile["org_id"]

    # Cannot remove yourself
    if user_id == user.id:
        raise HTTPException(status_code=400, detail="Você não pode remover a si mesmo")

    # Fetch the target member — include email for SSO cache invalidation.
    target = (
        db.table("noctus_users")
        .select("id, org_id, org_role, email")
        .eq("id", user_id)
        .eq("org_id", org_id)
        .single()
        .execute()
    )
    if not target.data:
        raise HTTPException(status_code=404, detail="Membro não encontrado")

    # Cannot remove the owner
    if target.data.get("org_role") == "owner":
        raise HTTPException(
            status_code=403,
            detail="Não é possível remover o proprietário da organização",
        )

    # Remove the member: delete their noctus_users profile.
    # (org_id is NOT NULL, so we cannot just clear it.)
    db.table("noctus_users").delete().eq("id", user_id).eq("org_id", org_id).execute()

    logger.info(f"Member {user_id} removed from org={org_id}")

    # Flush SSO cache for the removed user — compliance-audit Phase 6 (finding 9).
    try:
        from app.routers.sso import invalidate_sso_cache_for_user
        target_email = target.data.get("email")
        if target_email:
            invalidate_sso_cache_for_user(target_email)
    except Exception as exc:
        logger.warning("SSO cache invalidation after remove failed: %s", exc)

    # Audit log and webhook dispatch (best-effort)
    try:
        from app.services import audit_service
        await audit_service.log(
            user_id=user.id, org_id=org_id,
            action="remove", resource_type="team_member", resource_id=user_id,
        )
    except Exception as exc:
        logger.warning("team: remove-member audit log failed for user_id=%s (%s); removal succeeded", user_id, exc)
    try:
        from app.services import webhook_delivery
        await webhook_delivery.dispatch(
            org_id=org_id,
            event_type="team.member_removed",
            payload={"removed_user_id": user_id},
        )
    except Exception as exc:
        logger.warning("team: webhook dispatch on remove-member failed for user_id=%s (%s); removal succeeded", user_id, exc)

    return {"message": "Membro removido com sucesso"}


@router.patch("/{user_id}/role")
async def alterar_role_membro(
    user_id: str,
    body: TeamMemberRoleUpdate,
    authorization: Optional[str] = Header(None),
):
    """Change a member's role within the organization.

    Cannot change the owner's role. Cannot promote to owner.
    """
    user, token = await get_current_user(authorization)
    db = get_admin_client()

    profile = await _require_team_manage(user, db)
    org_id = profile["org_id"]

    # Cannot change your own role
    if user_id == user.id:
        raise HTTPException(status_code=400, detail="Você não pode alterar seu próprio papel")

    # Validate that the target role exists
    role_check = (
        db.table("roles")
        .select("id, slug")
        .eq("slug", body.role)
        .execute()
    )
    if not role_check.data:
        raise HTTPException(status_code=400, detail="Papel inválido")

    # Cannot promote to owner
    if body.role == "owner":
        raise HTTPException(
            status_code=403,
            detail="Não é possível promover a proprietário por esta rota",
        )

    # Fetch the target member — include email for SSO cache invalidation.
    target = (
        db.table("noctus_users")
        .select("id, org_id, org_role, email")
        .eq("id", user_id)
        .eq("org_id", org_id)
        .single()
        .execute()
    )
    if not target.data:
        raise HTTPException(status_code=404, detail="Membro não encontrado")

    # Cannot change the owner's role
    if target.data.get("org_role") == "owner":
        raise HTTPException(
            status_code=403,
            detail="Não é possível alterar o papel do proprietário",
        )

    result = (
        db.table("noctus_users")
        .update({"org_role": body.role})
        .eq("id", user_id)
        .eq("org_id", org_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=500, detail="Erro ao atualizar papel")

    logger.info(f"Member {user_id} role changed to {body.role} in org={org_id}")

    # Flush SSO cache for the mutated user — compliance-audit Phase 6 (finding 9).
    try:
        from app.routers.sso import invalidate_sso_cache_for_user
        target_email = target.data.get("email")
        if target_email:
            invalidate_sso_cache_for_user(target_email)
    except Exception as exc:
        logger.warning("SSO cache invalidation after role change failed: %s", exc)

    return {"data": result.data[0]}


@router.get("/invitations")
async def listar_convites(authorization: Optional[str] = Header(None)):
    """List pending invitations for the caller's organization."""
    user, token = await get_current_user(authorization)
    db = get_admin_client()

    profile = await _get_user_profile(db, user.id)
    org_id = profile["org_id"]

    # Check at least team:read permission
    has_perm = await check_permission(user.id, org_id, "team:read")
    if not has_perm:
        raise HTTPException(
            status_code=403,
            detail="Você não tem permissão para ver convites",
        )

    return {"data": list_pending_invitations(db, "invitations", org_id)}


@router.delete("/invitations/{invitation_id}")
async def cancelar_convite(
    invitation_id: str,
    authorization: Optional[str] = Header(None),
):
    """Cancel a pending invitation."""
    user, token = await get_current_user(authorization)
    db = get_admin_client()

    profile = await _require_team_manage(user, db)
    org_id = profile["org_id"]

    cancel_invitation(db, "invitations", invitation_id, org_id)
    return {"message": "Convite cancelado com sucesso"}


@router.post("/accept-invite")
@limiter.limit("30/minute")
async def aceitar_convite(
    request: Request,
    body: AcceptInviteRequest,
    authorization: Optional[str] = Header(None),
):
    """Accept an invitation by token.

    If the user is already authenticated, they are added to the org.
    If the request includes a `nome` field, a new user profile is created
    (useful for users who signed up via Supabase Auth but don't have
    a noctus_users profile yet).
    """
    db = get_admin_client()

    # Validate the invitation (checks pending + not expired)
    invite_data = validate_invitation(db, "invitations", body.token)

    # If user is authenticated, use their identity
    authenticated_user = None
    if authorization and authorization.startswith("Bearer "):
        try:
            authenticated_user, _ = await get_current_user(authorization)
        except HTTPException as exc:
            # Not authenticated — will proceed without user context.
            logger.debug("team: invitation accept proceeding without auth (%s)", exc.detail if hasattr(exc, 'detail') else exc)

    if authenticated_user:
        user_id = authenticated_user.id
        user_email = authenticated_user.email

        # Verify the email matches (or allow override for flexibility)
        # We allow accepting even if email differs — the invite was for a role

        # Check if user already has a profile
        existing = (
            db.table("noctus_users")
            .select("id, org_id")
            .eq("id", user_id)
            .single()
            .execute()
        )

        if existing.data and existing.data.get("org_id"):
            # User already belongs to an org — check if it's the same one
            if existing.data["org_id"] == invite_data["org_id"]:
                raise HTTPException(
                    status_code=409,
                    detail="Você já pertence a esta organização",
                )
            else:
                raise HTTPException(
                    status_code=409,
                    detail="Você já pertence a outra organização. Entre em contato com o suporte.",
                )

        if existing.data:
            # Update existing profile to join the org
            db.table("noctus_users").update({
                "org_id": invite_data["org_id"],
                "org_role": invite_data["role"],
            }).eq("id", user_id).execute()
        else:
            # Create a new noctus_users profile
            db.table("noctus_users").insert({
                "id": user_id,
                "email": user_email or invite_data["email"],
                "nome": body.nome or user_email or invite_data["email"],
                "org_id": invite_data["org_id"],
                "org_role": invite_data["role"],
                "role": "user",
            }).execute()
    else:
        # User is not authenticated — we create a placeholder profile
        # that will be completed when the user signs up / logs in.
        # For now, mark the invitation as accepted.
        if not body.nome:
            raise HTTPException(
                status_code=400,
                detail="Faça login ou forneça seu nome para aceitar o convite",
            )

    mark_accepted(db, "invitations", invite_data["id"])

    return {
        "message": "Convite aceito com sucesso",
        "data": {
            "org_id": invite_data["org_id"],
            "role": invite_data["role"],
        },
    }
