"""
NoctusAI Core — Granular RBAC permission service.

Permission format: "resource:action" e.g. "team:manage", "billing:manage"
Wildcard "*" grants all permissions (owner role).
"""
import logging
from typing import List, Optional
from fastapi import Header, HTTPException

from app.database import get_admin_client
from app.dependencies import get_current_user

logger = logging.getLogger(__name__)


async def get_user_permissions(user_id: str) -> List[str]:
    """Fetch the permission list for a user based on their org role."""
    db = get_admin_client()

    # Get user profile with role slug
    profile = (
        db.table("noctus_users")
        .select("org_id, org_role")
        .eq("id", user_id)
        .single()
        .execute()
    )
    if not profile.data:
        return []

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
    permissions = await get_user_permissions(user_id)

    # Wildcard grants everything
    if "*" in permissions:
        return True

    # Exact match
    if permission_slug in permissions:
        return True

    # Check hierarchical match: "team:manage" satisfies "team:read"
    # A "manage" permission on a resource implies "read" on the same resource
    resource = permission_slug.split(":")[0] if ":" in permission_slug else permission_slug
    action = permission_slug.split(":")[1] if ":" in permission_slug else ""

    if action == "read":
        # "resource:manage" implies "resource:read"
        if f"{resource}:manage" in permissions:
            return True

    # "products:access" implies "products:access:readonly"
    if ":readonly" in permission_slug:
        base = permission_slug.replace(":readonly", "")
        if base in permissions:
            return True

    return False


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

        profile = (
            db.table("noctus_users")
            .select("org_id")
            .eq("id", user.id)
            .single()
            .execute()
        )
        if not profile.data:
            raise HTTPException(status_code=403, detail="Perfil não encontrado")

        org_id = profile.data["org_id"]
        has_perm = await check_permission(user.id, org_id, slug)

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
