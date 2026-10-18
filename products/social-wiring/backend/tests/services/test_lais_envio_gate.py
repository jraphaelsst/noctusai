"""The Lais outbound gate (`lais_envio_gate`): two gates per flow, refuse-not-null, defaults off.

Gate 1 = `whatsapp_connections.agente_leads_ativo`, read from the DB at send time; gate 2 = the org's opt-in for
the flow. Every opt-in defaults off (Python defaults AND the migration DEFAULTs) and no migration seeds an org row.
A refusal raises `EnvioBloqueado` and leaves an `envio_bloqueado` event -- it is never a silent skip.
Seams: the mock DB of `tests.support.lais_world`; nothing of ours is patched."""
from __future__ import annotations

import asyncio
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from noctusai_lib.api.scheduler import SCHEDULERS_ENABLED_ENV
from noctusai_lib.testing.migrations import migration_sql

from app.services import lais_avaliacoes_service as av
from app.services import lais_envio_gate as gate
from app.services import lais_reengajamento_service as reeng
from app.services import lais_reengajamento_worker as worker

from tests.support.lais_world import CONNECTION_ID, LEAD_CHAT, ORG_ID, OTHER_ORG_ID, World

Fluxo = gate.Fluxo
MIGRATIONS = Path(__file__).resolve().parents[2] / "migrations"
CONTATO_ID = "00000000-0000-4000-8000-00000000c0c0"
# 2026-10-15 10:00 Sao Paulo: inside every business-hours window.
MANHA = datetime(2026, 10, 15, 13, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _public_url(monkeypatch):
    monkeypatch.setenv("PRODUCT_URL_SOCIAL_WIRING", "https://sw.example.test")  # the privacy disclosure's link


@pytest.fixture
def world() -> World:
    w = World()
    w.seed_connection()
    for t in (gate.T_REENGAJAMENTO_CONFIG, gate.T_REGUAS, gate.T_MODELOS, gate.T_AVALIACOES_CONFIG):
        w.sw.set_table_data(t, [])
    return w


def julia_off(world: World) -> None:
    world.sw.table("whatsapp_connections").update({"agente_leads_ativo": False}).eq("id", CONNECTION_ID).execute()


def opt_in_everything(world: World) -> str:
    """Every flow's opt-in on; returns the active regua id."""
    world.sw.table(gate.T_REENGAJAMENTO_CONFIG).insert({"org_id": ORG_ID, "minutos_ativo": True, "horas_ativo": True}).execute()
    world.sw.table(gate.T_AVALIACOES_CONFIG).insert({"org_id": ORG_ID, "google_review_url": "https://g.page/r/x/review"}).execute()
    world.sw.table(gate.T_MODELOS).insert({"org_id": ORG_ID, "categoria": "primeiro_contato", "status": "aprovado", "nome": "Abordagem neutra"}).execute()
    regua = world.sw.table(gate.T_REGUAS).insert({"org_id": ORG_ID, "nome": "R1", "ativa": True}).execute().data[0]
    return str(regua["id"])


def eventos(world: World) -> list[dict]:
    return [e for e in world.rows("lais_eventos") if e["tipo"] == gate.EVENTO_BLOQUEADO]


# ── gate 2 defaults: a fresh org with Julia on is still blocked on every automatic flow ──────────
class TestDefaultsOff:
    @pytest.mark.parametrize("fluxo,motivo", [
        (Fluxo.REENGAJAMENTO_MINUTOS, "reengajamento_desativado"),
        (Fluxo.REENGAJAMENTO_HORAS, "reengajamento_desativado"),
        (Fluxo.REGUA, "regua_inativa"),
        (Fluxo.PRIMEIRO_CONTATO, "modelo_nao_aprovado"),
        (Fluxo.AVALIACAO, "sem_link"),
    ])
    def test_a_fresh_org_has_every_automatic_flow_off(self, world, fluxo, motivo):
        assert gate.motivo_do_bloqueio(world.sw, ORG_ID, CONNECTION_ID, fluxo) == motivo

    def test_a_reply_needs_only_julia_on(self, world):
        assert gate.motivo_do_bloqueio(world.sw, ORG_ID, CONNECTION_ID, Fluxo.RESPOSTA) is None

    def test_python_defaults_are_off(self):
        assert reeng.CONFIG_PADRAO["minutos_ativo"] is False and reeng.CONFIG_PADRAO["horas_ativo"] is False
        assert av.CONFIG_PADRAO["google_review_url"] is None

    @pytest.mark.parametrize("arquivo,coluna,default", [
        ("lais_agente_roteamento", "agente_leads_ativo", "false"),
        ("lais_reengajamento", "minutos_ativo", "false"),
        ("lais_reengajamento", "horas_ativo", "false"),
        ("lais_cloud", "status", "'rascunho'"),
    ])
    def test_migration_defaults_are_off(self, arquivo, coluna, default):
        sql = migration_sql(MIGRATIONS, arquivo)
        assert re.search(rf"\b{coluna}\b\s+(boolean|text)\s+NOT NULL DEFAULT {default}", sql), (arquivo, coluna)

    def test_a_new_regua_is_inactive_and_the_review_link_has_no_default(self):
        reguas = migration_sql(MIGRATIONS, "lais_reengajamento")
        bloco = reguas[reguas.index("lais_reguas ("):]
        assert re.search(r"\bativa\s+boolean\s+NOT NULL DEFAULT false", bloco[: bloco.index(");")])
        avaliacao = migration_sql(MIGRATIONS, "lais_avaliacoes_capi")
        assert re.search(r"google_review_url\s+text\s*,", avaliacao)

    def test_no_lais_migration_seeds_an_opt_in_row(self):
        alvos = ("whatsapp_connections", gate.T_REENGAJAMENTO_CONFIG, gate.T_REGUAS, gate.T_MODELOS, gate.T_AVALIACOES_CONFIG)
        for path in sorted(MIGRATIONS.glob("*.sql")):
            sql = path.read_text()
            for tabela in alvos:
                assert not re.search(rf"INSERT\s+INTO\s+(social_wiring\.)?{tabela}\b", sql, re.I), (path.name, tabela)
                assert not re.search(rf"UPDATE\s+(social_wiring\.)?{tabela}\s+SET\s+[^;]*\b(agente_leads_ativo|minutos_ativo|horas_ativo|ativa)\s*=\s*true", sql, re.I), (path.name, tabela)


# ── gate 1: Julia on for THIS line, read at send time ────────────────────────────────────────────
class TestJuliaGate:
    @pytest.mark.parametrize("fluxo", list(Fluxo))
    def test_julia_off_blocks_every_flow_even_when_opted_in(self, world, fluxo):
        regua_id = opt_in_everything(world)
        assert gate.motivo_do_bloqueio(world.sw, ORG_ID, CONNECTION_ID, fluxo, regua_id=regua_id) is None
        julia_off(world)
        assert gate.motivo_do_bloqueio(world.sw, ORG_ID, CONNECTION_ID, fluxo, regua_id=regua_id) == "julia_desligada"

    def test_a_line_of_another_org_or_no_line_is_sem_conexao(self, world):
        assert gate.motivo_do_bloqueio(world.sw, OTHER_ORG_ID, CONNECTION_ID, Fluxo.RESPOSTA) == "sem_conexao"
        assert gate.motivo_do_bloqueio(world.sw, ORG_ID, None, Fluxo.RESPOSTA) == "sem_conexao"

    def test_an_inactive_regua_blocks_only_that_regua(self, world):
        regua_id = opt_in_everything(world)
        outra = world.sw.table(gate.T_REGUAS).insert({"org_id": ORG_ID, "nome": "R2", "ativa": False}).execute().data[0]
        assert gate.motivo_do_bloqueio(world.sw, ORG_ID, CONNECTION_ID, Fluxo.REGUA, regua_id=regua_id) is None
        assert gate.motivo_do_bloqueio(world.sw, ORG_ID, CONNECTION_ID, Fluxo.REGUA, regua_id=outra["id"]) == "regua_inativa"
        assert gate.motivo_do_bloqueio(world.sw, ORG_ID, CONNECTION_ID, Fluxo.REGUA) == "regua_inativa"


# ── refuse-not-null ──────────────────────────────────────────────────────────────────────────────
class TestRefuseNotNull:
    def test_a_refusal_raises_and_leaves_an_event(self, world):
        julia_off(world)
        with pytest.raises(gate.EnvioBloqueado) as exc:
            gate.exigir(world.sw, ORG_ID, CONNECTION_ID, Fluxo.AVALIACAO, contato_id=CONTATO_ID)
        assert exc.value.motivo == "julia_desligada" and exc.value.fluxo is Fluxo.AVALIACAO
        (e,) = eventos(world)
        assert e["contato_id"] == CONTATO_ID
        assert e["payload"] == {"fluxo": "avaliacao", "motivo": "julia_desligada", "connection_id": CONNECTION_ID}

    def test_a_pass_returns_a_liberacao_for_that_line_and_writes_nothing(self, world):
        lib = gate.exigir(world.sw, ORG_ID, CONNECTION_ID, Fluxo.RESPOSTA)
        assert (lib.org_id, lib.connection_id, lib.fluxo) == (ORG_ID, CONNECTION_ID, Fluxo.RESPOSTA)
        assert eventos(world) == []

    def test_conferir_refuses_anything_but_a_liberacao_for_the_same_line(self, world):
        lib = gate.exigir(world.sw, ORG_ID, CONNECTION_ID, Fluxo.RESPOSTA)
        assert gate.conferir(lib, CONNECTION_ID) is lib
        with pytest.raises(gate.EnvioBloqueado, match="sem_liberacao"):
            gate.conferir(None, CONNECTION_ID)
        with pytest.raises(gate.EnvioBloqueado, match="sem_liberacao"):
            gate.conferir(SimpleNamespace(connection_id=CONNECTION_ID), CONNECTION_ID)
        with pytest.raises(gate.EnvioBloqueado, match="liberacao_de_outra_conexao"):
            gate.conferir(lib, "00000000-0000-4000-8000-0000000000ff")


# ── the worker that sends on its own starts only in the deployed container ────────────────────────
class TestWorkerNeedsTheDeployMarker:
    def test_without_the_marker_the_worker_does_not_start(self, monkeypatch):
        monkeypatch.delenv(SCHEDULERS_ENABLED_ENV, raising=False)
        cfg = SimpleNamespace(lais_reengajamento_worker_enabled=True)
        assert asyncio.run(worker.start_worker(cfg, repo=object())) is False
        assert not worker.is_running()

    def test_the_kill_switch_still_wins_with_the_marker(self, monkeypatch):
        monkeypatch.setenv(SCHEDULERS_ENABLED_ENV, "1")
        cfg = SimpleNamespace(lais_reengajamento_worker_enabled=False)
        assert asyncio.run(worker.start_worker(cfg, repo=object())) is False
        assert not worker.is_running()

    def test_with_the_marker_it_starts(self, monkeypatch):
        from noctusai_lib.domain.jobs import FakeJobRepository

        monkeypatch.setenv(SCHEDULERS_ENABLED_ENV, "1")

        async def ciclo() -> bool:
            iniciou = await worker.start_worker(World().cfg, repo=FakeJobRepository())
            rodando = worker.is_running()
            await worker.stop_worker()
            return iniciou and rodando

        assert asyncio.run(ciclo()) is True
        assert not worker.is_running()


# ── every automatic sender goes through the gate (flow level, real services) ─────────────────────
class _Turnos:
    def __init__(self):
        self.chamadas: list = []

    async def __call__(self, deps, connection, chat_id, contato, estado_extra, marker_id) -> bool:
        self.chamadas.append(estado_extra)
        return True


def _contato_que_interagiu(world: World) -> dict:
    from app.services import lais_contatos_service as contatos

    c = contatos.obter_ou_criar_contato(world.sw, org_id=ORG_ID, connection_id=CONNECTION_ID, chat_id=LEAD_CHAT)
    contatos.registrar_inbound(world.sw, c)
    return world.contato()


@pytest.fixture
def lead_world(world: World) -> World:
    world.seed_chat()
    world.sw.set_table_data(reeng.T_TENTATIVAS, [])
    for t in (av.T_PEDIDOS, av.T_FEEDBACK):
        world.sw.set_table_data(t, [])
    return world


class TestEveryFlowGoesThroughTheGate:
    def test_a_tier_switched_off_after_enqueue_never_reaches_the_turn(self, lead_world):
        from noctusai_lib.domain.jobs import FakeJobRepository

        w = lead_world
        reeng.salvar_config(w.sw, ORG_ID, {"minutos_ativo": True})
        c = _contato_que_interagiu(w)
        repo = FakeJobRepository()
        asyncio.run(reeng.agendar_apos_outbound(w.sw, repo, ORG_ID, c, agora=MANHA))
        reeng.salvar_config(w.sw, ORG_ID, {"minutos_ativo": False})
        turnos = _Turnos()
        (job,) = list(repo._jobs.values())
        out = asyncio.run(reeng.executar_default(job, deps=w.deps(), repo=repo, run_turn=turnos, agora=MANHA))
        assert out == "bloqueado:reengajamento_desativado" and turnos.chamadas == []
        assert eventos(w)[0]["payload"]["fluxo"] == "reengajamento_minutos"

    def test_the_turn_itself_refuses_to_send_when_the_tier_is_off(self, lead_world):
        from app.services.lais_lead_turn_service import run_reengajamento_turn

        w = lead_world
        c = _contato_que_interagiu(w)
        conn = w.record(UUID(CONNECTION_ID))
        enviou = asyncio.run(run_reengajamento_turn(w.deps(), conn, LEAD_CHAT, c, {"reengajamento": "horas"}, "m-1"))
        assert enviou is False and w.sent_texts() == []
        (e,) = eventos(w)
        assert e["payload"] == {"fluxo": "reengajamento_horas", "motivo": "reengajamento_desativado", "connection_id": CONNECTION_ID}

    def test_a_regua_turn_is_gated_on_its_own_regua_and_the_id_never_reaches_agents(self, lead_world):
        from app.services.lais_lead_turn_service import run_reengajamento_turn

        w = lead_world
        c = _contato_que_interagiu(w)
        conn = w.record(UUID(CONNECTION_ID))
        inativa = w.sw.table(gate.T_REGUAS).insert({"org_id": ORG_ID, "nome": "R", "ativa": False}).execute().data[0]
        estado = {"reengajamento": "regua", "reescrever": True, "texto_base": "Oi", "tentativa": 1, "regua_id": str(inativa["id"])}
        assert asyncio.run(run_reengajamento_turn(w.deps(), conn, LEAD_CHAT, c, estado, "m-2")) is False
        assert w.sent_texts() == [] and "regua_id" not in w.agents.turns[-1].contexto["estado"]
        w.sw.table(gate.T_REGUAS).update({"ativa": True}).eq("id", inativa["id"]).execute()
        assert asyncio.run(run_reengajamento_turn(w.deps(), conn, LEAD_CHAT, c, estado, "m-3")) is True
        assert w.sent_texts()

    def test_an_unknown_tier_is_a_loud_error(self, lead_world):
        from app.services.lais_lead_turn_service import run_reengajamento_turn

        w = lead_world
        with pytest.raises(ValueError, match="tier"):
            asyncio.run(run_reengajamento_turn(w.deps(), w.record(UUID(CONNECTION_ID)), LEAD_CHAT, {}, {}, "m-4"))

    def test_the_review_ask_stops_when_julia_is_switched_off_after_it_was_queued(self, lead_world):
        """The gap the gate closed: the review-ask job re-checked the review rule at fire time, never Julia."""
        from app.services import lais_contatos_service as contatos

        w = lead_world
        w.sw.table(av.T_CONFIG).insert({"org_id": ORG_ID, "google_review_url": "https://g.page/r/x/review"}).execute()
        c = _contato_que_interagiu(w)
        contatos.atualizar_contato(w.sw, c["id"], {"ultimo_inbound_at": (MANHA - timedelta(hours=1)).isoformat(), "telefone_e164": "+5511988887777"})
        c = w.contato()
        inter = w.sw.table("lais_interacoes").insert({
            "id": str(uuid4()), "org_id": ORG_ID, "contato_id": c["id"], "iniciada_at": MANHA.isoformat(),
            "encerrada_at": MANHA.isoformat(), "desfecho": "qualificado", "tipo": "comercial", "slots": {}, "intencoes": [],
        }).execute().data[0]
        job = SimpleNamespace(id="j1", type=av.JOB_PEDIR, payload={"org_id": ORG_ID, "contato_id": c["id"], "interacao_id": inter["id"], "gen": c["gen"]})
        enviados: list = []

        async def enviar(contato, texto, liberacao):
            enviados.append((texto, liberacao))

        julia_off(w)
        assert asyncio.run(av.executar_pedido(job, client=w.sw, enviar=enviar, agora=MANHA)) == "bloqueado:julia_desligada"
        assert enviados == [] and w.rows(av.T_PEDIDOS) == []
        w.sw.table("whatsapp_connections").update({"agente_leads_ativo": True}).eq("id", CONNECTION_ID).execute()
        assert asyncio.run(av.executar_pedido(job, client=w.sw, enviar=enviar, agora=MANHA)) == "enviado"
        assert enviados[0][1].fluxo is Fluxo.AVALIACAO

    def test_the_review_sender_refuses_without_a_liberacao(self, lead_world):
        w = lead_world
        c = _contato_que_interagiu(w)
        enviar = av.enviador_padrao(w.record, lambda **kw: w.waha)
        with pytest.raises(gate.EnvioBloqueado):
            asyncio.run(enviar(c, "oi", None))
        assert w.sent_texts() == []

    def test_the_meta_first_contact_is_gated(self, lead_world):
        from app.services import lais_disparos_service as disparos

        w = lead_world
        conn = SimpleNamespace(id=CONNECTION_ID)
        r = asyncio.run(disparos.primeiro_contato_meta(w.sw, ORG_ID, connection=conn, transporte=None, telefone="+5511988887777",
                                                       nome="Ana", abordagem="neutra"))
        assert r == {"enviado": False, "motivo": "modelo_nao_aprovado"}
        julia_off(w)
        r = asyncio.run(disparos.primeiro_contato_meta(w.sw, ORG_ID, connection=conn, transporte=None, telefone="+5511988887777",
                                                       nome="Ana", abordagem="neutra"))
        assert r == {"enviado": False, "motivo": "julia_desligada"}
        assert [e["payload"]["fluxo"] for e in eventos(w)] == ["primeiro_contato", "primeiro_contato"]
