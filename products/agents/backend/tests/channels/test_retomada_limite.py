"""The follow-up cap (owner 2026-11-10): at most ``max_retomadas_seguidas`` (default 2) re-engagements in a row with
no reply from the lead, decided by ``decidir`` and booked as one append-only event per outcome. Pure table + the real
``aplicar_controles`` over the Fake stores (no patching of our own code)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from app.channels.controles import (
    MAX_RETOMADAS_PADRAO,
    STATUS_LIMITE_RETOMADAS,
    STATUS_NORMAL,
    STATUS_REENGAJAMENTO_IGNORADO,
    LeadIdentidade,
    ParticipanteView,
    ThreadView,
    aplicar_controles,
    decidir,
)
from app.stores.agent_controles import FakeAgentControleStore
from app.stores.conversations import FakeConversationStore
from app.stores.messages import FakeMessageStore
from app.stores.threads import FakeThreadStore

AGORA = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)
ATIVO = ParticipanteView(estado="ativo", entrou_em=AGORA - timedelta(days=2))


def _d(seguidas, *, modo="ligado", opt_out=False, max_=MAX_RETOMADAS_PADRAO, lead_em=None, part=ATIVO):
    th = ThreadView(ultima_mensagem_lead_em=lead_em or AGORA - timedelta(hours=1), lead_opt_out=opt_out, retomadas_seguidas=seguidas)
    return decidir(modo, th, part, "reengajamento", AGORA, max_retomadas_seguidas=max_)


def test_the_default_limit_is_two():
    assert MAX_RETOMADAS_PADRAO == 2


@pytest.mark.parametrize("seguidas,esperado", [(0, STATUS_NORMAL), (1, STATUS_NORMAL), (2, STATUS_LIMITE_RETOMADAS), (5, STATUS_LIMITE_RETOMADAS)])
def test_a_followup_runs_below_the_cap_and_is_refused_at_it(seguidas, esperado):
    d = _d(seguidas)
    assert d.status == esperado
    assert d.executar_llm is (esperado == STATUS_NORMAL)
    assert d.persistir_inbound is False and d.http_status == 200 and d.transicao is None


def test_the_limit_is_data_not_a_constant():
    assert _d(2, max_=3).status == STATUS_NORMAL
    assert _d(3, max_=3).status == STATUS_LIMITE_RETOMADAS
    assert _d(0, max_=0).status == STATUS_LIMITE_RETOMADAS  # 0 = never follow up


def test_opt_out_wins_over_the_cap():
    assert _d(2, opt_out=True).status == STATUS_REENGAJAMENTO_IGNORADO
    assert _d(0, opt_out=True).status == STATUS_REENGAJAMENTO_IGNORADO


def test_an_inactive_participant_or_an_idle_draining_thread_is_ignored_before_the_cap_is_looked_at():
    assert _d(9, part=ParticipanteView("pausado", AGORA - timedelta(days=2))).status == STATUS_REENGAJAMENTO_IGNORADO
    assert _d(9, modo="drenando", lead_em=AGORA - timedelta(days=30)).status == STATUS_REENGAJAMENTO_IGNORADO
    assert _d(9, modo="desligado").status == STATUS_REENGAJAMENTO_IGNORADO


def test_draining_with_a_live_thread_still_honours_the_cap():
    assert _d(1, modo="drenando").status == STATUS_NORMAL
    assert _d(2, modo="drenando").status == STATUS_LIMITE_RETOMADAS


def test_the_cap_does_not_touch_a_lead_message():
    th = ThreadView(ultima_mensagem_lead_em=AGORA, retomadas_seguidas=9)
    assert decidir("ligado", th, ATIVO, "mensagem", AGORA).status == STATUS_NORMAL


# ── the service: the count comes from the events, a lead reply resets it, every outcome is one row ─────────


ORG, JULIA = UUID(int=1), UUID(int=11)
REF = {"connection_id": str(UUID(int=77)), "chat_id": "chat-1"}
LEAD = LeadIdentidade(ref="contato-1", crm_lead_id=None, contato={"nome": "Fulano", "telefone_e164": "+5511999990000"})


class _W:
    def __init__(self):
        self.controles = FakeAgentControleStore()
        self.conversations = FakeConversationStore()
        self.threads = FakeThreadStore(self.conversations)
        self.messages = FakeMessageStore()
        self.controles.set(ORG, JULIA, modo="ligado", dreno_inatividade_dias=None)
        ref = self.threads.upsert_lead_ref(ORG, "contato-1").id
        self.thread = self.conversations.create_channel(ORG, JULIA, "whatsapp", REF, None, lead_ref_id=ref)
        self.threads.add_participante(ORG, self.thread.id, JULIA)

    def retomar(self, **kw):
        return aplicar_controles(
            org_id=ORG, agent_id=JULIA, gatilho="reengajamento", channel="whatsapp", channel_ref=REF,
            controles=self.controles, conversations=self.conversations, threads=self.threads,
            lead=LEAD, messages=self.messages, tier_retomada="horas", **kw)

    def enviada(self):
        self.threads.registrar_retomada(ORG, self.thread.id, JULIA, "enviada", "horas")

    def eventos(self, resultado):
        return [r for r in self.threads._retomadas if r["resultado"] == resultado]


def test_two_sent_followups_then_the_third_is_refused_and_booked_without_a_model_call():
    w = _W()
    for _ in range(2):
        assert w.retomar().prosseguir
        w.enviada()
    res = w.retomar()
    assert res.status == STATUS_LIMITE_RETOMADAS and not res.prosseguir and res.decisao.executar_llm is False
    assert len(w.eventos("enviada")) == 2 and len(w.eventos("recusada_limite")) == 1
    assert w.eventos("recusada_limite")[0]["tier"] == "horas"


def test_a_lead_reply_resets_the_count_with_no_write():
    w = _W()
    w.enviada(); w.enviada()
    assert w.retomar().status == STATUS_LIMITE_RETOMADAS
    before = len(w.threads._retomadas)
    w.conversations.touch_lead_message(ORG, w.thread.id)  # the lead answered
    assert w.retomar().prosseguir
    assert len(w.threads._retomadas) == before  # the reset wrote nothing


def test_the_limit_comes_from_the_caller_the_qualification_standard():
    w = _W()
    w.enviada(); w.enviada()
    assert w.retomar(max_retomadas_seguidas=3).prosseguir
    assert w.retomar(max_retomadas_seguidas=2).status == STATUS_LIMITE_RETOMADAS


def test_an_ignored_followup_is_booked_too_and_an_opt_out_ignores_before_the_cap():
    w = _W()
    w.enviada(); w.enviada()
    w.threads.registrar_opt_out(ORG, "contato-1")
    res = w.retomar()
    assert res.status == STATUS_REENGAJAMENTO_IGNORADO
    assert len(w.eventos("ignorada")) == 1 and not w.eventos("recusada_limite")


def test_a_lead_message_trigger_books_no_retomada_event():
    w = _W()
    aplicar_controles(
        org_id=ORG, agent_id=JULIA, gatilho="mensagem", channel="whatsapp", channel_ref=REF, controles=w.controles,
        conversations=w.conversations, threads=w.threads, lead=LEAD, messages=w.messages)
    assert w.threads._retomadas == []


def test_the_events_are_counted_per_agent_and_thread():
    w = _W()
    w.threads.registrar_retomada(ORG, w.thread.id, UUID(int=99), "enviada")
    assert w.threads.contar_retomadas_seguidas(ORG, w.thread.id, JULIA, None) == 0
    w.enviada()
    assert w.threads.contar_retomadas_seguidas(ORG, w.thread.id, JULIA, None) == 1
    with pytest.raises(ValueError):
        w.threads.registrar_retomada(ORG, w.thread.id, JULIA, "talvez")
