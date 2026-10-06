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
from fastapi import Header, HTTPException, Request
from noctusai_lib.api.audit import AuditActor
from noctusai_lib.api.auth import (
    _resolve_trusted_membership,
    make_resolve_platform_role,
    validate_bearer_token,
)
from noctusai_lib.api.auth.session.scopes import resolve_org_role
from noctusai_lib.domain.licensing import enforce_license

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

    async def get_current_user(
        self,
        authorization: Optional[str] = Header(None),
        # 🔴 `Request = None`, NEVER `Optional[Request] = None` — FastAPI's
        # special "inject the live Request" case matches the ANNOTATION
        # literally being the `Request` class (`lenient_issubclass
        # (type_annotation, Request)` in `fastapi/dependencies/utils.py`);
        # `Optional[Request]` resolves to `Union[Request, None]`, which is
        # not a class, so `lenient_issubclass` returns False and FastAPI
        # falls through to treating it as a normal Pydantic field —
        # `Request` isn't Pydantic-serializable, so EVERY route (anywhere
        # in the fleet) with `Depends(deps.get_current_user)` as a
        # sub-dependency fails at COLLECTION time with `FastAPIError:
        # Invalid args for response field!`. Reproduced + confirmed via
        # `products/social-wiring/backend/app/routers/clientes_router.py`
        # during this module's own test run.
        request: Request = None,
    ):
        """Extract and validate JWT from Authorization header. Returns (user, token).

        `request` is optional and keeps `authorization` as the FIRST
        parameter deliberately: every bundled seed router
        (`noctusai_seed.routers`, `ai_feedback_router`, `llm_router`,
        `scheduler_router`, ...) calls this method IMPERATIVELY —
        `await deps.get_current_user(authorization)`, a single
        positional argument, not through `Depends(...)`. FastAPI
        itself resolves `Depends(deps.get_current_user)` by NAME
        (`dependant.call(**values)`), so it still injects the live
        `Request` regardless of this parameter's position or default —
        only the many positional imperative callers required
        `authorization` to stay first.
        """
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Token ausente")
        token = authorization.replace("Bearer ", "")
        # 401 ONLY when Supabase Auth rejected the token; 503 + Retry-After
        # when it could not be asked (transport failure, provider 5xx/429).
        # This used to be `except Exception -> 401`, which turned a deploy-
        # window blip into "your session is dead" in every seed SPA — the
        # 2026-10-03 logouts. See `noctusai_lib.api.auth.validate_bearer_token`.
        user = validate_bearer_token(self._db.get_client(), token)
        # `request.state`, NOT a ContextVar — see
        # `noctusai_lib.api.audit` module docstring +
        # `noctusai_lib.api.auth.make_get_current_user_org`'s same
        # stash. This dependency doesn't resolve org_id/role (that's
        # `get_current_user_org`'s job); a request authenticated only
        # through this base dep still gets a `user_id`-only actor
        # rather than no actor at all. `request` is `None` for the
        # many imperative (non-`Depends`) callers above — nothing to
        # stash onto in that shape, and nothing reads it there either.
        if request is not None:
            request.state.audit_actor = AuditActor(user_id=getattr(user, "id", None))
        return user, token

    def get_user_role(self, user) -> str:
        """Resolve the caller's role from the TRUSTED DB — never ``user_metadata``.

        .. deprecated::
            Do NOT wire via ``Depends(get_user_role)``: the positional
            ``user`` arg becomes a required query parameter. The
            imperative call ``deps.get_user_role(user)`` is fine. See
            ``KB § PATTERNS/backend.md § Auth — canonical pattern``.

        Resolution order:

        1. ``"platform_admin"`` — the trusted-first cascade
           (:func:`noctusai_lib.api.auth.make_resolve_platform_role`,
           ``role-cascade-trusted`` 2026-07-14): ``noctus_users.role == 'admin'``
           or ``org_role`` in (owner, admin).
        2. The raw ``public.noctus_users.org_role`` (``manager`` / ``member`` /
           ``viewer`` / ``dev`` / ...) via
           :func:`noctusai_lib.api.auth.session.scopes.resolve_org_role`.
        3. ``"user"`` — no row / no org role (least privilege).

        SEC-1 (2026-09-28): the former step-2 ``user_metadata.role`` fallback is
        GONE. The platform never writes ``user_metadata.role`` (core's SSO sync
        writes ``noctus_role`` / ``org_role``), so the only party that could set
        it was the user themselves via ``auth.updateUser({data})`` — a
        self-granted ``"admin"`` that passed every ``role in (...)`` gate built on
        this method (the seed team router, igig's stage-editor gate, ...).
        """
        _warn_if_fastapi_caller("ProductDependencies.get_user_role")
        trusted = self._resolve_platform_role(user)
        if trusted:
            return trusted
        org_role = resolve_org_role(self._db.get_core_client(), getattr(user, "id", None))
        return org_role or "user"

    def get_org_id(self, user) -> str:
        """The caller's org from the TRUSTED ``public.noctus_users`` row.

        SEC hotfix (2026-10-06): this used to read ``user.user_metadata
        ["org_id"]`` — user-writable via ``auth.updateUser({data})``, so any
        user could name another tenant's org and (paired with a service-role
        client) read/write its data. It now resolves like
        :func:`noctusai_lib.api.auth.make_get_current_user_org` does:

        * no ``noctus_users`` row / no org → 403 (a metadata org is ignored);
        * effective org without a license  → 403 ``org_sem_licenca`` (round 2;
          acting superadmin ⇒ the target org);
        * DB / transport error             → 503 (fail closed, no fallback).

        Prefer the ``org_id`` already unpacked from ``get_current_user_org``
        — this does one extra DB round-trip per call and exists only for
        imperative call sites that hold nothing but ``user``. Bound method:
        call it on the instance (``deps.get_org_id(user)``).

        .. deprecated::
            Do NOT wire via ``Depends(get_org_id)``: the positional
            ``user`` arg becomes a required query parameter. Use
            :func:`noctusai_lib.api.auth.make_get_current_user_org`. See
            ``KB § PATTERNS/backend/no-metadata-authz.md``.
        """
        _warn_if_fastapi_caller("ProductDependencies.get_org_id")
        try:
            membership = _resolve_trusted_membership(
                lambda: self._db.get_core_client(), getattr(user, "id", None)
            )
        except Exception:
            logger.error(
                "trusted_org_lookup_error user_id=%s — failing closed",
                getattr(user, "id", "<unknown>"),
                exc_info=True,
            )
            raise HTTPException(
                status_code=503, detail="Falha ao resolver organizacao do usuario"
            )
        org_id = membership.get("org_id") if membership else None
        if not org_id:
            raise HTTPException(status_code=403, detail="Usuario sem organizacao associada")
        # Round-2 license gate on the EFFECTIVE org (acting ⇒ target org).
        enforce_license(org_id, membership.get("org_role"), allow_customer=True)
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
