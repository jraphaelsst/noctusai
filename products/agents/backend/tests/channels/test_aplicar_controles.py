"""``aplicar_controles`` -- the service the turn route calls: reads the control + thread + participant FAIL CLOSED,
decides, creates the thread, applies the implied transition with a compare-and-set. Real service over the Fake
stores (no patching of our own code)."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

from app.channels.controles import ControleIndisponivel, LeadIdentidade, aplicar_controles
from app.stores.agent_controles import FakeAgentControleStore
from app.stores.conversations import FakeConversationStore
from app.stores.messages import FakeMessageStore
from app.stores.threads import FakeThreadStore

ORG = UUID(int=1)
JULIA = UUID(int=11)
JURIDICO = UUID(int=12)
REF = {"connection_id": str(UUID(int=77)), "chat_id": "chat-1"}
LEAD = LeadIdentidade(ref="contato-1", crm_lead_id=None, contato={"nome": "Fulano", "telefone_e164": "+5511999990000"})
AGORA = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)


class World:
    def __init__(self) -> None:
        self.controles = FakeAgentControleStore()
        self.conversations = FakeConversationStore()
        self.messages = FakeMessageStore()
        self.threads = FakeThreadStore(self.conversations)

    def modo(self, modo: str, dias: int | None = None, agent: UUID = JULIA) -> None:
        self.controles.set(ORG, agent, modo=modo, dreno_inatividade_dias=dias)

    def open_thread(self, *, estado: str = "ativo", agent: UUID = JULIA, lead: bool = True):
        ref = self.threads.upsert_lead_ref(ORG, "contato-1").id if lead else None
        thread = self.conversations.create_channel(ORG, agent, "whatsapp", REF, None, lead_ref_id=ref)
        self.threads.add_participante(ORG, thread.id, agent)
        if estado != "ativo":
            self.threads.transicionar(ORG, thread.id, agent, de=["ativo"], para=estado, ator_tipo="sistema")
        return thread

    def run(self, gatilho="mensagem", **kw):
        return aplicar_controles(
            org_id=ORG, agent_id=JULIA, gatilho=gatilho, channel="whatsapp", channel_ref=REF,
            controles=self.controles, conversations=self.conversations, threads=self.threads,
            lead=kw.pop("lead", LEAD), messages=self.messages, agora=kw.pop("agora", AGORA), **kw,
        )


@pytest.fixture
def w() -> World:
    return World()


def test_a_new_lead_while_on_creates_the_thread_the_lead_ref_and_the_active_participant(w):
    w.modo("ligado")
    res = w.run(contact={"display_name": "Fulano"})
    assert res.prosseguir and res.decisao.criar_thread
    assert res.thread.tipo == "thread_lead" and res.thread.agent_id == JULIA
    assert res.lead_ref.ref_externa == "contato-1" and res.thread.lead_ref_id == res.lead_ref.id
    assert res.lead_ref.contato == LEAD.contato
    assert res.participante.estado == "ativo"
    assert [e.para for e in w.threads.list_eventos(ORG, res.thread.id)] == ["ativo"]
    assert w.conversations.find_thread(ORG, "whatsapp", REF).id == res.thread.id


def test_a_second_call_for_the_same_lead_reuses_the_thread(w):
    w.modo("ligado")
    first = w.run()
    second = w.run()
    assert second.thread.id == first.thread.id and not second.decisao.criar_thread
    assert len(w.conversations.list_channel(ORG)) == 1
    assert len(w.threads.list_participantes(ORG, first.thread.id)) == 1


@pytest.mark.parametrize("modo", ["desligado", "drenando"])
def test_a_new_lead_while_off_or_draining_is_refused_and_NOTHING_is_stored(w, modo):
    w.modo(modo)
    res = w.run()
    assert not res.prosseguir and res.thread is None and res.lead_ref is None
    assert w.conversations.list_channel(ORG) == []
    assert w.threads.get_lead_ref_by_externa(ORG, "contato-1") is None


def test_the_control_is_read_on_every_call_never_cached(w):
    w.modo("ligado")
    thread = w.run().thread
    w.modo("desligado")
    assert w.run().status == "agente_desligado"
    w.modo("ligado")
    assert w.run().status == "normal" and w.run().thread.id == thread.id


def test_off_with_an_existing_thread_says_to_append_without_replying(w):
    w.modo("desligado")
    w.open_thread()
    res = w.run()
    assert res.status == "agente_desligado" and res.decisao.persistir_inbound and res.thread is not None


def test_pausing_one_thread_leaves_the_others_answered(w):
    w.modo("ligado")
    pausada = w.open_thread(estado="pausado")
    assert w.run().status == "conversa_pausada"
    other_ref = {"connection_id": REF["connection_id"], "chat_id": "chat-2"}
    res = aplicar_controles(
        org_id=ORG, agent_id=JULIA, gatilho="mensagem", channel="whatsapp", channel_ref=other_ref,
        controles=w.controles, conversations=w.conversations, threads=w.threads, lead=LeadIdentidade(ref="contato-2"), agora=AGORA,
    )
    assert res.prosseguir and res.thread.id != pausada.id


def test_an_idle_draining_thread_is_closed_with_an_audited_transition(w):
    w.modo("drenando", dias=7)
    thread = w.open_thread()
    w.conversations._rows[thread.id]["ultima_mensagem_lead_em"] = AGORA - timedelta(days=8)
    res = w.run()
    assert (res.status, res.decisao.persistir_inbound, res.decisao.executar_llm) == ("novo_lead_recusado", True, False)
    assert res.participante.estado == "encerrado" and res.participante.saiu_em is not None
    ev = w.threads.list_eventos(ORG, thread.id)[-1]
    assert (ev.de, ev.para, ev.motivo, ev.ator_tipo) == ("ativo", "encerrado", "dreno_inativo", "sistema")
    # the lead writes again: still draining, now closed -> refused, no new transition
    again = w.run()
    assert again.status == "novo_lead_recusado" and again.participante.estado == "encerrado"
    assert len(w.threads.list_eventos(ORG, thread.id)) == 2


def test_an_ended_thread_reopens_for_a_new_message_while_on_and_the_move_is_audited(w):
    w.modo("ligado")
    thread = w.open_thread(estado="encerrado")
    w.threads._participantes[(thread.id, JULIA)] = replace(
        w.threads.get_participante(ORG, thread.id, JULIA), saiu_em=AGORA - timedelta(hours=30)
    )
    res = w.run()
    assert res.prosseguir and res.decisao.novo_ciclo and res.participante.estado == "ativo"
    ev = w.threads.list_eventos(ORG, thread.id)[-1]
    assert (ev.de, ev.para, ev.motivo) == ("encerrado", "ativo", "novo_ciclo")


def test_a_concluded_thread_is_never_reopened_by_a_message(w):
    w.modo("ligado")
    thread = w.open_thread(estado="concluido")
    res = w.run()
    assert res.status == "conversa_com_outro_responsavel" and res.participante.estado == "concluido"
    assert len(w.threads.list_eventos(ORG, thread.id)) == 2


def test_another_agent_active_in_the_thread_is_not_displaced(w):
    w.modo("ligado")
    thread = w.open_thread(agent=JURIDICO)
    res = w.run()
    assert res.status == "conversa_com_outro_agente" and res.decisao.persistir_inbound
    assert w.threads.get_participante(ORG, thread.id, JULIA) is None


def test_reengagement_runs_only_for_an_active_participant_and_never_creates_a_thread(w):
    w.modo("ligado")
    assert w.run("reengajamento").status == "reengajamento_ignorado"
    assert w.conversations.list_channel(ORG) == []
    w.open_thread()
    assert w.run("reengajamento").status == "normal"


def test_a_legacy_thread_without_a_lead_ref_is_linked_lazily_with_its_messages(w):
    w.modo("ligado")
    thread = w.open_thread(lead=False)
    w.messages.add(ORG, thread.id, "user", "oi")
    assert thread.lead_ref_id is None
    res = w.run()
    assert res.thread.lead_ref_id == res.lead_ref.id
    assert all(m.lead_ref_id == res.lead_ref.id for m in w.messages.list(ORG, thread.id))
    # a second run never moves the link
    other = w.threads.upsert_lead_ref(ORG, "outro")
    w.conversations.link_lead_ref(ORG, thread.id, other.id)
    assert w.conversations.get(ORG, thread.id).lead_ref_id == res.lead_ref.id


# ── fail closed ────────────────────────────────────────────────────────────


class _Down(Exception):
    pass


class _ThreadLookupDown(FakeConversationStore):
    def find_thread(self, *a, **k):
        raise _Down("db down")


class _ParticipantsDown(FakeThreadStore):
    def list_participantes(self, *a, **k):
        raise _Down("db down")


@pytest.mark.parametrize("boom", ["controle", "thread", "participantes"])
def test_any_failure_reading_the_control_is_503_and_stores_nothing(boom):
    world = World()
    world.modo("ligado")
    if boom == "controle":
        world.controles.falha = _Down("db down")
    elif boom == "thread":
        world.conversations = _ThreadLookupDown()
        world.threads = FakeThreadStore(world.conversations)
    else:
        world.open_thread()
        world.threads = _ParticipantsDown(world.conversations)
    with pytest.raises(ControleIndisponivel) as exc:
        world.run()
    assert exc.value.status_code == 503 and exc.value.code == "controle_indisponivel"
    http = exc.value.as_http_exception()
    assert http.status_code == 503 and http.detail["code"] == "controle_indisponivel"
    assert world.threads.get_lead_ref_by_externa(ORG, "contato-1") is None or boom == "participantes"


class _AlwaysLosesTheRace(FakeThreadStore):
    def transicionar(self, *a, **k):
        return False  # somebody else always wins the compare-and-set


def test_a_participant_that_keeps_moving_under_us_fails_closed_instead_of_looping():
    world = World()
    world.modo("ligado")
    thread = world.open_thread()
    world.threads.transicionar(ORG, thread.id, JULIA, de=["ativo"], para="encerrado", ator_tipo="sistema")
    racy = _AlwaysLosesTheRace(world.conversations)
    racy._participantes = world.threads._participantes
    world.threads = racy
    with pytest.raises(ControleIndisponivel):
        world.run()
