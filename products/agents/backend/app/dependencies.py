"""
Dependencies for Agentes.

Contract §E intro / §B.0 (``projects/julia-agents-academia-CONTRACT.md``):
every route in this product is **user-only**. This module replaces the
scaffold's JWT-only ``get_current_user_org`` with the unified auth
composition social-wiring uses (``make_get_auth_context`` +
``SupabaseApiTokenResolver`` + a legacy-JWT bridge), then layers
``require_scopes(..., restrict="user_only")`` role gates on top so a
``pk_*`` product-token caller gets a clean 403 ``user_required`` instead of
an ambiguous 401 (the whole point of shipping ``migrations/007_api_tokens.sql``
even though no route ever grants a product caller access).

See ``products/social-wiring/backend/app/dependencies.py`` for the sibling
composition this mirrors (docstring there has the full "why a factory, why
a lazy proxy" rationale — not repeated here).
"""
from __future__ import annotations

import uuid as _uuid
from types import SimpleNamespace
from typing import Any
from uuid import UUID

from noctusai_seed import (
    create_database_module,
    create_dependencies,
    make_get_settings,
    select_get_current_user,
)
from noctusai_seed.auth_router import get_session_store as _seed_get_session_store
from noctusai_lib.api.auth import (
    first_or_none,  # noqa: F401 — re-exported for product imports
    make_get_current_user,
    make_get_current_user_org,
    resolve_sso_role,  # noqa: F401 — re-exported for product imports
)
from noctusai_lib.api.auth.platform import require_platform_admin as _require_platform_admin
from noctusai_lib.api.auth.session import (
    AuthContext,
    FakeApiTokenResolver,
    SupabaseApiTokenResolver,
    make_get_auth_context,
    require_scopes,
)
from app.config import settings

_db = create_database_module(settings, schema="agents")
_deps = create_dependencies(_db)

# Class-A DI seam — routers `Depends(get_settings)` read `cfg.X`; tests
# override via `app.dependency_overrides[get_settings]`. Consumes the seed
# factory (the N>=3 settings-DI formalization) rather than a product-local
# def. Per `KB § PATTERNS/di-test-seam.md` Class-A.
get_settings = make_get_settings(settings)

# ── Legacy auth deps (kept — some standard/seed routers still expect them) ──
_prod_get_current_user = make_get_current_user(lambda: _db.get_client())
get_current_user = select_get_current_user(settings, _prod_get_current_user)
get_current_user_org = make_get_current_user_org(
    get_current_user,
    lambda u: (u.user_metadata or {}).get("org_id"),  # fallback only — trusted DB wins
    get_admin_client_fn=lambda: _db.get_core_client(),
    required=True,
)

get_user_role = _deps.get_user_role
get_org_id = _deps.get_org_id


def get_user_client(token: str):
    return _db.get_client(token)


def get_admin_client():
    return _db.get_admin_client()


def get_core_client():
    """``public``-schema-scoped client — ``noctus_users`` lives there, NOT
    the ``agents`` schema (a ``get_admin_client()`` lookup would 500 with
    PGRST205; see ``seed-trusted-org-resolution``, 2026-07-14)."""
    return _db.get_core_client()


# Adapter exposing exactly the `get_admin_client()` / `get_core_client()`
# surface `noctusai_seed.auth_router.create_auth_router(deps, settings)`
# needs — mirrors social-wiring's `auth_router_deps`.
auth_router_deps = SimpleNamespace(
    get_admin_client=get_admin_client,
    get_core_client=get_core_client,
)


def coerce_org_uuid(raw_org: Any) -> UUID:
    """Coerce the auth-side org_id into a UUID (see module docstring's
    sibling for the full rationale)."""
    try:
        return UUID(str(raw_org))
    except (ValueError, TypeError):
        return _uuid.uuid5(_uuid.NAMESPACE_OID, str(raw_org))


# ── Unified auth-context dep (contract §B.0) ────────────────────────────────

_api_token_resolver: SupabaseApiTokenResolver | FakeApiTokenResolver | None = None


def _get_session_store():
    """Delegates to the SAME process-local singleton
    ``create_auth_router`` (mounted directly in ``app/main.py``) uses —
    a second, independently-constructed ``FakeSessionStore()`` would be an
    empty dict invisible to the other, so a session minted through one
    composition would be unreadable through the other. See social-wiring's
    sibling docstring for the full incident this closes."""
    return _seed_get_session_store(settings)


def _get_api_token_resolver():
    """Lazy singleton — Supabase-backed (``schema="agents"``, SEED-1)."""
    global _api_token_resolver
    if _api_token_resolver is None:
        if not settings.supabase_service_role_key:
            _api_token_resolver = FakeApiTokenResolver()
        else:
            _api_token_resolver = SupabaseApiTokenResolver(
                get_admin_client(), schema="agents"
            )
    return _api_token_resolver


async def _legacy_jwt_resolver(token: str) -> AuthContext | None:
    """Bridge a raw Supabase JWT to an ``AuthContext`` (``caller_kind="user"``).

    Mirrors social-wiring's bridge exactly — see that module's docstring.
    """
    try:
        result = await get_current_user(authorization=f"Bearer {token}")
    except Exception:
        return None
    if result is None:
        return None
    user = result[0] if isinstance(result, tuple) else result
    if user is None:
        return None
    raw_org = (getattr(user, "user_metadata", None) or {}).get("org_id")
    if not raw_org:
        return None
    try:
        org_id = coerce_org_uuid(raw_org)
    except Exception:
        return None
    try:
        user_id = UUID(str(user.id))
    except (ValueError, TypeError):
        user_id = _uuid.uuid5(_uuid.NAMESPACE_OID, str(user.id))
    return AuthContext(
        org_id=org_id,
        caller_kind="user",
        user_id=user_id,
        scopes=[],
        raw_token=token,
        api_token_id=None,
    )


class _LazyApiTokenResolver:
    """Defers to ``_get_api_token_resolver()`` on first resolve call — the
    Real adapter needs ``get_admin_client()``, which needs a live Supabase
    URL not available during test collection."""

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


# ── Role gates (contract §E "Roles") ────────────────────────────────────────
#
# Every `agents` route is user-only (`restrict="user_only"` — a product
# caller 403s `user_required` before any role check runs, contract §E
# intro). Two role sets used across §E.2:
#   ADMIN  = {owner, admin}             — persona writes, agent toggles.
#   MEMBER = {owner, admin, member, viewer} — any org member: chat, read
#            their own conversations. Approval decisions additionally
#            require "requester or admin", which is NOT expressible as a
#            static role set — routers check that in the handler body.
ADMIN_ROLES = frozenset({"owner", "admin"})
MEMBER_ROLES = frozenset({"owner", "admin", "member", "viewer"})

require_admin = require_scopes(
    user_roles=ADMIN_ROLES,
    get_auth_context=get_auth_context,
    get_core_client=get_core_client,
    restrict="user_only",
)

require_member = require_scopes(
    user_roles=MEMBER_ROLES,
    get_auth_context=get_auth_context,
    get_core_client=get_core_client,
    restrict="user_only",
)


# Credenciais e integrações + Configurações do agente (2026-09-16): the
# NoctusAI OPERATOR only — `noctus_users.role == 'admin'`, never an org
# owner/admin (seed `noctusai_lib.api.auth.platform`). These pages hold the
# control plane's cross-product secrets. A missing credential still 401s
# from `get_auth_context`; a product token has no user and gets 403.
require_platform_admin = _require_platform_admin(
    get_auth_context=get_auth_context,
    get_core_client=get_core_client,
)


def get_credential_service_dep():
    """DI seam over ``app.credentials.build_credential_service`` — tests
    override it with a service over Fake store/admin/prober."""
    from app.credentials import build_credential_service

    return build_credential_service(settings)


def get_runtime_settings_service_dep():
    from app.services.runtime_settings import get_runtime_settings_service

    return get_runtime_settings_service(settings)


# ── Runtime seam (contract §E.9) ────────────────────────────────────────────
#
# `app/runtime/` is G2's slice (`get_agent_runtime` / `get_approval_broker`
# / `build_julia_spec`). These three dependency functions still do the
# `from app.runtime import ...` LAZILY, inside the function body — not
# because the package might be absent any more (G2 shipped it), but
# because `get_agent_runtime`'s real branch conditionally pulls in
# `claude_agent_sdk`, and deferring the import keeps that cost out of
# every request that never needs it. Tests override
# `app.dependency_overrides[get_agent_runtime_dep | get_approval_broker_dep
# | get_build_julia_spec_dep]` with G2's `FakeAgentRuntime` /
# `StoreApprovalBroker` (over the shared test stores) / `build_julia_spec`
# — a dependency seam, never monkeypatching.
def get_agent_runtime_dep():
    from app.runtime import get_agent_runtime

    return get_agent_runtime(settings)


def get_approval_broker_dep():
    from app.runtime import get_approval_broker

    return get_approval_broker(settings)


def get_agent_store_dep():
    """FastAPI dependency seam over ``app.stores.agents.get_agent_store``
    — routers depend on THIS (never call the factory inline), so tests
    override ``app.dependency_overrides[get_agent_store_dep]`` with a
    single shared ``FakeAgentStore()`` instance instead of monkeypatching
    ``settings.supabase_service_role_key`` to force the Real-store path
    just to get statefulness across two requests in one test."""
    from app.stores.agents import get_agent_store

    return get_agent_store(settings)


def get_conversation_store_dep():
    from app.stores.conversations import get_conversation_store

    return get_conversation_store(settings)


def get_message_store_dep():
    from app.stores.messages import get_message_store

    return get_message_store(settings)


def get_persona_store_dep():
    from app.stores.personas import get_persona_store

    return get_persona_store(settings)


def get_approval_store_dep():
    from app.stores.approvals import get_approval_store

    return get_approval_store(settings)


def get_social_wiring_client_dep():
    from app.clients.social_wiring import get_social_wiring_client

    return get_social_wiring_client(settings)


def get_realtime_bus_dep():
    """FastAPI dependency seam over ``app.realtime.get_bus()`` — the
    process-wide singleton is a Redis-or-Fake factory keyed on
    ``settings.redis_url``; tests override THIS dependency with a bare
    ``FakeRealtimeBus()`` so a publish never attempts a real (and, in some
    environments, measurably slow-to-fail) network connection."""
    from app.realtime import get_bus

    return get_bus()


def get_build_julia_spec_dep():
    """Returns G2's ``build_julia_spec(persona_row) -> AgentSpec`` callable
    itself (not its result) — the turn loop calls it once it has the
    active persona row. Same lazy-import-inside-the-function-body
    discipline as the two deps above; overridden in tests with a stand-in
    spec-builder so the turn loop never needs a real ``AgentSpec``."""
    from app.runtime import build_julia_spec
    from app.services.runtime_settings import get_runtime_settings_service

    runtime_settings = get_runtime_settings_service(settings)

    def _build(persona_row):
        # `max_turns` resolved per turn: the admin override
        # (Configurações do agente) applies without a restart.
        return build_julia_spec(persona_row, max_turns=runtime_settings.max_turns())

    return _build


__all__ = [
    "ADMIN_ROLES",
    "MEMBER_ROLES",
    "AuthContext",
    "auth_router_deps",
    "coerce_org_uuid",
    "first_or_none",
    "get_admin_client",
    "get_agent_runtime_dep",
    "get_agent_store_dep",
    "get_approval_broker_dep",
    "get_approval_store_dep",
    "get_auth_context",
    "get_build_julia_spec_dep",
    "get_conversation_store_dep",
    "get_credential_service_dep",
    "get_core_client",
    "get_current_user",
    "get_current_user_org",
    "get_message_store_dep",
    "get_org_id",
    "get_persona_store_dep",
    "get_realtime_bus_dep",
    "get_runtime_settings_service_dep",
    "get_settings",
    "get_social_wiring_client_dep",
    "get_user_client",
    "get_user_role",
    "require_admin",
    "require_member",
    "require_platform_admin",
    "resolve_sso_role",
]
