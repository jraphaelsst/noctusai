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
from types import SimpleNamespace
from typing import Any
from uuid import UUID

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
    FakeSessionStore,
    make_get_auth_context,
)
from app.config import settings
from app.sqlite_client import SQLiteClient

_logger = _logging.getLogger(__name__)

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
    get_current_user_org = make_get_current_user_org(
        get_current_user,
        lambda u: (u.user_metadata or {}).get("org_id"),
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

_session_store = None
_api_token_resolver = None
_get_auth_context = None


def _get_session_store():
    """Lazy singleton — ``FakeSessionStore`` under sqlite/dev, the
    seed's Redis-backed adapter under production. Real Redis adapter
    is owned by a follow-up wave; until then ``FakeSessionStore``
    is the runtime store. The cookie path doesn't have a production
    Real adapter yet — login flow + session-store-Redis-real land
    together (this file already wires the cookie dep to a real
    interface so the swap is purely an adapter change)."""
    global _session_store
    if _session_store is None:
        # TODO: swap to RedisSessionStore once the seed real adapter
        # lands. Tracked in platform-auth-modernization wave 3.
        _session_store = FakeSessionStore()
    return _session_store


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


__all__ = [
    "AuthContext",
    "auth_context_to_legacy_tuple",
    "coerce_org_uuid",
    "first_or_none",
    "get_admin_client",
    "get_auth_context",
    "get_current_user",
    "get_current_user_org",
    "get_org_id",
    "get_user_client",
    "get_user_role",
    "resolve_sso_role",
]
