"""Owner decision 2026-11-08 ("it shouldn't be deterministic, Julia judges"): a stop word in a conversation the controls
REFUSE (Julia handed the lead to a human, the agent is off) no longer records an opt-out by itself -- those turns run no
model, so there is no decision to make; the message is refused exactly as the refusal table says. (Before: the route
recorded the opt-out without the model.) Real route over the Fake stores."""
from __future__ import annotations

from uuid import UUID

import pytest
from noctusai_lib.integrations.llm import ChatToolsResponse, FakeProvider, LLMUsage, ToolCall

from tests.channels.conftest import turn_body
from tests.channels.test_channel_threads_router import STATUS_ONLY, TURN_ONLY, thr  # noqa: F401 — fixtures
from tests.channels.test_julia_v2_e2e import say


@pytest.fixture
def on(chan):
    chan.seed_agent()
    return chan


def test_parar_in_a_paused_conversation_is_refused_as_before_and_records_no_opt_out(on):
    on.use_provider(FakeProvider(tool_responses=[
        ChatToolsResponse(
            tool_calls=(ToolCall("c1", "handoff", {"motivo_codigo": "pedido_humano", "motivo": "pediu humano"}),),
            finish_reason="tool_calls", usage=LLMUsage(10, 5, 0, 0, 0.001)),
        ChatToolsResponse(text="Vou chamar alguém da equipe.", usage=LLMUsage(20, 8, 0, 0, 0.002)),
        *[say(f"R{i}?") for i in range(5)]]))
    first = on.turn(turn_body("quero falar com um corretor", ids=["a"])).json()
    assert first["status"] == "handoff"
    calls = len(on.provider.calls)
    body = on.turn(turn_body("PARAR", ids=["b"])).json()
    assert body["status"] != "encerrado" and not any(a["type"] in ("encerrar", "opt_out") for a in body["actions"])
    assert len(on.provider.calls) == calls and not on.lead_ref().opt_out_ativo and on.threads._opt_out_eventos == []
    assert on.threads.get_participante(on.org_id, UUID(first["thread_id"]), on.agent.id).estado == "pausado"


def test_parar_while_the_agent_is_off_is_refused_as_before_and_records_no_opt_out(on):
    on.use_provider(FakeProvider(tool_responses=[say("Olá!"), *[say(f"R{i}?") for i in range(5)]]))
    on.turn(turn_body("Oi", ids=["a"]))
    on.controles.set(on.org_id, on.agent.id, modo="desligado")
    body = on.turn(turn_body("PARAR", ids=["b"])).json()
    assert body["status"] != "encerrado" and body["reply"]["partes"] == []
    assert not on.lead_ref().opt_out_ativo and on.threads._opt_out_eventos == []
