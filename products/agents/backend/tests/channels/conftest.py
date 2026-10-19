"""Fixtures of the channel turn API suite (Lais A2).

``chan`` builds on the BE-RT ``rt`` harness (the REAL product app, shared Fake
stores) and binds the channel seams — inbound ledger, retention, the
provider-neutral runtime over the seed's ``FakeProvider``, the handoff
collector, per-org key resolver, token admin, token audit — through
``app.dependency_overrides`` (never a patch of our own code). A request becomes
a ``pk_*`` channel-token call with ``as_token`` (the same ``get_auth_context``
seam the package-scope suite uses): the SCOPES / ISSUER / PRINCIPAL are the
test's own, the guard under test (``require_scopes`` + the issuer allowlist +
the agent resolution) runs for real.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator
from uuid import UUID, uuid4

import pytest
from noctusai_lib.api.auth.session import AuthContext, FakeProductTokenAdmin
from noctusai_lib.integrations.llm import FakeProvider

from app.channels.retention import FakeChannelRetention
from app.clients.social_wiring import FakeSocialWiringClient
from app.channels.token_audit import FakeTokenAudit
from app.channels.tools import HandoffCollector, make_channel_tools_factory
from app.dependencies import (
    SCOPE_CHANNEL_STATUS,
    SCOPE_CHANNEL_TURN,
    get_auth_context,
    get_channel_inbound_store_dep,
    get_channel_llm_runtime_dep,
    get_channel_retention_dep,
    get_handoff_collector_dep,
    get_llm_runtime_dep,
    get_org_llm_key_resolver_dep,
    get_product_token_admin_dep,
    get_token_audit_dep,
)
from app.runtime.llm_runtime import LlmToolRuntime, LlmTurnLimiter, make_budget_guard
from app.stores.channel_inbound import FakeChannelInboundStore
from app.studio.julia import JULIA_KEY, ensure_julia
from tests.routers.conftest import DEFAULT_ORG_ID, DEFAULT_USER_ID, agents_client  # noqa: F401 — fixture
from tests.studio.rt.conftest import RtHarness, rt  # noqa: F401 — fixtures

_MISSING = object()

OTHER_ORG = UUID(int=424242)
ORG_KEY = "sk-org-a-key"
CONNECTION_ID = UUID(int=77)
BOTH = (SCOPE_CHANNEL_TURN, SCOPE_CHANNEL_STATUS)


def turn_body(*texts: str, agent_key: str = JULIA_KEY, chat_id: str = "chat-1", ids: list[str] | None = None,
              connection_id: UUID = CONNECTION_ID, contact: dict | None = None) -> dict[str, Any]:
    texts = texts or ("Oi, quero um apartamento",)
    ids = ids or [f"wamid.{i}-{abs(hash(t)) % 10**6}" for i, t in enumerate(texts)]
    return {
        "agent_key": agent_key,
        "channel": "whatsapp",
        "channel_ref": {"connection_id": str(connection_id), "chat_id": chat_id},
        "contact": contact if contact is not None else {"phone_e164": "+5511999990000", "display_name": "Fulano da Silva"},
        "messages": [
            {"texto": t, "provider_message_id": pmid, "at": datetime(2026, 10, 14, 12, 0, i, tzinfo=timezone.utc).isoformat()}
            for i, (t, pmid) in enumerate(zip(texts, ids, strict=True))
        ],
    }


class ChannelHarness:
    def __init__(self, rt_: RtHarness) -> None:
        self.rt = rt_
        self.client = rt_.client
        self.org_id: UUID = rt_.org_id
        self.inbound = FakeChannelInboundStore()
        self.retention = FakeChannelRetention(rt_.stores.conversations, rt_.stores.messages, self.inbound)
        self.collector = HandoffCollector()
        self.lais = FakeSocialWiringClient()
        self.provider = FakeProvider(tool_responses=["Oi! Você quer comprar ou alugar?"])
        self.keys: dict[tuple[str, UUID], str] = {("openai", rt_.org_id): ORG_KEY}
        self.limiter = LlmTurnLimiter(4)
        self.daily_cap_usd = 0.0
        self.token_admin = FakeProductTokenAdmin()
        self.audit = FakeTokenAudit()
        self.agent: Any = None
        self.version: Any = None

    # ── seeding
    def seed_agent(self, *, ativo: bool = True, publish: bool = True) -> Any:
        """`julia` through the production seed, optionally activated + published."""
        studio = self.rt.studio
        agent = ensure_julia(self.org_id, studio_store=studio, created_by=DEFAULT_USER_ID)
        if publish:
            draft = studio.get_draft(self.org_id, agent.id)
            self.version = self.rt.publish(agent, draft.id)
        if ativo:
            agent = studio.update_agent(self.org_id, JULIA_KEY, {"ativo": True})
        self.agent = studio.get_agent(self.org_id, JULIA_KEY)
        return self.agent

    # ── runtime
    def use_provider(self, provider: FakeProvider, *, key_for_org: bool = True) -> None:
        self.provider = provider
        self.keys = {("openai", self.org_id): ORG_KEY} if key_for_org else {}
        self._bind_runtime()

    def _bind_runtime(self) -> None:
        from app.main import app

        runtime = LlmToolRuntime(
            messages=self.rt.stores.messages,
            key_resolver=lambda provider, org: self.keys.get((provider, org)),
            limiter=self.limiter,
            budget_guard=make_budget_guard(messages=self.rt.stores.messages, daily_cap_usd=self.daily_cap_usd),
            tools_factory=make_channel_tools_factory(self.collector, lais_client_factory=lambda: self.lais),
            provider_impl=self.provider,
        )
        self.runtime = runtime
        app.dependency_overrides[get_channel_llm_runtime_dep] = lambda: runtime

    # ── auth
    @contextmanager
    def as_token(
        self, *scopes: str, issuer: str | None = "social-wiring", principal: UUID | None | object = _MISSING,
        org_id: UUID | None = None,
    ) -> Iterator[None]:
        from app.main import app

        principal_id = (self.agent.id if self.agent is not None else uuid4()) if principal is _MISSING else principal
        saved = app.dependency_overrides.get(get_auth_context, _MISSING)
        app.dependency_overrides[get_auth_context] = lambda: AuthContext(
            org_id=org_id or self.org_id, caller_kind="product", user_id=None, scopes=list(scopes or BOTH),
            raw_token="tok", api_token_id=UUID(int=9), principal_agent_id=principal_id, issuer=issuer,
        )
        try:
            yield
        finally:
            if saved is _MISSING:
                app.dependency_overrides.pop(get_auth_context, None)
            else:
                app.dependency_overrides[get_auth_context] = saved

    # ── HTTP (always the raw TestClient: the bearer, when any, is the test's)
    def request(self, method: str, url: str, **kw):
        return self.client.raw().request(method, url, **kw)

    def turn(self, body: dict | None = None, *, scopes=BOTH, **kw):
        with self.as_token(*scopes, **kw):
            return self.request("POST", "/api/channels/turns", json=body if body is not None else turn_body())

    def events(self, conversation_id: str | UUID) -> list:
        from app.realtime import conversation_scope

        return list(self.rt.stores.bus._streams.get(conversation_scope(UUID(str(conversation_id))), []))


@pytest.fixture
def chan(rt):
    from app.main import app

    h = ChannelHarness(rt)
    bindings = {
        get_channel_inbound_store_dep: lambda: h.inbound,
        get_channel_retention_dep: lambda: h.retention,
        get_handoff_collector_dep: lambda: h.collector,
        get_org_llm_key_resolver_dep: lambda: (lambda provider, org: h.keys.get((provider, org))),
        get_product_token_admin_dep: lambda: h.token_admin,
        get_token_audit_dep: lambda: h.audit,
    }
    saved = {k: app.dependency_overrides.get(k, _MISSING) for k in (*bindings, get_channel_llm_runtime_dep, get_llm_runtime_dep)}
    app.dependency_overrides.update(bindings)
    h._bind_runtime()
    try:
        yield h
    finally:
        for k, v in saved.items():
            if v is _MISSING:
                app.dependency_overrides.pop(k, None)
            else:
                app.dependency_overrides[k] = v
