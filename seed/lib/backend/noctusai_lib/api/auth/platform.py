"""Authorization spine for four distinct actor classes:

  1. **Platform admin** — the NoctusAI operator (`require_platform_admin`).
  2. **Org admin** — an agency's owner/admin/manager, scoped to their
     OWN org (`require_org_admin`).
  3. **Permission-grant holder** — a named, product-agnostic capability
     (`require_permission`).
  4. Everyone else (plain org member) — satisfies none of the above.

🔴 **Platform admin ≠ org admin.** `require_platform_admin` gates the
NoctusAI-*operator* surface (support/ops tooling, cross-org data). It
checks ONLY `public.noctus_users.role == 'admin'` and NEVER falls
through to an org's `org_role` — conflating the two lets any agency
owner reach cross-org data. This is deliberately narrower than
`noctusai_lib.api.auth.make_resolve_platform_role` (via
`_resolve_trusted_platform_role`), which CASCADES an org's
owner/admin `org_role` into a `"platform_admin"` verdict for the SSO
product-admin-on-entry use case — correct for THAT caller, wrong for
this one. Do not reuse that cascade here.

All three dependencies compose on top of a product's own
`AuthContext` resolver (`noctusai_lib.api.auth.session.
make_get_auth_context`) — a missing/invalid credential 401s from THAT
dependency; this module only ever raises `403`. Mirrors
`noctusai_lib.api.auth.session.scopes.require_scopes`'s composition
shape.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Optional

from fastapi import Depends, HTTPException

from noctusai_lib.api.auth.session.scopes import resolve_org_role
from noctusai_lib.api.auth.session.types import AuthContext
from noctusai_lib.domain.permissions.repo import PermissionGrantRepository
from noctusai_lib.primitives.roles import MANAGE_TEAM_ROLES

# ---------------------------------------------------------------------------
# Platform admin
# ---------------------------------------------------------------------------


def resolve_platform_admin_role(core_client: Any, user_id: Any) -> str | None:
    """Trusted-DB read of ONLY `public.noctus_users.role`.

    Deliberately narrower than `_resolve_trusted_platform_role` in
    `noctusai_lib.api.auth` (the `__init__.py` module) — that helper
    ALSO returns `"platform_admin"` when `org_role` is `owner`/`admin`
    (the SSO-entry cascade). This helper reads `role` ONLY and never
    consults `org_role` — a platform admin and an org admin are
    different actors, and this dependency must not blur them.

    Args:
        core_client: A `public`-schema-scoped Supabase client (e.g.
            `deps.get_core_client()`) — `noctus_users` lives in
            `public`, NOT a product's own schema.
        user_id: The caller's user id. Accepts `None` (a product-token
            caller has no `user_id`) and returns `None` immediately —
            no row lookup is attempted.

    Returns:
        The raw `role` string (e.g. `"admin"`, `"manager"`, `"user"`)
        or `None` when `user_id` is `None` or no matching row exists.

    Raises:
        Whatever the underlying client raises on a genuine DB/transport
        failure — NOT swallowed here. An unresolvable role must
        surface, never silently resolve to deny (or allow).
    """
    if user_id is None:
        return None
    lookup = (
        core_client.from_("noctus_users")
        .select("role")
        .eq("id", str(user_id))
        .limit(1)
        .execute()
    )
    rows = lookup.data or []
    if not rows:
        return None
    return rows[0].get("role")


def require_platform_admin(
    *,
    get_auth_context: Callable[..., Awaitable[AuthContext]],
    get_core_client: Callable[[], Any],
) -> Callable[..., Awaitable[AuthContext]]:
    """Build a FastAPI dependency enforcing strict platform-admin access.

    Args:
        get_auth_context: The product's own `get_auth_context` dep
            (composed via `Depends(...)`). A missing/invalid credential
            401s from THAT dep, never from here.
        get_core_client: Zero-arg callable returning a `public`-schema-
            scoped Supabase client, for the trusted-DB role read
            (`resolve_platform_admin_role`).

    Returns:
        An async dependency suitable for `Depends(...)`, returning the
        (unchanged) resolved `AuthContext` on success. Raises `403`
        (code `platform_admin_required`) for anyone whose
        `noctus_users.role` is not literally `"admin"` — including a
        `caller_kind == "product"` token (no `user_id` to resolve) and
        an org owner/admin (org-level admin never satisfies this).
    """

    async def _dependency(
        ctx: AuthContext = Depends(get_auth_context),
    ) -> AuthContext:
        role = resolve_platform_admin_role(get_core_client(), ctx.user_id)
        if role != "admin":
            raise HTTPException(
                status_code=403,
                detail={
                    "detail": "Restrito a administradores da plataforma NoctusAI",
                    "code": "platform_admin_required",
                },
            )
        return ctx

    return _dependency


# ---------------------------------------------------------------------------
# Org admin
# ---------------------------------------------------------------------------


def require_org_admin(
    *,
    get_auth_context: Callable[..., Awaitable[AuthContext]],
    get_core_client: Callable[[], Any],
    get_target_org_id: Optional[Callable[..., Any]] = None,
) -> Callable[..., Awaitable[AuthContext]]:
    """Build a FastAPI dependency enforcing org-admin access, scoped to
    the caller's OWN org.

    Reuses the EXISTING trusted resolver `resolve_org_role` (from
    `noctusai_lib.api.auth.session.scopes`) — the role is never
    re-derived here.

    Args:
        get_auth_context: The product's own `get_auth_context` dep.
        get_core_client: Zero-arg callable returning a `public`-schema-
            scoped Supabase client, threaded unchanged into
            `resolve_org_role`.
        get_target_org_id: Optional dependency callable (wired via
            `Depends(...)` at build time — e.g. a path-param binder
            such as `def _org_id_path(org_id: UUID) -> UUID: return
            org_id`) resolving the org id the ROUTE operates on. When
            supplied, the caller's own trusted `ctx.org_id` MUST equal
            it, else `403` (code `cross_org_denied`) — BEFORE the role
            check runs. This is the cross-org guard: an org A
            owner/admin/manager must not satisfy this dependency for
            org B merely by holding an admin-tier role, since the role
            lookup alone says nothing about WHICH org's resource is
            being accessed. Omit for endpoints that only ever act on
            the caller's own org (self-service team pages) — nothing
            to compare against.

    Returns:
        An async dependency suitable for `Depends(...)`, returning the
        (unchanged) resolved `AuthContext` on success. Raises `403`
        (code `org_admin_required`) when the caller's `org_role` is not
        in `("owner", "admin", "manager")`, or `403` (code
        `cross_org_denied`) when `get_target_org_id` is supplied and
        disagrees with `ctx.org_id`.
    """

    if get_target_org_id is not None:

        async def _dependency(
            ctx: AuthContext = Depends(get_auth_context),
            target_org_id: Any = Depends(get_target_org_id),
        ) -> AuthContext:
            if str(ctx.org_id) != str(target_org_id):
                raise HTTPException(
                    status_code=403,
                    detail={
                        "detail": "Acesso negado a outra organizacao",
                        "code": "cross_org_denied",
                    },
                )
            role = resolve_org_role(get_core_client(), ctx.user_id)
            if role not in MANAGE_TEAM_ROLES:
                raise HTTPException(
                    status_code=403,
                    detail={
                        "detail": "Restrito a administradores da organizacao",
                        "code": "org_admin_required",
                    },
                )
            return ctx

        return _dependency

    async def _dependency_self_org(
        ctx: AuthContext = Depends(get_auth_context),
    ) -> AuthContext:
        role = resolve_org_role(get_core_client(), ctx.user_id)
        if role not in MANAGE_TEAM_ROLES:
            raise HTTPException(
                status_code=403,
                detail={
                    "detail": "Restrito a administradores da organizacao",
                    "code": "org_admin_required",
                },
            )
        return ctx

    return _dependency_self_org


# ---------------------------------------------------------------------------
# Named permission grant
# ---------------------------------------------------------------------------


def require_permission(
    name: str,
    *,
    get_auth_context: Callable[..., Awaitable[AuthContext]],
    get_permission_repo: Callable[[], PermissionGrantRepository],
) -> Callable[..., Awaitable[AuthContext]]:
    """Build a FastAPI dependency enforcing a named, product-agnostic
    permission grant.

    Args:
        name: The opaque permission string a caller must hold (e.g.
            `"photo_curator:edit"`). This module imposes no vocabulary
            on it — nothing here may couple to a specific product.
        get_auth_context: The product's own `get_auth_context` dep.
        get_permission_repo: Zero-arg callable returning a
            `PermissionGrantRepository` (typically
            `make_permission_grant_repository(...)`, wired once at
            module load — mirrors `get_core_client`'s threading shape).

    Returns:
        An async dependency suitable for `Depends(...)`, returning the
        (unchanged) resolved `AuthContext` on success. Raises `403`
        (code `permission_denied`) when the caller has no `user_id`
        (a `caller_kind == "product"` token — grants are user-bound)
        or holds no live grant for `name`.
    """

    async def _dependency(
        ctx: AuthContext = Depends(get_auth_context),
    ) -> AuthContext:
        if ctx.user_id is None:
            raise HTTPException(
                status_code=403,
                detail={
                    "detail": f"Missing permission: {name}",
                    "code": "permission_denied",
                },
            )
        granted = await get_permission_repo().has_permission(
            user_id=ctx.user_id, permission=name
        )
        if not granted:
            raise HTTPException(
                status_code=403,
                detail={
                    "detail": f"Missing permission: {name}",
                    "code": "permission_denied",
                },
            )
        return ctx

    return _dependency


__all__ = [
    "require_org_admin",
    "require_permission",
    "require_platform_admin",
    "resolve_platform_admin_role",
]
