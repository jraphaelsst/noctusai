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

from app.database import get_admin_client
from app.dependencies import get_current_user, get_current_user_ungated
from app.rate_limit import limiter
from app.services.permissions import check_permission
from app.services import team_memberships
from app.schemas.team import AcceptInviteRequest, InviteCreate, TeamMemberRoleUpdate
from noctusai_lib.api.rate_limit_policies import DEFAULT_AUTH_RL
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


#: Who may grant which org role (mirror of the seed team router's ``_GRANT_REQUIRES``).
#: ``owner`` is NEVER grantable here -- not by invite, not by a role change, not by anyone
#: (ownership moves only through its dedicated flow). ``admin`` needs an inviter who is
#: already owner/admin, or the platform superadmin (``noctus_users.role = 'admin'``) inside
#: their own org -- without it any ``team:manage`` holder (e.g. a manager) could mint an
#: admin and take the org over.
_GRANT_REQUIRES = {"admin": frozenset({"owner", "admin"})}


def _require_can_grant(profile: dict, role: str) -> None:
    """403 unless the caller may hand out ``role`` (see ``_GRANT_REQUIRES``)."""
    if role == "owner":
        raise HTTPException(
            status_code=403,
            detail="Não é possível conceder o papel de proprietário por esta rota",
        )
    grantors = _GRANT_REQUIRES.get(role)
    if grantors is not None and profile.get("org_role") not in grantors and profile.get("role") != "admin":
        raise HTTPException(
            status_code=403,
            detail="Você não tem permissão para conceder este papel",
        )


def _require_can_touch_target(profile: dict, target_org_role: Optional[str]) -> None:
    """Acting ON a member (role change / removal) mirrors the grant rule: an ``owner`` target
    is untouchable here (strict 403); an ``admin`` target needs a caller who is owner/admin
    or the platform superadmin -- otherwise any ``team:manage`` holder (e.g. a manager) could
    demote or delete the admins above them."""
    if target_org_role == "owner":
        raise HTTPException(status_code=403, detail="Não é possível alterar o proprietário da organização")
    if target_org_role == "admin" and profile.get("org_role") not in _GRANT_REQUIRES["admin"] \
            and profile.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Você não tem permissão para alterar um administrador")


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

    # Members of THIS org = its ACTIVE memberships. noctus_users.org_id is only each user's
    # last-active org, so filtering on it would hide every member whose last-active org is elsewhere.
    return {"data": team_memberships.list_team(db, org_id)}


@router.post("/invite")
@limiter.limit(DEFAULT_AUTH_RL)
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
    _require_can_grant(profile, body.role)

    # Ensure the email is not already a member of this org (the profile is only the identity
    # lookup -- membership of THIS org is the org_memberships row).
    existing = (
        db.table("noctus_users")
        .select("id")
        .eq("email", body.email)
        .execute()
    )
    for row in existing.data or []:
        membership = team_memberships.get_membership(db, org_id, row["id"])
        if membership and membership.get("status") == "active":
            raise HTTPException(
                status_code=409,
                detail="Este e-mail já pertence a um membro da organização",
            )
        if membership and membership.get("status") == "suspended":
            raise HTTPException(
                status_code=409,
                detail="A participação deste e-mail nesta organização está suspensa",
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

    # The target is an ACTIVE MEMBERSHIP of this org (their profile may point at another org).
    target_membership = team_memberships.get_membership(db, org_id, user_id)
    if not target_membership or target_membership.get("status") != "active":
        raise HTTPException(status_code=404, detail="Membro não encontrado")
    target_role = target_membership.get("org_role")

    # Cannot remove the owner; removing an admin needs owner/admin (or superadmin)
    if target_role == "owner":
        raise HTTPException(
            status_code=403,
            detail="Não é possível remover o proprietário da organização",
        )
    _require_can_touch_target(profile, target_role)

    # Email for SSO cache invalidation (read BEFORE the remove: the profile may be deleted by it).
    target_profile = team_memberships.profiles_by_id(db, [user_id], "id, email").get(user_id) or {}

    # End the membership. ONE transaction (core team_membership_ops): when this org is the
    # user's profile org the profile moves to their most recently updated other ACTIVE
    # membership, or is deleted when there is none -- the deferred profile-org invariant
    # refuses anything else at COMMIT.
    outcome = team_memberships.remove_member(db, org_id, user_id)

    logger.info(f"Member {user_id} removed from org={org_id} ({outcome})")

    # Flush SSO cache for the removed user — compliance-audit Phase 6 (finding 9).
    try:
        from app.routers.sso import invalidate_sso_cache_for_user
        target_email = target_profile.get("email")
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
            details={
                "membership_ended": True,
                "profile_moved_to": outcome.get("profile_moved_to"),
                "profile_deleted": bool(outcome.get("profile_deleted")),
            },
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

    _require_can_grant(profile, body.role)

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

    # The target is an ACTIVE MEMBERSHIP of this org (their profile may point at another org).
    target_membership = team_memberships.get_membership(db, org_id, user_id)
    if not target_membership or target_membership.get("status") != "active":
        raise HTTPException(status_code=404, detail="Membro não encontrado")
    target_role = target_membership.get("org_role")

    # Cannot change the owner's role; changing an admin's needs owner/admin (or superadmin)
    if target_role == "owner":
        raise HTTPException(
            status_code=403,
            detail="Não é possível alterar o papel do proprietário",
        )
    _require_can_touch_target(profile, target_role)

    # Membership role + the profile mirror (only when this org IS the profile org): one transaction.
    outcome = team_memberships.set_member_role(db, org_id, user_id, body.role)

    logger.info(f"Member {user_id} role changed to {body.role} in org={org_id}")

    # Flush SSO cache for the mutated user — compliance-audit Phase 6 (finding 9).
    try:
        from app.routers.sso import invalidate_sso_cache_for_user
        target_email = team_memberships.profiles_by_id(db, [user_id], "id, email").get(user_id, {}).get("email")
        if target_email:
            invalidate_sso_cache_for_user(target_email)
    except Exception as exc:
        logger.warning("SSO cache invalidation after role change failed: %s", exc)

    try:
        from app.services import audit_service
        await audit_service.log(
            user_id=user.id, org_id=org_id,
            action="role_change", resource_type="team_member", resource_id=user_id,
            details={"from_role": target_role, "to_role": body.role},
        )
    except Exception as exc:
        logger.warning("team: role-change audit log failed for user_id=%s (%s); change succeeded", user_id, exc)

    return {"data": {
        "id": user_id,
        "org_id": outcome.get("org_id", org_id),
        "org_role": outcome.get("org_role", body.role),
    }}


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
@limiter.limit(DEFAULT_AUTH_RL)
async def aceitar_convite(
    request: Request,
    body: AcceptInviteRequest,
    authorization: Optional[str] = Header(None),
):
    """Accept an invitation by token.

    Requires authentication AND that the caller's email matches the invited
    address (case-insensitive) — 401 without auth, 403 on mismatch. If the
    request includes a `nome` field and the caller has no noctus_users
    profile yet, one is created.
    """
    db = get_admin_client()

    # Validate the invitation (checks pending + not expired)
    invite_data = validate_invitation(db, "invitations", body.token)

    # Acceptance REQUIRES an authenticated caller whose email IS the invited
    # address — otherwise anyone holding the link joins the org (or burns it).
    if not (authorization and authorization.startswith("Bearer ")):
        raise HTTPException(
            status_code=401,
            detail="Faça login com o email convidado para aceitar o convite",
        )
    # License-UNGATED on purpose: invitation acceptance onboards users whose org
    # lacks the license by definition; the email binding below is the control.
    authenticated_user, _ = await get_current_user_ungated(authorization)

    caller_email = (getattr(authenticated_user, "email", None) or "").strip().lower()
    invited_email = (invite_data.get("email") or "").strip().lower()
    if not caller_email or caller_email != invited_email:
        raise HTTPException(
            status_code=403,
            detail="Este convite foi enviado para outro email",
        )

    user_id = authenticated_user.id
    user_email = authenticated_user.email

    # Check if user already has a profile. A brand-new invitee has NONE — that is
    # the main path of an invite, so this MUST be maybe_single(): `.single()` raises
    # PGRST116 on 0 rows, which the global handler turns into a bare 404 and every
    # first-time invitee was locked out (2026-10-12). maybe_single() may also return
    # None itself (postgrest-py 0 rows), hence the double guard.
    existing_resp = (
        db.table("noctus_users")
        .select("id, org_id")
        .eq("id", user_id)
        .maybe_single()
        .execute()
    )
    existing_data = existing_resp.data if existing_resp is not None else None

    # Multi-org: belonging to another org is no reason to refuse. What decides is the user's
    # membership in the INVITING org: active -> already a member (409, replay stays refused);
    # suspended -> an org decision an invitation must not lift (403); removed/none -> join.
    membership = team_memberships.get_membership(db, invite_data["org_id"], user_id)
    if membership and membership.get("status") == "active":
        raise HTTPException(status_code=409, detail="Você já pertence a esta organização")
    if membership and membership.get("status") == "suspended":
        raise HTTPException(status_code=403, detail="Sua participação nesta organização está suspensa")

    if existing_data:
        # An EXISTING user: activate (or re-activate a removed) membership in the inviting org and
        # mark the invitation accepted -- one transaction. The profile does NOT move: their
        # last-active org stays, and the new org is reached through the platform org picker.
        team_memberships.accept_invitation_as_member(db, invite_data["id"], user_id)
    else:
        # First-time invitee: create the profile in the inviting org (the core 079 trigger
        # mirrors the ACTIVE membership).
        db.table("noctus_users").insert({
            "id": user_id,
            "email": user_email or invite_data["email"],
            "nome": body.nome or user_email or invite_data["email"],
            "org_id": invite_data["org_id"],
            "org_role": invite_data["role"],
            "role": "user",
        }).execute()
        mark_accepted(db, "invitations", invite_data["id"])

    try:
        from app.services import audit_service
        await audit_service.log(
            user_id=user_id, org_id=invite_data["org_id"],
            action="membership_added", resource_type="team_member", resource_id=user_id,
            details={
                "invitation_id": invite_data["id"], "org_role": invite_data["role"],
                "existing_user": bool(existing_data),
                "reactivated": bool(membership and membership.get("status") == "removed"),
            },
        )
    except Exception as exc:
        logger.warning("team: accept-invite audit log failed for user_id=%s (%s); acceptance succeeded", user_id, exc)

    return {
        "message": "Convite aceito com sucesso",
        "data": {
            "org_id": invite_data["org_id"],
            "role": invite_data["role"],
        },
    }
