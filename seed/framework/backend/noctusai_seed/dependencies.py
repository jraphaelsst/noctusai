"""
Standard FastAPI dependencies for NoctusAI products.

Every product needs the same auth pattern: extract JWT, validate user,
resolve role, get org_id, create authenticated clients. This module
provides factories that products call once at startup.

Usage::

    from noctusai_seed import create_dependencies

    deps = create_dependencies(db)

    # In routers:
    @router.get("/something")
    async def get_something(auth=Depends(deps.require_auth)):
        user, token = auth
        ...

**Deprecated:** ``ProductDependencies.get_org_id`` /
``get_user_role`` / ``get_user_client`` MUST NOT be wired through
``Depends(...)``. Their positional ``user`` / ``token`` arguments lack
``Depends()`` / ``Header()`` / ``Query()`` annotations, so FastAPI
treats them as required query parameters — every authed request that
uses such a dep returns 422 with ``loc: ['query', 'user']``. Migrate
to :func:`noctusai_lib.api.auth.make_get_current_user_org` (returns a
factory dep that takes only ``authorization: Header(None)`` and
yields ``(user, token, org_id)`` — closure-bound resolver).

See ``KB § PATTERNS/backend.md § Auth — canonical pattern`` for the
canonical wiring + the why-it-fails explanation. The plain-call API
(``deps.get_org_id(user)``) is fine for imperative call sites; only
the ``Depends(...)`` shape is broken.
"""
import inspect
import logging
import warnings
from typing import Optional
from fastapi import Header, HTTPException
from noctusai_lib.api.auth import make_resolve_platform_role

logger = logging.getLogger(__name__)


_AUTH_DEPRECATION_MSG = (
    "{qualname} is deprecated as a FastAPI Depends() target. Its "
    "positional argument has no Depends()/Header()/Query() annotation, "
    "so FastAPI treats it as a required query parameter and every "
    "authed request returns 422. Migrate to "
    "noctusai_lib.api.auth.make_get_current_user_org (factory returning "
    "a dep that yields (user, token, org_id)). See "
    "KB § PATTERNS/backend.md § Auth — canonical pattern."
)


def _warn_if_fastapi_caller(qualname: str) -> None:
    """Emit the migration warning only when the caller looks like
    FastAPI's dependency-injection machinery.

    Imperative callers (``deps.get_org_id(user)`` from a route body or
    a service helper) are NOT broken — the call shape is correct, only
    the ``Depends(...)``-wired shape fails. To honor design principle
    3 in PROJECT.md (warn at the broken shape only), we walk the call
    stack and look for ``fastapi.dependencies`` / ``fastapi.routing``
    frames. If they aren't present, the call is imperative — silent.

    Caveat: FastAPI rejects requests with 422 BEFORE actually invoking
    these deps when the missing-query-param introspection fires. So in
    practice this warning rarely surfaces at runtime — its job is
    diagnostic, not preventative. The keeper-detector (planned in a
    follow-up project) is the real third defense layer.

    Detection: we narrow to ``fastapi.dependencies.utils`` (the module
    that owns ``solve_dependencies`` / ``run_endpoint_function``'s
    dep-graph machinery) AND require the IMMEDIATE caller frame to be
    in that module — i.e., the direct ``await call(**values)`` site,
    not just "FastAPI is somewhere in the stack." Rationale: a route
    body that runs ``deps.get_org_id(user)`` imperatively also has
    FastAPI frames in its stack (the request handler runs under
    ``fastapi.routing``); filtering only on "FastAPI in stack" would
    fire on every legitimate imperative use. The immediate-frame
    constraint isolates the dep-injection call shape.
    """
    frame = inspect.currentframe()
    # Caller of _warn_if_fastapi_caller is the deprecated method
    # itself; the frame above that is our actual caller.
    if frame is None:  # pragma: no cover — defensive
        return
    method_frame = frame.f_back
    if method_frame is None:  # pragma: no cover — defensive
        return
    caller_frame = method_frame.f_back
    if caller_frame is None:
        return
    caller_mod = caller_frame.f_globals.get("__name__", "")
    if caller_mod == "fastapi.dependencies.utils":
        warnings.warn(
            _AUTH_DEPRECATION_MSG.format(qualname=qualname),
            DeprecationWarning,
            stacklevel=3,
        )


class ProductDependencies:
    """Encapsulates standard FastAPI dependencies for a product."""

    def __init__(self, db):
        self._db = db
        # Trusted-first platform-admin cascade (`role-cascade-trusted`,
        # 2026-07-14) — `public.noctus_users`, NOT the spoofable
        # `user_metadata` `resolve_sso_role` used to be the sole source of.
        # `get_core_client` targets the `public` schema (service role) —
        # the SAME client `get_current_user_org`'s trusted org_id lookup
        # uses; a product-schema-scoped client 500s with PGRST205.
        #
        # Late-binding lambda (NOT `db.get_core_client` captured eagerly):
        # some tests construct `ProductDependencies(db=object())` to
        # exercise db-independent methods (`get_org_id`, `get_user_client`
        # signature shape, etc.) — eagerly resolving `db.get_core_client`
        # here would raise `AttributeError` at construction time for every
        # such caller, even when `get_user_role` is never invoked. The
        # lambda defers the attribute access to first-call time, mirroring
        # the "late-binding lambda" convention already used at every
        # product's `get_current_user_org` wiring.
        self._resolve_platform_role = make_resolve_platform_role(
            lambda: self._db.get_core_client()
        )

    async def get_current_user(self, authorization: Optional[str] = Header(None)):
        """Extract and validate JWT from Authorization header. Returns (user, token)."""
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Token ausente")
        token = authorization.replace("Bearer ", "")
        try:
            admin = self._db.get_client()
            user_response = admin.auth.get_user(token)
            if not user_response or not user_response.user:
                raise HTTPException(status_code=401, detail="Token invalido")
            return user_response.user, token
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=401, detail="Nao autenticado")

    def get_user_role(self, user) -> str:
        """Resolve user role. Trusted DB cascades platform_admin; others get metadata role.

        .. deprecated::
            Do NOT wire via ``Depends(get_user_role)``: the positional
            ``user`` arg becomes a required query parameter. The
            imperative call ``deps.get_user_role(user)`` is fine. See
            ``KB § PATTERNS/backend.md § Auth — canonical pattern``.

        Trusted-first (``role-cascade-trusted``, 2026-07-14): the
        platform-admin cascade is resolved from ``public.noctus_users``
        (see :func:`noctusai_lib.api.auth.make_resolve_platform_role`), NOT
        the spoofable ``user_metadata`` a user can rewrite via
        ``auth.updateUser({data})``. ``user_metadata.role`` remains the base
        (non-elevated) role source — this class doesn't yet have a generic,
        product-agnostic notion of DB-backed base roles; only the
        cascading-admin check is hardened here.
        """
        _warn_if_fastapi_caller("ProductDependencies.get_user_role")
        trusted = self._resolve_platform_role(user)
        if trusted:
            return trusted
        return (user.user_metadata or {}).get("role", "user")

    @staticmethod
    def get_org_id(user) -> str:
        """Extract org_id from user metadata. Raises 403 if missing.

        .. deprecated::
            Do NOT wire via ``Depends(get_org_id)``: the positional
            ``user`` arg becomes a required query parameter. Migrate to
            :func:`noctusai_lib.api.auth.make_get_current_user_org`. The
            imperative call ``deps.get_org_id(user)`` is fine. See
            ``KB § PATTERNS/backend.md § Auth — canonical pattern``.
        """
        _warn_if_fastapi_caller("ProductDependencies.get_org_id")
        org_id = (user.user_metadata or {}).get("org_id")
        if not org_id:
            raise HTTPException(status_code=403, detail="Usuario sem organizacao associada")
        return org_id

    def get_user_client(self, token: str):
        """Get a Supabase client authenticated as the user (respects RLS).

        .. deprecated::
            Do NOT wire via ``Depends(get_user_client)``: the positional
            ``token`` arg becomes a required query parameter. Build the
            client imperatively from the ``token`` returned by
            :func:`noctusai_lib.api.auth.make_get_current_user_org`. See
            ``KB § PATTERNS/backend.md § Auth — canonical pattern``.
        """
        _warn_if_fastapi_caller("ProductDependencies.get_user_client")
        return self._db.get_client(token)

    def get_admin_client(self):
        """Get a Supabase client with service role (bypasses RLS)."""
        return self._db.get_admin_client()

    def get_core_client(self):
        """Get a Supabase client targeting the public schema."""
        return self._db.get_core_client()


def create_dependencies(db) -> ProductDependencies:
    """Factory to create standard dependencies for a product.

    Args:
        db: DatabaseModule instance from create_database_module()
    """
    return ProductDependencies(db)
