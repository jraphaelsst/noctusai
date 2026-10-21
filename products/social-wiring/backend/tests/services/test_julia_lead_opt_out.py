"""A lead who asked to stop is never contacted again, by any SW path that sends to a lead (owner decision 2026-10-21).

Agents holds the lead-level opt-out (who/why/notification are its). SW's duties: (1) never send to that lead -- every
direct send re-reads agents' consent state and refuses, recording why (`envio_bloqueado` event + log); an unreadable
state refuses too (fail-closed); (2) when agents reports the lead asked to stop in a turn (`encerrar` +
`lead_pediu_parar` / `lead_opt_out: true`), stop SW-side follow-ups and never call opt-out a second time.
Seams: `FakeAgentsClient` + the mock DB of `tests.support.julia_world`; nothing of ours is patched."""
from __future__ import annotations

import asyncio
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from noctusai_lib.domain.jobs import FakeJobRepository

from app.clients.agents import AgentsUpstreamError, FakeAgentsClient, JuliaAction, TurnResult
from app.services import julia_acoes_service as acoes
from app.services import julia_avaliacoes_service as av
from app.services import julia_disparos_service as disparos
from app.services import julia_envio_gate as gate
from app.services import julia_reengajamento_service as reeng
from app.services import julia_visitas_service as visitas

from tests.services.test_julia_envio_gate import (  # noqa: F401  (fixtures + helpers of the gate suite)
    MANHA, _Turnos, _contato_que_interagiu, eventos, lead_world, opt_in_everything, world,
)
from tests.support.julia_world import CONNECTION_ID, LEAD_CHAT, ORG_ID, World, buffer_lead

CONV = "22222222-2222-4222-8222-222222222222"


@pytest.fixture(autouse=True)
def _public_url(monkeypatch):
    monkeypatch.setenv("PRODUCT_URL_SOCIAL_WIRING", "https://sw.example.test")  # the privacy disclosure's link


def _com_opt_out(w: World, contato: dict) -> str:
    """The lead has a thread in agents and asked to stop there."""
    ref = str(contato["id"])
    w.agents.seed_lead_thread(ref)
    asyncio.run(w.agents.opt_out(ref, origem="agente", motivo="lead_pediu_parar"))
    return ref


def _bloqueios(w: World) -> list[dict]:
    return [e["payload"] for e in eventos(w)]


def _pedido(w: World):
    from app.services import julia_contatos_service as contatos

    w.sw.table(av.T_CONFIG).insert({"org_id": ORG_ID, "google_review_url": "https://g.page/r/x/review"}).execute()
    c = _contato_que_interagiu(w)
    contatos.atualizar_contato(w.sw, c["id"], {"ultimo_inbound_at": (MANHA - timedelta(hours=1)).isoformat(), "telefone_e164": "+5511988887777"})
    c = w.contato()
    inter = w.sw.table("julia_interacoes").insert({
        "id": str(uuid4()), "org_id": ORG_ID, "contato_id": c["id"], "iniciada_at": MANHA.isoformat(),
        "encerrada_at": MANHA.isoformat(), "desfecho": "qualificado", "tipo": "comercial", "slots": {}, "intencoes": [],
    }).execute().data[0]
    job = SimpleNamespace(id="j1", type=av.JOB_PEDIR, payload={"org_id": ORG_ID, "contato_id": c["id"], "interacao_id": inter["id"], "gen": c["gen"]})
    return c, job


class TestReviewAsk:
    def test_an_opted_out_lead_is_never_asked_for_a_review_and_the_refusal_is_recorded(self, lead_world):
        w = lead_world
        c, job = _pedido(w)
        _com_opt_out(w, c)
        enviados: list = []

        async def enviar(contato, texto, liberacao):
            enviados.append(texto)

        assert asyncio.run(av.executar_pedido(job, client=w.sw, enviar=enviar, agora=MANHA, agents=w.agents)) == "bloqueado:lead_opt_out"
        assert enviados == []
        assert _bloqueios(w) == [{"fluxo": "avaliacao", "motivo": "lead_opt_out", "connection_id": CONNECTION_ID}]

    def test_a_lead_without_opt_out_is_asked(self, lead_world):
        w = lead_world
        c, job = _pedido(w)
        w.agents.seed_lead_thread(str(c["id"]))
        enviados: list = []

        async def enviar(contato, texto, liberacao):
            enviados.append(texto)

        assert asyncio.run(av.executar_pedido(job, client=w.sw, enviar=enviar, agora=MANHA, agents=w.agents)) == "enviado"
        assert len(enviados) == 1

    @pytest.mark.parametrize("agents", [None, FakeAgentsClient(errors={"buscar_thread": AgentsUpstreamError("down")})])
    def test_an_unreadable_consent_state_refuses_instead_of_assuming_consent(self, lead_world, agents):
        w = lead_world
        c, job = _pedido(w)
        enviados: list = []

        async def enviar(contato, texto, liberacao):
            enviados.append(texto)

        assert asyncio.run(av.executar_pedido(job, client=w.sw, enviar=enviar, agora=MANHA, agents=agents)) == "bloqueado:opt_out_nao_verificavel"
        assert enviados == []
        assert _bloqueios(w)[0]["motivo"] == "opt_out_nao_verificavel"


class TestReengagement:
    def test_the_hours_tier_refuses_an_opted_out_lead_and_stops_the_chain(self, lead_world):
        w = lead_world
        reeng.salvar_config(w.sw, ORG_ID, {"minutos_ativo": True})
        c = _contato_que_interagiu(w)
        repo = FakeJobRepository()
        asyncio.run(reeng.agendar_apos_outbound(w.sw, repo, ORG_ID, c, agora=MANHA))
        (job,) = list(repo._jobs.values())
        c = w.contato()
        gen_antes = int(c["gen"])  # the mock DB hands out its stored row: read the number now
        _com_opt_out(w, c)
        turnos = _Turnos()
        out = asyncio.run(reeng.executar_default(job, deps=w.deps(), repo=repo, run_turn=turnos, agora=MANHA))
        assert out == "bloqueado:lead_opt_out" and turnos.chamadas == []
        assert _bloqueios(w)[0] == {"fluxo": "reengajamento_minutos", "motivo": "lead_opt_out", "connection_id": CONNECTION_ID}
        after = w.contato()
        assert after["encerrado_at"] and after["gen"] == gen_antes + 1  # every queued job of the contato is stale now
        assert asyncio.run(reeng.executar_default(job, deps=w.deps(), repo=repo, run_turn=turnos, agora=MANHA)) == "obsoleto"

    def test_a_regua_attempt_refuses_an_opted_out_lead(self, lead_world):
        w = lead_world
        c = _contato_que_interagiu(w)
        r = reeng.criar_regua(w.sw, ORG_ID, nome="R", compra=True, aluguel=True)
        reeng.criar_tentativa(w.sw, ORG_ID, r["id"], {"ordem": 1, "espera_valor": 1, "espera_unidade": "dias", "texto": "Oi"})
        reeng.ativar_regua(w.sw, ORG_ID, r["id"])
        repo = FakeJobRepository()
        asyncio.run(reeng._enfileirar_tentativa(repo, w.sw, ORG_ID, c, reeng.obter_regua(w.sw, ORG_ID, r["id"]),
                                                reeng.obter_regua(w.sw, ORG_ID, r["id"])["tentativas"][0], base=MANHA))
        (job,) = list(repo._jobs.values())
        _com_opt_out(w, c)
        turnos = _Turnos()
        out = asyncio.run(reeng.executar_tentativa(job, deps=w.deps(), repo=repo, run_turn=turnos, agora=MANHA))
        assert out == "bloqueado:lead_opt_out" and turnos.chamadas == []
        assert w.sent_texts() == []

    def test_with_no_agents_client_the_send_is_refused_not_assumed_fine(self, lead_world):
        w = lead_world
        reeng.salvar_config(w.sw, ORG_ID, {"horas_ativo": True})
        c = _contato_que_interagiu(w)
        repo = FakeJobRepository()
        asyncio.run(reeng.agendar_apos_outbound(w.sw, repo, ORG_ID, c, agora=MANHA))
        (job,) = [j for j in repo._jobs.values() if j.type == reeng.JOB_HORAS]
        turnos = _Turnos()
        out = asyncio.run(reeng.executar_default(job, deps=w.deps(agents_client_factory=lambda org_id: None), repo=repo, run_turn=turnos, agora=MANHA))
        assert out == "bloqueado:opt_out_nao_verificavel" and turnos.chamadas == []


class TestDirectSends:
    def test_the_meta_first_contact_refuses_an_opted_out_lead(self, lead_world):
        w = lead_world
        opt_in_everything(w)
        c = _contato_que_interagiu(w)
        _com_opt_out(w, c)
        conn = SimpleNamespace(id=CONNECTION_ID)
        r = asyncio.run(disparos.primeiro_contato_meta(
            w.sw, ORG_ID, connection=conn, transporte=None, telefone="+5511988887777", nome="Ana", abordagem="neutra",
            contato_id=c["id"], agents=w.agents))
        assert r == {"enviado": False, "motivo": "lead_opt_out"}
        assert _bloqueios(w)[-1]["fluxo"] == "primeiro_contato"

    def test_the_meta_first_contact_without_a_readable_state_is_refused(self, lead_world):
        w = lead_world
        opt_in_everything(w)
        c = _contato_que_interagiu(w)
        r = asyncio.run(disparos.primeiro_contato_meta(
            w.sw, ORG_ID, connection=SimpleNamespace(id=CONNECTION_ID), transporte=None, telefone="+5511988887777",
            nome="Ana", abordagem="neutra", contato_id=c["id"], agents=None))
        assert r == {"enviado": False, "motivo": "opt_out_nao_verificavel"}

    def test_a_disparo_skips_an_opted_out_lead_target_and_records_why(self, lead_world):
        w = lead_world
        c = _contato_que_interagiu(w)
        _com_opt_out(w, c)

        class Spy:
            chamadas: list = []

            async def enviar_template(self, *a, **k):
                self.chamadas.append(a)
                return {}

        spy = Spy()
        alvo = {"contato_id": c["id"], "proprietario_id": None, "telefone": "5511988887777"}
        patch = asyncio.run(disparos._enviar_um(
            w.sw, ORG_ID, {"id": "d1"}, {"nome": "m", "corpo": "oi"}, [], alvo, spy, {}, MANHA, w.agents))
        assert patch == {"status": "erro", "erro": "lead_opt_out"} and spy.chamadas == []
        assert _bloqueios(w)[-1] == {"fluxo": "disparo", "motivo": "lead_opt_out", "connection_id": None}

    def test_a_visit_notice_is_not_sent_to_an_opted_out_lead(self, lead_world):
        w = lead_world
        c = _contato_que_interagiu(w)
        _com_opt_out(w, c)
        enviados: list = []
        waha = SimpleNamespace(send_text=lambda *a: enviados.append(a))
        store = SimpleNamespace(get_connection=lambda **kw: SimpleNamespace(base_url=None, api_key=None, session_name=None))
        ok = asyncio.run(visitas.avisar_lead(
            w.sw, ORG_ID, {"id": "v1", "contato_id": c["id"]}, "Visita confirmada", store=store,
            waha_factory=lambda **kw: waha, agents=w.agents))
        assert ok is False and enviados == []
        assert _bloqueios(w)[-1]["fluxo"] == "aviso_visita" and _bloqueios(w)[-1]["motivo"] == "lead_opt_out"


@pytest.mark.asyncio
class TestAgentsRecordedTheOptOut:
    async def test_an_encerrar_pediu_parar_stops_follow_ups_records_it_and_never_calls_opt_out_again(self, world):
        from app.services.julia_lead_turn_service import process_lead_batch

        world.seed_chat()
        world.agents = FakeAgentsClient([TurnResult(
            conversation_id=CONV, partes=("Tudo bem, não vou mais te escrever.",), status="encerrado",
            actions=(JuliaAction("encerrar", 1, {"motivo": "lead_pediu_parar", "lead_opt_out": True}),))])
        k = buffer_lead(world, LEAD_CHAT, ["pare de me mandar mensagem"], ids=["m1"])
        await process_lead_batch(k, world.buffer.memory_for(k), deps=world.deps())
        c = world.contato()
        assert c["encerrado_at"]  # gen bumped: every queued job of the lead is stale
        assert world.agents.opt_outs == [] and world.agents.opt_out_calls == []  # agents already recorded it
        (ev,) = [e for e in world.rows("julia_eventos") if e["tipo"] == "lead_opt_out"]
        assert ev["payload"]["origem"] == "agente" and ev["payload"]["motivo"] == "lead_pediu_parar"
        assert world.notifications() == []  # agents notifies the admins; SW sends no second notification

    async def test_the_flag_alone_is_enough_and_the_motive_is_normalised(self, world):
        from app.services.julia_lead_turn_service import process_lead_batch

        world.seed_chat()
        world.agents = FakeAgentsClient([TurnResult(
            conversation_id=CONV, partes=(), status="encerrado",
            actions=(JuliaAction("encerrar", 1, {"motivo": "sem_interesse", "lead_opt_out": True}),))])
        k = buffer_lead(world, LEAD_CHAT, ["chega"], ids=["m1"])
        await process_lead_batch(k, world.buffer.memory_for(k), deps=world.deps())
        (ev,) = [e for e in world.rows("julia_eventos") if e["tipo"] == "lead_opt_out"]
        assert ev["payload"]["motivo"] == "lead_pediu_parar" and world.agents.opt_out_calls == []

    async def test_an_ordinary_encerrar_leaves_no_opt_out_record(self, world):
        from app.services.julia_lead_turn_service import process_lead_batch

        world.seed_chat()
        world.agents = FakeAgentsClient([TurnResult(
            conversation_id=CONV, partes=("Até logo!",), status="encerrado",
            actions=(JuliaAction("encerrar", 1, {"motivo": "lead_encerrou"}),))])
        k = buffer_lead(world, LEAD_CHAT, ["tchau"], ids=["m1"])
        await process_lead_batch(k, world.buffer.memory_for(k), deps=world.deps())
        assert [e for e in world.rows("julia_eventos") if e["tipo"] == "lead_opt_out"] == []
        assert "lead_pediu_parar" in acoes.MOTIVOS_ENCERRAR
