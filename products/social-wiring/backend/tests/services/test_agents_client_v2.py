"""`AgentsClient` julia-v2 (CONTRACT section 8): the turn v2 wire, every `status` of the response, the shared-thread API
(append without a turn, per-conversation pause, hand-offs, consent, controls, qualification) and the typed errors.

`HttpAgentsClient` is driven through an `httpx.MockTransport` (the HTTP seam is the external boundary; nothing of ours is
patched). The Fake is asserted to follow the same contract.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import httpx
import pytest

from app.clients.agents import (
    STATUS_RESPONDEU,
    STATUS_SEM_ATENDIMENTO,
    AgentsBadRequest,
    AgentsUpstreamError,
    ControleIndisponivel,
    FakeAgentsClient,
    HandoffAction,
    HandoffNotFound,
    HttpAgentsClient,
    JuliaAction,
    LeadSemQualificacao,
    ParticipanteNotFound,
    ThreadNotFound,
    TransicaoInvalida,
    TurnInProgress,
    TurnMessage,
    TurnRequest,
    parse_turn_result,
)

AT = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)
THREAD = "11111111-1111-4111-8111-111111111111"
LEAD = "22222222-2222-4222-8222-222222222222"
USER = "33333333-3333-4333-8333-333333333333"

pytestmark = pytest.mark.asyncio


def _client(handler) -> HttpAgentsClient:
    return HttpAgentsClient("https://agents.example.test", "pk_channel_token", transport=httpx.MockTransport(handler))


def _req(**over) -> TurnRequest:
    base = dict(
        agent_key="julia", connection_id="c1", chat_id="5511900000000@c.us", phone_e164="+5511900000000",
        display_name="Ana", messages=(TurnMessage(texto="oi", provider_message_id="m1", at=AT),),
        lead_ref=LEAD, crm_lead_id=None,
        contexto={"hash": "a" * 64, "agora": AT.isoformat(), "fuso": "America/Sao_Paulo",
                  "estado": {"interacao_id": LEAD, "encerrado": False}, "capacidades": {"ferramentas_sw": True}},
    )
    base.update(over)
    return TurnRequest(**base)


def _body(**over):
    base = {"thread_id": THREAD, "conversation_id": THREAD, "status": "respondido", "reply": {"partes": ["Oi!"]},
            "actions": [], "participante": {"agent_key": "julia", "estado": "ativo"}, "usage": {}}
    base.update(over)
    return base


# ── the v2 request ───────────────────────────────────────────────────────────
class TestTurnRequestWire:
    async def test_the_request_is_exactly_the_v2_shape(self):
        seen = []

        def handler(request):
            seen.append(json.loads(request.content))
            return httpx.Response(200, json=_body())

        await _client(handler).run_turn(_req())
        assert seen[0] == {
            "agent_key": "julia", "channel": "whatsapp",
            "channel_ref": {"connection_id": "c1", "chat_id": "5511900000000@c.us"},
            "lead": {"ref": LEAD, "crm_lead_id": None},
            "contact": {"phone_e164": "+5511900000000", "display_name": "Ana"},
            "gatilho": "mensagem",
            "messages": [{"texto": "oi", "provider_message_id": "m1", "at": AT.isoformat()}],
            "contexto": {"hash": "a" * 64, "agora": AT.isoformat(), "fuso": "America/Sao_Paulo",
                         "estado": {"interacao_id": LEAD, "encerrado": False}, "capacidades": {"ferramentas_sw": True}},
        }

    async def test_a_reengagement_turn_has_no_message_and_its_flavour_rides_in_the_contexto(self):
        seen = []

        def handler(request):
            seen.append(json.loads(request.content))
            return httpx.Response(200, json=_body())

        contexto = {"hash": "a" * 64, "agora": AT.isoformat(), "fuso": "America/Sao_Paulo", "capacidades": {"ferramentas_sw": True},
                    "estado": {"interacao_id": LEAD, "encerrado": False, "reengajamento": "regua", "reescrever": True,
                               "texto_base": "Oi, ainda procura?", "tentativa": 2}}
        await _client(handler).run_turn(_req(messages=(), gatilho="reengajamento", contexto=contexto))
        wire = seen[0]
        assert wire["gatilho"] == "reengajamento" and wire["messages"] == []
        assert "reengajamento" not in {k for k in wire if k != "gatilho"}  # no top-level object: it is `contexto.estado`
        assert wire["contexto"]["estado"]["texto_base"] == "Oi, ainda procura?"

    async def test_no_prompt_text_rides_in_the_request(self):
        """Data only: the keys of the wire are the closed set, and no key the old contexto carried is present."""
        seen = []
        await _client(lambda r: (seen.append(json.loads(r.content)), httpx.Response(200, json=_body()))[1]).run_turn(_req())
        flat = json.dumps(seen[0])
        for gone in ('"conhecimento_md"', '"perguntas"', '"ferramentas"', '"acoes"', '"regra_padrao"', "[sistema]"):
            assert gone not in flat

    async def test_lead_key_is_omitted_without_a_lead_ref(self):
        seen = []
        await _client(lambda r: (seen.append(json.loads(r.content)), httpx.Response(200, json=_body()))[1]).run_turn(
            _req(lead_ref=None))
        assert "lead" not in seen[0]


# ── every status of the response ─────────────────────────────────────────────
class TestTurnResponse:
    @pytest.mark.parametrize("status", STATUS_RESPONDEU)
    async def test_served_statuses_parse_with_the_thread_and_participant(self, status):
        r = await _client(lambda _r: httpx.Response(200, json=_body(status=status))).run_turn(_req())
        assert (r.status, r.thread, r.participante_estado, r.atendeu) == (status, THREAD, "ativo", True)
        assert r.partes == ("Oi!",)

    @pytest.mark.parametrize("status", STATUS_SEM_ATENDIMENTO)
    async def test_not_served_statuses_parse_without_a_reply_or_a_thread(self, status):
        body = {"status": status}
        r = await _client(lambda _r: httpx.Response(200, json=body)).run_turn(_req())
        assert r.status == status and not r.atendeu
        assert r.partes == () and r.actions == () and r.thread is None

    async def test_an_unknown_status_is_an_upstream_fault_not_a_guess(self):
        with pytest.raises(AgentsUpstreamError):
            await _client(lambda _r: httpx.Response(200, json=_body(status="vai_que_funciona"))).run_turn(_req())

    async def test_a_served_status_without_a_reply_is_malformed(self):
        with pytest.raises(AgentsUpstreamError):
            parse_turn_result({"status": "respondido", "thread_id": THREAD})

    async def test_handoff_keeps_the_typed_reason_code(self):
        body = _body(status="handoff", actions=[{"seq": 1, "type": "handoff", "motivo_codigo": "pedido_humano", "motivo": "quer falar com alguém"}])
        r = await _client(lambda _r: httpx.Response(200, json=body)).run_turn(_req())
        assert r.handoff == HandoffAction(motivo="quer falar com alguém", motivo_codigo="pedido_humano", seq=1)

    async def test_lead_pronto_and_intencao_visita_are_ordinary_actions_in_seq_order(self):
        body = _body(status="concluido", actions=[
            {"seq": 2, "type": "intencao_visita", "codigo": "A123", "preferencia_horario": "sábado"},
            {"seq": 1, "type": "lead_pronto", "estagio": "pronto_para_corretor", "score": 78, "valores": {"operacao": "compra"},
             "imoveis_gostou": ["A123"], "intencoes_visita": ["A123"]},
        ])
        r = await _client(lambda _r: httpx.Response(200, json=body)).run_turn(_req())
        assert [a.type for a in r.julia_actions] == ["lead_pronto", "intencao_visita"]
        assert r.julia_actions[0].payload["estagio"] == "pronto_para_corretor"
        assert isinstance(r.julia_actions[1], JuliaAction)

    async def test_qualificacao_and_conformidade_are_parsed(self):
        body = _body(
            qualificacao={"versao": "imob-lead@3", "estagio": "qualificado", "score": 61, "faltando": ["prazo_decisao"],
                          "estagios": ["novo", "qualificado", "pronto_para_corretor"]},
            conformidade={"violacoes": [{"regra": "termina_sem_pergunta", "politica": "registrar"}]},
        )
        r = await _client(lambda _r: httpx.Response(200, json=body)).run_turn(_req())
        q = r.qualificacao
        assert (q.versao, q.estagio, q.score, q.faltando, q.estagios) == (
            "imob-lead@3", "qualificado", 61, ("prazo_decisao",), ("novo", "qualificado", "pronto_para_corretor"))
        assert r.conformidade == ({"regra": "termina_sem_pergunta", "politica": "registrar"},)

    async def test_a_malformed_action_logs_the_kind_only_never_its_content(self, caplog):
        """audit H4 (minor): the old `%r` of a bad action could carry a lead's slot values into the log line."""
        secret = "CPF-123.456.789-00-do-lead"
        with caplog.at_level(logging.WARNING, logger="app.clients.agents"):
            r = parse_turn_result(_body(actions=[secret, {"seq": 1}, {"type": "encerrar", "motivo": "outro"}]))
        assert [a.type for a in r.julia_actions] == ["encerrar"]
        text = "\n".join(rec.getMessage() for rec in caplog.records)
        assert "malformed action" in text and secret not in text and "kind=str" in text


# ── the error table ──────────────────────────────────────────────────────────
class TestErrors:
    @pytest.mark.parametrize("status,detail,exc", [
        (503, {"detail": "x", "code": "controle_indisponivel"}, ControleIndisponivel),
        (409, {"detail": "x", "code": "turn_in_progress"}, TurnInProgress),
        (422, {"detail": "x", "code": "invalid_field"}, AgentsBadRequest),
    ])
    async def test_turn_errors_are_typed(self, status, detail, exc):
        with pytest.raises(exc):
            await _client(lambda _r: httpx.Response(status, json={"detail": detail})).run_turn(_req())

    async def test_a_503_that_is_not_the_control_is_a_plain_upstream_fault(self):
        with pytest.raises(AgentsUpstreamError) as e:
            await _client(lambda _r: httpx.Response(503, json={"detail": {"detail": "x", "code": "other"}})).run_turn(_req())
        assert not isinstance(e.value, ControleIndisponivel)


# ── the shared thread ────────────────────────────────────────────────────────
HANDOFF = {
    "id": "44444444-4444-4444-8444-444444444444", "thread_id": THREAD, "lead_ref": LEAD, "de_agent_key": "julia",
    "para": {"tipo": "humano", "user_id": USER, "agent_key": None, "papel": None}, "motivo_codigo": "pedido_humano",
    "resumo": "Procura 3 quartos na Granja Viana.", "perfil": {"operacao": "compra", "quartos_min": "3"},
    "identificacao_completa": False, "identificacao_mascarada": {"email": "a***@x.com", "cpf": "***.***.***-00"},
    "perguntas_abertas": ["prazo"], "compromissos": [], "created_at": "2026-10-19T12:00:00Z", "aceito_em": None, "aceito_por": None,
}
THREAD_BODY = {
    "thread_id": THREAD, "channel": "whatsapp", "lead_ref": LEAD,
    "participantes": [{"agent_key": "julia", "agent_nome": "Julia", "estado": "pausado", "entrou_em": "2026-10-19T10:00:00Z",
                       "saiu_em": None, "motivo": "toggle", "ultimo_turno_em": None, "pausado_ate": None}],
    "ultimo_turno_em": None, "ultima_mensagem_lead_em": "2026-10-19T11:00:00Z", "criado_em": "2026-10-19T10:00:00Z",
    "reengajamento_suprimido": True, "reengajamento_suprimido_motivo": "pausado", "ultimo_handoff": HANDOFF,
}


class TestThreadApi:
    async def test_get_thread_by_channel_ref_and_by_id(self):
        seen = []

        def handler(request):
            seen.append((request.method, request.url.path, dict(request.url.params)))
            return httpx.Response(200, json=THREAD_BODY)

        c = _client(handler)
        info = await c.buscar_thread(connection_id="c1", chat_id="chat")
        assert seen[0] == ("GET", "/api/channels/threads", {"channel": "whatsapp", "connection_id": "c1", "chat_id": "chat"})
        assert info.estado_de("julia") == "pausado" and info.reengajamento_suprimido and info.ultimo_handoff.id == HANDOFF["id"]
        await c.obter_thread(THREAD)
        assert seen[1][:2] == ("GET", f"/api/channels/threads/{THREAD}")
        await c.buscar_thread(lead_ref=LEAD)
        assert seen[2][2] == {"lead_ref": LEAD}

    async def test_thread_not_found_reads_as_none_for_the_lookup_and_raises_for_the_id(self):
        def handler(_r):
            return httpx.Response(404, json={"detail": {"detail": "x", "code": "thread_not_found"}})

        c = _client(handler)
        assert await c.buscar_thread(connection_id="c1", chat_id="chat") is None
        with pytest.raises(ThreadNotFound):
            await c.obter_thread(THREAD)

    async def test_the_lookup_needs_exactly_one_identity(self):
        c = _client(lambda _r: httpx.Response(200, json=THREAD_BODY))
        with pytest.raises(ValueError):
            await c.buscar_thread()
        with pytest.raises(ValueError):
            await c.buscar_thread(connection_id="c1", chat_id="x", lead_ref=LEAD)

    async def test_append_without_a_turn(self):
        seen = []

        def handler(request):
            seen.append((request.method, request.url.path, json.loads(request.content)))
            return httpx.Response(200, json={"message_id": "mm", "duplicado": False})

        out = await _client(handler).anexar_mensagem(
            THREAD, role="humano", texto="Já te ligo", provider_message_id="p1", at=AT, autor_user_id=USER)
        assert out.message_id == "mm" and not out.duplicado
        assert seen[0] == ("POST", f"/api/channels/threads/{THREAD}/mensagens", {
            "role": "humano", "texto": "Já te ligo", "provider_message_id": "p1", "at": AT.isoformat(), "autor_user_id": USER})

    async def test_append_reads_the_idempotent_replay(self):
        out = await _client(lambda _r: httpx.Response(200, json={"message_id": None, "duplicado": True})).anexar_mensagem(
            THREAD, role="user", texto="oi", provider_message_id="p1")
        assert out.duplicado and out.message_id is None

    async def test_append_rejects_a_role_outside_the_contract(self):
        with pytest.raises(ValueError):
            await _client(lambda _r: httpx.Response(200, json={})).anexar_mensagem(
                THREAD, role="assistant", texto="x", provider_message_id="p")

    async def test_pause_and_resume_one_conversation(self):
        seen = []

        def handler(request):
            seen.append((request.method, request.url.path, json.loads(request.content)))
            return httpx.Response(200, json={"agent_key": "julia", "agent_nome": "Julia", "estado": "pausado",
                                             "entrou_em": "2026-10-19T10:00:00Z", "saiu_em": None, "motivo": "toggle_sw",
                                             "ultimo_turno_em": None, "pausado_ate": None})

        p = await _client(handler).set_participante(THREAD, "julia", estado="pausado", ator_user_id=USER, motivo="toggle_sw")
        assert p.estado == "pausado"
        assert seen[0] == ("PATCH", f"/api/channels/threads/{THREAD}/participantes/julia",
                           {"estado": "pausado", "ator_user_id": USER, "motivo": "toggle_sw"})

    @pytest.mark.parametrize("status,code,exc", [
        (404, "participante_not_found", ParticipanteNotFound),
        (409, "transicao_invalida", TransicaoInvalida),
        (409, "outro_agente_ativo", TransicaoInvalida),
    ])
    async def test_participant_errors_are_typed(self, status, code, exc):
        with pytest.raises(exc):
            await _client(lambda _r: httpx.Response(status, json={"detail": {"detail": "x", "code": code}})).set_participante(
                THREAD, "julia", estado="ativo", ator_user_id=USER)

    async def test_handoffs_list_get_and_accept(self):
        seen = []

        def handler(request):
            seen.append((request.method, request.url.path))
            if request.url.path.endswith("/handoffs"):
                return httpx.Response(200, json=[HANDOFF])
            return httpx.Response(200, json=HANDOFF)

        c = _client(handler)
        lst = await c.listar_handoffs(THREAD)
        assert len(lst) == 1 and lst[0].identificacao_mascarada["cpf"] == "***.***.***-00" and lst[0].resumo.startswith("Procura")
        assert (await c.obter_handoff(HANDOFF["id"])).motivo_codigo == "pedido_humano"
        await c.aceitar_handoff(HANDOFF["id"], USER)
        assert seen == [("GET", f"/api/channels/threads/{THREAD}/handoffs"), ("GET", f"/api/channels/handoffs/{HANDOFF['id']}"),
                        ("POST", f"/api/channels/handoffs/{HANDOFF['id']}/aceite")]

    async def test_handoff_not_found(self):
        with pytest.raises(HandoffNotFound):
            await _client(lambda _r: httpx.Response(404, json={"detail": {"detail": "x", "code": "handoff_not_found"}})).obter_handoff("x")

    async def test_opt_in_and_opt_out(self):
        seen = []

        def handler(request):
            seen.append((request.method, request.url.path, json.loads(request.content or b"{}")))
            return httpx.Response(200, json={"lead_ref": LEAD, "opt_in_em": None, "opt_in_origem": None, "opt_out_em": "2026-10-19T12:00:00Z",
                                             "opt_out_ativo": True, "participantes_encerrados": 1})

        c = _client(handler)
        await c.opt_in(LEAD, origem="lead_iniciou")
        out = await c.opt_out(LEAD)
        assert out.opt_out_ativo and out.participantes_encerrados == 1
        assert seen[0] == ("PUT", f"/api/channels/leads/{LEAD}/opt-in", {"origem": "lead_iniciou"})
        assert seen[1][:2] == ("POST", f"/api/channels/leads/{LEAD}/opt-out")

    async def test_opt_out_forwards_who_and_why_and_returns_the_event_id(self):
        seen = []

        def handler(request):
            seen.append(json.loads(request.content or b"{}"))
            return httpx.Response(200, json={"lead_ref": LEAD, "opt_out_em": "2026-10-21T12:00:00Z", "opt_out_ativo": True,
                                             "participantes_encerrados": 2, "evento_id": "ev-1"})

        c = _client(handler)
        out = await c.opt_out(LEAD, origem="operador", motivo="Pediu por telefone", mensagem_lead="parar",
                              ator_user_id="00000000-0000-4000-8000-000000000042")
        assert out.evento_id == "ev-1"
        assert seen[0] == {"origem": "operador", "motivo": "Pediu por telefone", "mensagem_lead": "parar",
                           "ator_user_id": "00000000-0000-4000-8000-000000000042"}
        await c.opt_out(LEAD)  # no operator: the integration default is sent, the optional fields are not
        assert seen[1] == {"origem": "integracao"}

    async def test_opt_out_refuses_what_agents_would_422(self):
        c = _client(lambda _r: httpx.Response(200, json={"lead_ref": LEAD}))
        with pytest.raises(ValueError, match="origem"):
            await c.opt_out(LEAD, origem="sistema")
        with pytest.raises(ValueError, match="motivo"):
            await c.opt_out(LEAD, motivo="x" * 501)
        with pytest.raises(ValueError, match="mensagem_lead"):
            await c.opt_out(LEAD, mensagem_lead="x" * 1001)

    async def test_the_fake_validates_like_the_real_one_and_reports_the_consent_state(self):
        from app.clients.agents import FakeAgentsClient

        f = FakeAgentsClient()
        assert await f.consentimento(LEAD) is None  # never seen = never opted out
        out = await f.opt_out(LEAD, origem="agente", motivo="m")
        assert out.opt_out_ativo and out.evento_id
        assert f.opt_out_calls[0]["origem"] == "agente" and f.opt_out_calls[0]["motivo"] == "m"
        assert (await f.consentimento(LEAD)).opt_out_ativo is True
        with pytest.raises(ValueError):
            await f.opt_out(LEAD, origem="sistema")
        await f.opt_in(LEAD, origem="formulario_meta")  # a later opt-in lifts it
        c = await f.consentimento(LEAD)
        assert c.opt_out_ativo is False and c.opt_in_origem == "formulario_meta"

    async def test_consentimento_reads_the_lead_level_state_and_maps_404_lead_desconhecido_to_none(self):
        from app.clients.agents import AgentsUpstreamError

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.method == "GET" and request.url.path.endswith("/consentimento")
            if LEAD in request.url.path:
                return httpx.Response(200, json={
                    "lead_ref": LEAD, "opt_in_em": None, "opt_in_origem": None, "opt_out_em": "2026-10-21T12:00:00Z",
                    "opt_out_ativo": True, "opt_out_evento": {"id": "ev-1", "origem": "agente"}})
            if "desconhecido" in request.url.path:
                return httpx.Response(404, json={"detail": {"detail": "x", "code": "lead_desconhecido"}})
            return httpx.Response(500, json={})

        c = _client(handler)
        out = await c.consentimento(LEAD)
        assert out.opt_out_ativo and out.evento_id == "ev-1"
        assert await c.consentimento("desconhecido") is None
        with pytest.raises(AgentsUpstreamError):
            await c.consentimento("outro")

    async def test_delete_lead_is_a_204_delete(self):
        seen = []
        await _client(lambda r: (seen.append((r.method, r.url.path)), httpx.Response(204))[1]).apagar_lead(LEAD)
        assert seen == [("DELETE", f"/api/channels/leads/{LEAD}")]

    async def test_delete_lead_in_progress_is_typed(self):
        with pytest.raises(TurnInProgress):
            await _client(lambda _r: httpx.Response(409, json={"detail": {"detail": "x", "code": "turn_in_progress"}})).apagar_lead(LEAD)

    async def test_controle_is_read_only(self):
        body = {"agent_key": "julia", "modo": "drenando", "aceita_novos_leads": False, "dreno_inatividade_dias": 7,
                "threads_abertas": 4, "drenagem": {"abertas": 4, "ociosas": 1, "efetivas": 3, "concluida": False,
                                                    "idade_max_dias": 6, "idades_dias": [6, 2]}}
        seen = []
        c = await _client(lambda r: (seen.append((r.method, r.url.path)), httpx.Response(200, json=body))[1]).controle("julia")
        assert (c.modo, c.aceita_novos_leads, c.threads_abertas, c.drenagem["efetivas"]) == ("drenando", False, 4, 3)
        assert seen == [("GET", "/api/channels/agents/julia/controle")]

    async def test_qualificacao_and_identificacao_and_their_404s(self):
        body = {"lead_ref": LEAD, "versao_id": "v", "estagio": "qualificado", "regra_id": "r", "score": 61, "scores": {"prontidao": 30},
                "valores": {"operacao": "compra"}, "faltando": ["prazo_decisao"], "pode_ofertar": True, "pode_concluir": False,
                "hash": "h", "eventos_imovel": [{"codigo": "A1", "evento": "gostou"}]}

        def handler(request):
            if request.url.path.endswith("/qualificacao"):
                return httpx.Response(200, json=body)
            return httpx.Response(200, json={"email": "a***@x.com"})

        c = _client(handler)
        q = await c.qualificacao(LEAD)
        assert (q.estagio, q.score, q.valores, q.pode_ofertar, q.eventos_imovel[0]["codigo"]) == ("qualificado", 61, {"operacao": "compra"}, True, "A1")
        assert await c.identificacao_mascarada(LEAD) == {"email": "a***@x.com"}

        vazio = _client(lambda _r: httpx.Response(404, json={"detail": {"detail": "x", "code": "lead_sem_qualificacao"}}))
        assert await vazio.qualificacao(LEAD) is None and await vazio.identificacao_mascarada(LEAD) is None

    async def test_a_non_404_qualificacao_error_still_raises(self):
        with pytest.raises(AgentsUpstreamError):
            await _client(lambda _r: httpx.Response(500, json={})).qualificacao(LEAD)

    async def test_the_lead_sem_qualificacao_error_is_exported(self):
        assert issubclass(LeadSemQualificacao, Exception)

    async def test_resumo_is_the_thread_route_and_narrative_only(self):
        from app.clients.agents import ResumoRequest

        seen = []

        def handler(request):
            seen.append((request.url.path, json.loads(request.content)))
            return httpx.Response(200, json={"resumo": "Resumo.", "desfecho_sugerido": "qualificado"})

        out = await _client(handler).resumo(THREAD, ResumoRequest(desde=AT))
        assert seen == [(f"/api/channels/threads/{THREAD}/resumo", {"desde": AT.isoformat()})]
        assert (out.resumo, out.desfecho, out.slots, out.intencoes) == ("Resumo.", "qualificado", {}, ())

    async def test_decisao_sends_options_and_data_only_no_rule(self):
        from app.clients.agents import DecisaoRequest

        seen = []

        def handler(request):
            seen.append(json.loads(request.content))
            return httpx.Response(200, json={"escolha": "neutra", "motivo": "sem codigo", "regra": "padrao_da_versao"})

        out = await _client(handler).decidir("julia", "abordagem-meta", DecisaoRequest(opcoes=("comercial", "neutra"), dados={"codigo_imovel": None}))
        assert seen == [{"opcoes": ["comercial", "neutra"], "dados": {"codigo_imovel": None}}]
        assert (out.escolha, out.regra) == ("neutra", "padrao_da_versao")

    async def test_message_feedback(self):
        seen = []
        await _client(lambda r: (seen.append((r.url.path, json.loads(r.content))), httpx.Response(204))[1]).feedback_mensagem(
            "mid", nota="like", user_id=USER)
        assert seen == [("/api/channels/messages/mid/feedback", {"nota": "like", "user_id": USER, "origem": "sw"})]


# ── the Fake follows the same contract ───────────────────────────────────────
class TestFake:
    async def test_the_default_reply_is_a_served_turn_with_a_thread(self):
        fake = FakeAgentsClient()
        r = await fake.run_turn(_req())
        assert r.status == "respondido" and r.thread == r.conversation_id and r.participante_estado == "ativo"
        info = await fake.buscar_thread(connection_id="c1", chat_id="5511900000000@c.us")
        assert info is not None and info.estado_de("julia") == "ativo"

    async def test_pause_resume_append_and_idempotency(self):
        fake = FakeAgentsClient()
        r = await fake.run_turn(_req())
        await fake.set_participante(r.thread, "julia", estado="pausado", ator_user_id=USER)
        assert (await fake.obter_thread(r.thread)).estado_de("julia") == "pausado"
        a = await fake.anexar_mensagem(r.thread, role="user", texto="oi", provider_message_id="p9")
        b = await fake.anexar_mensagem(r.thread, role="user", texto="oi", provider_message_id="p9")
        assert not a.duplicado and b.duplicado and len(fake.appended) == 1

    async def test_a_human_message_needs_an_author_like_agents(self):
        fake = FakeAgentsClient()
        r = await fake.run_turn(_req())
        with pytest.raises(AgentsBadRequest):
            await fake.anexar_mensagem(r.thread, role="humano", texto="oi", provider_message_id="p1")

    async def test_pausing_a_non_participant_or_a_concluded_one_is_refused(self):
        fake = FakeAgentsClient()
        with pytest.raises(ParticipanteNotFound):
            await fake.set_participante(THREAD, "julia", estado="pausado", ator_user_id=USER)
        r = await fake.run_turn(_req())
        fake.participantes[(r.thread, "julia")] = "concluido"
        with pytest.raises(TransicaoInvalida):
            await fake.set_participante(r.thread, "julia", estado="ativo", ator_user_id=USER)

    async def test_error_injection_per_method(self):
        fake = FakeAgentsClient(errors={"anexar_mensagem": ControleIndisponivel()})
        with pytest.raises(ControleIndisponivel):
            await fake.anexar_mensagem(THREAD, role="user", texto="x", provider_message_id="p")
