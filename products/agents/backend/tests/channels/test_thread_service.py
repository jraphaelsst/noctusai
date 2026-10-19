"""The thread service: append without a turn (idempotent), human pause/resume, delete-by-lead, drain progress.
Real service over the Fake stores."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from app.channels.retention import FakeChannelRetention
from app.channels.thread_service import (
    IdempotencyConflict,
    MensagemEntrada,
    TransicaoInvalida,
    alterar_estado_humano,
    anexar_mensagens,
    apagar_lead,
    progresso_dreno,
)
from app.stores.channel_inbound import FakeChannelInboundStore
from app.stores.conversations import FakeConversationStore
from app.stores.errors import NotFound, TurnInProgress
from app.stores.messages import FakeMessageStore
from app.stores.threads import FakeThreadStore, OutroAgenteAtivo, ThreadAberto

ORG, OTHER_ORG = UUID(int=1), UUID(int=2)
JULIA, JURIDICO = UUID(int=11), UUID(int=12)
USER = UUID(int=900)
REF = {"connection_id": str(UUID(int=77)), "chat_id": "chat-1"}
AGORA = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)


class World:
    def __init__(self) -> None:
        self.conversations = FakeConversationStore()
        self.messages = FakeMessageStore()
        self.inbound = FakeChannelInboundStore()
        self.threads = FakeThreadStore(self.conversations)
        self.retention = FakeChannelRetention(self.conversations, self.messages, self.inbound, self.threads)

    def thread(self, ref="contato-1", chat="chat-1", agent=JULIA, org=ORG):
        lead = self.threads.upsert_lead_ref(org, ref)
        t = self.conversations.create_channel(
            org, agent, "whatsapp", {**REF, "chat_id": chat}, None, lead_ref_id=lead.id
        )
        self.threads.add_participante(org, t.id, agent)
        return t

    def append(self, thread, *msgs):
        return anexar_mensagens(
            org_id=thread.org_id, thread=thread, mensagens=list(msgs),
            conversations=self.conversations, messages=self.messages, inbound=self.inbound,
        )


@pytest.fixture
def w() -> World:
    return World()


# ── append without a turn ──────────────────────────────────────────────────


def test_a_lead_message_is_appended_with_the_lead_and_stamps_the_drain_clock(w):
    t = w.thread()
    res = w.append(t, MensagemEntrada("oi, tem apartamento?", "wamid.1"))
    [m] = res.novas
    assert (m.role, m.texto, m.lead_ref_id, m.agent_id) == ("user", "oi, tem apartamento?", t.lead_ref_id, None)
    after = w.conversations.get(ORG, t.id)
    assert after.ultima_mensagem_lead_em is not None and after.last_message_at is not None


def test_a_human_message_carries_its_author_and_does_not_stamp_the_lead_clock(w):
    t = w.thread()
    res = w.append(t, MensagemEntrada("Sou o corretor, já te ligo.", "wamid.h1", role="humano", autor_user_id=USER))
    assert res.novas[0].role == "humano" and res.novas[0].autor_user_id == USER
    after = w.conversations.get(ORG, t.id)
    assert after.ultima_mensagem_lead_em is None and after.last_message_at is not None


def test_a_human_message_without_an_author_is_refused(w):
    with pytest.raises(ValueError):
        w.append(w.thread(), MensagemEntrada("x", "wamid.h", role="humano"))


def test_a_retried_provider_message_id_appends_nothing(w):
    t = w.thread()
    w.append(t, MensagemEntrada("oi", "wamid.1"))
    again = w.append(t, MensagemEntrada("oi", "wamid.1"))
    assert again.novas == [] and again.duplicadas == ["wamid.1"]
    assert len(w.messages.list(ORG, t.id)) == 1


def test_the_same_id_with_other_text_is_an_idempotency_conflict(w):
    t = w.thread()
    w.append(t, MensagemEntrada("oi", "wamid.1"))
    with pytest.raises(IdempotencyConflict):
        w.append(t, MensagemEntrada("outro texto", "wamid.1"))


def test_the_same_id_in_another_thread_is_an_idempotency_conflict(w):
    a, b = w.thread(), w.thread(ref="contato-2", chat="chat-2")
    w.append(a, MensagemEntrada("oi", "wamid.1"))
    with pytest.raises(IdempotencyConflict):
        w.append(b, MensagemEntrada("oi", "wamid.1"))


# ── pause / resume ─────────────────────────────────────────────────────────


def _toggle(w, thread, para, **kw):
    return alterar_estado_humano(
        org_id=ORG, thread_id=thread.id, agent_id=kw.pop("agent", JULIA), para=para,
        ator_user_id=USER, motivo=kw.pop("motivo", None), threads=w.threads,
    )


def test_pause_then_resume_records_the_actor_each_time(w):
    t = w.thread()
    assert _toggle(w, t, "pausado", motivo="assumi").estado == "pausado"
    assert _toggle(w, t, "ativo").estado == "ativo"
    ev = w.threads.list_eventos(ORG, t.id)
    assert [(e.de, e.para, e.ator_tipo, e.ator_id) for e in ev[1:]] == [
        ("ativo", "pausado", "usuario", USER), ("pausado", "ativo", "usuario", USER),
    ]
    assert ev[1].motivo == "assumi"


def test_pausing_an_already_paused_thread_is_a_no_op_with_no_new_event(w):
    t = w.thread()
    _toggle(w, t, "pausado")
    n = len(w.threads.list_eventos(ORG, t.id))
    assert _toggle(w, t, "pausado").estado == "pausado"
    assert len(w.threads.list_eventos(ORG, t.id)) == n


def test_a_person_can_resume_an_ended_thread_but_never_a_concluded_or_transferred_one(w):
    t = w.thread()
    w.threads.transicionar(ORG, t.id, JULIA, de=["ativo"], para="encerrado", ator_tipo="sistema")
    assert _toggle(w, t, "ativo").estado == "ativo"
    for estado in ("concluido", "transferido"):
        w.threads.transicionar(ORG, t.id, JULIA, de=["ativo"], para=estado, ator_tipo="agente")
        with pytest.raises(TransicaoInvalida):
            _toggle(w, t, "ativo")
        w.threads._participantes[(t.id, JULIA)] = replace(w.threads.get_participante(ORG, t.id, JULIA), estado="ativo")


def test_you_cannot_pause_what_is_not_active(w):
    t = w.thread()
    w.threads.transicionar(ORG, t.id, JULIA, de=["ativo"], para="concluido", ator_tipo="agente")
    with pytest.raises(TransicaoInvalida):
        _toggle(w, t, "pausado")


def test_an_agent_that_does_not_take_part_has_nothing_to_pause(w):
    with pytest.raises(NotFound):
        _toggle(w, w.thread(), "pausado", agent=JURIDICO)


def test_resuming_while_another_agent_is_active_is_refused(w):
    t = w.thread()
    _toggle(w, t, "pausado")
    w.threads.add_participante(ORG, t.id, JURIDICO)
    with pytest.raises(OutroAgenteAtivo):
        _toggle(w, t, "ativo")
    assert w.threads.get_participante(ORG, t.id, JULIA).estado == "pausado"


def test_a_participant_of_another_org_cannot_be_moved(w):
    t = w.thread()
    with pytest.raises(NotFound):
        alterar_estado_humano(org_id=OTHER_ORG, thread_id=t.id, agent_id=JULIA, para="pausado",
                              ator_user_id=USER, motivo=None, threads=w.threads)


# ── LGPD: delete by lead ───────────────────────────────────────────────────


def test_delete_by_lead_erases_every_thread_of_every_agent_and_the_lead_ref(w):
    a = w.thread(chat="chat-1")
    b = w.thread(chat="chat-2")
    w.threads.transicionar(ORG, a.id, JULIA, de=["ativo"], para="concluido", ator_tipo="agente")
    w.threads.add_participante(ORG, a.id, JURIDICO)  # a second agent took the thread over
    w.append(a, MensagemEntrada("oi", "wamid.1"))
    w.append(b, MensagemEntrada("oi", "wamid.2"))
    w.messages.add(ORG, a.id, "assistant", "do outro agente", agent_id=JURIDICO)
    keep = w.thread(ref="contato-2", chat="chat-9")
    w.append(keep, MensagemEntrada("sou outro lead", "wamid.9"))

    assert apagar_lead(org_id=ORG, ref_externa="contato-1", threads=w.threads, conversations=w.conversations,
                       retention=w.retention, instance_id="i1", ttl_seconds=60) is True

    assert w.threads.get_lead_ref_by_externa(ORG, "contato-1") is None
    for t in (a, b):
        assert w.conversations.find_thread(ORG, "whatsapp", t.channel_ref) is None
        assert w.messages.list(ORG, t.id) == []
        assert w.threads.list_participantes(ORG, t.id) == [] and w.threads.list_eventos(ORG, t.id) == []
        assert w.inbound.find(ORG, UUID(int=77), ["wamid.1", "wamid.2"]) == {}
    # the other lead is untouched
    assert w.threads.get_lead_ref_by_externa(ORG, "contato-2") is not None
    assert len(w.messages.list(ORG, keep.id)) == 1


def test_delete_by_lead_is_idempotent_and_org_scoped(w):
    t = w.thread()
    kw = dict(threads=w.threads, conversations=w.conversations, retention=w.retention, instance_id="i1", ttl_seconds=60)
    assert apagar_lead(org_id=OTHER_ORG, ref_externa="contato-1", **kw) is False
    assert w.conversations.get(ORG, t.id)
    assert apagar_lead(org_id=ORG, ref_externa="contato-1", **kw) is True
    assert apagar_lead(org_id=ORG, ref_externa="contato-1", **kw) is False


def test_delete_by_lead_refuses_while_any_thread_has_a_turn_running_and_releases_what_it_took(w):
    a, b = w.thread(chat="chat-1"), w.thread(chat="chat-2")
    assert w.conversations.try_acquire_turn(ORG, b.id, "turno-em-andamento", 60)
    with pytest.raises(TurnInProgress):
        apagar_lead(org_id=ORG, ref_externa="contato-1", threads=w.threads, conversations=w.conversations,
                    retention=w.retention, instance_id="i1", ttl_seconds=60)
    assert w.conversations.try_acquire_turn(ORG, a.id, "outro", 60)  # a's lock was released
    assert w.threads.get_lead_ref_by_externa(ORG, "contato-1") is not None


def test_the_retention_purge_cascades_to_the_participants_and_drops_the_orphaned_lead(w):
    old = w.thread(chat="chat-old")
    w.conversations._rows[old.id]["created_at"] = AGORA - timedelta(days=400)
    fresh = w.thread(ref="contato-2", chat="chat-new")
    purged = w.retention.purge_older_than(AGORA - timedelta(days=180))
    assert purged == 1
    assert w.threads.list_participantes(ORG, old.id) == []
    assert w.threads.get_lead_ref_by_externa(ORG, "contato-1") is None
    assert w.threads.get_lead_ref_by_externa(ORG, "contato-2") is not None
    assert w.conversations.get(ORG, fresh.id)


def test_deleting_one_thread_keeps_the_lead_ref_while_another_thread_remains(w):
    a, b = w.thread(chat="chat-1"), w.thread(chat="chat-2")
    assert w.retention.delete_conversation(ORG, a.id)
    assert w.threads.get_lead_ref_by_externa(ORG, "contato-1") is not None
    assert w.retention.delete_conversation(ORG, b.id)
    assert w.threads.get_lead_ref_by_externa(ORG, "contato-1") is None


# ── drain progress ─────────────────────────────────────────────────────────


def _aberto(dias: float | None, entrou_dias: float = 30) -> ThreadAberto:
    return ThreadAberto(
        thread_id=UUID(int=int(dias or 0) + 1000), agent_id=JULIA, entrou_em=AGORA - timedelta(days=entrou_dias),
        ultima_mensagem_lead_em=AGORA - timedelta(days=dias) if dias is not None else None,
    )


def test_drain_progress_counts_idle_threads_as_closed_and_is_done_when_no_recent_one_is_left():
    p = progresso_dreno([_aberto(0.1), _aberto(3), _aberto(8), _aberto(20)], 7, AGORA)
    assert (p["abertas"], p["ociosas"], p["efetivas"], p["concluida"]) == (4, 2, 2, False)
    assert p["idade_max_dias"] == 20 and p["idades_dias"] == [20, 8, 3, 0]
    done = progresso_dreno([_aberto(8), _aberto(20)], 7, AGORA)
    assert (done["efetivas"], done["concluida"]) == (0, True)
    assert progresso_dreno([], 7, AGORA) == {
        "abertas": 0, "ociosas": 0, "efetivas": 0, "concluida": True, "idade_max_dias": 0, "idades_dias": [],
    }


def test_a_thread_whose_lead_never_wrote_ages_from_the_participant_entry():
    p = progresso_dreno([_aberto(None, entrou_dias=9)], 7, AGORA)
    assert (p["ociosas"], p["efetivas"]) == (1, 0)
