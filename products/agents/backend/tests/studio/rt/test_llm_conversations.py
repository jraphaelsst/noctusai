"""Studio "Testar conversa" for a ``runtime='llm'`` agent (Lais A1) through the
REAL product app: the same conversation route, the provider-neutral runtime
over the seed's ``FakeProvider`` (installed through the product's
``get_llm_runtime_dep`` seam), Bia / ``claude_sdk`` agents unchanged.
"""
from __future__ import annotations

from dataclasses import replace
from uuid import UUID, uuid4

import pytest

from noctusai_lib.integrations.llm import ChatToolsResponse, FakeProvider, LLMUsage

from app.dependencies import get_llm_runtime_dep
from app.runtime.llm_runtime import LlmToolRuntime, LlmTurnLimiter, make_budget_guard
from tests.routers.conftest import install_runtime, wait_turn_released, wait_until

ORG_KEY = "sk-org-test-key"


def _llm_agent(rt, key="julia", *, provider="openai", model="gpt-5.6-terra"):
    agent, _ = rt.make_agent(key, nome="Julia", publish=False, ativo=True)
    rt.studio._agents[(rt.org_id, key)] = replace(agent, runtime="llm")
    draft = rt.studio.get_draft(rt.org_id, agent.id)
    rt.studio.update_draft(rt.org_id, draft.id, {"provider": provider, "model": model})
    agent = rt.studio.get_agent(rt.org_id, key)
    version = rt.publish(agent, draft.id)
    return agent, version


def _install_llm(rt, provider, *, key=ORG_KEY, budget_guard=None, capacity=2):
    from app.main import app

    runtime = LlmToolRuntime(
        messages=rt.stores.messages,
        key_resolver=lambda p, org: key if org == rt.org_id else None,
        limiter=LlmTurnLimiter(capacity),
        budget_guard=budget_guard,
        provider_impl=provider,
    )
    app.dependency_overrides[get_llm_runtime_dep] = lambda: runtime
    return runtime


@pytest.fixture(autouse=True)
def _drop_llm_override():
    yield
    from app.main import app

    app.dependency_overrides.pop(get_llm_runtime_dep, None)


def _conv(rt, key="julia"):
    resp = rt.post("/api/conversations", json={"agent_key": key})
    assert resp.status_code == 201, resp.text
    return resp.json()


def _post(rt, conv_id, texto="Oi, quero um apartamento"):
    return rt.post(f"/api/conversations/{conv_id}/messages", json={"texto": texto})


class TestLlmAgentTestChat:
    def test_turn_runs_on_the_llm_runtime_and_persists_reply_cost_and_stamps(self, rt):
        provider = FakeProvider(tool_responses=[
            ChatToolsResponse(text="Oi! Comprar ou alugar?", usage=LLMUsage(100, 20, 0, 0, 0.0042)),
        ])
        _install_llm(rt, provider)
        claude, _ = install_runtime(rt.client, [])  # the Claude runtime must NOT be used
        agent, version = _llm_agent(rt)
        assert version.provider == "openai" and version.model == "gpt-5.6-terra"
        conv = _conv(rt)

        resp = _post(rt, conv["id"])
        assert resp.status_code == 202, resp.text
        assert wait_turn_released(rt.stores.conversations, rt.org_id, UUID(conv["id"]))

        assert claude.calls == []
        call = provider.calls[0]
        assert call["api_key"] == ORG_KEY and call["model"] == "gpt-5.6-terra"
        assert call["messages"][0].role == "system" and call["messages"][-1].content == "Oi, quero um apartamento"

        msgs = rt.get(f"/api/conversations/{conv['id']}/messages").json()["items"]
        assistant = [m for m in msgs if m["role"] == "assistant"]
        assert [m["texto"] for m in assistant] == ["Oi! Comprar ou alugar?"]
        assert assistant[0]["version_id"] == str(version.id)
        assert assistant[0]["compiled_hash"].startswith("sha256:")
        assert assistant[0]["custo_usd"] == pytest.approx(0.0042)
        assert assistant[0]["tokens_entrada"] == 100 and assistant[0]["tokens_saida"] == 20

    def test_second_turn_remembers_the_first(self, rt):
        provider = FakeProvider(tool_responses=["Comprar ou alugar?", "Em que bairro?"])
        _install_llm(rt, provider)
        _llm_agent(rt)
        conv = _conv(rt)
        for texto in ("Oi", "Comprar"):
            assert _post(rt, conv["id"], texto).status_code == 202
            assert wait_turn_released(rt.stores.conversations, rt.org_id, UUID(conv["id"]))
        second = [(m.role, m.content) for m in provider.calls[1]["messages"][1:]]
        assert second == [("user", "Oi"), ("assistant", "Comprar ou alugar?"), ("user", "Comprar")]

    def test_org_without_a_key_is_424_with_zero_trace(self, rt):
        provider = FakeProvider(tool_responses=["nunca"])
        _install_llm(rt, provider, key="")
        _llm_agent(rt)
        conv = _conv(rt)
        resp = _post(rt, conv["id"])
        assert resp.status_code == 424
        assert resp.json()["code"] == "llm_not_configured"
        assert rt.get(f"/api/conversations/{conv['id']}/messages").json()["items"] == []
        assert provider.calls == []
        # no lock was left behind
        assert rt.stores.conversations.try_acquire_turn(rt.org_id, UUID(conv["id"]), "probe", 5)

    def test_exhausted_org_budget_is_429_capacidade_with_retry_after_and_zero_trace(self, rt):
        async def monthly(_org):
            from noctusai_lib.integrations.llm import LLMBudgetExceeded

            raise LLMBudgetExceeded(str(rt.org_id), 10.0, 10.0)

        provider = FakeProvider(tool_responses=["nunca"])
        _install_llm(rt, provider, budget_guard=make_budget_guard(monthly=monthly))
        _llm_agent(rt)
        conv = _conv(rt)
        resp = _post(rt, conv["id"])
        assert resp.status_code == 429
        assert resp.json()["code"] == "capacidade"
        assert int(resp.headers["Retry-After"]) > 0
        assert provider.calls == []
        assert rt.get(f"/api/conversations/{conv['id']}/messages").json()["items"] == []

    def test_full_limiter_is_429_agente_capacidade_like_every_runtime(self, rt):
        provider = FakeProvider(tool_responses=["x"])
        runtime = _install_llm(rt, provider, capacity=1)
        _llm_agent(rt)
        conv = _conv(rt)
        held = runtime.try_reserve()
        assert held is not None
        resp = _post(rt, conv["id"])
        assert resp.status_code == 429 and resp.json()["code"] == "agente_capacidade"

    def test_org_b_conversation_never_uses_org_a_key(self, rt):
        """The injected resolver only knows org A (`rt.org_id`); a different
        org's agent turn cannot borrow it. Driven at the runtime seam the
        route uses, so the proof does not depend on a second auth identity."""
        provider = FakeProvider(tool_responses=["x"])
        runtime = _install_llm(rt, provider)
        import asyncio

        from app.runtime.errors import LlmNotConfiguredError

        with pytest.raises(LlmNotConfiguredError):
            asyncio.run(runtime.preflight("openai", uuid4()))
        assert provider.calls == []

    def test_a_provider_the_runtime_cannot_serve_is_refused_before_the_turn(self, rt):
        _install_llm(rt, FakeProvider(tool_responses=["x"]))
        # openai version on a claude_sdk agent -> 409, never run on Anthropic
        agent, _ = rt.make_agent("claude-agent", publish=False)
        draft = rt.studio.get_draft(rt.org_id, agent.id)
        rt.studio.update_draft(rt.org_id, draft.id, {"provider": "openai", "model": "gpt-5.6-terra"})
        rt.publish(agent, draft.id)
        conv = _conv(rt, "claude-agent")
        resp = _post(rt, conv["id"])
        assert resp.status_code == 409
        assert resp.json()["code"] == "provider_runtime_mismatch"


class TestClaudeSdkAgentsUnchanged:
    def test_a_claude_sdk_studio_agent_still_runs_on_the_claude_runtime(self, rt):
        provider = FakeProvider(tool_responses=["nunca"])
        _install_llm(rt, provider)
        runtime, _ = install_runtime(rt.client, [])
        rt.make_agent()
        conv = rt.post("/api/conversations", json={"agent_key": "isa"}).json()
        assert _post(rt, conv["id"], "Crie um roteiro").status_code == 202
        assert wait_turn_released(rt.stores.conversations, rt.org_id, UUID(conv["id"]))
        spec, _ctx, prompt = runtime.calls[0]
        assert spec.runtime == "claude_sdk" and spec.provider == "anthropic"
        assert provider.calls == []
        assert wait_until(lambda: any(
            m["role"] == "assistant"
            for m in rt.get(f"/api/conversations/{conv['id']}/messages").json()["items"]
        ))
