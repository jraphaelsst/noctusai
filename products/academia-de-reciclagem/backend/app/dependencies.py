"""
Dependencies for Academia de Reciclagem.

This file is the canonical reference every new product inherits via
``scaffold_product``. The auth dep ``get_current_user_org`` is wired
through :func:`noctusai_lib.api.auth.make_get_current_user_org` (factory
pattern) — using the seed's plain ``get_org_id`` / ``get_user_role``
through ``Depends(...)`` does NOT chain through FastAPI because their
positional ``user`` / ``token`` args become required query parameters.

See ``KB § PATTERNS/backend.md § Auth — canonical pattern`` for the
full why and the deprecation warning that fires on the broken shape.

SEED-1 (``project-history/roadmaps/julia-agents-academia-2026-09.md``,
contract §B.0) replaces the JWT-only auth surface with the unified
``AuthContext`` composition: ``get_auth_context`` resolves a cookie
session, a ``pk_*`` product token (the REAL ``SupabaseApiTokenResolver``
— never the Fake), or a legacy JWT bearer (the bridge below, so
``get_current_user_org`` callers are unaffected). Mirrors
``products/social-wiring/backend/app/dependencies.py`` — see that
module's docstring for the lazy-proxy / race-avoidance rationale this
one repeats verbatim.
"""
from __future__ import annotations

import logging
import uuid as _uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from uuid import UUID

from noctusai_seed import (
    create_database_module,
    create_dependencies,
    select_get_current_user,
)
from noctusai_lib.api.auth import (
    first_or_none,  # noqa: F401 — re-exported for product imports
    make_get_current_user,
    make_get_current_user_org,
    resolve_sso_role,  # noqa: F401 — re-exported for product imports
)
from noctusai_lib.api.auth.session import (
    AuthContext,
    SupabaseApiTokenResolver,
    make_api_token_audit_writer,
    make_get_auth_context,
    require_scopes,
)
from noctusai_lib.security.app_config import (
    AppConfigStore,
    CachedAppConfigStore,
    FakeAppConfigStore,
    build_app_config_store,
)
from noctusai_lib.security.key_ring import resolve_key_ring
from noctusai_seed.auth_router import get_session_store as _seed_get_session_store
from cryptography.fernet import Fernet

from app.auth.roles import ADMIN, READ, WRITE
from app.config import settings
from app.interessados import InteressadosStore, build_interessados_store
from app.knowledge import KnowledgeStore, get_knowledge_store

logger = logging.getLogger(__name__)

_db = create_database_module(settings, schema="academia_de_reciclagem")
_deps = create_dependencies(_db)

# Canonical auth deps — wire via the factory so FastAPI sees only
# ``authorization: Header(None)`` in the dep signature.
#
# Late-binding lambdas: tests patch ``_db.get_client`` AFTER this module
# imports. Capturing the bound method at module load would freeze the
# pre-patch reference. The lambda re-resolves on every request so both
# production and test paths see the right client.
# Prod path (Supabase JWT validation). `select_get_current_user`
# transparently swaps in the already-shipped dev-auth dependency when
# `DATABASE_BACKEND=sqlite` AND the dev-auth double-gate is on — zero
# per-product code, parallel-never-modify (the prod path is returned
# untouched in every non-sqlite env). Inherited by every product
# through scaffold_product / propagation.
_prod_get_current_user = make_get_current_user(lambda: _db.get_client())
get_current_user = select_get_current_user(settings, _prod_get_current_user)
# `get_admin_client_fn=lambda: _db.get_core_client()` — NOT get_admin_client().
# `noctus_users` lives in the `public` schema; `get_admin_client()` is scoped
# to THIS product's schema and would 500 with PGRST205 (see
# `seed-trusted-org-resolution`, 2026-07-14 — the make_get_current_user_org
# docstring in noctusai_lib.api.auth has the full rationale + the prod
# incident this mirrors on the ERP side).
get_current_user_org = make_get_current_user_org(
    get_current_user,
    lambda u: (u.user_metadata or {}).get("org_id"),  # fallback only — trusted DB wins
    get_admin_client_fn=lambda: _db.get_core_client(),
    required=True,
)

# Plain-call helpers (NOT to be wired via ``Depends(...)``) — kept for
# imperative call-sites and for backward compatibility.
get_user_role = _deps.get_user_role
get_org_id = _deps.get_org_id


# Late-binding wrappers so test patches on ``_db.get_*`` reach call sites.
def get_user_client(token: str):
    return _db.get_client(token)


def get_admin_client():
    return _db.get_admin_client()


def get_core_client():
    """``public``-schema-scoped client — ``noctus_users`` lives there,
    NOT this product's own schema (see the module docstring above)."""
    return _db.get_core_client()


auth_router_deps = SimpleNamespace(
    get_admin_client=get_admin_client,
    get_core_client=get_core_client,
)


def coerce_org_uuid(raw_org: Any) -> UUID:
    """Coerce the auth-side org_id into a UUID.

    Auth-side ``org_id`` is sometimes a real UUID string, sometimes an
    opaque test fixture (``"test-org-123"``). DB columns are UUID-typed,
    so coerce at the boundary. Non-UUID inputs map to a deterministic
    ``uuid5(NAMESPACE_OID, raw)`` so the same fixture always lands on
    the same row. The user-scoped Supabase client is RLS-bound by the
    JWT, not by this UUID — safe to derive deterministically.

    Lifted to the seed at the N=3 recurrence trigger (youtube-crawler's
    upload + settings + videos routers each had a private copy before
    being lifted to a single helper). Now every new product inherits it.
    """
    try:
        return UUID(str(raw_org))
    except (ValueError, TypeError):
        return _uuid.uuid5(_uuid.NAMESPACE_OID, str(raw_org))


# ─── SEED-1 unified auth-context composition (contract §B.0) ────────────
#
# Real ``ApiTokenResolver`` + a legacy-JWT bridge so the pre-existing
# ``get_current_user_org`` callers (and the ``AuthClient`` test fixture,
# which sends a bearer JWT) keep working unchanged through the SAME
# resolver. Lazy proxies avoid resolving the Real adapter's
# ``get_admin_client()`` at MODULE-IMPORT time — the test conftest only
# patches ``_db.get_admin_client`` AFTER ``app.main`` starts importing
# (mirrors ``products/social-wiring/backend/app/dependencies.py``).


def _get_session_store():
    """Delegates to the SAME process-local singleton the seed's
    ``create_auth_router`` composition uses (keyed by ``id(settings)``)
    — see social-wiring's ``dependencies.py`` for why sharing matters
    for the in-memory Fake (a second instance is a separate empty dict)."""
    return _seed_get_session_store(settings)


_api_token_resolver: SupabaseApiTokenResolver | None = None


def _get_api_token_resolver() -> SupabaseApiTokenResolver:
    global _api_token_resolver
    if _api_token_resolver is None:
        _api_token_resolver = SupabaseApiTokenResolver(
            get_admin_client(), schema="academia_de_reciclagem"
        )
    return _api_token_resolver


async def _legacy_jwt_resolver(token: str) -> AuthContext | None:
    """Bridge a raw Supabase JWT to an ``AuthContext`` (``caller_kind="user"``).

    The dep's contract is that this is called ONLY when the bearer is
    NOT ``pk_*`` (i.e. a JWT-shaped legacy token). Synthesizes an
    ``Authorization: Bearer <token>`` header, runs it through the
    existing JWT-verifying ``get_current_user`` machinery, then projects
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
    # ``make_get_current_user`` returns ``(user, token)``.
    user = result[0] if isinstance(result, tuple) else result
    if user is None:
        return None
    raw_org = (getattr(user, "user_metadata", None) or {}).get("org_id")
    if not raw_org:
        return None
    try:
        org_id = coerce_org_uuid(raw_org)
    except Exception:
        logger.warning("legacy_jwt_org_coerce_failed raw=%r", raw_org)
        return None
    try:
        user_id = UUID(str(user.id))
    except (ValueError, TypeError):
        # Local-dev/test fixtures may use opaque ids; derive a stable UUID.
        user_id = _uuid.uuid5(_uuid.NAMESPACE_OID, str(user.id))
    return AuthContext(
        org_id=org_id,
        caller_kind="user",
        user_id=user_id,
        scopes=[],
        raw_token=token,  # JWT — preserves the bearer for legacy callers
        api_token_id=None,
    )


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


_audit_writer = None


def _get_audit_writer():
    """Lazy singleton — same race-avoidance rationale as
    ``_get_api_token_resolver`` (``get_admin_client()`` must not
    resolve before a test conftest's post-import patch lands)."""
    global _audit_writer
    if _audit_writer is None:
        _audit_writer = make_api_token_audit_writer(
            get_admin_client(), schema="academia_de_reciclagem"
        )
    return _audit_writer


class _LazyAuditWriter:
    """`ApiTokenAuditWriter` proxy for `app.main`'s
    `ApiTokenAuditMiddleware` wiring — defers to `_get_audit_writer()`
    on the first `.record()` call."""

    async def record(self, **kwargs):
        return await _get_audit_writer().record(**kwargs)


get_auth_context = make_get_auth_context(
    session_store=_LazySessionStore(),
    api_token_resolver=_LazyApiTokenResolver(),
    legacy_jwt_resolver=_legacy_jwt_resolver,
    session_cookie_name="nai_session",
)


# ─── Scope/role gates — contract §B.0 ────────────────────────────────────
#
# Every GET needs READ; every write below needs its domain's WRITE scope
# (product callers) / the WRITE role set (SSO users); `/api/import`
# (A2, not this slice) needs ADMIN. Bound ONCE at module load — every
# router ``Depends(require_kb_write)`` etc. shares the same dependency
# object, matching the ``get_current_user_org``-factory pattern above.
#
# NOTE (contract gap, flagged in this slice's delivery note): §B.0 lists
# 6 write scopes for 7 write-domains — no ``academia:timeline:write``
# exists. Timeline (`POST /api/timeline`, §B.5) is grouped with content
# under `academia:content:write` here; sources keeps its own scope
# because it accepts an external URL (a materially different risk).
require_read = require_scopes(
    "academia:read",
    user_roles=READ,
    get_auth_context=get_auth_context,
    get_core_client=get_core_client,
)
require_kb_write = require_scopes(
    "academia:kb:write",
    user_roles=WRITE,
    get_auth_context=get_auth_context,
    get_core_client=get_core_client,
)
require_decisions_write = require_scopes(
    "academia:decisions:write",
    user_roles=WRITE,
    get_auth_context=get_auth_context,
    get_core_client=get_core_client,
)
require_questions_write = require_scopes(
    "academia:questions:write",
    user_roles=WRITE,
    get_auth_context=get_auth_context,
    get_core_client=get_core_client,
)
require_roadmap_write = require_scopes(
    "academia:roadmap:write",
    user_roles=WRITE,
    get_auth_context=get_auth_context,
    get_core_client=get_core_client,
)
require_content_write = require_scopes(
    "academia:content:write",
    user_roles=WRITE,
    get_auth_context=get_auth_context,
    get_core_client=get_core_client,
)
require_sources_write = require_scopes(
    "academia:sources:write",
    user_roles=WRITE,
    get_auth_context=get_auth_context,
    get_core_client=get_core_client,
)
require_import_admin = require_scopes(
    "academia:import",
    user_roles=ADMIN,
    get_auth_context=get_auth_context,
    get_core_client=get_core_client,
)
# Interessados admin routes (public-signup contract, "Routes" section) --
# same ADMIN role set as import, distinct scope so a product token minted
# for one purpose is not silently valid for the other.
require_interessados_admin = require_scopes(
    "academia:interessados",
    user_roles=ADMIN,
    get_auth_context=get_auth_context,
    get_core_client=get_core_client,
)


# ─── Knowledge store seam (contract §A.11) ───────────────────────────────


_approval_ring_store: AppConfigStore | None = None


class _AgentsSchemaClient:
    """Late-binding ``.table()`` over the admin client scoped to the ring's
    schema (`agents`) — resolved per call, so a test that swaps
    ``_db.get_admin_client`` is honoured and no client is built at import."""

    def table(self, name: str):
        return _db.get_admin_client().schema(settings.approval_assertion_ring_schema).table(name)


def _get_approval_ring_store() -> AppConfigStore:
    """Process singleton: the `agents`-published ring, behind a 30 s cache.

    Fake (always-empty ⇒ env fallback) when there is no service-role key or
    no valid ``ENCRYPTION_KEY`` — never a boot failure, never plaintext."""
    global _approval_ring_store
    if _approval_ring_store is None:
        inner: AppConfigStore = FakeAppConfigStore()
        key = settings.encryption_key
        if settings.supabase_service_role_key and key:
            try:
                Fernet(key.encode("utf-8"))
            except (ValueError, TypeError):
                logger.error(
                    "approval_ring_store_disabled reason=invalid_encryption_key "
                    "— accepting only APPROVAL_ASSERTION_SECRETS from env"
                )
            else:
                inner = build_app_config_store(
                    client=_AgentsSchemaClient(), fernet_key=key.encode("utf-8")
                )
        _approval_ring_store = CachedAppConfigStore(inner, ttl_seconds=30)
    return _approval_ring_store


class _ApprovalAssertionKeys(list):
    """A `list[str]` that supports `weakref.ref()` — the plain builtin
    `list` does not. `get_approval_assertion_keys` is a FastAPI `Depends()`
    target, and `noctus.dev.check_stand_in_conformance` leg B(i) resolves
    every such dependency against a REAL call and probes the result with
    `weakref.ref()` fleet-wide (the same defensive property that would
    have caught `_SchemaPinnedAdminClient`'s missing `__weakref__` before
    it 500'd every social-wiring route in production — see
    `noctusai_seed.database._SchemaPinnedAdminClient.__slots__`, which adds
    `"__weakref__"` for the identical reason). A `list` subclass gets a
    `__weakref__` slot for free (no `__slots__` declared here) and is
    otherwise indistinguishable from `list` for every consumer — iteration,
    indexing, `in`, `==` against a plain list, etc. — so this changes
    nothing observable, only makes the object weak-referenceable."""


def get_approval_assertion_keys() -> list[str]:
    """FastAPI dependency returning every §D key academia accepts right now.

    The ring `agents` publishes (DB) wins over
    `settings.approval_assertion_secrets_list` (env); staged keys are
    accepted before `agents` starts signing with them, retired keys are not
    (`noctusai_lib.security.key_ring`). An explicit seam — routers
    `Depends(...)` this and pass the result to
    `app.auth.provenance.build_write_provenance(keys=...)` — so a test
    overrides `app.dependency_overrides[get_approval_assertion_keys]`
    instead of `monkeypatch.setattr(settings, "approval_assertion_secrets",
    ...)`, which trips `check_no_self_monkeypatch` (CLAUDE.md §1: no
    monkey-patching our own code, incl. tests).

    Returns `_ApprovalAssertionKeys` (a weak-referenceable `list` subclass)
    rather than a plain `list` — see that class's docstring."""
    return _ApprovalAssertionKeys(
        approval_assertion_keys_from(
            _get_approval_ring_store(), env_value=settings.approval_assertion_secrets
        )
    )


def approval_assertion_keys_from(store: AppConfigStore, *, env_value: str) -> list[str]:
    """Pure resolution step behind :func:`get_approval_assertion_keys`."""
    ring = resolve_key_ring(store, settings.approval_assertion_ring_key, env_value=env_value)
    return ring.accepted(datetime.now(timezone.utc))


def get_store() -> KnowledgeStore:
    """FastAPI dependency returning the configured `KnowledgeStore`.

    A seam on purpose — tests override this (`app.dependency_overrides
    [get_store] = lambda: shared_fake_instance`) with a single shared
    `FakeKnowledgeStore()` instance so state persists across the
    multiple requests one test typically issues. In prod/dev this calls
    the real `get_knowledge_store(settings)` factory (§A.11), which is
    stateless per call for `PgKnowledgeStore` (a thin Postgres wrapper).
    """
    return get_knowledge_store(settings)


def get_interessados_store() -> InteressadosStore:
    """FastAPI dependency returning the configured `InteressadosStore`.

    Same DI-seam shape as `get_store` above (tests override via
    `app.dependency_overrides[get_interessados_store] = lambda: fake`) --
    stateless per call for `PgInteressadosStore` (a thin Postgres
    wrapper).
    """
    return build_interessados_store(settings)


__all__ = [
    "AuthContext",
    "auth_router_deps",
    "coerce_org_uuid",
    "first_or_none",
    "get_admin_client",
    "approval_assertion_keys_from",
    "get_approval_assertion_keys",
    "get_auth_context",
    "get_core_client",
    "get_current_user",
    "get_current_user_org",
    "get_interessados_store",
    "get_org_id",
    "get_store",
    "get_user_client",
    "get_user_role",
    "require_content_write",
    "require_decisions_write",
    "require_import_admin",
    "require_interessados_admin",
    "require_kb_write",
    "require_questions_write",
    "require_read",
    "require_roadmap_write",
    "require_sources_write",
    "resolve_sso_role",
]
