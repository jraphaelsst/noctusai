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
    "CallerRestriction",
    "require_scopes",
    "resolve_org_role",
]
