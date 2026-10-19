"""Lais contract X — social-wiring's REAL ``HttpAgentsClient`` against agents' REAL
channel routes (julia-agent-contract.md §3.1/§3.2/§10.1 M5, noc-contract-first step 6).

Why this lives in agents' suite: both products ship a top-level package named ``app``,
so one process cannot import both. SW's client module has no ``app`` dependency (httpx +
``noctusai_lib`` only), so it is loaded BY FILE PATH under a private module name; agents'
app is the one imported normally. The client talks to agents' ASGI app through the
client's own injectable ``transport`` (``httpx.ASGITransport``) — real bytes, real routing.

What is real: the SW client, agents' routes + guards (scopes, issuer allowlist, principal
binding), the token MINT route and the seed ``SupabaseApiTokenResolver`` row mapper over the
minted row. What is substituted, through declared dependency seams only: the LLM
(seed ``FakeProvider``), the stores (agents' Fakes) and the auth dependency (rebuilt with
the seed's own ``make_get_auth_context`` over the minted rows — no guard is patched).
"""
from __future__ import annotations

import asyncio
import importlib.util
from dataclasses import fields
from pathlib import Path

import httpx
import pytest
from noctusai_lib.api.auth.session import SupabaseApiTokenResolver, make_get_auth_context
from noctusai_lib.integrations.llm import ChatToolsResponse, FakeProvider, LLMUsage, ToolCall
from noctusai_lib.testing import MockSupabaseClient

from app.dependencies import get_auth_context
from app.runtime.llm_runtime import LlmTurnLimiter
from tests.channels.conftest import CONNECTION_ID, chan  # noqa: F401 — fixture
from tests.routers.conftest import agents_client  # noqa: F401 — fixture
from tests.studio.rt.conftest import rt  # noqa: F401 — fixture

_SW_CLIENT = Path(__file__).resolve().parents[4] / "social-wiring" / "backend" / "app" / "clients" / "agents.py"


def _load_sw_client():
    spec = importlib.util.spec_from_file_location("sw_agents_client_under_contract", _SW_CLIENT)
    mod = importlib.util.module_from_spec(spec)
    import sys

    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


sw = _load_sw_client()
_MISSING = object()


class _NoSession:
    async def create(self, **kw): ...
    async def lookup(self, sid):
        return None
    async def refresh_ttl(self, sid, ttl_seconds=86400): ...
    async def delete(self, sid): ...


@pytest.fixture
def wired(chan):  # noqa: F811
    """Mint a REAL channel token, resolve it through the seed resolver, return a SW client."""
    from app.main import app

    minted = chan.client.post(
        "/api/agents/julia/channel-token", json={"product": "social-wiring", "label": "contract-x"}
    )
    assert minted.status_code == 201, minted.text
    token = minted.json()["token"]
    agent = chan.rt.studio.get_agent(chan.org_id, "julia")
    chan.version = chan.rt.publish(agent, chan.rt.studio.get_draft(chan.org_id, agent.id).id)
    chan.rt.studio.update_agent(chan.org_id, "julia", {"ativo": True})
    chan.agent = chan.rt.studio.get_agent(chan.org_id, "julia")

    resolver = SupabaseApiTokenResolver(
        MockSupabaseClient(list(chan.token_admin.rows["agents"]), schema="agents"), schema="agents"
    )
    saved = app.dependency_overrides.get(get_auth_context, _MISSING)
    app.dependency_overrides[get_auth_context] = make_get_auth_context(
        session_store=_NoSession(), api_token_resolver=resolver
    )
    chan.token = token

    def client(tok: str | None = None):
        return sw.HttpAgentsClient(
            "http://agents.test", tok or token, transport=httpx.ASGITransport(app=app)
        )

    chan.sw_client = client
    try:
        yield chan
    finally:
        if saved is _MISSING:
            app.dependency_overrides.pop(get_auth_context, None)
        else:
            app.dependency_overrides[get_auth_context] = saved


def _req(*texts, ids=None, chat_id="chat-1", agent_key="julia"):
    from datetime import datetime, timezone

    ids = ids or [f"wamid.x{i}" for i in range(len(texts))]
    return sw.TurnRequest(
        agent_key=agent_key,
        connection_id=str(CONNECTION_ID),
        chat_id=chat_id,
        messages=tuple(
            sw.TurnMessage(texto=t, provider_message_id=p, at=datetime(2026, 10, 14, 12, 0, i, tzinfo=timezone.utc))
            for i, (t, p) in enumerate(zip(texts, ids, strict=True))
        ),
        phone_e164="+5511999990000",
        display_name="Fulano da Silva",
    )


def _run(coro):
    return asyncio.run(coro)


class TestTurn:
    def test_turn_is_parsed_into_sw_turnresult_with_exactly_the_contract_fields(self, wired):
        wired.use_provider(FakeProvider(tool_responses=[
            ChatToolsResponse(text="Oi!\n\nComprar ou alugar?", usage=LLMUsage(120, 30, 0, 0, 0.0021)),
        ]))
        result = _run(wired.sw_client().run_turn(_req("Oi, quero um apartamento")))
        assert isinstance(result, sw.TurnResult)
        assert {f.name for f in fields(result)} == {
            "conversation_id", "partes", "status", "actions", "custo_usd", "tokens_entrada", "tokens_saida",
        }
        assert result.partes == ("Oi!", "Comprar ou alugar?")
        assert result.status == "respondido" and result.actions == () and result.handoff is None
        assert (result.custo_usd, result.tokens_entrada, result.tokens_saida) == (0.0021, 120, 30)
        assert result.conversation_id

    def test_handoff_action_reaches_sw(self, wired):
        call = ToolCall("c1", "handoff", {"motivo": "Cliente pediu um corretor."})
        wired.use_provider(FakeProvider(tool_responses=[
            ChatToolsResponse(tool_calls=(call,), finish_reason="tool_calls", usage=LLMUsage(10, 5, 0, 0, 0.001)),
            ChatToolsResponse(text="Vou chamar alguém da equipe.", usage=LLMUsage(20, 8, 0, 0, 0.002)),
        ]))
        result = _run(wired.sw_client().run_turn(_req("quero falar com um corretor")))
        assert result.status == "handoff"
        assert result.handoff == sw.HandoffAction(motivo="Cliente pediu um corretor.")
        assert result.partes == ("Vou chamar alguém da equipe.",)

    def test_idempotent_replay_returns_same_reply_without_a_second_provider_call(self, wired):
        client = wired.sw_client()
        first = _run(client.run_turn(_req("Oi", ids=["m-replay"])))
        calls = len(wired.provider.calls)
        again = _run(client.run_turn(_req("Oi", ids=["m-replay"])))
        assert again == first
        assert len(wired.provider.calls) == calls == 1


class TestStatusAndDelete:
    def test_status_parses_into_sw_agentstatus(self, wired):
        st = _run(wired.sw_client().agent_status("julia"))
        assert isinstance(st, sw.AgentStatus)
        assert st.agent_key == "julia" and st.ativo is True
        assert st.versao_ativa == wired.version.versao
        assert st.llm_configurado is True and st.provider == "openai" and st.model

    def test_delete_204_is_success_and_erases(self, wired):
        client = wired.sw_client()
        _run(client.run_turn(_req("Oi", ids=["m-del"])))
        req = sw.DeletionRequest(agent_key="julia", connection_id=str(CONNECTION_ID), chat_id="chat-1")
        res = _run(client.delete_conversation_data(req))
        assert isinstance(res, sw.DeletionResult)
        assert wired.rt.stores.conversations.list_channel(wired.org_id) == []
        # nothing left: a second delete is still success (idempotent 204)
        assert isinstance(_run(client.delete_conversation_data(req)), sw.DeletionResult)


class TestErrorClasses:
    def test_401_token_invalid(self, wired):
        with pytest.raises(sw.AgentsTokenInvalid):
            _run(wired.sw_client("pk_" + "0" * 40).run_turn(_req("Oi")))

    def test_404_agent_not_found(self, wired):
        with pytest.raises(sw.AgentNotFound):
            _run(wired.sw_client().agent_status("nao-existe"))

    def test_424_llm_not_configured(self, wired):
        wired.use_provider(FakeProvider(tool_responses=["x"]), key_for_org=False)
        with pytest.raises(sw.LlmNotConfigured):
            _run(wired.sw_client().run_turn(_req("Oi")))

    def test_429_capacidade_carries_retry_after(self, wired):
        wired.limiter = LlmTurnLimiter(1)
        wired._bind_runtime()
        held = wired.limiter.try_reserve()
        assert held is not None
        with pytest.raises(sw.CapacityExceeded) as exc:
            _run(wired.sw_client().run_turn(_req("Oi")))
        assert exc.value.code == "capacidade"
        assert exc.value.retry_after >= 1
