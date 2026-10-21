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
from cryptography.fernet import Fernet
from noctusai_lib.api.auth.session import AuthContext, FakeProductTokenAdmin
from noctusai_lib.integrations.llm import FakeProvider

from app.channels.retention import FakeChannelRetention
from app.channels.token_audit import FakeTokenAudit
from app.channels.tool_registry import make_channel_tools_factory
from app.clients.social_wiring import FakeSocialWiringClient
from app.dependencies import (
    SCOPE_CHANNEL_STATUS,
    SCOPE_CHANNEL_TURN,
    get_auth_context,
    get_channel_inbound_store_dep,
    get_channel_llm_runtime_dep,
    get_channel_retention_dep,
    get_conformidade_store_dep,
    get_julia_tools_client_dep,
    get_llm_runtime_dep,
    get_org_llm_key_resolver_dep,
    get_product_token_admin_dep,
    get_notification_sink_dep,
    get_skills_factory_dep,
    get_token_audit_dep,
)
from app.notifications import FakeNotificationSink
from app.qualificacao.ident_store import FakeIdentificacaoStore
from app.qualificacao.identificacao import IdentCipher, IdentificacaoService
from app.qualificacao.lead_store import FakeLeadQualificacaoStore
from app.qualificacao.service import QualificacaoService
from app.qualificacao.store import FakePadraoStore
from app.routers.channel_threads_router import get_agent_controle_store_dep, get_thread_store_dep
from app.routers.qualificacao_router import (
    get_identificacao_service_dep,
    get_lead_qualificacao_store_dep,
    get_padrao_store_dep,
)
from app.runtime.llm_runtime import LlmToolRuntime, LlmTurnLimiter, make_budget_guard
from app.stores.agent_controles import FakeAgentControleStore
from app.stores.channel_inbound import FakeChannelInboundStore
from app.stores.conformidade import FakeConformidadeStore
from app.stores.threads import FakeThreadStore
from app.studio.catalog import StoreKnowledgeCatalog
from app.studio.julia import JULIA_KEY
from tests.channels.julia_v2 import montar_julia_v2, publicar_padrao
from tests.routers.conftest import DEFAULT_ORG_ID, DEFAULT_USER_ID, agents_client  # noqa: F401 — fixture
from tests.studio.rt.conftest import RtHarness, rt  # noqa: F401 — fixtures

_MISSING = object()

OTHER_ORG = UUID(int=424242)
ORG_KEY = "sk-org-a-key"
CONNECTION_ID = UUID(int=77)
BOTH = (SCOPE_CHANNEL_TURN, SCOPE_CHANNEL_STATUS)


def contexto_body(*, origem: dict | None = None, credito: dict | None = None, **estado_extra: Any) -> dict[str, Any]:
    """A v2 ``contexto`` (the operational facts SW owns)."""
    estado: dict[str, Any] = {"interacao_id": str(UUID(int=555)), "encerrado": False, **estado_extra}
    if origem is not None:
        estado["origem"] = origem
    if credito is not None:
        estado["credito"] = credito
    return {
        "hash": "a" * 64, "estado": estado, "agora": datetime(2026, 10, 19, 15, 0, tzinfo=timezone.utc).isoformat(),
        "fuso": "America/Sao_Paulo",
    }


def turn_body(*texts: str, agent_key: str = JULIA_KEY, chat_id: str = "chat-1", ids: list[str] | None = None,
              connection_id: UUID = CONNECTION_ID, contact: dict | None = None, lead_ref: str | None = "contato-1",
              contexto: dict | None = None, gatilho: str | None = None) -> dict[str, Any]:
    texts = texts or ("Oi, quero um apartamento",)
    ids = ids or [f"wamid.{i}-{abs(hash(t)) % 10**6}" for i, t in enumerate(texts)]
    extra: dict[str, Any] = {}
    if lead_ref is not None:
        extra["lead"] = {"ref": lead_ref}
    if contexto is not None:
        extra["contexto"] = contexto
    if gatilho is not None:
        extra["gatilho"] = gatilho
    return {
        **extra,
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
        self.threads = FakeThreadStore(rt_.stores.conversations)
        self.controles = FakeAgentControleStore()
        self.conformidade = FakeConformidadeStore()
        self.padroes = FakePadraoStore()
        self.leads = FakeLeadQualificacaoStore()
        self.ident = IdentificacaoService(FakeIdentificacaoStore(), IdentCipher(Fernet.generate_key()))
        self.qual = QualificacaoService(self.padroes, self.leads, identificacao=self.ident)
        self.retention = FakeChannelRetention(
            rt_.stores.conversations, rt_.stores.messages, self.inbound, self.threads, self.qual)
        #: the org's owner/admin the lead opt-out notice goes to (the Fake sink; never the real core)
        self.notificacoes = FakeNotificationSink(org_admins={rt_.org_id: [str(UUID(int=0xA11CE))]})
        self.sw = FakeSocialWiringClient()
        self.sw.julia_token_orgs.add(rt_.org_id)
        self.skills_factory: Any = None
        self.provider = FakeProvider(tool_responses=["Oi! Você quer comprar ou alugar?"])
        self.keys: dict[tuple[str, UUID], str] = {("openai", rt_.org_id): ORG_KEY}
        self.limiter = LlmTurnLimiter(4)
        self.daily_cap_usd = 0.0
        self.token_admin = FakeProductTokenAdmin()
        self.audit = FakeTokenAudit()
        self.agent: Any = None
        self.version: Any = None

    # ── seeding
    def seed_agent(self, *, ativo: bool = True, publish: bool = True, modo: str | None = None, **world: Any) -> Any:
        """Julia v2: the platform definition (published unless ``publish=False``) + this org's instance, the
        published ``imob-lead`` standard, and the control set to ``ligado`` (``ativo=False`` -> ``desligado``)."""
        studio = self.rt.studio
        catalog = StoreKnowledgeCatalog(self.rt.knowledge)
        mundo = montar_julia_v2(
            studio, catalog, self.org_id, DEFAULT_USER_ID, controles=self.controles,
            ativo_modo=modo or ("ligado" if ativo else "desligado"), publicar=publish, **world)
        self.world = mundo
        self.version = mundo.versao if publish else None
        self.padrao_versao_id = publicar_padrao(self.padroes)
        self.agent = studio.get_agent(self.org_id, JULIA_KEY)
        return self.agent

    def lead_ref(self, ref: str = "contato-1"):
        return self.threads.get_lead_ref_by_externa(self.org_id, ref)

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
            tools_factory=make_channel_tools_factory(),
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
        get_thread_store_dep: lambda: h.threads,
        get_agent_controle_store_dep: lambda: h.controles,
        get_conformidade_store_dep: lambda: h.conformidade,
        get_padrao_store_dep: lambda: h.padroes,
        get_lead_qualificacao_store_dep: lambda: h.leads,
        get_identificacao_service_dep: lambda: h.ident,
        get_julia_tools_client_dep: lambda: h.sw,
        get_skills_factory_dep: lambda: h.skills_factory,
        get_notification_sink_dep: lambda: h.notificacoes,
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
