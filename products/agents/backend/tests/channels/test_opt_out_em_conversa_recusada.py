"""LGPD: a lead's stop word is honoured in EVERY conversation state. Once Julia handed the lead to a human (paused /
transferred), or the agent is off / draining / platform-killed, the controls refuse the turn -- but a PARAR is still
recorded (the ONE opt-out path: ``aplicar_encerramento`` -> ``OptOutService``) and the responsible is told, because the
turn answers the same ``encerrar`` (``lead_opt_out``) + ``opt_out`` actions SW consumes. Any other message is refused
exactly as before. Real route over the Fake stores."""
from __future__ import annotations

from uuid import UUID

import pytest
from noctusai_lib.integrations.llm import ChatToolsResponse, FakeProvider, LLMUsage, ToolCall

from app.channels.opt_out import KIND_LEAD_OPT_OUT
from tests.channels.conftest import turn_body
from tests.channels.test_channel_threads_router import STATUS_ONLY, TURN_ONLY, thr  # noqa: F401 — fixtures
from tests.channels.test_julia_v2_e2e import call, say, step


@pytest.fixture
def on(chan):
    chan.seed_agent()
    return chan


def _pausada(on):
    """Julia hands the lead to a human (the `handoff` tool): the participant ends `pausado`."""
    on.use_provider(FakeProvider(tool_responses=[
        ChatToolsResponse(
            tool_calls=(ToolCall("c1", "handoff", {"motivo_codigo": "pedido_humano", "motivo": "pediu humano"}),),
            finish_reason="tool_calls", usage=LLMUsage(10, 5, 0, 0, 0.001)),
        ChatToolsResponse(text="Vou chamar alguém da equipe.", usage=LLMUsage(20, 8, 0, 0, 0.002)),
        *[say(f"R{i}?") for i in range(5)]]))
    first = on.turn(turn_body("quero falar com um corretor", ids=["a"])).json()
    assert first["status"] == "handoff"
    assert on.threads.get_participante(on.org_id, UUID(first["thread_id"]), on.agent.id).estado == "pausado"
    return first


def _eventos(on):
    return on.threads._opt_out_eventos


def _provider_calls(on) -> int:
    return len(on.provider.calls)


class TestPausedConversation:
    def test_parar_in_a_paused_conversation_records_the_opt_out_and_emits_the_actions(self, on):
        _pausada(on)
        calls = _provider_calls(on)
        body = on.turn(turn_body("PARAR", ids=["b"])).json()
        assert body["status"] == "encerrado"
        assert [a["type"] for a in body["actions"]] == ["encerrar", "opt_out"]
        enc, opt = body["actions"]
        assert enc["lead_opt_out"] is True and enc["opt_out_origem"] == "palavra_chave"
        assert opt["motivo"] == "palavra_chave" and opt["trecho"]
        assert _provider_calls(on) == calls  # no model call
        [ev] = _eventos(on)
        assert ev.origem == "agente" and ev.motivo == '"parar"' and ev.mensagem_lead == "PARAR"
        assert on.lead_ref().opt_out_ativo
        assert on.threads.get_participante(on.org_id, ev.thread_id, on.agent.id).estado == "encerrado"
        assert body["participante"]["estado"] == "encerrado"

    def test_the_lead_gets_the_confirmation_once_and_the_owner_is_notified_once(self, on):
        _pausada(on)
        body = on.turn(turn_body("PARAR", ids=["b"])).json()
        assert len(body["reply"]["partes"]) == 1  # the human owns the chat, but the lead is acknowledged once
        again = on.turn(turn_body("PARAR", ids=["c"])).json()
        # the opt-out is in force: the second one is the ordinary refusal -- no second event, no second confirmation
        assert again["status"] == "lead_opt_out" and again["reply"]["partes"] == [] and again["actions"] == []
        assert len(_eventos(on)) == 1
        assert [n["kind"] for n in on.notificacoes.sent] == [KIND_LEAD_OPT_OUT]

    def test_a_replayed_parar_returns_the_stored_answer_without_a_second_event(self, on):
        _pausada(on)
        a = on.turn(turn_body("PARAR", ids=["b"])).json()
        b = on.turn(turn_body("PARAR", ids=["b"])).json()
        assert a == b and len(_eventos(on)) == 1

    def test_a_message_that_is_not_a_stop_word_is_still_refused(self, on):
        _pausada(on)
        body = on.turn(turn_body("oi", ids=["b"])).json()
        assert body["status"] == "conversa_pausada" and body["actions"] == [] and body["reply"]["partes"] == []
        assert _eventos(on) == [] and not on.lead_ref().opt_out_ativo

    @pytest.mark.parametrize("texto", [
        "não quero mais apartamento", "não quero mais esse apartamento, tem outro?", "quero parar de pagar aluguel",
    ])
    def test_false_positives_are_not_opt_outs(self, on, texto):
        _pausada(on)
        body = on.turn(turn_body(texto, ids=["b"])).json()
        assert body["status"] == "conversa_pausada" and body["actions"] == []
        assert _eventos(on) == [] and not on.lead_ref().opt_out_ativo


class TestOtherRefusedStates:
    def _com_thread(self, on):
        on.use_provider(FakeProvider(tool_responses=[say("Olá!"), *[say(f"R{i}?") for i in range(5)]]))
        return on.turn(turn_body("Oi", ids=["a"])).json()

    def test_agent_off_still_records_the_opt_out_and_sends_nothing(self, on):
        self._com_thread(on)
        on.controles.set(on.org_id, on.agent.id, modo="desligado")
        body = on.turn(turn_body("PARAR", ids=["b"])).json()
        assert body["status"] == "encerrado" and [a["type"] for a in body["actions"]] == ["encerrar", "opt_out"]
        assert body["reply"]["partes"] == []  # she is off: no compiled content, no confirmation -- the alert still goes
        assert on.lead_ref().opt_out_ativo and len(_eventos(on)) == 1

    def test_agent_off_other_messages_are_refused_as_before(self, on):
        self._com_thread(on)
        on.controles.set(on.org_id, on.agent.id, modo="desligado")
        body = on.turn(turn_body("oi", ids=["b"])).json()
        assert body["status"] == "agente_desligado" and body["actions"] == [] and _eventos(on) == []

    def test_draining_idle_thread_records_the_opt_out(self, on):
        self._com_thread(on)
        on.controles.set(on.org_id, on.agent.id, modo="drenando")
        # the thread is fresh (active, not idle): the drain keeps chatting -> the in-turn backstop handles it
        body = on.turn(turn_body("SAIR", ids=["b"])).json()
        assert body["status"] == "encerrado" and body["actions"][0]["lead_opt_out"] is True
        assert on.lead_ref().opt_out_ativo and len(_eventos(on)) == 1

    def test_platform_kill_still_records_the_opt_out(self, on):
        self._com_thread(on)
        on.plataforma.set("julia", desligado=True, motivo="incidente")
        body = on.turn(turn_body("PARAR", ids=["b"])).json()
        assert body["status"] == "encerrado" and [a["type"] for a in body["actions"]] == ["encerrar", "opt_out"]
        assert on.lead_ref().opt_out_ativo

    def test_platform_kill_other_messages_are_refused_as_before(self, on):
        self._com_thread(on)
        on.plataforma.set("julia", desligado=True)
        body = on.turn(turn_body("oi", ids=["b"])).json()
        assert body["status"] == "agente_desligado_plataforma" and _eventos(on) == []

    def test_a_brand_new_lead_refused_while_off_has_no_thread_and_nothing_is_recorded(self, on):
        on.controles.set(on.org_id, on.agent.id, modo="desligado")
        body = on.turn(turn_body("PARAR", ids=["b"])).json()
        assert body["status"] == "agente_desligado" and body["thread_id"] is None and _eventos(on) == []

    def test_a_closed_conversation_reopens_and_the_in_turn_backstop_records_it(self, on):
        first = self._com_thread(on)
        on.threads.transicionar(on.org_id, UUID(first["thread_id"]), on.agent.id, de=("ativo",), para="encerrado",
                                ator_tipo="usuario")
        body = on.turn(turn_body("PARAR", ids=["b"])).json()
        assert body["status"] == "encerrado" and on.lead_ref().opt_out_ativo and len(_eventos(on)) == 1
