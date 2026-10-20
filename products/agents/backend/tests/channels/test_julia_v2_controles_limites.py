"""The controls matrix through the REAL turn route (CONTRACT §5.2) and the per-chat abuse limits (owner round 2).

``decidir`` / ``aplicar_controles`` have their own exhaustive suites (A-THREAD); here the question is the ORDER the
route keeps: controls under the turn lock, BEFORE the inbound text is stored or any model is called, failing closed.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from noctusai_lib.integrations.llm import ChatToolsResponse, FakeProvider, LLMUsage

from app.channels.thread_service import alterar_estado_humano
from app.stores.threads import HandoffDestino
from tests.channels.conftest import contexto_body, turn_body
from tests.channels.test_julia_v2_e2e import say


def msgs(chan, thread_id, role=None):
    rows = chan.rt.stores.messages.list(chan.org_id, UUID(str(thread_id)), limite=200)
    return [m for m in rows if role is None or m.role == role]


def model_calls(chan) -> int:
    return len([c for c in chan.provider.calls if c["method"] == "chat_with_tools"])


@pytest.fixture
def on(chan):
    chan.seed_agent()
    chan.use_provider(FakeProvider(tool_responses=[say(f"Resposta {i}?") for i in range(30)]))
    return chan


class TestTheControlsMatrix:
    def test_off_with_an_existing_thread_appends_the_message_and_answers_nothing(self, on):
        first = on.turn(turn_body("Oi", ids=["a"])).json()
        on.controles.set(on.org_id, on.agent.id, modo="desligado")
        calls = model_calls(on)
        body = on.turn(turn_body("Alguém aí?", ids=["b"])).json()
        assert body["status"] == "agente_desligado" and body["reply"]["partes"] == [] and body["actions"] == []
        assert [m.texto for m in msgs(on, first["thread_id"], "user")] == ["Oi", "Alguém aí?"]  # Q5: kept
        assert model_calls(on) == calls

    def test_the_control_is_read_on_every_turn_never_cached(self, on):
        on.turn(turn_body("Oi", ids=["a"]))
        on.controles.set(on.org_id, on.agent.id, modo="desligado")
        assert on.turn(turn_body("2", ids=["b"])).json()["status"] == "agente_desligado"
        on.controles.set(on.org_id, on.agent.id, modo="ligado")
        assert on.turn(turn_body("3", ids=["c"])).json()["status"] == "respondido"

    def test_draining_refuses_a_new_lead_but_keeps_chatting_in_an_open_thread(self, on):
        on.turn(turn_body("Oi", ids=["a"]))
        on.controles.set(on.org_id, on.agent.id, modo="drenando")
        novo = on.turn(turn_body("Oi", ids=["n1"], chat_id="outro", lead_ref="contato-9"))
        assert novo.json()["status"] == "novo_lead_recusado" and novo.json()["thread_id"] is None
        assert on.threads.get_lead_ref_by_externa(on.org_id, "contato-9") is None  # NOTHING stored
        assert on.turn(turn_body("Segue", ids=["b"])).json()["status"] == "respondido"

    def test_an_open_thread_idle_past_the_drain_window_is_closed_and_the_message_only_appended(self, on):
        thread = on.turn(turn_body("Oi", ids=["a"])).json()["thread_id"]
        on.controles.set(on.org_id, on.agent.id, modo="drenando")
        row = on.rt.stores.conversations._rows[UUID(thread)]
        row["ultima_mensagem_lead_em"] = datetime.now(timezone.utc) - timedelta(days=8)
        body = on.turn(turn_body("Voltei", ids=["b"])).json()
        assert body["status"] == "novo_lead_recusado"
        assert on.threads.get_participante(on.org_id, UUID(thread), on.agent.id).estado == "encerrado"
        assert "Voltei" in [m.texto for m in msgs(on, thread, "user")]

    def test_a_paused_thread_is_appended_to_never_answered(self, on):
        thread = on.turn(turn_body("Oi", ids=["a"])).json()["thread_id"]
        alterar_estado_humano(org_id=on.org_id, thread_id=UUID(thread), agent_id=on.agent.id, para="pausado",
                              ator_user_id=uuid4(), motivo="atendendo", threads=on.threads)
        calls = model_calls(on)
        body = on.turn(turn_body("Preciso de ajuda", ids=["b"])).json()
        assert body["status"] == "conversa_pausada" and body["participante"]["estado"] == "pausado"
        assert model_calls(on) == calls and "Preciso de ajuda" in [m.texto for m in msgs(on, thread, "user")]

    def test_the_other_threads_stay_answered_when_one_is_paused(self, on):
        pausada = on.turn(turn_body("Oi", ids=["a"])).json()["thread_id"]
        alterar_estado_humano(org_id=on.org_id, thread_id=UUID(pausada), agent_id=on.agent.id, para="pausado",
                              ator_user_id=uuid4(), motivo=None, threads=on.threads)
        assert on.turn(turn_body("Oi", ids=["c"], chat_id="chat-2", lead_ref="contato-2")).json()["status"] == "respondido"

    def test_a_thread_handed_to_the_broker_is_not_answered(self, on):
        thread = on.turn(turn_body("Oi", ids=["a"])).json()["thread_id"]
        on.threads.registrar_handoff(
            on.org_id, UUID(thread), on.agent.id, para=HandoffDestino.dono_da_org(), motivo_codigo="x", resumo="r",
            para_estado="transferido")
        assert on.turn(turn_body("Oi?", ids=["b"])).json()["status"] == "conversa_com_outro_responsavel"

    def test_an_ended_thread_reopens_when_the_lead_writes_again_while_on(self, on):
        thread = on.turn(turn_body("Oi", ids=["a"])).json()["thread_id"]
        on.threads.transicionar(on.org_id, UUID(thread), on.agent.id, de=["ativo"], para="encerrado",
                                ator_tipo="agente", motivo="lead_encerrou")
        body = on.turn(turn_body("Mudei de ideia", ids=["b"])).json()
        assert body["status"] == "respondido" and body["participante"]["estado"] == "ativo"

    def test_an_unreadable_control_is_503_and_nothing_is_stored_or_sent(self, on):
        on.turn(turn_body("Oi", ids=["a"]))
        before = {t.id: len(msgs(on, t.id)) for t in on.rt.stores.conversations.list_channel(on.org_id)}
        calls = model_calls(on)
        on.controles.falha = RuntimeError("db down")
        resp = on.turn(turn_body("De novo", ids=["b"]))
        assert resp.status_code == 503 and resp.json()["code"] == "controle_indisponivel"
        assert {t.id: len(msgs(on, t.id)) for t in on.rt.stores.conversations.list_channel(on.org_id)} == before
        assert model_calls(on) == calls and on.inbound.find(on.org_id, UUID(int=77), ["b"]) == {}

    def test_a_lead_who_opted_out_is_recorded_but_never_answered(self, on):
        on.turn(turn_body("Oi", ids=["a"]))
        on.threads.registrar_opt_out(on.org_id, "contato-1")
        calls = model_calls(on)
        body = on.turn(turn_body("Quero voltar", ids=["b"])).json()
        assert body["status"] == "lead_opt_out" and model_calls(on) == calls

    def test_a_refusal_is_replayed_not_re_evaluated(self, on):
        on.turn(turn_body("Oi", ids=["a"]))
        on.controles.set(on.org_id, on.agent.id, modo="desligado")
        first = on.turn(turn_body("X", ids=["b"]))
        on.controles.set(on.org_id, on.agent.id, modo="ligado")
        assert on.turn(turn_body("X", ids=["b"])).json() == first.json()  # the stored status, no model run


class TestReengagement:
    def _re(self, **estado):
        return turn_body(gatilho="reengajamento", contexto=contexto_body(reengajamento="horas", **estado))

    def _body(self, **estado):
        b = self._re(**estado)
        b["messages"] = []
        return b

    def test_it_runs_for_an_active_participant_with_no_fake_user_message(self, on):
        on.turn(turn_body("Oi", ids=["a"]))
        body = on.turn(self._body(texto_base="Oi, ainda procura imóvel?", reescrever=True, atendente_nome="Bia")).json()
        assert body["status"] == "respondido"
        last = [c for c in on.provider.calls if c["method"] == "chat_with_tools"][-1]["messages"]
        assert [m.role for m in last if m.role != "system"] == ["user", "assistant"]  # history only: the lead's "Oi" + the reply
        sistema = last[1].content
        assert "txt:reengajamento.horas" in sistema and '"Oi, ainda procura imóvel?"' in sistema
        assert 'txt:contexto.rotulo_atendente: "Bia"' in sistema
        assert not any("[sistema]" in str(m.content) for m in last)

    def test_after_the_agent_ends_the_conversation_no_follow_up_runs(self, chan):
        """A-polish #7: the lead asks to stop, the model calls ``encerrar``; afterwards a scheduled re-engagement is
        ignored (no model call, nothing stored) and the thread tells SW to suppress follow-ups."""
        from app.dependencies import SCOPE_CHANNEL_STATUS
        from tests.channels.test_julia_v2_e2e import call, step

        chan.seed_agent()
        chan.use_provider(FakeProvider(tool_responses=[
            step(call("encerrar", motivo="lead_encerrou")), say("Tudo bem, não envio mais mensagens."),
            *[say(f"Resposta {i}?") for i in range(5)],
        ]))
        first = chan.turn(turn_body("Não quero mais, pare de me mandar mensagem", ids=["a"])).json()
        assert [a["type"] for a in first["actions"]] == ["encerrar"]
        [p] = chan.threads.list_participantes(chan.org_id, UUID(first["thread_id"]))
        assert p.estado == "encerrado"
        calls, antes = model_calls(chan), len(msgs(chan, first["thread_id"]))
        body = chan.turn(self._body(texto_base="Oi, ainda procura imóvel?")).json()
        assert body["status"] == "reengajamento_ignorado" and body["reply"]["partes"] == [] and body["actions"] == []
        assert model_calls(chan) == calls and len(msgs(chan, first["thread_id"])) == antes
        with chan.as_token(SCOPE_CHANNEL_STATUS):
            t = chan.request("GET", f"/api/channels/threads/{first['thread_id']}").json()
        assert t["reengajamento_suprimido"] is True and t["reengajamento_suprimido_motivo"] == "encerrado"

    def test_after_a_lead_opt_out_no_follow_up_runs(self, on):
        """The lead-level opt-out (SW ``POST /leads/{ref}/opt-out``) ends every participation; a re-engagement is
        then ignored, and a lead message is recorded but never answered."""
        first = on.turn(turn_body("Oi", ids=["a"])).json()
        on.threads.registrar_opt_out(on.org_id, "contato-1")
        calls, antes = model_calls(on), len(msgs(on, first["thread_id"]))
        body = on.turn(self._body(texto_base="Oi, ainda procura imóvel?")).json()
        assert body["status"] == "reengajamento_ignorado" and body["reply"]["partes"] == []
        assert model_calls(on) == calls and len(msgs(on, first["thread_id"])) == antes

    @pytest.mark.parametrize("modo", ["desligado"])
    def test_it_is_ignored_when_the_agent_is_off(self, on, modo):
        on.turn(turn_body("Oi", ids=["a"]))
        on.controles.set(on.org_id, on.agent.id, modo=modo)
        calls = model_calls(on)
        body = on.turn(self._body()).json()
        assert body["status"] == "reengajamento_ignorado" and model_calls(on) == calls

    def test_it_is_ignored_for_a_paused_thread_and_for_a_lead_never_served(self, on):
        thread = on.turn(turn_body("Oi", ids=["a"])).json()["thread_id"]
        alterar_estado_humano(org_id=on.org_id, thread_id=UUID(thread), agent_id=on.agent.id, para="pausado",
                              ator_user_id=uuid4(), motivo=None, threads=on.threads)
        assert on.turn(self._body()).json()["status"] == "reengajamento_ignorado"
        nunca = turn_body(gatilho="reengajamento", lead_ref="contato-77", chat_id="nunca",
                          contexto=contexto_body(reengajamento="horas"))
        nunca["messages"] = []
        r = on.turn(nunca).json()
        assert r["status"] == "reengajamento_ignorado" and r["thread_id"] is None

    def test_a_reengagement_turn_needs_its_contexto(self, on):
        b = turn_body(gatilho="reengajamento")
        b["messages"] = []
        resp = on.turn(b)
        assert resp.status_code == 422 and resp.json()["code"] == "invalid_field"


class TestPerChatAbuseLimits:
    def test_turns_per_window_are_limited_in_data_and_the_message_is_still_stored(self, on):
        on.conformidade.definir_limites(on.org_id, on.agent.id, max_turnos_janela=2)
        for i in range(2):
            assert on.turn(turn_body(f"m{i}", ids=[f"a{i}"])).json()["status"] == "respondido"
        calls = model_calls(on)
        over = on.turn(turn_body("flood", ids=["a9"])).json()
        assert over["status"] == "limite_atingido" and over["reply"]["partes"] == [] and over["actions"] == []
        assert model_calls(on) == calls
        assert "flood" in [m.texto for m in msgs(on, over["thread_id"], "user")]
        assert on.turn(turn_body("flood", ids=["a9"])).json() == over  # replayed, not re-evaluated

    def test_the_limit_is_per_chat(self, on):
        on.conformidade.definir_limites(on.org_id, on.agent.id, max_turnos_janela=1)
        assert on.turn(turn_body("a", ids=["a"])).json()["status"] == "respondido"
        assert on.turn(turn_body("b", ids=["b"])).json()["status"] == "limite_atingido"
        assert on.turn(turn_body("c", ids=["c"], chat_id="chat-2", lead_ref="contato-2")).json()["status"] == "respondido"

    def test_daily_turns_and_daily_spend_per_chat(self, on):
        on.conformidade.definir_limites(on.org_id, on.agent.id, max_turnos_janela=100, max_turnos_dia=2)
        assert on.turn(turn_body("a", ids=["a"])).json()["status"] == "respondido"
        assert on.turn(turn_body("b", ids=["b"])).json()["status"] == "respondido"
        assert on.turn(turn_body("c", ids=["c"])).json()["status"] == "limite_atingido"

    def test_daily_spend_per_chat(self, on):
        on.conformidade.definir_limites(on.org_id, on.agent.id, max_turnos_janela=100, max_custo_dia_usd=0.002)
        on.use_provider(FakeProvider(tool_responses=[
            ChatToolsResponse(text="Quanto?", usage=LLMUsage(10, 5, 0, 0, 0.003)) for _ in range(5)]))
        assert on.turn(turn_body("a", ids=["a"])).json()["status"] == "respondido"
        assert on.turn(turn_body("b", ids=["b"])).json()["status"] == "limite_atingido"

    def test_the_defaults_come_from_the_columns_a_fresh_instance_has_a_sane_limit(self, on):
        from app.stores.conformidade import LIMITES_PADRAO

        lim = on.conformidade.limites(on.org_id, on.agent.id)
        assert lim == LIMITES_PADRAO and lim.max_turnos_janela >= 1 and lim.max_recusas_por_turno == 2

    def test_a_reengagement_turn_is_not_a_lead_flood(self, on):
        on.conformidade.definir_limites(on.org_id, on.agent.id, max_turnos_janela=1)
        on.turn(turn_body("Oi", ids=["a"]))
        b = turn_body(gatilho="reengajamento", contexto=contexto_body(reengajamento="minutos"))
        b["messages"] = []
        assert on.turn(b).json()["status"] == "respondido"


class TestSharedThreadHistory:
    """§6.3: another agent's lines, a human attendant's lines and events are labelled with the version's text rows."""

    def test_the_turn_reads_labelled_lines_for_everyone_who_is_not_the_lead_or_itself(self, on):
        thread = on.turn(turn_body("Oi", ids=["a"])).json()["thread_id"]
        tid = UUID(thread)
        outro = on.rt.studio.create_studio_agent(on.org_id, "juridico", "Jurídico", None, runtime="llm")
        on.rt.stores.messages.add(on.org_id, tid, "assistant", "Documentos ok.", agent_id=outro.id)
        on.rt.stores.messages.add(on.org_id, tid, "humano", "Já liguei para ele.", autor_user_id=uuid4())
        on.turn(turn_body("E agora?", ids=["b"]))
        sent = [(m.role, m.content) for m in on.provider.calls[-1]["messages"] if m.role != "system"]
        assert ("user", "txt:historico.rotulo_agente Jurídico Documentos ok.") in sent
        assert ("user", "txt:historico.rotulo_humano Já liguei para ele.") in sent
        assert ("assistant", "Resposta 0?") in sent  # its OWN earlier reply keeps the assistant role
        assert sent[-1] == ("user", "E agora?")


class TestTheDossierAndTheStandardPin:
    def test_what_was_recorded_is_in_the_next_turns_state_message_so_it_is_never_asked_again(self, on):
        from tests.channels.test_julia_v2_e2e import call, say, step

        on.use_provider(FakeProvider(tool_responses=[
            step(call("registrar_perfil", itens=[{"criterio": "operacao", "valor": "compra", "trecho": "Quero comprar"}])),
            say("Qual o bairro?"), say("Entendi?")]))
        on.turn(turn_body("Quero comprar", ids=["a"]))
        on.turn(turn_body("No centro", ids=["b"]))
        estado = [m.content for m in on.provider.calls[-1]["messages"] if m.role == "system"][1]
        assert '- Operacao: "compra"' in estado and "txt:contexto.rotulo_estagio:" in estado

    def test_an_agent_version_that_pins_a_standard_version_uses_exactly_that_one(self, on):
        from dataclasses import replace

        pin = on.padrao_versao_id
        studio = on.rt.studio
        v = on.version
        studio._versions[v.id] = replace(studio._versions[v.id], qualificacao_versao_id=pin)
        assert on.turn(turn_body("Oi", ids=["a"])).json()["qualificacao"]["versao"] == "imob-lead@1"

    def test_no_published_standard_is_a_typed_409_before_anything_is_stored(self, chan):
        chan.seed_agent()
        chan.padroes.__init__()  # no standard exists in this library
        resp = chan.turn()
        assert resp.status_code == 409 and resp.json()["code"] == "qualificacao_indisponivel"
        assert chan.rt.stores.conversations.list_channel(chan.org_id) == []
