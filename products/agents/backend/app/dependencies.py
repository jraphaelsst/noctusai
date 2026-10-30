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

from fastapi import Depends, HTTPException, Request, Response
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
    make_trusted_legacy_jwt_resolver,
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
    lambda u: None,  # retired positional slot — never consulted (trusted DB only)
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


_legacy_jwt_resolver = make_trusted_legacy_jwt_resolver(
    lambda authorization: get_current_user(authorization=authorization),
    lambda: _db.get_core_client(),
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


# ── Agent Packages scoped gates (agent-packages CONTRACT §A8, §I) ───────────
#
# The ONLY routes a `pk_*` product token may reach. `restrict="any"` branches
# per caller kind (seed `require_scopes`): a product token must carry the
# listed scope (else 403 `scope_missing`), a human user needs the role set.
# Every OTHER route keeps `restrict="user_only"` above → 403 `user_required`.
SCOPE_PACKAGES_READ = "packages:read"
SCOPE_PROJECT_KNOWLEDGE_WRITE = "project-knowledge:write"
SCOPE_LEARNINGS_WRITE = "learnings:write"
SCOPE_LEARNINGS_READ = "learnings:read"
#: 2026-10-03 — the noc pre-push publish leg ONLY (never minted for consumer
#: repos). Accepted on import / eval-run start+read / draft publish, and only
#: for a `dev-advisor` agent (the handler enforces the kind; runtime agents
#: stay `user_required`). A token can never use the publish override.
SCOPE_STUDIO_PUBLISH = "studio:publish"
#: The scopes an admin may put on a minted token (`POST /api/settings/api-tokens`
#: accepts any string; this is the documented, product-honoured set).
PACKAGE_TOKEN_SCOPES = frozenset({
    SCOPE_PACKAGES_READ, SCOPE_PROJECT_KNOWLEDGE_WRITE, SCOPE_LEARNINGS_WRITE, SCOPE_LEARNINGS_READ,
    SCOPE_STUDIO_PUBLISH,
})

# ── Channel turn API scopes (Lais A2, contract §3 / §4 / §10.1 M1 + L1) ────
#
# The product-to-product surface a CHANNEL TRANSPORT (social-wiring) drives with
# a minted `pk_*` token. Split scopes (L1): turns vs. link-health status. Both
# are minted together onto the channel token (§4) — status is what SW calls to
# validate a pasted token — but a route only ever demands its own.
SCOPE_CHANNEL_TURN = "agents:channel-turn"
SCOPE_CHANNEL_STATUS = "agents:channel-status"
CHANNEL_TOKEN_SCOPES = frozenset({SCOPE_CHANNEL_TURN, SCOPE_CHANNEL_STATUS})
#: Who may hold a channel token. Read off the STORED token row (`api_tokens.
#: issuer`, set only server-side at mint) — a token minted for any other
#: transport answers 403 `issuer_not_allowed` even with the scope.
CHANNEL_ALLOWED_ISSUERS = frozenset({"social-wiring"})
#: The server-side registry of scopes an admin-initiated mint may put on a
#: token (the union of every documented, product-honoured set).
MINTABLE_TOKEN_SCOPES = PACKAGE_TOKEN_SCOPES | CHANNEL_TOKEN_SCOPES


def _require_channel(scope: str):
    """Product-token-only gate for one channel scope + the issuer allowlist.
    `restrict="product_only"`: a human session answers 403 `product_required`;
    a wrong/absent scope 403 `scope_missing`; a bad/expired token 401 comes from
    `get_auth_context` itself."""
    base = require_scopes(
        scope,
        get_auth_context=get_auth_context,
        restrict="product_only",
    )

    def _dep(ctx: AuthContext = Depends(base)) -> AuthContext:
        if ctx.issuer not in CHANNEL_ALLOWED_ISSUERS:
            raise HTTPException(
                status_code=403,
                detail={"detail": "Token issuer not allowed for this API", "code": "issuer_not_allowed"},
            )
        return ctx

    return _dep


require_channel_turn = _require_channel(SCOPE_CHANNEL_TURN)
require_channel_status = _require_channel(SCOPE_CHANNEL_STATUS)

require_packages_read = require_scopes(
    SCOPE_PACKAGES_READ,
    user_roles=MEMBER_ROLES,
    get_auth_context=get_auth_context,
    get_core_client=get_core_client,
    restrict="any",
)

require_project_knowledge_write = require_scopes(
    SCOPE_PROJECT_KNOWLEDGE_WRITE,
    user_roles=ADMIN_ROLES,
    get_auth_context=get_auth_context,
    get_core_client=get_core_client,
    restrict="any",
)

require_learnings_write = require_scopes(
    SCOPE_LEARNINGS_WRITE,
    user_roles=ADMIN_ROLES,
    get_auth_context=get_auth_context,
    get_core_client=get_core_client,
    restrict="any",
)

require_learnings_read = require_scopes(
    SCOPE_LEARNINGS_READ,
    user_roles=MEMBER_ROLES,
    get_auth_context=get_auth_context,
    get_core_client=get_core_client,
    restrict="any",
)

require_publish_write = require_scopes(
    SCOPE_STUDIO_PUBLISH,
    user_roles=ADMIN_ROLES,
    get_auth_context=get_auth_context,
    get_core_client=get_core_client,
    restrict="any",
)

require_publish_read = require_scopes(
    SCOPE_STUDIO_PUBLISH,
    user_roles=MEMBER_ROLES,
    get_auth_context=get_auth_context,
    get_core_client=get_core_client,
    restrict="any",
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


#: The product-token scope of the ``noctus.agents.content`` MCP path (Julia v2 CONTRACT 2.5) and
#: the ONLY issuer a content-write token may carry. The token is minted server-side by
#: ``POST /api/studio/plataforma/content-token`` (platform admin); the generic
#: ``POST /api/settings/api-tokens`` never sets an issuer, so a token an org admin minted with this
#: scope still answers 403 ``issuer_not_allowed``.
SCOPE_STUDIO_CONTENT_WRITE = "studio:content-write"
#: The extra scope that lets the SAME platform-issued token DELETE an agent (``DELETE /api/studio/agents/{key}``).
#: Opt-in at mint time (``permitir_exclusao``): a content token never carries it by default.
SCOPE_STUDIO_AGENT_DELETE = "studio:agent-delete"
CONTENT_TOKEN_ISSUER = "noctus-platform"


def _content_token_gate(ctx: AuthContext, scope: str = SCOPE_STUDIO_CONTENT_WRITE) -> AuthContext:
    """A product caller must carry ``scope`` (default ``studio:content-write``) AND the platform issuer."""
    if scope not in ctx.scopes:
        raise HTTPException(
            status_code=403,
            detail={"detail": f"Missing scope(s): {scope}", "code": "scope_missing"},
        )
    if ctx.issuer != CONTENT_TOKEN_ISSUER:
        raise HTTPException(
            status_code=403,
            detail={"detail": "Token issuer not allowed for this API", "code": "issuer_not_allowed"},
        )
    return ctx


async def require_platform_content_admin(
    ctx: AuthContext = Depends(get_auth_context), request: Request = None, response: Response = None,
) -> AuthContext:
    """Platform-only definition content (the skill library, the qualification standard): a NoctusAI
    platform admin (``noctus_users.role == 'admin'``, 403 ``platform_admin_required`` for anyone
    else, 401 unauthenticated, the admin-MFA gate included) OR the platform-issued
    ``studio:content-write`` product token (the ``noctus.agents.content`` MCP path)."""
    if ctx.caller_kind == "product":
        return _content_token_gate(ctx)
    return await require_platform_admin(ctx=ctx, request=request, response=response)


async def require_agent_delete(
    ctx: AuthContext = Depends(get_auth_context), request: Request = None, response: Response = None,
) -> AuthContext:
    """Deleting an agent: a NoctusAI platform admin (``noctus_users.role == 'admin'``; 403
    ``platform_admin_required`` otherwise, 401 unauthenticated, the admin-MFA gate included) OR the
    platform-issued product token that carries ``studio:agent-delete`` (minted with ``permitir_exclusao``).
    A plain ``studio:content-write`` token is refused (403 ``scope_missing``)."""
    if ctx.caller_kind == "product":
        return _content_token_gate(ctx, SCOPE_STUDIO_AGENT_DELETE)
    return await require_platform_admin(ctx=ctx, request=request, response=response)


_admin_or_content_base = require_scopes(
    SCOPE_STUDIO_CONTENT_WRITE,
    user_roles=ADMIN_ROLES,
    get_auth_context=get_auth_context,
    get_core_client=get_core_client,
    restrict="any",
)


async def require_admin_or_content_token(ctx: AuthContext = Depends(_admin_or_content_base)) -> AuthContext:
    """An org owner/admin (their own agents) OR the platform-issued ``studio:content-write`` token
    (a platform definition's sections, written by the MCP tool)."""
    if ctx.caller_kind == "product" and ctx.issuer != CONTENT_TOKEN_ISSUER:
        raise HTTPException(
            status_code=403,
            detail={"detail": "Token issuer not allowed for this API", "code": "issuer_not_allowed"},
        )
    return ctx


def get_skills_store_dep():
    """DI seam over ``get_skills_store`` (the shared skill library): the skills router, the AI draft generation and
    the agent page's completeness signal all read through it, so ONE override reaches every consumer."""
    from app.stores.skills_biblioteca import get_skills_store

    return get_skills_store(settings)


def get_geracao_store_dep():
    """DI seam over ``get_geracao_store`` (the AI draft generation runs)."""
    from app.stores.studio_geracoes import get_geracao_store

    return get_geracao_store(settings)


def get_geracao_chat_dep():
    """DI seam over the generator's LLM call: the seed's ``chat_completion_with_usage`` (tests inject a wrapper over
    the seed ``FakeProvider``)."""
    from noctusai_lib.integrations.llm import chat_completion_with_usage

    return chat_completion_with_usage


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
# / `build_legacy_chat_spec`). These three dependency functions still do the
# `from app.runtime import ...` LAZILY, inside the function body — not
# because the package might be absent any more (G2 shipped it), but
# because `get_agent_runtime`'s real branch conditionally pulls in
# `claude_agent_sdk`, and deferring the import keeps that cost out of
# every request that never needs it. Tests override
# `app.dependency_overrides[get_agent_runtime_dep | get_approval_broker_dep
# | get_build_legacy_chat_spec_dep]` with G2's `FakeAgentRuntime` /
# `StoreApprovalBroker` (over the shared test stores) / `build_legacy_chat_spec`
# — a dependency seam, never monkeypatching.
def get_agent_runtime_dep():
    from app.runtime import get_agent_runtime

    return get_agent_runtime(settings, None, None)


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


def get_llm_runtime_dep(msg_store=Depends(get_message_store_dep)):
    """The provider-neutral runtime (``agents.runtime='llm'``, Lais A1) —
    memory over the SAME message store the route persists to, so a test that
    overrides ``get_message_store_dep`` (or this dep, with a ``FakeProvider``-
    driven ``LlmToolRuntime``) reaches it. Cheap: no network at construction.

    The studio TEST chat of an ``llm`` agent carries no channel tools: they need a lead, a thread and
    the server-built turn state a channel turn brings (``TurnContext.julia``)."""
    from app.channels.tool_registry import make_channel_tools_factory
    from app.runtime import get_llm_runtime

    return get_llm_runtime(settings, messages=msg_store, tools_factory=make_channel_tools_factory())


def get_channel_llm_runtime_dep(msg_store=Depends(get_message_store_dep)):
    """The runtime a CHANNEL turn runs on: the same provider-neutral runtime,
    with the per-org daily cap ON by default (`channel_daily_budget_usd`, §10.1
    M4) and the Julia v2 toolset (``app.channels.tool_registry``). Tests
    override THIS dep with a ``FakeProvider``-driven runtime."""
    from app.channels.tool_registry import make_channel_tools_factory
    from app.runtime import get_llm_runtime

    return get_llm_runtime(
        settings,
        messages=msg_store,
        tools_factory=make_channel_tools_factory(),
        daily_cap_usd=float(settings.channel_daily_budget_usd),
    )


def get_thread_store_dep():
    """The shared lead-thread store (participants, hand-offs, lead refs). Lives here -- not in a router -- so the
    conversations router and the channel-threads router share ONE seam object (a test overrides it once)."""
    from app.stores.threads import get_thread_store

    return get_thread_store(settings)


def get_notification_sink_dep():
    """The in-app notification sink (core's ``public.notifications``). A seam, so a test overrides it with the
    Fake -- never patches it."""
    from app.notifications import get_notification_sink

    return get_notification_sink()


def get_conformidade_store_dep():
    """Conformance rules/violations, leak fingerprints and the per-agent abuse limits (migration 037)."""
    from app.stores.conformidade import get_conformidade_store

    return get_conformidade_store(settings)


def get_julia_tools_client_dep():
    """The SW client the channel tools read the CRM through (the org's own tools token, per call)."""
    from app.clients.social_wiring import get_julia_tools_client

    return get_julia_tools_client(settings)


def get_skills_factory_dep():
    """``(definitions, definition_org, definition_agent, version) -> SkillFonte``; ``None`` = the version's
    own skills. With pins in the shared skill library (A-SKILLS, migration 039) the turn opens the PINNED
    library versions first (never the latest), falling back to the version's own skills."""
    from app.stores.skills_biblioteca import get_skills_store
    from app.studio.skills_fonte import skills_factory

    return skills_factory(lambda: get_skills_store(settings))


def get_channel_inbound_store_dep():
    from app.stores.channel_inbound import get_channel_inbound_store

    return get_channel_inbound_store(settings)


def get_channel_retention_dep():
    from app.channels.retention import get_channel_retention

    return get_channel_retention(settings)


def get_org_llm_key_resolver_dep():
    """``(provider, org_id) -> key | None`` — THIS org's key only (B1)."""
    from app.credentials.org_keys import make_org_llm_key_resolver

    return make_org_llm_key_resolver()


def get_product_token_admin_dep():
    """Service-side ``api_tokens`` writer (the seed's ``ProductTokenAdmin``)."""
    from noctusai_lib.api.auth.session import make_product_token_admin

    return make_product_token_admin(get_admin_client() if settings.supabase_service_role_key else None)


def get_token_audit_dep():
    from app.channels.token_audit import get_token_audit

    return get_token_audit(settings)


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


def get_build_legacy_chat_spec_dep():
    """Returns G2's ``build_legacy_chat_spec(persona_row) -> AgentSpec`` callable
    itself (not its result) — the turn loop calls it once it has the
    active persona row. Same lazy-import-inside-the-function-body
    discipline as the two deps above; overridden in tests with a stand-in
    spec-builder so the turn loop never needs a real ``AgentSpec``."""
    from app.runtime import build_legacy_chat_spec
    from app.services.runtime_settings import get_runtime_settings_service

    runtime_settings = get_runtime_settings_service(settings)

    def _build(persona_row):
        # `max_turns` resolved per turn: the admin override
        # (Configurações do agente) applies without a restart.
        return build_legacy_chat_spec(persona_row, max_turns=runtime_settings.max_turns())

    return _build


__all__ = [
    "CHANNEL_ALLOWED_ISSUERS",
    "CHANNEL_TOKEN_SCOPES",
    "MINTABLE_TOKEN_SCOPES",
    "SCOPE_CHANNEL_STATUS",
    "SCOPE_CHANNEL_TURN",
    "get_channel_inbound_store_dep",
    "get_channel_llm_runtime_dep",
    "get_channel_retention_dep",
    "get_conformidade_store_dep",
    "get_julia_tools_client_dep",
    "get_skills_factory_dep",
    "get_org_llm_key_resolver_dep",
    "get_product_token_admin_dep",
    "get_token_audit_dep",
    "require_channel_status",
    "require_channel_turn",
    "PACKAGE_TOKEN_SCOPES",
    "SCOPE_LEARNINGS_READ",
    "SCOPE_LEARNINGS_WRITE",
    "SCOPE_PACKAGES_READ",
    "SCOPE_PROJECT_KNOWLEDGE_WRITE",
    "require_learnings_read",
    "require_learnings_write",
    "require_packages_read",
    "require_project_knowledge_write",
    "ADMIN_ROLES",
    "MEMBER_ROLES",
    "AuthContext",
    "auth_router_deps",
    "coerce_org_uuid",
    "first_or_none",
    "get_admin_client",
    "get_agent_runtime_dep",
    "get_agent_store_dep",
    "get_skills_store_dep",
    "get_geracao_store_dep",
    "get_geracao_chat_dep",
    "get_llm_runtime_dep",
    "get_approval_broker_dep",
    "get_approval_store_dep",
    "get_auth_context",
    "get_build_legacy_chat_spec_dep",
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
    "require_publish_read",
    "require_publish_write",
    "SCOPE_STUDIO_PUBLISH",
    "require_member",
    "require_platform_admin",
    "require_platform_content_admin",
    "require_admin_or_content_token",
    "SCOPE_STUDIO_CONTENT_WRITE",
    "SCOPE_STUDIO_AGENT_DELETE",
    "require_agent_delete",
    "CONTENT_TOKEN_ISSUER",
    "resolve_sso_role",
]
