"""Emergency: the thread stays open, the org is pointed at the numbers, and the participant closes after 10 minutes of
inactivity; every interaction (lead, agent, human) refreshes the timer. Fake clock -- nothing sleeps."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

from noctusai_lib.integrations.llm import FakeProvider
from noctusai_lib.testing.migrations import migration_sql

from app.channels.thread_service import MOTIVO_INATIVIDADE, MensagemEntrada, anexar_mensagens, encerrar_inativos
from app.stores.channel_inbound import FakeChannelInboundStore
from app.stores.conversations import FakeConversationStore
from app.stores.messages import FakeMessageStore
from app.stores.thread_alertas import TIPOS_ALERTA
from app.stores.threads import FakeThreadStore
from tests.channels.conftest import turn_body
from tests.channels.test_julia_v2_e2e import call, say, step, tool_results  # noqa: F401

ORG, JULIA = UUID(int=1), UUID(int=11)
T0 = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)


class Mundo:
    def __init__(self) -> None:
        self.conv = FakeConversationStore()
        self.messages = FakeMessageStore()
        self.inbound = FakeChannelInboundStore()
        self.threads = FakeThreadStore(self.conv)
        lead = self.threads.upsert_lead_ref(ORG, "c1")
        self.thread = self.conv.create_channel(
            ORG, JULIA, "whatsapp", {"connection_id": str(UUID(int=77)), "chat_id": "x"}, None, lead_ref_id=lead.id)
        self.threads.add_participante(ORG, self.thread.id, JULIA)

    def ultima_msg_em(self, quando: datetime) -> None:
        self.conv._rows[self.thread.id]["last_message_at"] = quando

    def janela(self, min_: int | None = 10) -> None:
        self.threads.definir_janela_inatividade(ORG, self.thread.id, JULIA, min_)

    def estado(self) -> str:
        return self.threads.get_participante(ORG, self.thread.id, JULIA).estado


def test_activity_at_9_minutes_moves_the_deadline():
    m = Mundo()
    m.janela()
    m.ultima_msg_em(T0)
    assert encerrar_inativos(m.threads, T0 + timedelta(minutes=9)) == 0
    m.ultima_msg_em(T0 + timedelta(minutes=9))  # an interaction at minute 9 (any actor)
    assert encerrar_inativos(m.threads, T0 + timedelta(minutes=18)) == 0
    assert m.estado() == "ativo"
    assert encerrar_inativos(m.threads, T0 + timedelta(minutes=19)) == 1


def test_a_human_message_appended_refreshes_the_timer():
    m = Mundo()
    m.janela()
    m.ultima_msg_em(T0)
    anexar_mensagens(
        org_id=ORG, thread=m.conv.get(ORG, m.thread.id),
        mensagens=[MensagemEntrada(role="humano", texto="oi", provider_message_id="h1", autor_user_id=UUID(int=900))],
        conversations=m.conv, messages=m.messages, inbound=m.inbound)
    assert m.conv.get(ORG, m.thread.id).last_message_at > T0


def test_idle_10_minutes_closes_with_exactly_one_event_and_job_twice_adds_none():
    m = Mundo()
    m.janela()
    m.ultima_msg_em(T0)
    assert encerrar_inativos(m.threads, T0 + timedelta(minutes=10)) == 1
    assert encerrar_inativos(m.threads, T0 + timedelta(minutes=11)) == 0
    assert m.estado() == "encerrado"
    fechos = [e for e in m.threads.list_eventos(ORG, m.thread.id) if e.para == "encerrado"]
    assert len(fechos) == 1
    assert (fechos[0].motivo, fechos[0].ator_tipo, fechos[0].de) == (MOTIVO_INATIVIDADE, "sistema", "ativo")


def test_no_window_never_closes_and_a_move_clears_the_window():
    m = Mundo()
    m.ultima_msg_em(T0)
    assert encerrar_inativos(m.threads, T0 + timedelta(days=3)) == 0
    m.janela()
    m.threads.transicionar(ORG, m.thread.id, JULIA, de=("ativo",), para="pausado", ator_tipo="usuario")
    m.threads.transicionar(ORG, m.thread.id, JULIA, de=("pausado",), para="ativo", ator_tipo="usuario")
    assert m.threads.get_participante(ORG, m.thread.id, JULIA).fecha_inativo_min is None
    assert encerrar_inativos(m.threads, T0 + timedelta(days=3)) == 0


def test_thread_without_messages_counts_from_creation():
    m = Mundo()
    m.janela(5)
    criado = m.conv.get(ORG, m.thread.id).created_at
    assert encerrar_inativos(m.threads, criado + timedelta(minutes=4)) == 0
    assert encerrar_inativos(m.threads, criado + timedelta(minutes=5)) == 1


class TestFerramentas:
    def test_emergency_alert_sets_the_window_and_encerrar_is_refused_until_a_human_closes(self, chan):
        chan.seed_agent()
        chan.use_provider(FakeProvider(tool_responses=[
            step(call("sinalizar_alerta", tipo="emergencia", descricao="Vazamento de gas no imovel")),
            step(call("encerrar", motivo="lead_encerrou")),
            say("Ja avisei a equipe, ligue 193 se houver risco.")]))
        r = chan.turn(turn_body("Estou sentindo cheiro de gas!")).json()
        tid = UUID(r["thread_id"])
        assert [a["tipo"] for a in r["actions"] if a["type"] == "alerta"] == ["emergencia"]
        assert chan.alertas.listar(chan.org_id, tid)[0].tipo == "emergencia"
        part = chan.threads.get_participante(chan.org_id, tid, chan.agent.id)
        assert part.fecha_inativo_min == 10 and part.estado == "ativo"
        assert tool_results(chan.provider)[-1]["codigo"] == "emergencia_aberta"
        assert not [a for a in r["actions"] if a["type"] == "encerrar"]
        # the agent's reply refreshed the clock
        assert chan.rt.stores.conversations.get(chan.org_id, tid).last_message_at is not None
        # a human can still close
        assert chan.threads.transicionar(
            chan.org_id, tid, chan.agent.id, de=("ativo",), para="encerrado", ator_tipo="usuario", ator_id=UUID(int=9))

    def test_the_leads_stop_request_is_never_refused_by_an_open_emergency(self, chan):
        chan.seed_agent()
        chan.use_provider(FakeProvider(tool_responses=[
            step(call("sinalizar_alerta", tipo="emergencia", descricao="Incendio")),
            step(call("encerrar", motivo="lead_pediu_parar", motivo_texto="Pediu para parar", trecho="PARAR")),
            say("Ok.")]))
        r = chan.turn(turn_body("PARAR")).json()
        assert [a for a in r["actions"] if a["type"] == "encerrar"]

    def test_encerrar_without_emergency_still_works(self, chan):
        chan.seed_agent()
        chan.use_provider(FakeProvider(tool_responses=[step(call("encerrar", motivo="sem_interesse")), say("Ok.")]))
        r = chan.turn(turn_body("nao quero")).json()
        assert r["status"] == "encerrado"


def test_emergencia_is_a_known_alert_tipo_and_migration_allows_it():
    assert "emergencia" in TIPOS_ALERTA
    sql = migration_sql(Path(__file__).resolve().parents[2], "emergencia_inatividade")
    assert "'emergencia'" in sql and "fecha_inativo_min" in sql and "idx_agents_thread_participantes_inatividade" in sql
    assert "IF NOT EXISTS" in sql  # idempotent


def test_the_job_is_registered_every_minute():
    import app.scheduler as scheduler
    from noctusai_lib.api import scheduler as seed_scheduler

    scheduler.configure()
    job = seed_scheduler.scheduler.get_job(scheduler.INATIVIDADE_JOB_NAME)
    assert job is not None and "minute='*'" in str(job.trigger)
