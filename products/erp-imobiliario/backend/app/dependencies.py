"""
Shared dependencies for FastAPI routers — seed framework + ERP extensions.

Standard deps (get_current_user, get_user_role, get_user_client, get_admin_client)
come from the seed framework. ERP-specific deps (get_org_id with required param,
log_action) are defined here.

Canonical auth pattern (PF retro §e row 1 — formalized 2026-05-11):
The :func:`noctusai_lib.api.auth.make_get_current_user_org` factory binds the
``(user, token, org_id)`` triple resolution at module load. Routers consume the
resulting closure-bound dep via ``Depends(get_current_user_org)`` instead of
the imperative ``Header(authorization) + await get_current_user(authorization)``
shape — see ``KB § PATTERNS/backend.md § Auth — canonical pattern`` (the
original reference adopter was the retired ``youtube-crawler`` product,
consolidated into ``social-wiring`` 2026-05-16).
"""
import logging
from types import SimpleNamespace
from typing import Optional

from fastapi import Depends, HTTPException
from noctusai_seed import create_database_module, create_dependencies
from noctusai_seed.auth_router import get_session_store as _seed_get_session_store
from noctusai_lib.domain.action_log import log_action as _shared_log_action
from noctusai_lib.api.auth import (
    first_or_none,  # noqa: F401 — re-exported for product imports
    make_get_current_user,
    make_get_current_user_org,
    make_require_role,
    make_resolve_platform_role,
)
from noctusai_lib.api.auth.session import (
    AuthContext,
    FakeApiTokenResolver,
    make_get_auth_context,
    make_token_exchanger,
)
from app.config import settings

_db = create_database_module(settings, schema="erp")
deps = create_dependencies(_db)

get_user_role = deps.get_user_role
get_user_client = deps.get_user_client
get_admin_client = deps.get_admin_client

logger = logging.getLogger(__name__)


def resolve_org_id_db(user_id: str) -> Optional[str]:
    """Single source of truth for a caller's org: the DB, not the JWT.

    Reads ``public.noctus_users`` — the SAME row RLS resolves via
    ``current_org_id()`` — so the app's notion of org can never drift from
    what RLS enforces. Unlike a JWT ``user_metadata`` read (which goes stale
    until the user re-authenticates), this reflects a provisioning change
    immediately.

    Uses the CORE client — ``noctus_users`` lives in the ``public`` schema, NOT
    the product's ``erp`` schema. The erp-scoped admin client would resolve
    ``.table("noctus_users")`` to ``erp.noctus_users`` and PGRST205 → 500
    (regression shipped + caught in prod 2026-07-07; the schema-agnostic mock
    hid it). ``get_core_client`` targets ``public`` with the service role
    (bypasses RLS), reading the single PK row.
    Returns None for an unprovisioned user (no noctus_users row / null org).
    """
    core = _db.get_core_client()
    res = (
        core.table("noctus_users")
        .select("org_id")
        .eq("id", user_id)
        .limit(1)
        .execute()
    )
    if res.data and res.data[0].get("org_id"):
        return res.data[0]["org_id"]
    return None


def get_org_id(user, *, required: bool = False) -> Optional[str]:
    """Resolve a caller's org — trusted DB first, JWT metadata transition fallback.

    ``org-source-of-truth Phase 2`` (2026-07-16): this is THE call-site every
    one of ERP's 21 org-scoped routers funnels through (rather than each
    router reaching into ``user.user_metadata`` directly), so fixing org
    resolution HERE — once — fans the fix to every router without touching
    20 files individually (the ``No quick fixes`` root-cause principle: a fix
    needed in N call-sites for one reason belongs at the ONE function they
    all call, not copy-pasted N times).

    Mirrors :func:`resolve_org_id_db` / the seed's
    :func:`noctusai_lib.api.auth.make_get_current_user_org` trust model
    exactly: ``public.noctus_users`` (the SAME row RLS's ``current_org_id()``
    reads) wins whenever a row exists. ``user.user_metadata.get("org_id")``
    — spoofable via ``auth.updateUser({data})`` — is now ONLY a transition
    fallback for a user mid-provisioning (no ``noctus_users`` row yet), and
    fires with a ``logger.warning`` naming the user id, never silently.

    By default returns None if missing (backwards-compatible with every
    existing non-required call site). Pass required=True where org_id is
    strictly needed — raises the same 400 as before.
    """
    org_id = resolve_org_id_db(user.id)
    if not org_id:
        fallback = (user.user_metadata or {}).get("org_id")
        if fallback:
            logger.warning(
                "erp_org_lookup_empty user_id=%s — no noctus_users row, "
                "falling back to user_metadata resolver (org_id=%r)",
                user.id, fallback,
            )
        org_id = fallback
    if not org_id and required:
        raise HTTPException(status_code=400, detail="Organizacao nao encontrada no perfil do usuario")
    return org_id or None


# Canonical auth deps — wire via the factory so FastAPI sees only
# ``authorization: Header(None)`` in the dep signature.
#
# Late-binding lambda: the conftest patches ``_db.get_client`` AFTER this
# module imports. Capturing the bound method at module load
# (``make_get_current_user(_db.get_client)``) would freeze the pre-patch
# reference. The lambda re-resolves on every request so both production
# and test paths see the right client.
get_current_user = make_get_current_user(lambda: _db.get_client())
# `get_admin_client_fn=lambda: _db.get_core_client()` — same client
# `resolve_org_id_db` above already uses. `noctus_users` lives in the
# `public` schema; the erp-scoped admin client would 500 with PGRST205
# (the exact regression `resolve_org_id_db`'s docstring documents,
# 2026-07-07). See `seed-trusted-org-resolution` (2026-07-14) — the
# make_get_current_user_org docstring in noctusai_lib.api.auth has the
# full trust-model rationale.
get_current_user_org = make_get_current_user_org(
    get_current_user,
    lambda u: get_org_id(u),  # fallback only — trusted DB wins
    get_admin_client_fn=lambda: _db.get_core_client(),
    required=True,
    missing_status=400,
    missing_detail="Organizacao nao encontrada no perfil do usuario",
)

# Trusted-first platform-admin cascade (``role-cascade-trusted``, 2026-07-14)
# — same ``get_core_client`` client `get_current_user_org` already uses;
# `noctus_users` lives in `public`, not `erp`. See
# `noctusai_lib.api.auth.make_resolve_platform_role`'s docstring for the
# full trust-model rationale (mirrors `make_get_current_user_org`'s).
resolve_platform_role = make_resolve_platform_role(lambda: _db.get_core_client())


def log_action(user_id: str, tipo_acao: str, tipo_entidade: str,
               entidade_id: Optional[str] = None, descricao: str = "", detalhes: Optional[dict] = None):
    """Server-side action logging. Always runs with service role."""
    _shared_log_action(
        get_admin_client(), "user_actions_log", "usuario_id",
        user_id, tipo_acao, tipo_entidade, entidade_id, descricao, detalhes,
    )


# ---------------------------------------------------------------------------
# Role resolution + `require_role` factory wiring
# ---------------------------------------------------------------------------
# Phase 3 (erp-wiring 2026-05-11) — Pattern F continuation. Replaces the
# bespoke `vista_showcase.require_admin` SSO-aware gate and the inline
# `metas_digest` role check with seed `make_require_role` composition.
#
# ERP's role resolution differs from the seed default because it preserves
# *both* historical metadata keys (`erp_role` first, `noctus_role` second)
# while still letting the platform-admin cascade short-circuit to
# "platform_admin" for cross-product SSO admins. The seed primitive only
# consumes the resolver — composition stays in product code.
#
# `role-cascade-trusted` (2026-07-14): closed the role-spoof hole AND added
# the missing ERP-scoped elevation tier. Resolution order is now:
#   1. Trusted platform-admin cascade (`public.noctus_users`, via
#      `resolve_platform_role`) — a Noctus platform admin is admin in
#      EVERY product, including ERP. Trusted DB, never spoofable
#      `user_metadata`.
#   2. Trusted ERP-scoped elevation (`public.has_role(user.id,
#      'admin'::erp.app_role)`, backed by `erp.user_roles`) — an ERP admin
#      explicitly granted THIS user 'admin' WITHIN ERP (see
#      `POST /api/profiles/{user_id}/roles`). Elevate-only + product-scoped
#      by construction: it is consulted ONLY after step 1 has already
#      returned (so it can never demote a platform admin), and it reads
#      `erp.user_roles` — a table no other product's role resolver touches
#      (so it can never cascade elsewhere).
#   3. `erp.user_roles` base row (`corretor` / `coordenador` / `dev`) when
#      one exists — the ERP-native role vocabulary, trusted DB.
#   4. `user_metadata.erp_role` / `.noctus_role` — legacy, spoofable,
#      transition-only fallback (warned). `"user"` sentinel default
#      otherwise; downstream `require_role(*allowed)` will 403.
#
# Both DB legs (2 + 3) fail CLOSED on a genuine error — the exception
# propagates rather than silently falling through to the spoofable
# metadata fallback, mirroring `make_resolve_platform_role`'s documented
# trust model for the exact same reason: falling back in the error branch
# would reopen the hole this change closes, in the one place a regression
# would hide silently.


def get_erp_user_role(user) -> str:
    """Resolve ERP-tier role for a user — trusted-first, product-scoped override.

    See the module-level comment above for the full resolution order + the
    fail-closed rationale on the two DB legs.
    """
    platform_role = resolve_platform_role(user)
    if platform_role == "platform_admin":
        return platform_role

    # `public.has_role` lives in the `public` schema (NOT `erp`) — the
    # erp-scoped admin client would resolve it against the wrong schema
    # and 500 with PGRST205 (the same class of regression documented on
    # `resolve_org_id_db` above). Use the core client, same as
    # `resolve_platform_role`.
    core = _db.get_core_client()
    try:
        elevated = core.rpc(
            "has_role", {"_user_id": user.id, "_role": "admin"}
        ).execute()
    except Exception:
        logger.error(
            "erp_has_role_lookup_error user_id=%s — failing closed "
            "(NOT treating as elevated)",
            user.id, exc_info=True,
        )
        raise
    if elevated.data:
        return "admin"

    admin = get_admin_client()  # erp-scoped — erp.user_roles lives here
    try:
        base_row = (
            admin.table("user_roles")
            .select("role")
            .eq("user_id", user.id)
            .limit(1)
            .execute()
        )
    except Exception:
        logger.error(
            "erp_user_roles_lookup_error user_id=%s — failing closed",
            user.id, exc_info=True,
        )
        raise
    if base_row.data:
        return base_row.data[0]["role"]

    metadata = user.user_metadata or {}
    fallback = metadata.get("erp_role") or metadata.get("noctus_role")
    if fallback:
        logger.warning(
            "erp_role_lookup_empty user_id=%s — no erp.user_roles row, "
            "falling back to user_metadata resolver (role=%r)",
            user.id, fallback,
        )
    return fallback or "user"


# Canonical `require_role(*allowed)` factory — bound once at module load to
# this product's `get_current_user` (Supabase-client-aware) and ERP role
# resolver. Routers consume via `Depends(require_role("admin", "owner"))`.
require_role = make_require_role(get_current_user, get_erp_user_role)


# ─── Cookie-session auth infra (erp-httponly-cookie-session-2026-07 roadmap,
# Slice 2) ───────────────────────────────────────────────────────────────
#
# ERP's existing `get_current_user_org` (raw Supabase JWT bearer, above) is
# UNCHANGED and remains every one of the 61 existing routers' dep — this
# section is ADDITIVE, mirroring `products/social-wiring/backend/app/
# dependencies.py`'s Wave-2 auth infra: a parallel `get_current_user_org_
# unified` dep any router can opt into for cookie-session support, the same
# per-router opt-in rollout social-wiring used for its
# youtube-drive-folder-fanout endpoints. No existing ERP router is migrated
# by this slice — see the mount in `app/main.py` (`standard_routers=[...,
# "auth"]`) for the `/api/auth/{login,me,logout}` + `/api/settings/
# api-tokens` endpoints themselves, which do not need this dep at all
# (`login`/`me`/`logout` never touch a per-request RLS client; the
# api-token endpoints use `deps.get_admin_client()` / `get_core_client()`
# service-role clients).


def _get_session_store():
    """Delegates to ``noctusai_seed.auth_router.get_session_store(settings)``
    — the SAME process-local singleton the seed's ``create_auth_router``
    mount (wired via ``standard_routers=["auth"]`` in ``app/main.py``) uses
    internally. A second ``make_session_store(...)`` call here would
    split-brain the in-memory Fake (dev/test, no ``redis_url``): a session
    minted through the mounted router's own ``/login`` would be invisible
    to a lookup running through a SEPARATE ``FakeSessionStore()`` instance.
    See that factory's docstring for the full rationale — identical
    reasoning to social-wiring's ``_get_session_store``.
    """
    return _seed_get_session_store(settings)


_token_exchanger = None
_token_exchanger_settings_id = None


def _get_token_exchanger():
    """Lazy singleton ``TokenExchanger`` (SEC-1/SEC-2) — the seam SEC-6
    requires: a per-request RLS-scoped Supabase client for a cookie-session
    caller MUST be built from the token this returns (a freshly-MINTED
    Supabase access token), never the opaque ``nai_session`` cookie value /
    session id itself. See ``get_current_user_org_unified`` below for the
    consumer.

    Real (``SupabaseTokenExchanger``) when ``settings.redis_url`` is set —
    the per-session ``SET NX EX`` refresh lock (SEC-2) needs a live Redis
    connection to serialize concurrent refreshes. The refresh itself always
    runs through ``make_default_refresh_fn`` on a THROWAWAY anon
    ``create_client(url, anon_key)`` (SEC-1 — never the shared admin
    singleton; ``check_auth_session_mutation_on_shared_client`` guards this
    class of regression, the 2026-05-23 core prod outage). Falls back to
    the in-memory ``FakeTokenExchanger`` under local-dev/test (no Redis
    configured) — mirrors ``_get_session_store``'s Fake fallback.

    The lock client is a SEPARATE ``redis.asyncio`` connection from the
    session store's — safe by construction (Redis IS the shared state, not
    the Python object handle; ``make_session_store``'s docstring makes the
    same argument for the store side).

    Keyed by ``id(settings)`` (not memoized forever) so per-test suites
    that construct a fresh ``Settings()`` per test get an isolated
    exchanger instead of leaking state across tests — mirrors
    ``noctusai_seed.auth_router.get_session_store``'s keying.
    """
    global _token_exchanger, _token_exchanger_settings_id
    if _token_exchanger is None or _token_exchanger_settings_id != id(settings):
        redis_url = getattr(settings, "redis_url", None) or None
        lock_client = None
        if redis_url:
            from redis.asyncio import Redis

            lock_client = Redis.from_url(redis_url, decode_responses=True)
        _token_exchanger = make_token_exchanger(
            _get_session_store(),
            supabase_url=getattr(settings, "supabase_url", None) or None,
            supabase_anon_key=getattr(settings, "supabase_anon_key", None) or None,
            lock_client=lock_client,
        )
        _token_exchanger_settings_id = id(settings)
    return _token_exchanger


class _LazySessionStore:
    """Defers to ``_get_session_store()`` on first method call — so wiring
    ``get_auth_context`` at module-import time never touches Redis (test
    collection / sqlite local-dev safety). Mirrors social-wiring's
    ``_LazySessionStore``."""

    async def create(self, **kwargs):
        return await _get_session_store().create(**kwargs)

    async def lookup(self, session_id):
        return await _get_session_store().lookup(session_id)

    async def refresh_ttl(self, session_id, ttl_seconds: int = 86400):
        return await _get_session_store().refresh_ttl(session_id, ttl_seconds)

    async def delete(self, session_id):
        return await _get_session_store().delete(session_id)

    async def read_tokens(self, session_id):
        return await _get_session_store().read_tokens(session_id)

    async def write_tokens(self, session_id, **kwargs):
        return await _get_session_store().write_tokens(session_id, **kwargs)


# Pure new-scheme dep (cookie + `pk_*` only — NO `legacy_jwt_resolver`). A
# cookie-authenticated `caller_kind="user"` AuthContext's `raw_token` is
# therefore GUARANTEED to be the session id (never a raw JWT), which is
# exactly what `get_current_user_org_unified` below needs to call
# `TokenExchanger.access_token_for(session_id)` unambiguously — mixing in a
# legacy-JWT bridge here would make `raw_token` ambiguous between "session
# id" and "raw JWT" for the SAME `caller_kind`, breaking that precondition.
# No pk_* automation consumer is wired to ERP's business routers yet
# (`FakeApiTokenResolver` never resolves a bearer), matching the "no
# real-resolver need on day one" ERP-shaped choice `app/main.py`'s
# `standard_routers=["auth"]` mount also makes.
get_auth_context = make_get_auth_context(
    session_store=_LazySessionStore(),
    api_token_resolver=FakeApiTokenResolver(),
    legacy_jwt_resolver=None,
    session_cookie_name="nai_session",
)


async def get_current_user_org_unified(ctx: AuthContext = Depends(get_auth_context)):
    """Cookie-session-aware sibling of ``get_current_user_org`` — SEC-6.

    Exchanges the cookie session for a freshly-minted Supabase access token
    (never the opaque session id) via ``TokenExchanger.access_token_for``,
    so ``get_user_client(token)`` -> ``make_supabase_client(..., access_
    token=...)`` -> ``client.auth.set_session(access_token, "")`` always
    receives a REAL access token. ``check_auth_session_mutation_on_shared_
    client`` guards the separate "which CLIENT" hazard (never the shared
    admin singleton); this dep is the companion "which VALUE" invariant the
    roadmap's SEC-6 line names explicitly — a cookie-derived AuthContext's
    session id never reaches ``set_session`` as-is.

    Returns the same ``(user, token, org_id)`` shape ``get_current_user_org``
    does, so an opting-in router's existing ``db = get_user_client(token)``
    call site needs NO change beyond the ``Depends(...)`` swap.

    Not yet consumed by any existing ERP router (out of this slice's scope
    — the 61 routers stay on ``get_current_user_org``/legacy JWT bearer,
    unchanged); a future per-router migration opts in the same way
    social-wiring's youtube-drive-folder-fanout endpoints did for its own
    ``get_current_user_org_unified``.
    """
    if ctx.caller_kind != "user":
        # No product/pk_* automation consumer is wired to ERP's business
        # routers yet — `FakeApiTokenResolver` never resolves a `pk_*`
        # bearer above, so this branch is unreachable today. Kept explicit
        # (rather than silently coerced into a user-shaped tuple) so it
        # fails loud instead of silently misrepresenting the caller if a
        # real `ApiTokenResolver` is wired in later.
        raise HTTPException(status_code=403, detail="Restricted to human users")

    access_token = await _get_token_exchanger().access_token_for(ctx.raw_token)
    user = SimpleNamespace(
        id=str(ctx.user_id),
        email=None,
        user_metadata={"org_id": str(ctx.org_id)},
    )
    return user, access_token, str(ctx.org_id)
