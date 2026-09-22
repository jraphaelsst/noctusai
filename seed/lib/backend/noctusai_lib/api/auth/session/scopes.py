"""``require_scopes`` — the FastAPI dependency factory enforcing
per-route scope/role authorization over an ``AuthContext``.

SEED-1 (``project-history/roadmaps/julia-agents-academia-2026-09.md``,
contract §B.0): no scope check exists anywhere in the seed before this
module. Composes ON TOP of a product's own ``get_auth_context`` dep
(from :func:`noctusai_lib.api.auth.session.make_get_auth_context`), so
a missing/invalid credential still surfaces as ``401`` from THAT dep —
this module only ever raises ``403``.

Two caller kinds, two different checks:

  - ``caller_kind == "product"``: every listed scope must be in
    ``ctx.scopes``, else ``403 scope_missing``.
  - ``caller_kind == "user"``: the caller's org role (trusted-DB read
    off ``public.noctus_users.org_role`` — NEVER
    ``user_metadata.org_role``, which the user can rewrite themselves
    via ``auth.updateUser``; see :func:`resolve_org_role`) must be in
    ``user_roles``, else ``403 role_missing``. User sessions carry
    ``scopes=[]`` today, so scopes are never a user's authorization —
    only the role is.

``restrict`` narrows to ONE caller kind up front (contract §E.6's
product-only bridge routes / §E's user-only ``agents`` routes):

  - ``"product_only"``: a user caller gets ``403 product_required``
    before the scope check runs.
  - ``"user_only"``: a product caller gets ``403 user_required``
    before the role check runs.

See ``KB § PATTERNS/backend/seed-fake-real-adapter.md`` for the
Protocol+Fake+Real+factory shape the sibling ``api_tokens`` /
``audit`` modules in this package follow; this module has no IO seam
of its own to Fake — ``get_core_client`` is the seam callers already
have (``deps.get_core_client()``), threaded through unchanged.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Literal, Optional

from fastapi import Depends, HTTPException

from noctusai_lib.api.auth.session.types import AuthContext

CallerRestriction = Literal["any", "product_only", "user_only"]


def resolve_org_role(core_client: Any, user_id: Any) -> str | None:
    """Trusted-DB read of ``public.noctus_users.org_role`` for ``user_id``.

    Mirrors ``noctusai_seed.auth_router._require_org_admin``'s query
    shape exactly (same table, same trusted-DB rationale — a user can
    rewrite their own ``user_metadata`` via ``auth.updateUser({data})``,
    so authorization NEVER reads it; see that function's docstring for
    the 2026-07-14 role-cascade audit this pattern closes).

    Args:
        core_client: A ``public``-schema-scoped Supabase client (e.g.
            ``deps.get_core_client()``) — ``noctus_users`` lives in
            ``public``, NOT a product's own schema.
        user_id: The caller's user id. Anything ``str()``-able; accepts
            ``None`` and returns ``None`` immediately (a product-token
            caller has no ``user_id`` — callers MUST NOT reach this
            helper for a product caller, but it fails safe either way).

    Returns:
        The role string (e.g. ``"owner"``) or ``None`` when
        ``user_id`` is ``None`` or no matching row exists.
    """
    if user_id is None:
        return None
    lookup = (
        core_client.from_("noctus_users")
        .select("org_role")
        .eq("id", str(user_id))
        .limit(1)
        .execute()
    )
    rows = lookup.data or []
    if not rows:
        return None
    return rows[0].get("org_role")


#: The canonical "admin-equivalent" org-role set — the same two values
#: ``noctusai_seed.auth_router._require_org_admin`` and every product-level
#: org-admin gate compare against.
ADMIN_ORG_ROLES: frozenset[str] = frozenset({"owner", "admin"})


def is_org_admin(
    core_client: Any,
    user_id: Any,
    *,
    admin_roles: frozenset[str] = ADMIN_ORG_ROLES,
) -> bool:
    """Trusted-DB bool predicate — "does this user have an admin-equivalent
    org_role" — never raises, and NEVER reads ``user_metadata`` (that
    column is user-writable via ``auth.updateUser({data})``; see
    :func:`resolve_org_role`'s own docstring for the exact spoof class this
    closes — the SAME class ``products/core/backend/app/routers
    /admin_llm_usage.py`` documents).

    The shared N=3 predicate behind (as of this dispatch, 2026-09-2x):
    ``noctusai_seed.auth_router._require_org_admin`` (raises 403 directly,
    ``AuthContext``-shaped), and social-wiring's own
    ``settings_router._require_admin`` + ``clientes_router._is_org_admin``
    — both of which previously read the spoofable
    ``user_metadata.org_role``/``role`` and are fixed, this same dispatch,
    to call THIS instead. New product code should call this (or
    :func:`require_org_admin_role` / :func:`make_require_org_admin` below)
    rather than hand-rolling a fourth copy.

    Args:
        core_client: A ``public``-schema-scoped Supabase client
            (``deps.get_core_client()``) — ``noctus_users`` lives in
            ``public``, never a product's own schema.
        user_id: The caller's user id. ``None`` is a legitimate input
            (``resolve_org_role`` returns ``None`` for it, which never
            matches ``admin_roles``, so this returns ``False`` — fails
            closed, never raises).
        admin_roles: The role set that counts as "admin". Defaults to the
            platform's own ``("owner", "admin")``.
    """
    return resolve_org_role(core_client, user_id) in admin_roles


def require_org_admin_role(
    core_client: Any,
    user_id: Any,
    context: str,
    *,
    admin_roles: frozenset[str] = ADMIN_ORG_ROLES,
) -> None:
    """Imperative 403 gate — the drop-in replacement for a hand-rolled
    ``if role not in (...): raise HTTPException(403, ...)`` block INSIDE an
    already-authenticated route body. This is the shape every legacy
    ``get_current_user_org``-based product route needs: those routes
    resolve ``user``/``org_id`` themselves (a plain tuple, not a
    ``Depends()``-composed ``AuthContext``), so the gate has to be callable
    imperatively rather than only as a dependency — see
    :func:`make_require_org_admin` for the dependency-shaped alternative
    when a route CAN afford to resolve auth entirely through ``Depends()``.

    ``context`` names the action being gated (e.g. ``"Chaves de API"``),
    so the 403 detail stays specific per call site — mirrors the
    ``context`` parameter every pre-existing hand-rolled gate this
    replaces already took.
    """
    if not is_org_admin(core_client, user_id, admin_roles=admin_roles):
        raise HTTPException(
            status_code=403, detail=f"{context} restrito a administradores."
        )


def make_require_org_admin(
    get_current_user_org: Callable[..., Awaitable[tuple]],
    get_core_client: Callable[[], Any],
    *,
    admin_roles: frozenset[str] = ADMIN_ORG_ROLES,
    detail: str = "Ação restrita a administradores.",
) -> Callable[..., Awaitable[tuple]]:
    """FastAPI dependency FACTORY for the legacy ``(user, token, org_id)``
    auth shape (``noctusai_lib.api.auth.make_get_current_user_org``'s
    return value) — binds a product's own ``get_current_user_org`` +
    ``get_core_client`` ONCE, returns a ``Depends()``-able async dependency
    that resolves auth THEN 403s unless the caller is a trusted-DB org
    admin/owner. A route can ``Depends()`` this INSTEAD OF
    ``get_current_user_org`` directly and get both auth AND the admin gate
    from one dependency; the (unchanged) auth tuple is returned on
    success, so no route body needs to change shape.
    """

    async def _dependency(auth: tuple = Depends(get_current_user_org)) -> tuple:
        user, _token, _org_id = auth
        if not is_org_admin(
            get_core_client(), getattr(user, "id", None), admin_roles=admin_roles
        ):
            raise HTTPException(status_code=403, detail=detail)
        return auth

    return _dependency


def require_scopes(
    *scopes: str,
    user_roles: frozenset[str] = frozenset(),
    get_auth_context: Callable[..., Awaitable[AuthContext]],
    get_core_client: Optional[Callable[[], Any]] = None,
    restrict: CallerRestriction = "any",
) -> Callable[..., Awaitable[AuthContext]]:
    """Build a FastAPI dependency enforcing scopes (product) / role (user).

    Args:
        *scopes: Scope strings a ``caller_kind == "product"`` token
            must ALL carry (e.g. ``require_scopes("academia:read")``).
            Ignored for a ``"user"`` caller (contract §B.0 — user
            sessions carry no scopes; the role check applies instead).
        user_roles: The org-role set a ``caller_kind == "user"`` caller
            must belong to (e.g. ``frozenset({"owner", "admin"})``).
            Required whenever a ``"user"`` caller can reach the route
            (i.e. ``restrict != "product_only"``); an empty set means
            NO user role satisfies the check, so every user 403s —
            correct for a route the contract marks product-only via a
            scope check alone, but callers SHOULD prefer
            ``restrict="product_only"`` for that case (it 403s before
            the DB round-trip and with the more specific
            ``product_required`` code).
        get_auth_context: The product's own ``get_auth_context`` dep
            (composed via ``Depends(...)`` — a missing/invalid
            credential 401s from THAT dep, never from here).
        get_core_client: Zero-arg callable returning a ``public``-
            schema-scoped Supabase client, for the trusted-DB role
            read (:func:`resolve_org_role`). Required whenever a
            ``"user"`` caller can reach the route; omit only for a
            ``restrict="product_only"`` dependency, which never
            resolves a role.
        restrict: ``"any"`` (default) — both caller kinds allowed,
            branching per kind. ``"product_only"`` — a ``"user"``
            caller 403s ``product_required`` before the scope check
            (contract §E.6). ``"user_only"`` — a ``"product"`` caller
            403s ``user_required`` before the role check (contract §E
            intro — every ``agents`` route is user-only).

    Returns:
        An async dependency suitable for ``Depends(...)``, returning
        the (unchanged) resolved ``AuthContext`` on success.
    """

    async def _dependency(
        ctx: AuthContext = Depends(get_auth_context),
    ) -> AuthContext:
        if restrict == "product_only" and ctx.caller_kind != "product":
            raise HTTPException(
                status_code=403,
                detail={
                    "detail": "Restricted to product tokens",
                    "code": "product_required",
                },
            )
        if restrict == "user_only" and ctx.caller_kind != "user":
            raise HTTPException(
                status_code=403,
                detail={
                    "detail": "Restricted to human users",
                    "code": "user_required",
                },
            )

        if ctx.caller_kind == "product":
            missing = [s for s in scopes if s not in ctx.scopes]
            if missing:
                raise HTTPException(
                    status_code=403,
                    detail={
                        "detail": f"Missing scope(s): {', '.join(missing)}",
                        "code": "scope_missing",
                    },
                )
            return ctx

        # caller_kind == "user"
        role = (
            resolve_org_role(get_core_client(), ctx.user_id)
            if get_core_client is not None
            else None
        )
        if role not in user_roles:
            raise HTTPException(
                status_code=403,
                detail={
                    "detail": "Insufficient role",
                    "code": "role_missing",
                },
            )
        return ctx

    return _dependency


__all__ = [
    "ADMIN_ORG_ROLES",
    "CallerRestriction",
    "is_org_admin",
    "make_require_org_admin",
    "require_org_admin_role",
    "require_scopes",
    "resolve_org_role",
]
