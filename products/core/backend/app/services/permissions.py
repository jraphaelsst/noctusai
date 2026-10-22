"""
NoctusAI Core — Granular RBAC permission service.

Permission format: "resource:action" e.g. "team:manage", "billing:manage"
Wildcard "*" grants all permissions (owner role).
"""
import logging
from typing import List, Optional
from fastapi import Header, HTTPException

from noctusai_lib.api.auth._blocking import run_blocking
from app.database import get_admin_client
from app.dependencies import get_current_user
from noctusai_lib.api.auth.platform import resolve_platform_admin_role

logger = logging.getLogger(__name__)


def _load_profile_and_permissions(db, user_id: str) -> Optional[List[str]]:
    """SYNC (run it via ``run_blocking``): the caller's permissions -- profile, then the role row
    (org-specific first, then the system role). ``None`` when there is no profile."""
    profile = (
        db.table("noctus_users")
        .select("org_id, org_role")
        .eq("id", user_id)
        .single()
        .execute()
    )
    if not profile.data:
        return None

    org_id = profile.data.get("org_id")
    role_slug = profile.data.get("org_role", "member")

    # Look up role: first org-specific, then system-level
    role_record = (
        db.table("roles")
        .select("permissions")
        .eq("slug", role_slug)
        .eq("org_id", org_id)
        .execute()
    )
    if not role_record.data:
        # Fallback to system role (org_id IS NULL)
        role_record = (
            db.table("roles")
            .select("permissions")
            .eq("slug", role_slug)
            .is_("org_id", "null")
            .execute()
        )
    if not role_record.data:
        return []
    return role_record.data[0].get("permissions", [])


async def get_user_permissions(user_id: str) -> List[str]:
    """Fetch the permission list for a user based on their org role (off the event loop)."""
    permissions = await run_blocking(_load_profile_and_permissions, get_admin_client(), user_id)
    return permissions or []


def _grants(permissions: List[str], permission_slug: str) -> bool:
    """Pure: does ``permissions`` grant ``permission_slug`` (wildcard, exact, manage=>read, readonly)?"""
    if "*" in permissions:
        return True
    if permission_slug in permissions:
        return True
    resource = permission_slug.split(":")[0] if ":" in permission_slug else permission_slug
    action = permission_slug.split(":")[1] if ":" in permission_slug else ""
    if action == "read" and f"{resource}:manage" in permissions:
        return True
    if ":readonly" in permission_slug and permission_slug.replace(":readonly", "") in permissions:
        return True
    return False


async def check_permission(user_id: str, org_id: str, permission_slug: str) -> bool:
    """Check if a user's role grants the required permission.

    Args:
        user_id: The Supabase auth user ID.
        org_id: The organization ID (used for context, but permissions
                are resolved from the user's role).
        permission_slug: Permission to check, e.g. "team:manage".

    Returns:
        True if the user has the permission, False otherwise.
    """
    return _grants(await get_user_permissions(user_id), permission_slug)


async def require_org_permission(
    user_id: str,
    org_id: str,
    permission_slug: str,
    *,
    detail: Optional[str] = None,
) -> None:
    """Imperative 403 gate for an org-scoped action — the ONE place core's
    routers ask "may this caller do <permission_slug> in <org_id>?".

    ``org_id`` MUST be the caller's TRUSTED org (``app.dependencies.get_org_id``,
    which reads ``public.noctus_users``) — this gate authorizes the action, the
    trusted org scopes it; neither replaces the other.

    Passes when the caller's org role grants ``permission_slug``
    (:func:`check_permission` — ``roles`` table, org-specific then system) OR
    the caller is a NoctusAI platform operator (``noctus_users.role == 'admin'``,
    via the seed's strict :func:`resolve_platform_admin_role` — never the
    owner/admin CASCADE). The operator branch exists because core's ``/admin/*``
    pages drive these same org-scoped endpoints; it still acts only inside the
    operator's own trusted ``org_id``.

    SEC-1 (2026-09-28): ``/api/settings/org`` writes, ``/api/webhooks``,
    ``/api/api-keys`` writes and ``PATCH /api/organizations/{id}`` authenticated
    the caller and scoped by org but never asked this question — any member
    could rotate the org's API keys, read webhook signing secrets, or flip the
    org's ``category`` to ``test`` (which bypasses every entitlement check).
    """
    if await check_permission(user_id, org_id, permission_slug):
        return
    if await run_blocking(resolve_platform_admin_role, get_admin_client(), user_id) == "admin":
        return
    raise HTTPException(
        status_code=403,
        detail=detail or f"Permissão necessária: {permission_slug}",
    )


def require_permission(slug: str):
    """FastAPI dependency factory that checks permission and raises 403 if denied.

    Usage:
        @router.post("/some-endpoint")
        async def my_endpoint(
            authorization: Optional[str] = Header(None),
            _perm=Depends(require_permission("team:manage")),
        ):
            ...
    """

    async def _check(authorization: Optional[str] = Header(None)):
        user, token = await get_current_user(authorization)
        db = get_admin_client()

        # ONE worker hop, ONE profile read (the old shape read the profile twice: here and again
        # inside check_permission) -> profile + role row.
        permissions = await run_blocking(_load_profile_and_permissions, db, user.id)
        if permissions is None:
            raise HTTPException(status_code=403, detail="Perfil não encontrado")
        has_perm = _grants(permissions, slug)

        if not has_perm:
            raise HTTPException(
                status_code=403,
                detail=f"Permissão necessária: {slug}",
            )

        return user, token

    return _check


async def get_current_user_with_permissions(
    authorization: Optional[str] = Header(None),
):
    """Authenticate user and return (user, token, permissions_list).

    This is a convenience dependency that combines authentication
    with permission loading in a single call.
    """
    user, token = await get_current_user(authorization)
    permissions = await get_user_permissions(user.id)
    return user, token, permissions
