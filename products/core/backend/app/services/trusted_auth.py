"""Trusted FastAPI auth dependencies (billing + platform-admin routes).

Composed from the seed's `require_platform_admin` / `require_org_admin`
(`noctusai_lib.api.auth.platform`), both of which read the trusted
`public.noctus_users` row — never `user_metadata`, which a user can rewrite.

The client both checks use comes from `get_trusted_db`, a dependency, and
the caller identity from `get_trusted_auth` — so a test swaps either one
with `app.dependency_overrides` and still runs the real role checks.
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import Depends, Header, HTTPException

from noctusai_lib.api.auth.platform import resolve_platform_admin_role
from noctusai_lib.api.auth.session.scopes import resolve_org_role
from noctusai_lib.api.auth.session.types import AuthContext
from noctusai_lib.primitives.roles import MANAGE_TEAM_ROLES

from app import database
from app.dependencies import get_current_user


def get_trusted_db() -> Any:
    """Service-role client for trusted role reads (overridable).

    Resolved through the module attribute at call time so the legacy
    conftest (which swaps `app.database.get_admin_client`) and the
    `dependency_overrides` route both reach the same client.
    """
    return database.get_admin_client()


async def get_session_user(authorization: Optional[str] = Header(None)) -> Any:
    """The Supabase user behind the bearer token (401 when absent/invalid)."""
    user, _token = await get_current_user(authorization)
    return user


async def get_trusted_auth(
    user: Any = Depends(get_session_user),
    db: Any = Depends(get_trusted_db),
) -> AuthContext:
    """401 on a missing/invalid token; org resolved from `noctus_users`.

    `org_id` is None for a user with no org (a platform operator may have
    none); every org-scoped dependency refuses that case itself.
    """
    rows = (
        db.table("noctus_users").select("org_id").eq("id", str(user.id)).limit(1).execute().data or []
    )
    org_id = rows[0].get("org_id") if rows else None
    return AuthContext(
        org_id=str(org_id) if org_id else None,  # type: ignore[arg-type]
        caller_kind="user",
        user_id=str(user.id),  # type: ignore[arg-type]
        scopes=[],
        raw_token="session",
        api_token_id=None,
    )


async def require_platform_admin_dep(
    ctx: AuthContext = Depends(get_trusted_auth),
    db: Any = Depends(get_trusted_db),
) -> AuthContext:
    """Strict platform admin (`noctus_users.role == 'admin'`); an org owner is not one."""
    if resolve_platform_admin_role(db, ctx.user_id) != "admin":
        raise HTTPException(
            status_code=403,
            detail={"detail": "Restrito a administradores da plataforma NoctusAI", "code": "platform_admin_required"},
        )
    return ctx


async def require_org_admin_dep(
    ctx: AuthContext = Depends(get_trusted_auth),
    db: Any = Depends(get_trusted_db),
) -> AuthContext:
    """owner / admin / manager of the caller's OWN org."""
    if not ctx.org_id or resolve_org_role(db, ctx.user_id) not in MANAGE_TEAM_ROLES:
        raise HTTPException(
            status_code=403,
            detail={"detail": "Restrito a administradores da organização", "code": "org_admin_required"},
        )
    return ctx


__all__ = [
    "get_session_user",
    "get_trusted_auth",
    "get_trusted_db",
    "require_org_admin_dep",
    "require_platform_admin_dep",
]
