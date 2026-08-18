"""
Dependencies for Social Wiring.

The seed framework's ``ProductDependencies`` exports ``get_org_id`` /
``get_user_role`` / ``get_user_client`` as plain functions; using them as
``Depends()`` does NOT chain through FastAPI because their positional
``user`` / ``token`` args become required query parameters (loc:
``['query', 'user']``). The canonical pattern is to bind
:func:`noctusai_lib.api.auth.make_get_current_user_org` once at module
load and use the resulting closure-bound dep at every router site.

See ``KB § PATTERNS/backend.md § Auth — canonical pattern`` for the why.

Wave 2 of ``platform-auth-modernization`` (2026-05-20) adds:

  - ``get_auth_context``: the new unified dep from
    :func:`noctusai_lib.api.auth.session.make_get_auth_context`. Returns
    an ``AuthContext`` value object for cookie-session human users AND
    ``pk_*`` automation tokens. New routes (login / api-tokens
    management) take ``Depends(get_auth_context)`` directly.
  - Dual-mode bridge: the legacy JWT bearer path continues to work
    through ``_legacy_jwt_resolver`` so every existing route keeps its
    ``Depends(get_current_user_org)`` shape — the resolver-side change
    is INVISIBLE to those handlers.
"""
import asyncio as _asyncio
import logging as _logging
import uuid as _uuid
import weakref as _weakref
from types import SimpleNamespace
from typing import Any
from uuid import UUID

from fastapi import Depends

from noctusai_seed import create_database_module, create_dependencies
from noctusai_lib.api.auth import (
    first_or_none,  # noqa: F401 — re-exported for product imports
    make_get_current_user,
    make_get_current_user_org,
    resolve_sso_role,  # noqa: F401 — re-exported for product imports
)
from noctusai_lib.api.auth.session import (
    AuthContext,
    FakeApiTokenResolver,
    make_get_auth_context,
)
from noctusai_seed import make_get_settings
from noctusai_seed.auth_router import get_session_store as _seed_get_session_store

from app.config import settings
from app.sqlite_client import SQLiteClient

_logger = _logging.getLogger(__name__)


# FastAPI dependency returning the product settings singleton — the honest
# Class-A DI seam: routers ``Depends(get_settings)`` read ``cfg.X``; tests
# override via ``app.dependency_overrides[get_settings]`` instead of
# ``monkeypatch.setattr(settings, "X", ...)`` (which trips
# ``check_no_self_monkeypatch``). Consumes the seed factory
# ``noctusai_seed.make_get_settings`` — the N>=3 settings-DI formalization —
# rather than a product-local def. Per ``KB § PATTERNS/di-test-seam.md`` Class-A.
get_settings = make_get_settings(settings)


_sqlite_client = SQLiteClient(settings.sqlite_path)
_db = None
_deps = None
_use_sqlite = settings.database_backend.lower() == "sqlite"
if not _use_sqlite:
    _db = create_database_module(settings, schema="social_wiring")
    _deps = create_dependencies(_db)

# Canonical auth deps — wire via the factory so FastAPI sees only
# ``authorization: Header(None)`` in the dep signature.
#
# Late-binding lambda: the conftest patches ``_db.get_client`` AFTER
# this module imports. Capturing the bound method at module load
# (``make_get_current_user(get_supabase_client)``) would freeze the
# pre-patch reference. The lambda re-resolves on every request so
# both production and test paths see the right client.
if _use_sqlite:
    async def get_current_user():
        return SimpleNamespace(
            id=settings.local_dev_user_id,
            email="local-dev@noctusai.local",
            user_metadata={"org_id": settings.local_dev_org_id},
        )

    async def get_current_user_org():
        user = await get_current_user()
        return user, "local-dev-token", settings.local_dev_org_id
else:
    get_current_user = make_get_current_user(lambda: _db.get_client())
    # `get_admin_client_fn=lambda: _db.get_core_client()` — NOT
    # `_db.get_admin_client()`. `noctus_users` lives in the `public`
    # schema; the social_wiring-scoped admin client would 500 with
    # PGRST205 (see `seed-trusted-org-resolution`, 2026-07-14 — the
    # make_get_current_user_org docstring in noctusai_lib.api.auth has
    # the full rationale + the prod incident this mirrors on the ERP
    # side). NOTE: `_legacy_jwt_resolver` below (the AuthContext / cookie
    # / pk_* bridge) still resolves org_id straight from
    # `user.user_metadata` — a SEPARATE, still-spoofable path this slice
    # deliberately did not touch (org_id-only scope; the bridge is a
    # platform-auth-modernization concern). Flagged as `drift-found:`.
    get_current_user_org = make_get_current_user_org(
        get_current_user,
        lambda u: (u.user_metadata or {}).get("org_id"),  # fallback only — trusted DB wins
        get_admin_client_fn=lambda: _db.get_core_client(),
        required=True,
    )

# Plain-call helpers (NOT to be wired via ``Depends(...)``) — kept for
# imperative call-sites and for backward compatibility with existing
# imports. Will emit ``DeprecationWarning`` after Phase 2 lands the
# seed-side warning.
get_user_role = _deps.get_user_role if _deps is not None else (lambda *_args, **_kwargs: "owner")
get_org_id = _deps.get_org_id if _deps is not None else (lambda *_args, **_kwargs: settings.local_dev_org_id)
# Late-binding wrappers so test patches on ``_db.get_*`` reach call sites.
def get_user_client(token: str):
    if _use_sqlite:
        return _sqlite_client
    return _db.get_client(token)


def get_admin_client():
    if _use_sqlite:
        return _sqlite_client
    return _db.get_admin_client()


_scoped_client_cache: "_weakref.WeakKeyDictionary[Any, dict[str, Any]]" = (
    _weakref.WeakKeyDictionary()
)


def get_scoped_admin_client(schema: str = "social_wiring") -> Any:
    """Schema-scoped admin client, cached by the underlying admin-client
    OBJECT (never re-derived per call) — the formalized version of a
    pattern that had already independently recurred THREE times before
    this one: `app/modules/leads/deps.py::get_leads_client`,
    `app/services/portal_roi_service.py::get_portal_roi_client`,
    `app/routers/clientes_router.py::get_clientes_client`. All three fix
    the SAME confirmed `MockSupabaseClient` defect: `.schema(name)`
    returns a BRAND NEW wrapper with an EMPTY per-table row cache on
    every call, so re-deriving the schema binding per request silently
    loses every prior write the instant two separate calls re-scope. A
    real Supabase client is stateless HTTP-request shaping either way —
    this is a pure test-correctness fix, zero production behaviour
    change.

    This is the FOURTH occurrence (the clientes-inactivity settings
    endpoints below), i.e. the N≥3 DRY-recurrence trigger
    (`KB § PATTERNS/architect/project-execution.md § 2.7`). The three
    existing local copies are NOT migrated onto this shared helper here
    — doing so is out of this change's scope and flagged as a
    `scoped-improvement:` in the delivery note instead, so this edit
    stays limited to what it actually needs."""
    admin = get_admin_client()
    per_admin = _scoped_client_cache.setdefault(admin, {})
    cached = per_admin.get(schema)
    if cached is None:
        cached = admin.schema(schema)
        per_admin[schema] = cached
    return cached


def get_core_client():
    """``public``-schema-scoped client — ``noctus_users`` lives there,
    NOT the product schema (a `get_admin_client()` lookup 500s with
    PGRST205; see ``feedback_product_client_schema_scoping_public_tables``
    memory entry). Falls back to the sqlite client under local-dev
    sqlite mode (mirrors ``get_admin_client``'s fallback — sqlite has no
    schema separation to get wrong)."""
    if _use_sqlite:
        return _sqlite_client
    return _db.get_core_client()


# Adapter exposing exactly the `deps.get_admin_client()` / `deps.get_core_client()`
# surface `noctusai_seed.auth_router.create_auth_router(deps, settings)` needs —
# NOT the full `ProductDependencies` shape (`_deps` is `None` under sqlite
# local-dev). Consumed by `app.main` to build the seed's auth router directly
# (passing this product's REAL `api_token_resolver` / `legacy_jwt_resolver`
# overrides — the registry's `_build_auth_router(deps, settings, product_name,
# version)` builder has no seam for those, see `create_auth_router`'s
# docstring).
auth_router_deps = SimpleNamespace(
    get_admin_client=get_admin_client,
    get_core_client=get_core_client,
)


# Auth-side org_id is sometimes a UUID string, sometimes an opaque
# fixture string (`"test-org-123"`). DB columns are UUID-typed; coerce
# here so call sites don't repeat the try/except. Lifted to this module
# at the N=3 recurrence trigger (upload_router + settings_router +
# videos_router each had a private copy). The user-scoped supabase
# client is RLS-bound by the JWT, not by this UUID — safe to derive a
# deterministic UUID via uuid5 for non-UUID fixture inputs.
def coerce_org_uuid(raw_org: Any) -> UUID:
    """Coerce the auth-side org_id (string or UUID) into a UUID."""
    try:
        return UUID(str(raw_org))
    except (ValueError, TypeError):
        return _uuid.uuid5(_uuid.NAMESPACE_OID, str(raw_org))


# ─── Wave-2 unified auth-context dep ─────────────────────────────────
#
# Composes the seed's ``make_get_auth_context`` factory with:
#   - ``SessionStore``: Redis-backed in production, ``FakeSessionStore``
#     under sqlite/dev. Lazy singleton so import doesn't pin Redis.
#   - ``ApiTokenResolver``: ``SupabaseApiTokenResolver`` over the admin
#     client; ``FakeApiTokenResolver`` under sqlite/dev.
#   - ``legacy_jwt_resolver``: bridges raw JWT bearers through
#     ``make_get_current_user`` + org resolution so every existing
#     route keeps working untouched during the migration window.
#
# Routes that want the new shape ``Depends(get_auth_context)`` get
# ``AuthContext`` directly; routes still on ``Depends(get_current_user_org)``
# resolve the same way (the dep is unchanged in shape; the underlying
# resolution can fall through the new unified path or remain on the
# legacy JWT verifier — both produce identical ``(user, token, org_id)``).

_api_token_resolver = None
_get_auth_context = None


def _get_session_store():
    """Delegates to ``noctusai_seed.auth_router.get_session_store(settings)``
    — the SAME process-local singleton the seed's promoted
    ``create_auth_router`` composition uses (keyed by ``id(settings)``,
    see that module's docstring). Redis-backed (SEC-3 encrypted-at-rest)
    when ``settings.redis_url`` is set; the in-memory ``FakeSessionStore``
    otherwise (dev/test — no Redis configured).

    Sharing the SAME accessor (rather than this module calling its own
    ``make_session_store(...)``) matters for the in-memory Fake: a
    second ``FakeSessionStore()`` instance is a separate empty dict, so
    a session minted through one composition (this product's
    ``get_auth_context``, used by ``get_current_user_org_unified``) would
    be invisible to a lookup running through the OTHER (the seed
    router's own ``/me``/``/logout``) — and vice versa. Delegating here
    closes that hazard by construction. Fixes the erp-httponly-cookie-
    session-2026-07 roadmap Slice 1b (iii) finding: this function
    previously returned a bare, never-persisted ``FakeSessionStore()``
    unconditionally (a `TODO: swap to RedisSessionStore` that never
    landed) — every cookie session died on process restart fleet-wide
    regardless of ``settings.redis_url``."""
    return _seed_get_session_store(settings)


def _get_api_token_resolver():
    """Lazy singleton — Supabase-backed in production, ``FakeApiTokenResolver``
    under sqlite/dev (no DB to look up against)."""
    global _api_token_resolver
    if _api_token_resolver is None:
        if _use_sqlite:
            _api_token_resolver = FakeApiTokenResolver()
        else:
            # Local import to avoid the resolver pulling its
            # noctusai_lib chain into the test-collection path before
            # the conftest patches DatabaseModule.get_admin_client.
            from app.services.api_token_resolver import SupabaseApiTokenResolver
            _api_token_resolver = SupabaseApiTokenResolver(get_admin_client())
    return _api_token_resolver


async def _legacy_jwt_resolver(token: str) -> AuthContext | None:
    """Bridge a raw Supabase JWT to an ``AuthContext`` (``caller_kind="user"``).

    The dep's contract is that this is called ONLY when the bearer is
    NOT ``pk_*`` (i.e. a JWT-shaped legacy token). We synthesize an
    ``Authorization: Bearer <token>`` header, run it through the
    existing JWT-verifying ``get_current_user`` machinery, then project
    the resulting user into an ``AuthContext``. Returns ``None`` on any
    failure so the dep returns 401 — never raises out.
    """
    try:
        result = await get_current_user(authorization=f"Bearer {token}")
    except Exception:
        # The legacy verifier raises HTTPException(401) on bad JWTs;
        # the bridge must return None so the dep can produce its own
        # 401 (consistent shape with the new auth scheme).
        return None
    if result is None:
        return None
    # The seed's ``make_get_current_user`` returns ``(user, token)``;
    # the sqlite local-dev shape above returns just ``user``. Tolerate
    # both — we only need the user object.
    if isinstance(result, tuple):
        user = result[0]
    else:
        user = result
    if user is None:
        return None
    raw_org = (getattr(user, "user_metadata", None) or {}).get("org_id")
    if not raw_org:
        return None
    try:
        org_id = coerce_org_uuid(raw_org)
    except Exception:
        _logger.warning("legacy_jwt_org_coerce_failed raw=%r", raw_org)
        return None
    try:
        user_id = UUID(str(user.id))
    except (ValueError, TypeError):
        # Local-dev fixtures may use opaque ids; derive a stable UUID.
        user_id = _uuid.uuid5(_uuid.NAMESPACE_OID, str(user.id))
    return AuthContext(
        org_id=org_id,
        caller_kind="user",
        user_id=user_id,
        scopes=[],
        raw_token=token,  # JWT — preserves the bearer for legacy callers
        api_token_id=None,
    )


# get_current_user is defined above for the bearer path. The bridge
# above invokes it with a Header-shaped authorization string, which is
# the exact signature the seed's ``make_get_current_user`` produces.


# Lazy proxy objects so that ``make_get_auth_context`` can be wired at
# import time WITHOUT resolving the real SessionStore / ApiTokenResolver
# (the Real ApiTokenResolver pulls ``get_admin_client()`` which needs a
# live Supabase URL — not available during test collection or sqlite
# local-dev). Each proxy lazily defers to ``_get_*()`` on the FIRST
# protocol method call (per-request).
class _LazyApiTokenResolver:
    """Defers to ``_get_api_token_resolver()`` on first resolve call."""

    async def resolve(self, token_secret):
        return await _get_api_token_resolver().resolve(token_secret)


class _LazySessionStore:
    """Defers to ``_get_session_store()`` on first method call."""

    async def create(self, **kwargs):
        return await _get_session_store().create(**kwargs)

    async def lookup(self, session_id):
        return await _get_session_store().lookup(session_id)

    async def refresh_ttl(self, session_id, ttl_seconds=86400):
        return await _get_session_store().refresh_ttl(session_id, ttl_seconds)

    async def delete(self, session_id):
        return await _get_session_store().delete(session_id)


get_auth_context = make_get_auth_context(
    session_store=_LazySessionStore(),
    api_token_resolver=_LazyApiTokenResolver(),
    legacy_jwt_resolver=_legacy_jwt_resolver,
    session_cookie_name="nai_session",
)


def auth_context_to_legacy_tuple(ctx: AuthContext):
    """Project an ``AuthContext`` back to the legacy ``(user, token,
    org_id)`` tuple every existing router expects.

    For ``caller_kind == "user"`` callers (JWT bridge or cookie session),
    builds a ``SimpleNamespace`` user mirroring the Supabase shape with
    just enough surface for the routes that touch ``user.id`` /
    ``user.user_metadata``. For ``caller_kind == "product"`` callers the
    user is a stub with the org_id in metadata — most existing routes
    only read ``user.user_metadata["org_id"]`` and don't differentiate.
    """
    user = SimpleNamespace(
        id=str(ctx.user_id) if ctx.user_id is not None else f"product:{ctx.api_token_id}",
        email=None,
        user_metadata={"org_id": str(ctx.org_id)},
    )
    return user, ctx.raw_token, str(ctx.org_id)


# ─── Opt-in unified dep for selective route migration ────────────────
#
# Routes can opt INTO the unified resolver by depending on
# `get_current_user_org_unified` instead of `get_current_user_org`.
# This accepts the legacy Supabase JWT AND `pk_*` ApiToken bearers AND
# cookie sessions, projecting to the same `(user, token, org_id)` tuple
# the original returns. The youtube-drive-folder-fanout endpoints use
# this so automation/n8n/agent live-tests can hit them with an ApiToken;
# unrelated routes stay on the legacy JWT-only dep until their own
# per-route migration projects fire (avoids broad regression risk on
# test fixtures that mock only the legacy bridge).
async def get_current_user_org_unified(
    ctx: AuthContext = Depends(get_auth_context),
):
    return auth_context_to_legacy_tuple(ctx)


__all__ = [
    "AuthContext",
    "auth_context_to_legacy_tuple",
    "auth_router_deps",
    "coerce_org_uuid",
    "first_or_none",
    "get_admin_client",
    "get_auth_context",
    "get_core_client",
    "get_current_user",
    "get_current_user_org",
    "get_current_user_org_unified",
    "get_org_id",
    "get_settings",
    "get_user_client",
    "get_user_role",
    "resolve_sso_role",
]
