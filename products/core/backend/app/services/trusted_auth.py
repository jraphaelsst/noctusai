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

from fastapi import Depends, Header, HTTPException, Request, Response

from noctusai_lib.api.auth.mfa.aal import read_aal
from noctusai_lib.api.auth.mfa.gate import ADMIN_TIER_ROLES, require_admin_assurance
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


async def get_session_aal(
    authorization: Optional[str] = Header(None),
    user: Any = Depends(get_session_user),
) -> Optional[str]:
    """`aal1`/`aal2` of the bearer token `get_session_user` just accepted.

    Read strictly AFTER validation and bound to the validated user's `sub`
    (`read_aal`). `None` when there is no bearer to read (an overridden user
    in tests) — the gate treats an unknown aal as aal1 (fails closed).
    """
    parts = (authorization or "").split(" ", 1)
    token = parts[1].strip() if len(parts) == 2 and parts[0].lower() == "bearer" else ""
    return read_aal(token, validated_user=user) if token else None


async def get_trusted_auth(
    user: Any = Depends(get_session_user),
    db: Any = Depends(get_trusted_db),
    aal: Optional[str] = Depends(get_session_aal),
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
        aal=aal,
    )


async def require_platform_admin_dep(
    ctx: AuthContext = Depends(get_trusted_auth),
    db: Any = Depends(get_trusted_db),
    request: Request = None,
    response: Response = None,
) -> AuthContext:
    """Strict platform admin (`noctus_users.role == 'admin'`); an org owner is not one.

    Assurance-gated like every product's admin factories (policy `off` = no-op).
    """
    if resolve_platform_admin_role(db, ctx.user_id) != "admin":
        raise HTTPException(
            status_code=403,
            detail={"detail": "Restrito a administradores da plataforma NoctusAI", "code": "platform_admin_required"},
        )
    await require_admin_assurance(
        request, response, caller_kind=ctx.caller_kind, aal=ctx.aal,
        user_id=ctx.user_id, org_id=ctx.org_id, role="admin",
    )
    return ctx


async def require_org_admin_dep(
    ctx: AuthContext = Depends(get_trusted_auth),
    db: Any = Depends(get_trusted_db),
    request: Request = None,
    response: Response = None,
) -> AuthContext:
    """owner / admin / manager of the caller's OWN org.

    Only the admin tier (`ADMIN_TIER_ROLES`: owner/admin) is assurance-gated;
    a `manager` passes at aal1 (owner decision `plat-mfa-who`, 2026-10-05).
    """
    role = resolve_org_role(db, ctx.user_id) if ctx.org_id else None
    if not ctx.org_id or role not in MANAGE_TEAM_ROLES:
        raise HTTPException(
            status_code=403,
            detail={"detail": "Restrito a administradores da organização", "code": "org_admin_required"},
        )
    if role in ADMIN_TIER_ROLES:
        await require_admin_assurance(
            request, response, caller_kind=ctx.caller_kind, aal=ctx.aal,
            user_id=ctx.user_id, org_id=ctx.org_id, role=role,
        )
    return ctx


__all__ = [
    "get_session_aal",
    "get_session_user",
    "get_trusted_auth",
    "get_trusted_db",
    "require_org_admin_dep",
    "require_platform_admin_dep",
]
