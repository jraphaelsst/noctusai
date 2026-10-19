"""The lead worker v2 (julia-v2 CONTRACT 5 / 8): Julia is HOSTED in agents, SW only transports.

What is pinned here, against the Fakes the seed and product ship (mock DB, `FakeWahaClient`, fakeredis, the in-memory buffer,
`FakeAgentsClient` -- nothing of ours is patched):

  * SW does not gate: `agente_pausado` is a display mirror, every batch reaches agents;
  * the STATUS TABLE -- every status agents can answer maps to exactly one outcome, and every not-served one sends nothing;
  * Q5: what a not-served turn leaves in the thread (append without reply) and what it does NOT keep (a refused lead);
  * the hand-off note rendered to its human target (the org owner by default);
  * `lead_pronto` / the computed stage fire the CRM send (Q6);
  * the re-engagement turn carries data, not a fake lead message.
"""
from __future__ import annotations

import pytest

from app.clients.agents import (
    STATUS_RESPONDEU,
    STATUS_SEM_ATENDIMENTO,
    AgentsTimeout,
    ControleIndisponivel,
    FakeAgentsClient,
    HandoffRecord,
    QualificacaoResumo,
    TurnResult,
)
from app.services import julia_envio_service as envio
from app.services import julia_lead_turn_service as turn
from app.services.julia_lead_turn_service import process_lead_batch, run_reengajamento_turn

from tests.support.julia_world import (
    ADMIN_ID,
    CONNECTION_ID,
    LEAD_CHAT,
    ORG_ID as ORG,
    OWNER_ID,
    THREAD_ID,
    World,
    buffer_lead,
)

pytestmark = pytest.mark.asyncio

USUARIO_CORRETOR = "00000000-0000-4000-8000-0000000000c1"


@pytest.fixture(autouse=True)
def _public_url(monkeypatch):
    monkeypatch.setenv("PRODUCT_URL_SOCIAL_WIRING", "https://sw.example.test")


@pytest.fixture
def world() -> World:
    w = World()
    w.seed_connection()
    w.seed_chat()
    for t in (envio.T_REGRAS, envio.T_POLITICAS, envio.T_ENTREGAS, "leads", "lead_sources", "lead_source_aliases",
              "cliente_notas", "clientes", "cliente_touches", "atendimentos",
              "julia_equipes", "julia_equipe_membros", "julia_distribuicao_cursor", "julia_atribuicoes", "ai_outputs"):
        w.sw.set_table_data(t, [])
    return w


@pytest.fixture(autouse=True)
def core_provider(world):
    envio.registrar_core_provider(lambda: world.core)
    envio.registrar_client_provider(lambda: world.sw)
    yield
    envio.registrar_core_provider(None)
    envio.registrar_client_provider(None)


async def _run(world: World, key: str, **deps_over):
    await process_lead_batch(key, world.buffer.memory_for(key), deps=world.deps(**deps_over))


def _ok(*partes: str, status: str = "respondido", actions=(), estado: str | None = "ativo", thread: str | None = THREAD_ID,
        qualificacao: QualificacaoResumo | None = None) -> TurnResult:
    return TurnResult(
        conversation_id=thread or "", thread_id=thread, partes=tuple(partes), status=status, actions=tuple(actions),
        participante_estado=estado, qualificacao=qualificacao,
    )


def _nao_atendeu(status: str, *, thread: str | None = None, estado: str | None = None) -> TurnResult:
    return TurnResult(conversation_id=thread or "", thread_id=thread, partes=(), status=status, participante_estado=estado)


def _enviou_algo(world: World) -> bool:
    return bool(world.waha.sent_messages)


# ── SW does not gate ─────────────────────────────────────────────────────────
class TestSemPortaoLocal:
    async def test_a_chat_the_mirror_says_is_paused_still_reaches_agents(self, world):
        """`agente_pausado=True` is a display mirror: agents decides, so the batch is sent to it and its answer rules."""
        world.sw.table("whatsapp_chats").update({"agente_pausado": True, "agente_estado": "pausado"}).eq("chat_id", LEAD_CHAT).execute()
        world.agents = FakeAgentsClient([_ok("Oi, voltei!")])
        await _run(world, buffer_lead(world, LEAD_CHAT, ["oi"]))
        assert len(world.agents.turns) == 1
        assert "Oi, voltei!" in world.sent_texts()

    async def test_agents_saying_paused_is_what_stops_the_reply(self, world):
        world.agents = FakeAgentsClient([_nao_atendeu("conversa_pausada", thread=THREAD_ID, estado="pausado")])
        await _run(world, buffer_lead(world, LEAD_CHAT, ["oi"]))
        assert len(world.agents.turns) == 1 and not _enviou_algo(world)

    async def test_the_turn_request_is_v2_lead_ref_gatilho_and_data_only_contexto(self, world):
        await _run(world, buffer_lead(world, LEAD_CHAT, ["oi"]))
        req = world.agents.turns[0]
        contato = world.contato()
        assert (req.lead_ref, req.gatilho) == (contato["id"], "mensagem")
        assert set(req.contexto) == {"hash", "agora", "fuso", "estado", "capacidades"}
        assert set(req.contexto["estado"]) <= {"interacao_id", "encerrado", "atendente_nome", "origem", "credito"}
        wire = req.to_wire()
        assert wire["lead"] == {"ref": contato["id"], "crm_lead_id": None}
        for gone in ("conhecimento_md", "perguntas", "acoes", "ferramentas"):
            assert gone not in wire["contexto"]

    async def test_a_foundation_failure_sends_no_turn_at_all(self, world):
        """No lead identity => agents has nothing to attach a thread to: fail closed (it used to run without contexto)."""

        class Quebrado:
            def __init__(self, inner): self._i = inner
            def table(self, n):
                if n == "julia_contatos":
                    raise RuntimeError("db down")
                return self._i.table(n)
            def __getattr__(self, k): return getattr(self._i, k)

        await _run(world, buffer_lead(world, LEAD_CHAT, ["oi"]), scoped=Quebrado(world.sw))
        assert world.agents.turns == [] and not _enviou_algo(world)


# ── the status table ─────────────────────────────────────────────────────────
class TestTabelaDeStatus:
    @pytest.mark.parametrize("status", [s for s in STATUS_SEM_ATENDIMENTO])
    async def test_every_not_served_status_sends_nothing_and_applies_nothing(self, world, status):
        # an action riding a not-served answer must still be ignored (agents never sends one; defence in depth)
        res = TurnResult(conversation_id="", thread_id=None, partes=("não devia sair",), status=status)
        world.agents = FakeAgentsClient([res])
        key = buffer_lead(world, LEAD_CHAT, ["oi"])
        await _run(world, key)
        assert not _enviou_algo(world)
        assert world.rows("julia_acoes_aplicadas") == []
        assert world.rows("whatsapp_chats", chat_id=LEAD_CHAT)[0]["agente_pausado"] is False  # no local pause invented
        assert turn.unprocessed_run(world.buffer.memory_for(key)) == []  # the run is closed: no replay loop

    @pytest.mark.parametrize("status", [s for s in STATUS_RESPONDEU if s != "silencio"])
    async def test_every_served_status_with_a_reply_sends_it(self, world, status):
        world.agents = FakeAgentsClient([_ok("Resposta.", status=status)])
        await _run(world, buffer_lead(world, LEAD_CHAT, ["oi"]))
        assert "Resposta." in world.sent_texts()

    async def test_silencio_sends_nothing_but_is_a_served_turn(self, world):
        world.agents = FakeAgentsClient([_ok(status="silencio")])
        await _run(world, buffer_lead(world, LEAD_CHAT, ["oi"]))
        assert not _enviou_algo(world)

    async def test_not_served_leaves_a_visible_event_with_the_status_only(self, world):
        world.agents = FakeAgentsClient([_nao_atendeu("agente_desligado", thread=THREAD_ID)])
        await _run(world, buffer_lead(world, LEAD_CHAT, ["oi"]))
        ev = [e for e in world.rows("julia_eventos") if e["tipo"] == "agente_nao_atendeu"]
        assert [e["payload"] for e in ev] == [{"status": "agente_desligado"}]

    async def test_the_participant_state_agents_reports_is_mirrored_on_the_chat(self, world):
        world.agents = FakeAgentsClient([_nao_atendeu("conversa_com_outro_responsavel", thread=THREAD_ID, estado="concluido")])
        await _run(world, buffer_lead(world, LEAD_CHAT, ["oi"]))
        row = world.chat_row()
        assert (row["agente_thread_id"], row["agente_estado"], row["agente_pausado"]) == (THREAD_ID, "concluido", False)

    async def test_a_served_turn_mirrors_estado_and_thread_after_the_first_bubble(self, world):
        world.agents = FakeAgentsClient([_ok("oi!", estado="ativo")])
        await _run(world, buffer_lead(world, LEAD_CHAT, ["oi"]))
        row = world.chat_row()
        assert (row["agente_thread_id"], row["agente_conversation_id"], row["agente_estado"]) == (THREAD_ID, THREAD_ID, "ativo")

    async def test_a_silent_first_turn_does_not_mirror_the_thread_so_the_disclosure_is_not_burnt(self, world):
        world.agents = FakeAgentsClient([_ok(status="silencio"), _ok("agora sim")])
        k = buffer_lead(world, LEAD_CHAT, ["..."], ids=["m1"])
        await _run(world, k)
        assert world.chat_row()["agente_thread_id"] is None
        buffer_lead(world, LEAD_CHAT, ["oi"], ids=["m2"])
        await _run(world, k)
        assert "assistente virtual" in world.sent_texts()[0]

    async def test_the_disclosure_names_the_agent_from_its_status_not_from_code(self, world):
        from app.clients.agents import AgentStatus

        world.agents = FakeAgentsClient(
            [_ok("oi!")], status=AgentStatus(agent_key="julia", nome="Bia da Casa", ativo=True, versao_ativa=1, provider="openai",
                                             model="m", llm_configurado=True))
        await _run(world, buffer_lead(world, LEAD_CHAT, ["oi"]))
        assert world.sent_texts()[0].startswith("Oi! Eu sou Bia da Casa, assistente virtual da Empresa Exemplo.")


# ── fail closed ──────────────────────────────────────────────────────────────
class TestFailClosed:
    async def test_controle_indisponivel_requeues_once_then_drops_and_never_sends(self, world):
        world.agents = FakeAgentsClient([ControleIndisponivel(code="controle_indisponivel"), ControleIndisponivel(code="controle_indisponivel")])
        key = buffer_lead(world, LEAD_CHAT, ["oi"])
        await _run(world, key)
        assert not _enviou_algo(world) and len(world.agents.turns) == 1
        # first failure: re-queued (the run stays open), the link health says why
        assert turn.unprocessed_run(world.buffer.memory_for(key)) != []
        await _run(world, key)  # the retry also fails: dropped, nothing sent
        assert not _enviou_algo(world) and len(world.agents.turns) == 2
        assert turn.unprocessed_run(world.buffer.memory_for(key)) == []

    async def test_a_timeout_sends_nothing(self, world):
        world.agents = FakeAgentsClient([AgentsTimeout()])
        await _run(world, buffer_lead(world, LEAD_CHAT, ["oi"]))
        assert not _enviou_algo(world)


# ── Q5: what a not-served turn leaves behind ─────────────────────────────────
class TestAnexarSemResponder:
    @pytest.mark.parametrize("status", ["conversa_pausada", "conversa_com_outro_responsavel", "conversa_com_outro_agente", "agente_desligado"])
    async def test_the_leads_messages_join_the_thread_when_it_exists(self, world, status):
        world.agents = FakeAgentsClient([_nao_atendeu(status, thread=THREAD_ID, estado="pausado")])
        await _run(world, buffer_lead(world, LEAD_CHAT, ["primeira", "segunda"], ids=["a1", "a2"]))
        assert [(m["thread_id"], m["role"], m["texto"], m["provider_message_id"]) for m in world.agents.appended] == [
            (THREAD_ID, "user", "primeira", "a1"), (THREAD_ID, "user", "segunda", "a2")]

    async def test_a_retry_appends_nothing_twice(self, world):
        world.agents = FakeAgentsClient([_nao_atendeu("conversa_pausada", thread=THREAD_ID), _nao_atendeu("conversa_pausada", thread=THREAD_ID)])
        key = buffer_lead(world, LEAD_CHAT, ["oi"], ids=["a1"])
        await _run(world, key)
        world.agents._replays.clear()
        await turn.process_lead_batch(key, [{"direction": "inbound", "text": "oi", "provider_message_id": "a1", "timestamp": 1}], deps=world.deps())
        assert len(world.agents.appended) == 1

    @pytest.mark.parametrize("status", ["novo_lead_recusado", "agente_desligado"])
    async def test_a_lead_agents_refused_to_serve_is_not_kept_in_sw_either(self, world, status):
        world.agents = FakeAgentsClient([_nao_atendeu(status)])  # no thread
        await _run(world, buffer_lead(world, LEAD_CHAT, ["oi"]))
        assert world.agents.appended == []
        assert world.contato() is None  # the contato SW created for this batch is erased (Q5, minimisation)
        assert world.rows("julia_interacoes") == []

    async def test_a_known_conversation_is_never_erased_by_a_refusal(self, world):
        world.agents = FakeAgentsClient([_ok("oi!"), _nao_atendeu("agente_desligado")])
        k = buffer_lead(world, LEAD_CHAT, ["oi"], ids=["m1"])
        await _run(world, k)
        buffer_lead(world, LEAD_CHAT, ["e aí"], ids=["m2"])
        await _run(world, k)
        assert world.contato() is not None

    async def test_lead_opt_out_stales_every_queued_job_and_sends_nothing(self, world):
        world.agents = FakeAgentsClient([_ok("oi!"), _nao_atendeu("lead_opt_out", thread=THREAD_ID, estado="encerrado")])
        k = buffer_lead(world, LEAD_CHAT, ["oi"], ids=["m1"])
        await _run(world, k)
        gen = world.contato()["gen"]
        buffer_lead(world, LEAD_CHAT, ["parar"], ids=["m2"])
        n = len(world.waha.sent_messages)
        await _run(world, k)
        c = world.contato()
        assert len(world.waha.sent_messages) == n and c["encerrado_at"] and c["gen"] > gen


# ── hand-off ─────────────────────────────────────────────────────────────────
def _registro(**over) -> HandoffRecord:
    base = dict(
        id="44444444-4444-4444-8444-444444444444", thread_id=THREAD_ID, de_agent_key="julia",
        para={"tipo": "humano", "user_id": OWNER_ID, "agent_key": None, "papel": None}, motivo_codigo="pedido_humano",
        resumo="Procura casa de 3 quartos na Granja Viana, quer visitar no sábado.",
        perfil={"operacao": "compra", "quartos_min": "3", "regioes": ["Granja Viana"]},
        identificacao_completa=False,
        identificacao_mascarada={"email": "a***@exemplo.com", "cpf": "***.***.***-00"},
        perguntas_abertas=("prazo de decisão",), compromissos=("ligar sábado",),
    )
    base.update(over)
    return HandoffRecord(**base)


def _handoff_notas(world: World) -> list[dict]:
    return [n for n in world.notifications() if (n.get("metadata") or {}).get("tipo") == "julia_handoff"]


def _handoff_turn(**over) -> TurnResult:
    from app.clients.agents import HandoffAction

    return TurnResult(
        conversation_id=THREAD_ID, thread_id=THREAD_ID, partes=("Vou chamar um corretor.",), status="handoff",
        actions=(HandoffAction(motivo="quer falar com uma pessoa", motivo_codigo="pedido_humano", seq=1),),
        participante_estado="pausado", **over,
    )


class TestHandoff:
    async def test_the_note_is_rendered_to_the_org_owner_by_default(self, world):
        """The connection belongs to the ADMIN, the org's owner is someone else: the owner decision (0.4) wins."""
        world.sw.table("whatsapp_connections").update({"user_id": ADMIN_ID}).eq("id", CONNECTION_ID).execute()
        world.agents = FakeAgentsClient([_handoff_turn()], handoffs=[_registro()])
        await _run(world, buffer_lead(world, LEAD_CHAT, ["quero falar com alguém"]))
        notas = _handoff_notas(world)
        assert len(notas) == 1 and str(notas[0]["user_id"]) == OWNER_ID
        msg = notas[0]["message"]
        assert "Procura casa de 3 quartos" in msg                                # the atendimento summary
        assert "operacao: compra" in msg and "Granja Viana" in msg               # the lead profile
        assert "a***@exemplo.com" in msg and "***.***.***-00" in msg             # the MASKED identity only
        assert "prazo de decisão" in msg and "ligar sábado" in msg
        assert notas[0]["metadata"]["handoff_id"] == _registro().id

    async def test_a_configured_admin_target_wins_while_still_owner_or_admin(self, world):
        world.sw.table("whatsapp_connections").update({"agente_handoff_notificar_user_id": ADMIN_ID}).eq("id", CONNECTION_ID).execute()
        world.agents = FakeAgentsClient([_handoff_turn()], handoffs=[_registro()])
        await _run(world, buffer_lead(world, LEAD_CHAT, ["humano"]))
        assert [str(n["user_id"]) for n in _handoff_notas(world)] == [ADMIN_ID]

    async def test_a_target_who_is_no_longer_admin_falls_back_to_the_owner(self, world):
        world.sw.table("whatsapp_connections").update({"agente_handoff_notificar_user_id": USUARIO_CORRETOR}).eq("id", CONNECTION_ID).execute()
        world.agents = FakeAgentsClient([_handoff_turn()], handoffs=[_registro()])
        await _run(world, buffer_lead(world, LEAD_CHAT, ["humano"]))
        assert [str(n["user_id"]) for n in _handoff_notas(world)] == [OWNER_ID]

    async def test_the_pause_is_mirrored_from_agents_not_set_locally(self, world):
        world.agents = FakeAgentsClient([_handoff_turn()], handoffs=[_registro()])
        await _run(world, buffer_lead(world, LEAD_CHAT, ["humano"]))
        row = world.chat_row()
        assert (row["agente_estado"], row["agente_pausado"]) == ("pausado", True)
        assert world.agents.participante_calls == []  # SW never PATCHed: agents set it server-side
        assert ("chat.upsert", True) in [(e, p.get("agente_pausado")) for e, p in world.bus_events() if e == "chat.upsert"]

    async def test_the_reason_is_recorded_as_the_typed_code_agents_sent(self, world):
        world.agents = FakeAgentsClient([_handoff_turn()], handoffs=[_registro()])
        await _run(world, buffer_lead(world, LEAD_CHAT, ["humano"]))
        ev = [e for e in world.rows("julia_eventos") if e["tipo"] == "handoff"]
        assert [e["payload"] for e in ev] == [{"motivo_codigo": "pedido_humano"}]

    async def test_an_unreadable_note_still_notifies_with_the_reason(self, world):
        from app.clients.agents import AgentsUpstreamError

        world.agents = FakeAgentsClient([_handoff_turn()], handoffs=[_registro()], errors={"listar_handoffs": AgentsUpstreamError()})
        await _run(world, buffer_lead(world, LEAD_CHAT, ["humano"]))
        notas = _handoff_notas(world)
        assert len(notas) == 1 and "quer falar com uma pessoa" in notas[0]["message"] and "Resumo do atendimento" not in notas[0]["message"]

    async def test_the_handoff_bumps_gen_so_queued_jobs_go_stale(self, world):
        world.agents = FakeAgentsClient([_handoff_turn()], handoffs=[_registro()])
        k = buffer_lead(world, LEAD_CHAT, ["humano"])
        await _run(world, k)
        assert world.contato()["gen"] >= 2


# ── Q6: the computed stage fires the CRM send ────────────────────────────────
def _regra(world: World, minimo: str = "qualificado") -> None:
    envio.substituir_regras(world.sw, ORG, False, [{"operacao": "ambas", "estagio_minimo": minimo}])


class TestEnvioPorEstagio:
    async def test_lead_pronto_sends_the_lead_and_mirrors_the_values(self, world):
        from app.clients.agents import JuliaAction

        _regra(world, "pronto_para_corretor")
        acao = JuliaAction(type="lead_pronto", seq=1, payload={
            "estagio": "pronto_para_corretor", "score": 78, "valores": {"operacao": "compra", "faixa_preco": "400-500k", "nome": "Ana Exemplo"},
            "imoveis_gostou": ["A123"], "intencoes_visita": ["A123"]})
        world.agents = FakeAgentsClient([_ok("Perfeito, vou te passar para um corretor.", status="concluido", actions=[acao], estado="concluido",
                                             qualificacao=QualificacaoResumo(estagio="pronto_para_corretor", score=78))])
        await _run(world, buffer_lead(world, LEAD_CHAT, ["quero visitar"]))
        c = world.contato()
        assert c["status_envio"] == "enviado" and c["lead_id"]
        assert c["operacao"] == "compra" and c["slots"] == {"faixa_preco": "400-500k"}   # written from the response
        assert len(world.rows("leads")) == 1
        assert [e["payload"] for e in world.rows("julia_eventos") if e["tipo"] == "lead_pronto"] == [
            {"estagio": "pronto_para_corretor", "score": 78, "enviado": True}]
        assert world.rows("ai_outputs")[0]["label"] == "pronto_para_corretor"

    async def test_without_a_rule_nothing_is_sent(self, world):
        from app.clients.agents import JuliaAction

        acao = JuliaAction(type="lead_pronto", seq=1, payload={"estagio": "pronto_para_corretor", "score": 78, "valores": {}})
        world.agents = FakeAgentsClient([_ok("ok", status="concluido", actions=[acao])])
        await _run(world, buffer_lead(world, LEAD_CHAT, ["x"]))
        assert world.contato()["status_envio"] == "nao_pronto" and world.rows("leads") == []

    async def test_a_computed_stage_at_the_minimum_sends_without_any_action(self, world):
        _regra(world, "qualificado")
        world.agents = FakeAgentsClient([_ok("ótimo!", qualificacao=QualificacaoResumo(estagio="qualificado", score=61))])
        await _run(world, buffer_lead(world, LEAD_CHAT, ["tenho 500 mil"]))
        assert world.contato()["status_envio"] == "enviado"

    async def test_a_stage_below_the_minimum_does_not_send(self, world):
        _regra(world, "qualificado")
        world.agents = FakeAgentsClient([_ok("ok", qualificacao=QualificacaoResumo(estagio="perfil_basico", score=30))])
        await _run(world, buffer_lead(world, LEAD_CHAT, ["oi"]))
        assert world.contato()["status_envio"] == "nao_pronto"

    async def test_beyond_the_minimum_needs_agents_stage_order(self, world):
        _regra(world, "qualificado")
        ordem = ("novo", "perfil_basico", "qualificado", "pronto_para_corretor")
        world.agents = FakeAgentsClient([_ok("ok", qualificacao=QualificacaoResumo(estagio="pronto_para_corretor", score=80, estagios=ordem))])
        await _run(world, buffer_lead(world, LEAD_CHAT, ["oi"]))
        assert world.contato()["status_envio"] == "enviado"

    async def test_beyond_the_minimum_without_the_order_never_guesses(self, world):
        _regra(world, "qualificado")
        world.agents = FakeAgentsClient([_ok("ok", qualificacao=QualificacaoResumo(estagio="pronto_para_corretor", score=80))])
        await _run(world, buffer_lead(world, LEAD_CHAT, ["oi"]))
        assert world.contato()["status_envio"] == "nao_pronto"

    async def test_a_second_turn_at_the_stage_does_not_send_twice(self, world):
        _regra(world, "qualificado")
        q = QualificacaoResumo(estagio="qualificado", score=61)
        world.agents = FakeAgentsClient([_ok("a", qualificacao=q), _ok("b", qualificacao=q)])
        k = buffer_lead(world, LEAD_CHAT, ["oi"], ids=["m1"])
        await _run(world, k)
        buffer_lead(world, LEAD_CHAT, ["mais"], ids=["m2"])
        await _run(world, k)
        assert len(world.rows("leads")) == 1 and len([e for e in world.rows("julia_eventos") if e["tipo"] == "lead_pronto"]) == 1

    async def test_a_recorded_model_value_never_comes_from_a_model_action(self, world):
        """`salvar_slots` / `definir_operacao` are retired: an agents build that still sent one gets an `acao_sem_handler` event."""
        from app.clients.agents import JuliaAction

        acao = JuliaAction(type="salvar_slots", seq=1, payload={"slots": {"orcamento": "999"}})
        world.agents = FakeAgentsClient([_ok("ok", actions=[acao])])
        await _run(world, buffer_lead(world, LEAD_CHAT, ["oi"]))
        assert (world.contato().get("slots") or {}) == {}
        assert [e["payload"]["tipo"] for e in world.rows("julia_eventos") if e["tipo"] == "acao_sem_handler"] == ["salvar_slots"]

    async def test_a_visit_intent_is_recorded_and_nothing_is_scheduled(self, world):
        from app.clients.agents import JuliaAction

        acao = JuliaAction(type="intencao_visita", seq=1, payload={"codigo": "A123", "preferencia_horario": "sábado de manhã"})
        world.agents = FakeAgentsClient([_ok("combinado!", actions=[acao])])
        await _run(world, buffer_lead(world, LEAD_CHAT, ["quero ver o A123"]))
        ev = [e for e in world.rows("julia_eventos") if e["tipo"] == "intencao_visita"]
        assert [e["payload"] for e in ev] == [{"codigo": "A123", "preferencia_horario": "sábado de manhã"}]
        assert world.rows("julia_visitas") == []


# ── mirror ───────────────────────────────────────────────────────────────────
class TestEspelhoDaQualificacao:
    async def test_values_come_from_agents_read_after_the_turn(self, world):
        from app.clients.agents import QualificacaoEstado

        contato_ref: dict = {}

        def script(req):
            contato_ref["id"] = req.lead_ref
            return _ok("anotado", qualificacao=QualificacaoResumo(estagio="perfil_basico", score=40))

        fake = FakeAgentsClient([script])
        world.agents = fake
        # the mirror reads `GET qualificacao` for the lead ref the turn carried
        class Lido(FakeAgentsClient):
            pass

        async def qualificacao(lead_ref):
            return QualificacaoEstado(lead_ref=lead_ref, estagio="perfil_basico", score=40,
                                      valores={"operacao": "aluguel", "quartos_min": 2, "caracteristicas": ["piscina", "varanda"],
                                               "animais": True, "nome": "Ana Exemplo", "email": "ana@exemplo.com"})

        fake.qualificacao = qualificacao  # the Fake's own seam: its answer for this lead
        await _run(world, buffer_lead(world, LEAD_CHAT, ["procuro apto"]))
        c = world.contato()
        assert c["operacao"] == "aluguel" and c["email"] == "ana@exemplo.com"
        assert c["slots"] == {"quartos_min": "2", "caracteristicas": "piscina, varanda", "animais": "true"}
        assert world.rows("ai_outputs")[0]["score"] == 40

    async def test_an_unreadable_qualification_keeps_the_last_mirror_and_the_reply_stays_out(self, world):
        from app.clients.agents import AgentsUpstreamError

        world.agents = FakeAgentsClient([_ok("oi", qualificacao=QualificacaoResumo(estagio="novo", score=0))],
                                        errors={"qualificacao": AgentsUpstreamError()})
        await _run(world, buffer_lead(world, LEAD_CHAT, ["oi"]))
        assert "oi" in world.sent_texts()

    async def test_the_stage_is_logged_to_ai_outputs_only_when_it_changes(self, world):
        q1 = QualificacaoResumo(estagio="perfil_basico", score=40)
        world.agents = FakeAgentsClient([_ok("a", qualificacao=q1), _ok("b", qualificacao=q1),
                                         _ok("c", qualificacao=QualificacaoResumo(estagio="qualificado", score=61))])
        k = buffer_lead(world, LEAD_CHAT, ["1"], ids=["m1"])
        await _run(world, k)
        buffer_lead(world, LEAD_CHAT, ["2"], ids=["m2"])
        await _run(world, k)
        buffer_lead(world, LEAD_CHAT, ["3"], ids=["m3"])
        await _run(world, k)
        assert [r["label"] for r in world.rows("ai_outputs")] == ["perfil_basico", "qualificado"]


# ── re-engagement ────────────────────────────────────────────────────────────
class TestReengajamento:
    async def _contato(self, world: World) -> dict:
        world.agents = FakeAgentsClient([_ok("oi!")])
        await _run(world, buffer_lead(world, LEAD_CHAT, ["oi"]))
        world.agents.turns.clear()
        world.agents._replays.clear()
        world.waha.sent_messages.clear()
        return world.contato()

    async def test_the_turn_has_no_message_and_the_flavour_is_data_in_estado(self, world):
        contato = await self._contato(world)
        world.sw.set_table_data("julia_reguas", [{"id": "r1", "org_id": ORG, "ativa": True}])  # the outbound gate (regua active)
        world.agents._script.append(_ok("Oi, ainda procura imóvel?"))
        enviou = await run_reengajamento_turn(
            world.deps(), world.record(CONNECTION_ID), LEAD_CHAT, contato,
            {"reengajamento": "regua", "reescrever": True, "texto_base": "Ainda procura imóvel?", "tentativa": 2, "regua_id": "r1"}, "regua:job1")
        assert enviou and "Oi, ainda procura imóvel?" in world.sent_texts()
        req = world.agents.turns[0]
        assert (req.gatilho, req.messages) == ("reengajamento", ())
        est = req.contexto["estado"]
        assert (est["reengajamento"], est["reescrever"], est["texto_base"], est["tentativa"]) == ("regua", True, "Ainda procura imóvel?", 2)
        assert "regua_id" not in est and "[sistema]" not in str(req.to_wire())

    async def test_reengajamento_ignorado_sends_nothing(self, world):
        contato = await self._contato(world)
        world.agents._script.append(_nao_atendeu("reengajamento_ignorado", thread=THREAD_ID, estado="pausado"))
        enviou = await run_reengajamento_turn(world.deps(), world.record(CONNECTION_ID), LEAD_CHAT, contato, {"reengajamento": "horas"}, "reeng:j2")
        assert not enviou and not world.waha.sent_messages

    async def test_an_empty_base_text_is_not_sent(self, world):
        contato = await self._contato(world)
        world.agents._script.append(_ok("oi"))
        await run_reengajamento_turn(world.deps(), world.record(CONNECTION_ID), LEAD_CHAT, contato,
                                     {"reengajamento": "minutos", "reescrever": True, "texto_base": "  "}, "reeng:j3")
        est = world.agents.turns[0].contexto["estado"]
        assert "texto_base" not in est and "reescrever" not in est


# ── an archived contato that writes again is handed back to the agent AT AGENTS ──────────────
class TestDevolvido:
    async def test_the_agent_is_resumed_in_agents_not_only_in_the_mirror(self, world):
        world.agents = FakeAgentsClient([_ok("oi!"), _ok("de volta!")])
        k = buffer_lead(world, LEAD_CHAT, ["oi"], ids=["m1"])
        await _run(world, k)
        world.agents.participantes = {key: "pausado" for key in world.agents.participantes}
        from app.services import julia_contatos_service as contatos

        contatos.atualizar_contato(world.sw, world.contato()["id"], {"arquivado": True})
        buffer_lead(world, LEAD_CHAT, ["voltei"], ids=["m2"])
        await _run(world, k)
        (call,) = world.agents.participante_calls
        assert (call["estado"], call["motivo"], call["ator_user_id"]) == ("ativo", "contato_devolvido", OWNER_ID)
        assert world.contato()["arquivado"] is False and "de volta!" in world.sent_texts()

    async def test_agents_down_never_blocks_the_turn(self, world):
        world.agents = FakeAgentsClient([_ok("oi!"), _ok("ok")], errors={"set_participante": AgentsTimeout()})
        k = buffer_lead(world, LEAD_CHAT, ["oi"], ids=["m1"])
        await _run(world, k)
        from app.services import julia_contatos_service as contatos

        contatos.atualizar_contato(world.sw, world.contato()["id"], {"arquivado": True})
        buffer_lead(world, LEAD_CHAT, ["voltei"], ids=["m2"])
        await _run(world, k)
        assert len(world.agents.turns) == 2
