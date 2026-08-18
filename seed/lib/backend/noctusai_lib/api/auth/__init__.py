"""
Shared authentication helpers for all NoctusAI APIs.

Provides the common get_current_user auth dependency, SSO-role resolution,
and (as of `core-seed-wiring-v2` Phase 4 — 2026-04-23) reusable SSO-JWT
primitives + session cache for any identity-source product. Today's sole
consumer is `core`; the primitives live in the seed lib so a future
2nd identity-source product composes them out of the box rather than
reimplementing.

**What's here:**

- `first_or_none(result)` — Supabase list-response helper.
- `make_get_current_user(fn)` — factory for product-specific JWT validation.
- `resolve_sso_role(user)` — reads `org_role` / `noctus_role` from user_metadata.
- `get_sso_context(user)` — extracts full SSO context from user_metadata.
- `make_require_role(get_current_user_fn, get_user_role_fn)` — factory for
  product-specific role-guard dependency factories. Mirrors the
  `make_get_current_user(fn)` pattern: products bind it once at module load
  and use the resulting `require_role(*roles)` at every router site.
- **NEW** `create_sso_token_factory(settings)` — returns a token-mint callable
  parameterized by product settings (`jwt_secret`, `jwt_algorithm`,
  `sso_token_expiration_minutes`). Tokens carry `iss=noctusai` /
  `aud=noctusai-sso`; signed with `sso_jwt_secret` when set, else `jwt_secret`.
- **NEW** `verify_sso_token_factory(settings)` — returns a token-verify callable.
  Validates `iss` / `aud` / required claims; 10 s clock-skew leeway.
- **NEW** `SSOSessionCache(ttl_seconds=300)` — thread-safe in-memory cache with
  per-key locks and explicit invalidation API.
- **NEW** (`seed-trusted-org-resolution`, 2026-07-14) `make_get_current_user_org`
  now resolves ``org_id`` from ``public.noctus_users`` (the trusted source
  every product's RLS ``current_org_id()`` reads) FIRST, falling back to the
  caller-supplied resolver (typically ``user_metadata``) only when no
  ``noctus_users`` row exists — closing the residual org-spoofing hole where
  a user could overwrite their own ``user_metadata.org_id`` via
  ``auth.updateUser({data})``. See :func:`make_get_current_user_org`.
- **NEW** (`role-cascade-trusted`, 2026-07-14) `make_resolve_platform_role`
  is the role-authz analog of the above: it resolves the platform-admin
  cascade from ``public.noctus_users.role`` / ``org_role`` (trusted DB)
  FIRST, falling back to :func:`resolve_sso_role`'s spoofable
  ``user_metadata`` read only as a transition fallback. Closes the
  role-spoofing hole flagged as a follow-up above: a user could previously
  self-grant ``platform_admin`` fleet-wide by rewriting
  ``user_metadata.org_role`` / ``noctus_role`` via ``auth.updateUser({data})``.
  Wired into ``noctusai_seed.ProductDependencies.get_user_role`` (every
  product that uses the seed default) and into each product's local
  role resolver that previously called ``resolve_sso_role`` directly
  (ERP, AdConnect, therapy-platform). See :func:`make_resolve_platform_role`.

**Not here:**

- SSO endpoint routers (`/api/auth/*`, `/api/sso/*`). Those stay local to core
  as organ routers — per the recurrence rule in `KB § 01-PHILOSOPHY § Triage at
  decision time`, seam formalization happens when 2+ products share the shape.
"""
from __future__ import annotations

import datetime
import logging
import threading
import time
from typing import Any, Callable, Dict, Optional, Tuple

import jwt
from fastapi import Header, HTTPException

from noctusai_lib.primitives.timeutil import now_utc

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SSO-token identity constants — fixed so mint and verify can NEVER drift
# out of symmetry regardless of how settings are composed across products.
# Using constants (not settings fields) means there is no configuration
# surface that could produce a mint/verify mismatch in any deployment.
# ---------------------------------------------------------------------------
SSO_ISSUER = "noctusai"        # who minted it — the core SSO bridge
SSO_AUDIENCE = "noctusai-sso"  # token purpose — distinct from session JWTs


def _sso_secret(settings) -> str:
    """Dedicated SSO-bridge signing secret when configured, else jwt_secret.

    Setting ``SSO_JWT_SECRET`` on core decouples bridge-token signing from
    per-product session signing so a leaked product ``jwt_secret`` cannot
    forge SSO identities.  Empty default → zero-config back-compat (falls
    back to ``jwt_secret``).
    """
    dedicated = (getattr(settings, "sso_jwt_secret", "") or "").strip()
    return dedicated or settings.jwt_secret


def first_or_none(result) -> Optional[dict]:
    """Extract first record from a Supabase list response, or None."""
    if not result.data:
        return None
    if isinstance(result.data, dict):
        return result.data
    return result.data[0]


async def _get_current_user(
    authorization: Optional[str] = Header(None),
    *,
    _get_supabase_client=None,
):
    """
    Internal JWT validator. Products MUST use make_get_current_user() to
    obtain a product-specific dependency — never import this directly.

    Extract and validate the JWT from the Authorization header.
    Returns (user, token) tuple.

    The _get_supabase_client parameter is injected by each product's
    dependencies.py to supply the product-specific client factory. This
    avoids a circular dependency between shared auth and product database
    modules.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token ausente")

    token = authorization.replace("Bearer ", "")
    try:
        if _get_supabase_client is None:
            raise RuntimeError(
                "get_current_user must be called via a product-specific wrapper "
                "that supplies _get_supabase_client"
            )
        admin = _get_supabase_client()  # service role to validate
        user_response = admin.auth.get_user(token)
        if not user_response or not user_response.user:
            raise HTTPException(status_code=401, detail="Token inválido")
        return user_response.user, token
    except HTTPException:
        raise
    except (TimeoutError, OSError) as exc:
        # 🔴 NOT a 401. Validation here is a NETWORK CALL to Supabase, so a
        # transport failure (DNS, TLS handshake, connection reset, timeout)
        # means "I could not ask whether this token is valid" — which is
        # nothing like "this token is invalid". Reporting it as 401 tells
        # the user they are logged out and sends the SPA to the login page,
        # while the real fault is server-side and the credentials are fine.
        #
        # That is not hypothetical: on 2026-08-18 a VPN MTU mismatch (host
        # tunnel 1380, container 1500) broke the TLS 1.3 handshake to
        # Supabase from inside a container. Login succeeded in the browser,
        # every API call then 401'd, and the app bounced to home — the UI
        # blamed the user's session for what was a dropped packet. Twenty
        # minutes went into "why is login broken" because the error said
        # the wrong thing.
        #
        # `ssl.SSLError`, `socket.timeout`, `ConnectionError` and httpx's
        # transport errors are all `OSError`/`TimeoutError` subclasses, so
        # this catches the transport family without guessing at any one
        # client library's exception tree.
        logger.error(
            "auth: could not reach the auth provider to validate a token — "
            "reporting 503, NOT 401 (the caller's credentials are not in "
            "question here): %s: %s",
            type(exc).__name__,
            exc,
        )
        raise HTTPException(
            status_code=503,
            detail="Serviço de autenticação indisponível. Tente novamente.",
        ) from exc
    except Exception:
        raise HTTPException(status_code=401, detail="Não autenticado")


def make_get_current_user(get_supabase_client_fn):
    """
    Factory that creates a product-specific get_current_user dependency.

    Usage in each product's dependencies.py:

        from noctusai_lib.api.auth import make_get_current_user, first_or_none
        from app.database import get_supabase_client

        get_current_user = make_get_current_user(get_supabase_client)
    """
    async def _product_get_current_user(authorization: Optional[str] = Header(None)):
        return await _get_current_user(
            authorization,
            _get_supabase_client=get_supabase_client_fn,
        )
    return _product_get_current_user


# ---------------------------------------------------------------------------
# SSO role resolution
# ---------------------------------------------------------------------------


def resolve_sso_role(user) -> Optional[str]:
    """Check SSO metadata for product-level admin access.

    # SECURITY (`role-cascade-trusted`, 2026-07-14): this reads
    # `user_metadata` — spoofable, since Supabase lets any authenticated
    # user rewrite their own metadata via `auth.updateUser({data})`. It is
    # now ONLY consumed as a transition fallback by
    # :func:`make_resolve_platform_role` (used when no trusted
    # `public.noctus_users` row exists yet) — new callers should reach for
    # `make_resolve_platform_role` instead of calling this directly. Kept
    # standalone (not inlined) because it is still the correct primitive
    # for reading the SSO-synced `user_metadata` shape on its own terms,
    # and existing per-product callers are migrated in the same commit
    # that introduced this note.

    When a user enters a product via SSO from the NoctusAI Core platform,
    the Core's ``/api/sso/session`` endpoint syncs ``org_role`` and
    ``noctus_role`` into the user's ``user_metadata``.

    Resolution order:
    1. ``org_role`` in (owner, admin) → ``"platform_admin"`` — the user's
       org bought the product license; they manage it.
    2. ``noctus_role == "admin"`` → ``"platform_admin"`` — NoctusAI
       platform admins have full access to every product.
    3. Otherwise → ``None`` — caller falls through to product-specific
       role logic (e.g. therapy-native roles, ERP DB roles).

    Products should call this first in their ``get_user_role()``::

        def get_user_role(user) -> str:
            sso = resolve_sso_role(user)
            if sso:
                return sso
            # … product-specific logic …
    """
    metadata = getattr(user, "user_metadata", None) or {}
    if metadata.get("org_role") in ("owner", "admin"):
        return "platform_admin"
    if metadata.get("noctus_role") == "admin":
        return "platform_admin"
    return None


def get_sso_context(user) -> dict:
    """Extract all SSO-synced context from user_metadata.

    Returns a dict with keys: ``noctus_role``, ``org_role``, ``org_id``,
    ``org_name``, ``org_logo_url``, ``plan_slug``, ``plan_max_users``,
    ``plan_max_products``, ``plan_features``, ``subscription_status``,
    ``subscription_expires_at``, ``license_expires_at``.

    All values default to None when not present in metadata.
    Products can use this in services to check plan limits, display
    org branding, or show license/trial warnings.
    """
    metadata = getattr(user, "user_metadata", None) or {}
    keys = (
        "noctus_role", "org_role", "org_id",
        "org_name", "org_logo_url",
        "plan_slug", "plan_max_users", "plan_max_products", "plan_features",
        "subscription_status", "subscription_expires_at",
        "license_expires_at",
    )
    return {k: metadata.get(k) for k in keys}


def make_require_role(get_current_user_fn, get_user_role_fn):
    """Factory that creates a product-specific ``require_role`` dependency factory.

    Mirrors the :func:`make_get_current_user` pattern: products bind it once
    at module load with their already-wrapped ``get_current_user`` (which
    knows the product's Supabase client) and their ``get_user_role``
    callable, then use the resulting ``require_role(*roles)`` at every
    router site.

    Parameters:
        get_current_user_fn: The product's already-wrapped
            ``get_current_user`` dependency (typically the return value
            of :func:`make_get_current_user`). Must be an async callable
            that takes ``authorization: Optional[str]`` and returns
            ``(user, token)``.
        get_user_role_fn: A callable ``(user) -> str`` that returns
            the resolved role for the user. Each product provides its own
            (typically falls through ``resolve_sso_role`` to product-native
            roles).

    Returns:
        A ``require_role(*allowed_roles: str)`` factory; calling it
        produces a FastAPI dependency that:
          - extracts + validates the JWT via the product's get_current_user
          - resolves the user's role via ``get_user_role_fn``
          - raises ``HTTPException(403)`` if the role is not in
            ``allowed_roles``
          - returns ``(user, token, role)`` to dependent endpoints.

    Usage in a product's ``app/dependencies.py``::

        from noctusai_lib.api.auth import make_require_role
        from app.dependencies import get_current_user, get_user_role

        require_role = make_require_role(get_current_user, get_user_role)

    And then in routers::

        @router.get("/admin/dashboard")
        async def dashboard(
            auth_role=Depends(require_role("platform_admin")),
        ):
            user, token, role = auth_role
            ...
    """
    def require_role(*allowed_roles: str):
        async def _check_role(authorization: Optional[str] = Header(None)):
            user, token = await get_current_user_fn(authorization)
            role = get_user_role_fn(user)
            if role not in allowed_roles:
                raise HTTPException(
                    status_code=403,
                    detail=f"Acesso negado. Restrito a: {', '.join(allowed_roles)}",
                )
            return user, token, role
        return _check_role
    return require_role


def _resolve_trusted_org_id(get_admin_client_fn: Callable[[], Any], user_id) -> Optional[str]:
    """Look up ``org_id`` from ``public.noctus_users`` for ``user_id``.

    This is the SAME row every product's RLS ``current_org_id()`` SECURITY
    DEFINER function reads (``SELECT org_id FROM public.noctus_users WHERE
    id = auth.uid()``) — the trusted source, populated server-side during
    provisioning / SSO sync, never writable by the authenticated user
    themselves. Contrast with ``user.user_metadata["org_id"]``, which the
    SAME user can overwrite via ``auth.updateUser({data})`` (Supabase lets
    any authenticated user rewrite their own metadata) — an app layer that
    trusts metadata for org resolution is spoofable to another tenant's
    data even after per-endpoint auth is otherwise correctly wired.

    ``get_admin_client_fn`` MUST return a service-role client scoped to the
    ``public`` schema — i.e. ``DatabaseModule.get_core_client()``, NEVER
    ``get_admin_client()``. A product-schema-scoped admin client resolves
    ``.table("noctus_users")`` against the WRONG schema and 500s with
    PGRST205 — this exact regression already shipped + was caught in prod
    once for a single ERP route (see ``products/erp-imobiliario/backend/
    app/dependencies.py:resolve_org_id_db``'s docstring, 2026-07-07).

    Uses ``.limit(1)`` (a plain list query) rather than ``.single()`` /
    ``.maybe_single()`` — deliberately, to avoid conflating "no
    ``noctus_users`` row yet" (an expected, non-error transition state)
    with PostgREST's 0-rows-raises-``APIError`` semantics on ``.single()``.

    Returns ``None`` when no ``noctus_users`` row exists for ``user_id``
    (e.g. a user mid-provisioning) — the caller decides the no-row policy.
    Any OTHER exception (network / auth / schema error) is NOT swallowed
    here — it propagates so the caller can fail closed.
    """
    core = get_admin_client_fn()
    result = (
        core.table("noctus_users")
        .select("org_id")
        .eq("id", user_id)
        .limit(1)
        .execute()
    )
    if result.data and result.data[0].get("org_id"):
        return result.data[0]["org_id"]
    return None


def _resolve_trusted_platform_role(
    get_admin_client_fn: Callable[[], Any], user_id
) -> Optional[str]:
    """Look up the platform-level role for ``user_id`` from ``public.noctus_users``.

    Mirrors :func:`_resolve_trusted_org_id` — same client-threading contract
    (``get_admin_client_fn`` MUST be ``DatabaseModule.get_core_client``, the
    ``public``-schema service-role client; a product-schema-scoped admin
    client 500s with PGRST205, the exact regression documented on
    :func:`_resolve_trusted_org_id`), same ``.limit(1)`` shape (distinguishes
    "no row" from PostgREST's 0-rows-raises-``APIError`` on ``.single()``),
    same fail-open-on-exception contract (a genuine DB/transport error is NOT
    swallowed here — it propagates so the caller can fail closed).

    ``public.noctus_users`` is the trusted, non-spoofable analog of
    ``user.user_metadata["org_role"]`` / ``["noctus_role"]`` (the fields
    :func:`resolve_sso_role` reads) — populated server-side during
    provisioning / SSO sync, never writable by the authenticated user
    themselves via ``auth.updateUser({data})``.

    Returns:
        ``"platform_admin"`` when ``role == "admin"`` OR ``org_role`` is
        ``"owner"``/``"admin"`` — the platform-admin-cascades-to-every-
        product rule the ``role-cascade-trusted`` slice (2026-07-14) exists
        to enforce.
        The raw ``org_role`` string (e.g. ``"member"``, ``"viewer"``) when a
        row exists but does not qualify for ``platform_admin`` — callers
        decide what (if anything) that base value means for their own
        product-local role vocabulary; the seed default and every audited
        product-local resolver in this fleet treat it as "not elevated"
        and fall through to their own base-role default.
        ``None`` when no ``noctus_users`` row exists for ``user_id`` (e.g. a
        user mid-provisioning) — the caller decides the no-row policy.
    """
    core = get_admin_client_fn()
    result = (
        core.table("noctus_users")
        .select("role, org_role")
        .eq("id", user_id)
        .limit(1)
        .execute()
    )
    if not result.data:
        return None
    row = result.data[0]
    if row.get("role") == "admin" or row.get("org_role") in ("owner", "admin"):
        return "platform_admin"
    return row.get("org_role")


def make_resolve_platform_role(
    get_admin_client_fn: Callable[[], Any],
) -> Callable[[Any], Optional[str]]:
    """Factory: returns a sync ``resolve_platform_role(user) -> Optional[str]``.

    Trusted-first replacement for calling :func:`resolve_sso_role` directly.
    Preserves :func:`resolve_sso_role`'s exact contract — returns
    ``"platform_admin"`` or ``None`` (``None`` meaning "not a cascading
    platform admin; caller falls through to product-specific role logic") —
    so every existing ``if sso: return sso`` call site swaps in unchanged.

    **Trust model** (``role-cascade-trusted``, 2026-07-14): mirrors
    :func:`make_get_current_user_org`'s trust model for ``org_id``, applied
    to the platform-admin cascade. ``public.noctus_users`` (via
    :func:`_resolve_trusted_platform_role`) wins whenever a row exists — a
    row that isn't ``platform_admin``-qualifying (e.g. a plain org member)
    resolves to ``None`` here, exactly like a genuinely non-admin
    ``user_metadata`` read would, so it is NOT treated as "no row" and does
    NOT fall back to the spoofable resolver. The :func:`resolve_sso_role`
    fallback fires ONLY when no ``noctus_users`` row exists yet (a
    legitimate transition state, e.g. a provisioning race) — and even then,
    LOUDLY: a ``logger.warning`` names the user id whenever the fallback
    actually resolves a role. On a genuine DB/transport ERROR (as opposed to
    "no row"), resolution fails CLOSED — the exception propagates rather
    than falling back to the spoofable resolver, for the same reason
    documented on :func:`make_get_current_user_org`: falling back in the
    error branch would reopen the exact spoofing hole this function exists
    to close, in the one place a security regression would hide silently.

    Parameters:
        get_admin_client_fn: A sync callable ``() -> Client`` returning a
            service-role Supabase client scoped to the ``public`` schema
            (``DatabaseModule.get_core_client()``).

    Returns:
        A sync ``resolve_platform_role(user) -> Optional[str]`` callable.

    Usage in a product's ``app/dependencies.py``::

        from noctusai_lib.api.auth import make_resolve_platform_role

        _db = create_database_module(settings, schema="my_product")
        resolve_platform_role = make_resolve_platform_role(
            lambda: _db.get_core_client()
        )

        def get_my_product_role(user) -> str:
            sso = resolve_platform_role(user)  # trusted-first, was resolve_sso_role(user)
            if sso:
                return sso
            # … product-specific logic, unchanged …
    """
    def resolve_platform_role(user) -> Optional[str]:
        user_id = getattr(user, "id", None)
        try:
            trusted = _resolve_trusted_platform_role(get_admin_client_fn, user_id)
        except Exception:
            # Fail CLOSED — see make_get_current_user_org's documented
            # rationale for the identical org_id trust model. A DB outage
            # already fails every downstream data-access query for this
            # same request anyway (same database); failing here instead of
            # one hop later is not a materially larger availability blast
            # radius, and it keeps the security invariant intact instead of
            # trading it away for uptime.
            logger.error(
                "trusted_role_lookup_error user_id=%s — failing closed "
                "(NOT falling back to user_metadata)",
                user_id,
                exc_info=True,
            )
            raise

        if trusted is not None:
            # A row exists. Either it qualifies for platform_admin (return
            # it), or it doesn't (a genuine, trusted "not elevated" answer —
            # NOT a "no row" transition state, so the spoofable fallback is
            # never consulted here).
            return trusted if trusted == "platform_admin" else None

        # No noctus_users row — a legitimate transition state (e.g. a
        # provisioning race). Fall back to the caller-supplied resolver so
        # existing flows keep working, but LOUDLY — never silent.
        fallback = resolve_sso_role(user)
        if fallback:
            logger.warning(
                "trusted_role_lookup_empty user_id=%s — no noctus_users row, "
                "falling back to resolve_sso_role (user_metadata; role=%r)",
                user_id, fallback,
            )
        return fallback

    return resolve_platform_role


def make_get_current_user_org(
    get_current_user_fn,
    get_org_id_fn,
    *,
    get_admin_client_fn: Callable[[], Any],
    required: bool = True,
    missing_status: int = 403,
    missing_detail: str = "Usuario sem organizacao associada",
):
    """Factory that creates a product-specific ``get_current_user_org`` dependency.

    Mirrors the :func:`make_require_role` pattern: products bind it once at
    module load with their already-wrapped ``get_current_user`` (which knows
    the product's Supabase client) and a pure ``get_org_id`` resolver, then
    use the resulting dep at every router site that needs ``(user, token, org_id)``.

    Surfaced by the ``personal-finance-wiring`` Phase 1 Verify-the-seed-ships-it
    test (2026-05-04). PF's ``dependencies.py:get_current_user_org`` and ERP's
    ``dependencies.py:get_org_id`` shared the ``(user.user_metadata or {}).get(
    "org_id")`` resolution body in different request-time wrappings — N=2
    recurrence, formalized as this factory.

    **Trust model** (``seed-trusted-org-resolution``, 2026-07-14): org_id is
    resolved from ``public.noctus_users`` (see :func:`_resolve_trusted_org_id`)
    FIRST — the SAME source RLS trusts. ``get_org_id_fn`` (historically
    ``user_metadata``-based) is now ONLY a transition fallback, used solely
    when no ``noctus_users`` row exists yet, and it fires with a
    ``logger.warning`` naming the user id — never silently. Any REAL user
    has a ``noctus_users`` row, so the DB lookup wins and a spoofed
    ``user_metadata.org_id`` is simply ignored — this closes the residual
    org-spoofing hole (a user rewriting their own ``user_metadata.org_id``
    via ``auth.updateUser({data})`` to reach another tenant's data) by
    construction. On a genuine DB/transport ERROR (as opposed to "no row"),
    resolution fails CLOSED — it does NOT fall back to the spoofable
    resolver; see the inner dependency body for the full rationale.

    Parameters:
        get_current_user_fn: The product's already-wrapped
            ``get_current_user`` dependency (typically the return value
            of :func:`make_get_current_user`). Must be an async callable
            that takes ``authorization: Optional[str]`` and returns
            ``(user, token)``.
        get_org_id_fn: A sync callable ``(user) -> Optional[str]`` that
            resolves the org_id for a user — now a FALLBACK, used only when
            ``public.noctus_users`` has no row for the user. Each product
            provides its own (typically ``lambda u: (u.user_metadata or
            {}).get("org_id")`` or ERP's pre-existing ``get_org_id(user)``
            resolver).
        get_admin_client_fn: A sync callable ``() -> Client`` returning a
            service-role Supabase client scoped to the ``public`` schema
            (``DatabaseModule.get_core_client()``). Required — every caller
            of this factory must supply the trusted-lookup client.
        required: When True (default), raises ``HTTPException(missing_status,
            missing_detail)`` if the resolved org_id is falsy. PF's shape.
            When False, the dep returns ``(user, token, None)`` on missing
            org_id — no exception. Tuple-with-None lets callers branch on
            membership without re-running auth.
        missing_status: HTTP status code raised when ``required=True`` and
            org_id is missing. Defaults to 403 (PF). ERP's local ``get_org_id(
            required=True)`` uses 400 — pass ``missing_status=400`` to mirror.
        missing_detail: HTTP detail string raised with ``missing_status``.
            Defaults to PF's "Usuario sem organizacao associada".

    Returns:
        An async dependency callable
        ``get_current_user_org(authorization: Optional[str] = Header(None))``
        that resolves ``(user, token, org_id|None)``.

    Usage in a product's ``app/dependencies.py``::

        from noctusai_lib.api.auth import make_get_current_user, make_get_current_user_org

        _db = create_database_module(settings, schema="my_product")
        get_current_user = make_get_current_user(lambda: _db.get_client())
        get_current_user_org = make_get_current_user_org(
            get_current_user,
            lambda u: (u.user_metadata or {}).get("org_id"),  # fallback only
            get_admin_client_fn=lambda: _db.get_core_client(),  # public schema, service role
            required=True,  # 403 on missing
        )

    And then in routers::

        @router.get("/things")
        async def list_things(
            auth=Depends(get_current_user_org),
        ):
            user, token, org_id = auth
            ...
    """
    async def get_current_user_org(authorization: Optional[str] = Header(None)):
        user, token = await get_current_user_fn(authorization)

        # Trusted-first resolution — `public.noctus_users` is the SAME
        # source every product's RLS `current_org_id()` reads. It wins over
        # the spoofable `get_org_id_fn` (typically `user_metadata`)
        # whenever a row exists.
        try:
            org_id = _resolve_trusted_org_id(get_admin_client_fn, user.id)
        except Exception:
            # Fail CLOSED on a genuine DB/transport error. Falling back to
            # the spoofable resolver here would reopen the exact hole this
            # factory exists to close — and precisely in the failure
            # branch, the worst place for a security regression to hide
            # silently. A DB outage already fails every downstream
            # data-access query for this same request anyway (same
            # database) — failing at auth instead of one hop later is not
            # a materially larger availability blast radius, and it keeps
            # the security invariant intact under partial-failure
            # conditions instead of trading it away for uptime.
            logger.error(
                "trusted_org_lookup_error user_id=%s — failing closed "
                "(NOT falling back to user_metadata)",
                getattr(user, "id", "<unknown>"),
                exc_info=True,
            )
            if required:
                raise HTTPException(
                    status_code=503,
                    detail="Falha ao resolver organizacao do usuario",
                )
            return user, token, None

        if org_id is None:
            # No noctus_users row (as opposed to a DB ERROR) — a
            # legitimate transition state (e.g. a provisioning race).
            # Fall back to the caller-supplied resolver so existing flows
            # keep working, but LOUDLY — never silent.
            fallback_org_id = get_org_id_fn(user)
            if fallback_org_id:
                logger.warning(
                    "trusted_org_lookup_empty user_id=%s — no noctus_users "
                    "row, falling back to org_from_user resolver (org_id=%r)",
                    getattr(user, "id", "<unknown>"), fallback_org_id,
                )
            org_id = fallback_org_id

        if not org_id:
            if required:
                raise HTTPException(
                    status_code=missing_status,
                    detail=missing_detail,
                )
            return user, token, None
        return user, token, org_id
    return get_current_user_org


# ---------------------------------------------------------------------------
# Credential-on-request guard — `ai-plumbing-seed-absorption` (2026-05-04)
# ---------------------------------------------------------------------------
#
# Surfaced by `personal-finance-wiring` Phase 1 audit at N=2 recurrence:
# PF + ERP each ship a local `_require_openai(org_id)` helper raising
# HTTPException 422 when `resolve_credential("openai_api_key", org_id)`
# returns falsy. The bodies are byte-identical modulo the Portuguese
# detail string. Triage outcome per `KB § PATTERNS/project-execution.md
# § 2.7 The recurrence rule`: formalize.
#
# The helper sits next to `make_require_role` because it shares the
# HTTP-layer raise-on-violation shape — both translate a missing pre-
# condition (role / credential) into a typed HTTP error.


def require_credential_or_422(
    key: str,
    org_id: Optional[str] = None,
    *,
    detail: Optional[str] = None,
) -> str:
    """Resolve a credential through `noctusai_lib.config.credentials.resolve_credential`
    and raise ``HTTPException(422)`` when the result is falsy.

    Returns the resolved credential value, so callers may use the value
    directly when convenient::

        api_key = require_credential_or_422("openai_api_key", org_id)
        client = OpenAI(api_key=api_key)

    Or in raise-only form (when the value is consumed elsewhere)::

        require_credential_or_422("openai_api_key", org_id, detail="…pt-br copy…")

    Args:
        key: lowercase credential key (matches `org_settings`/`platform_settings`
            row + `key.upper()` env-var fallback). E.g. ``"openai_api_key"``,
            ``"resend_api_key"``.
        org_id: organization id for tier-1 (per-org override) lookup; ``None``
            skips tier 1 and starts at platform-tier 2.
        detail: optional override for the 422 detail string. Default is
            ``f"Credential {key} not configured."``. Override with the
            product's localized user-facing copy when needed.

    Returns:
        The resolved credential value (non-empty string).

    Raises:
        HTTPException(422): when no tier of the resolution chain has the value.
    """
    # Imported lazily to avoid a startup-time import cycle: `noctusai_lib.api.auth`
    # is consumed by product `dependencies.py` at module load, while
    # `noctusai_lib.config.credentials` reaches into `integrations.database`.
    # Lazy import keeps the credential surface optional for products that
    # don't use HTTP credential gating.
    from noctusai_lib.config.credentials import resolve_credential

    value = resolve_credential(key, org_id)
    if not value:
        raise HTTPException(
            status_code=422,
            detail=detail or f"Credential {key} not configured.",
        )
    return value


# ---------------------------------------------------------------------------
# SSO JWT primitives — Phase 4 promotion (2026-04-23)
# ---------------------------------------------------------------------------
#
# Promoted verbatim from `products/core/backend/app/dependencies.py` so any
# future identity-source product (a 2nd "control-plane product") can compose
# them instead of reimplementing. Today's sole caller is `core`.
#
# Settings requirements (product's settings object must expose):
#   - `jwt_secret: str`
#   - `jwt_algorithm: str`             (e.g. "HS256")
#   - `sso_token_expiration_minutes: int`
#
# Usage in a product's `app/dependencies.py`::
#
#     from noctusai_lib.api.auth import create_sso_token_factory, verify_sso_token_factory
#     create_sso_token = create_sso_token_factory(settings)
#     verify_sso_token = verify_sso_token_factory(settings)


def create_sso_token_factory(settings) -> Callable[..., str]:
    """Return a `create_sso_token` callable bound to `settings`.

    Signature of the returned callable::

        create_sso_token(
            user_id: str,
            org_id: str,
            product_slug: str,
            email: str,
            role: str = "user",
            org_role: str = "member",
        ) -> str

    `role` is the NoctusAI platform-level role (admin / manager / user).
    `org_role` is the user's role within their org (owner / admin / member /
    viewer). Products use `org_role` to decide product-level admin access.
    """
    def create_sso_token(
        user_id: str,
        org_id: str,
        product_slug: str,
        email: str,
        role: str = "user",
        org_role: str = "member",
    ) -> str:
        payload = {
            "sub": user_id,
            "org_id": org_id,
            "product": product_slug,
            "email": email,
            "role": role,
            "org_role": org_role,
            "type": "sso",
            "iss": SSO_ISSUER,
            "aud": SSO_AUDIENCE,
            "exp": now_utc() + datetime.timedelta(
                minutes=settings.sso_token_expiration_minutes
            ),
            "iat": now_utc(),
        }
        return jwt.encode(payload, _sso_secret(settings), algorithm=settings.jwt_algorithm)

    return create_sso_token


def verify_sso_token_factory(settings) -> Callable[[str], dict]:
    """Return a `verify_sso_token(token) -> payload` callable bound to `settings`.

    Raises `HTTPException(401)` on expired / invalid / non-SSO tokens.
    """
    def verify_sso_token(token: str) -> dict:
        # NOC-REMEDIATE[security]: `aud` is a fixed bridge constant and the minted
        # `product` claim is NOT verified here — so a token issued for product A is,
        # at the JWT layer, valid if redeemed for product B. Bounded today because
        # core is the SOLE verifier (products are couriers that POST back to core's
        # /api/sso/session). BEFORE a 2nd identity-source product consumes these
        # factories, bind the audience to the product: pass an expected slug into
        # verify (e.g. verify_sso_token(token, expected_product=...)) and assert
        # payload["product"], or mint aud=f"noctusai-sso:{slug}". (security review
        # 2026-06-04, warning-2.)
        try:
            payload = jwt.decode(
                token,
                _sso_secret(settings),
                algorithms=[settings.jwt_algorithm],
                issuer=SSO_ISSUER,
                audience=SSO_AUDIENCE,
                leeway=10,  # seconds of clock-skew tolerance for exp/iat/nbf
                options={"require": ["exp", "iat", "iss", "aud", "type"]},
            )
            if payload.get("type") != "sso":
                raise HTTPException(status_code=401, detail="Token não é SSO")
            return payload
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token SSO expirado")
        except jwt.InvalidTokenError:
            raise HTTPException(status_code=401, detail="Token SSO inválido")

    return verify_sso_token


class SSOSessionCache:
    """Thread-safe in-memory SSO session cache with TTL + per-key locking.

    Promoted from `products/core/backend/app/routers/sso.py::_SSOSessionCache`
    so any identity-source product can reuse the same concurrency semantics.

    Shape preserved byte-for-byte: get/set/invalidate/clear + per-key lock
    acquisition to serialize expensive Supabase session generation per user.

    TTL is parameterizable. Core uses 300s (5 min) — above Supabase's 60s
    rate limit between magic-link generations but tight enough to let role
    revocations take effect quickly. Explicit invalidation via `invalidate(email)`
    or `clear()` flushes on demand (role-change / license-revoke / org-reassign
    hooks should call invalidate; see core's `invalidate_sso_cache_for_user`).
    """

    def __init__(self, ttl_seconds: int = 300) -> None:
        self._ttl = ttl_seconds
        self._store: Dict[str, Tuple[dict, float]] = {}
        self._locks: Dict[str, threading.Lock] = {}
        self._global_lock = threading.Lock()

    def get(self, email: str) -> Optional[dict]:
        """Return cached session for email or None (expired / absent)."""
        entry = self._store.get(email)
        if entry is None:
            return None
        data, created_at = entry
        if time.monotonic() - created_at > self._ttl:
            self._store.pop(email, None)
            return None
        return data

    def set(self, email: str, data: dict) -> None:
        """Store session data keyed by email with current timestamp."""
        self._store[email] = (data, time.monotonic())

    def get_lock(self, email: str) -> threading.Lock:
        """Per-email lock — serializes concurrent SSO session generation."""
        with self._global_lock:
            if email not in self._locks:
                self._locks[email] = threading.Lock()
            return self._locks[email]

    def invalidate(self, email: str) -> bool:
        """Remove a single entry. Returns True iff removed."""
        return self._store.pop(email, None) is not None

    def clear(self) -> None:
        """Flush every entry and every per-key lock."""
        self._store.clear()
        with self._global_lock:
            self._locks.clear()
