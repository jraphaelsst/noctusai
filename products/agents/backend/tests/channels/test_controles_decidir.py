"""``decidir`` -- EVERY row of the contract section 5.2 decision table (Julia v2, A-THREAD), plus the
re-engagement rules, the reopen rules and the drain-idle close. Pure function: no store, no mock."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.channels.controles import (
    CICLO_NOVO_APOS,
    STATUS_AGENTE_DESLIGADO,
    STATUS_CONTROLE_INDISPONIVEL,
    STATUS_CONVERSA_COM_OUTRO_AGENTE,
    STATUS_CONVERSA_COM_OUTRO_RESPONSAVEL,
    STATUS_CONVERSA_PAUSADA,
    STATUS_NORMAL,
    STATUS_NOVO_LEAD_RECUSADO,
    STATUS_REENGAJAMENTO_IGNORADO,
    ParticipanteView,
    ThreadView,
    Transicao,
    decidir,
)

AGORA = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)
RECENTE = AGORA - timedelta(hours=3)
OCIOSA = AGORA - timedelta(days=7)


def _thread(*, lead_em=RECENTE, outro_ativo=False) -> ThreadView:
    return ThreadView(ultima_mensagem_lead_em=lead_em, outro_agente_ativo=outro_ativo)


def _part(estado: str, *, saiu_em=None, entrou_em=AGORA - timedelta(days=30)) -> ParticipanteView:
    return ParticipanteView(estado=estado, entrou_em=entrou_em, saiu_em=saiu_em)


def _d(modo, thread, part, gatilho="mensagem", **kw):
    return decidir(modo, thread, part, gatilho, AGORA, **kw)


# ── row 1: the control cannot be read -> fail closed, whatever the trigger ──


@pytest.mark.parametrize("modo", [None, "", "pausado", "LIGADO"])
@pytest.mark.parametrize("gatilho", ["mensagem", "reengajamento"])
def test_an_unreadable_or_unknown_mode_is_a_503_that_persists_nothing_and_never_runs_the_model(modo, gatilho):
    d = _d(modo, _thread(), _part("ativo"), gatilho)
    assert (d.status, d.http_status, d.persistir_inbound, d.executar_llm) == (
        STATUS_CONTROLE_INDISPONIVEL, 503, False, False
    )
    assert d.transicao is None and not d.criar_thread


# ── desligado ──────────────────────────────────────────────────────────────


def test_off_with_no_thread_refuses_and_does_NOT_store_the_lead():
    d = _d("desligado", None, None)
    assert (d.status, d.persistir_inbound, d.executar_llm, d.criar_thread) == (STATUS_AGENTE_DESLIGADO, False, False, False)


@pytest.mark.parametrize("estado", ["ativo", "pausado", "concluido", "encerrado", "transferido", None])
def test_off_with_an_existing_thread_appends_the_message_without_replying_for_any_participant_state(estado):
    d = _d("desligado", _thread(), _part(estado) if estado else None)
    assert (d.status, d.persistir_inbound, d.executar_llm) == (STATUS_AGENTE_DESLIGADO, True, False)
    assert d.transicao is None


def test_off_wins_over_another_agent_being_active():
    d = _d("desligado", _thread(outro_ativo=True), None)
    assert d.status == STATUS_AGENTE_DESLIGADO and d.persistir_inbound


# ── drenando ───────────────────────────────────────────────────────────────


def test_draining_with_no_thread_refuses_the_new_lead_and_does_not_store_it():
    d = _d("drenando", None, None)
    assert (d.status, d.persistir_inbound, d.executar_llm, d.criar_thread) == (STATUS_NOVO_LEAD_RECUSADO, False, False, False)


def test_draining_when_the_agent_never_took_part_refuses_and_does_not_store():
    d = _d("drenando", _thread(), None)
    assert (d.status, d.persistir_inbound, d.executar_llm) == (STATUS_NOVO_LEAD_RECUSADO, False, False)


def test_draining_keeps_chatting_in_an_open_recent_thread():
    d = _d("drenando", _thread(lead_em=RECENTE), _part("ativo"))
    assert (d.status, d.persistir_inbound, d.executar_llm, d.transicao) == (STATUS_NORMAL, True, True, None)


def test_draining_just_under_the_idle_window_still_answers_and_at_the_window_it_closes():
    dias = 7
    antes = _d("drenando", _thread(lead_em=AGORA - timedelta(days=dias) + timedelta(seconds=1)), _part("ativo"), dreno_inatividade_dias=dias)
    assert antes.status == STATUS_NORMAL
    no_limite = _d("drenando", _thread(lead_em=AGORA - timedelta(days=dias)), _part("ativo"), dreno_inatividade_dias=dias)
    assert (no_limite.status, no_limite.persistir_inbound, no_limite.executar_llm) == (STATUS_NOVO_LEAD_RECUSADO, True, False)
    assert no_limite.transicao == Transicao(de=("ativo",), para="encerrado", motivo="dreno_inativo")


def test_the_drain_window_is_the_agents_setting_not_a_constant():
    thread = _thread(lead_em=AGORA - timedelta(days=3))
    assert _d("drenando", thread, _part("ativo"), dreno_inatividade_dias=7).status == STATUS_NORMAL
    assert _d("drenando", thread, _part("ativo"), dreno_inatividade_dias=3).status == STATUS_NOVO_LEAD_RECUSADO


def test_a_thread_whose_lead_never_wrote_is_aged_from_the_participant_entry():
    sem_msg = _thread(lead_em=None)
    assert _d("drenando", sem_msg, _part("ativo", entrou_em=AGORA - timedelta(days=1))).status == STATUS_NORMAL
    assert _d("drenando", sem_msg, _part("ativo", entrou_em=AGORA - timedelta(days=9))).status == STATUS_NOVO_LEAD_RECUSADO


@pytest.mark.parametrize("estado", ["pausado", "concluido", "transferido", "encerrado"])
def test_draining_never_reopens_or_answers_a_non_active_participant(estado):
    d = _d("drenando", _thread(), _part(estado))
    assert d.executar_llm is False and d.persistir_inbound is True and d.transicao is None
    assert d.status != STATUS_NORMAL


# ── ligado ─────────────────────────────────────────────────────────────────


def test_on_with_no_thread_creates_the_thread_and_answers():
    d = _d("ligado", None, None)
    assert (d.status, d.persistir_inbound, d.executar_llm, d.criar_thread) == (STATUS_NORMAL, True, True, True)


def test_on_with_an_active_participant_answers_even_when_the_thread_is_old():
    d = _d("ligado", _thread(lead_em=AGORA - timedelta(days=90)), _part("ativo"))
    assert (d.status, d.persistir_inbound, d.executar_llm, d.transicao) == (STATUS_NORMAL, True, True, None)


# ── ligado / drenando: per-participant states ──────────────────────────────


@pytest.mark.parametrize("modo", ["ligado", "drenando"])
def test_paused_is_appended_and_not_answered(modo):
    d = _d(modo, _thread(), _part("pausado"))
    assert (d.status, d.persistir_inbound, d.executar_llm) == (STATUS_CONVERSA_PAUSADA, True, False)


@pytest.mark.parametrize("modo", ["ligado", "drenando"])
@pytest.mark.parametrize("estado", ["concluido", "transferido"])
def test_a_concluded_or_transferred_thread_belongs_to_the_broker_and_is_never_reopened(modo, estado):
    d = _d(modo, _thread(), _part(estado, saiu_em=AGORA - timedelta(days=30)))
    assert (d.status, d.persistir_inbound, d.executar_llm, d.transicao) == (
        STATUS_CONVERSA_COM_OUTRO_RESPONSAVEL, True, False, None
    )


@pytest.mark.parametrize("modo", ["ligado", "drenando"])
def test_another_active_agent_owns_the_conversation(modo):
    d = _d(modo, _thread(outro_ativo=True), None)
    assert (d.status, d.persistir_inbound, d.executar_llm) == (STATUS_CONVERSA_COM_OUTRO_AGENTE, True, False)
    d2 = _d(modo, _thread(outro_ativo=True), _part("encerrado"))
    assert d2.status == STATUS_CONVERSA_COM_OUTRO_AGENTE


def test_on_with_a_thread_only_other_finished_agents_took_part_in_is_the_brokers():
    d = _d("ligado", _thread(), None)
    assert (d.status, d.persistir_inbound, d.executar_llm) == (STATUS_CONVERSA_COM_OUTRO_RESPONSAVEL, True, False)


# ── reopen ─────────────────────────────────────────────────────────────────


def test_an_ended_thread_reopens_as_a_new_cycle_after_24_hours():
    d = _d("ligado", _thread(), _part("encerrado", saiu_em=AGORA - CICLO_NOVO_APOS))
    assert (d.status, d.persistir_inbound, d.executar_llm, d.novo_ciclo) == (STATUS_NORMAL, True, True, True)
    assert d.transicao == Transicao(de=("encerrado",), para="ativo", motivo="novo_ciclo")


def test_an_ended_thread_whose_lead_writes_again_within_24_hours_is_still_answered_but_is_not_a_new_cycle():
    d = _d("ligado", _thread(), _part("encerrado", saiu_em=AGORA - CICLO_NOVO_APOS + timedelta(seconds=1)))
    assert (d.status, d.executar_llm, d.novo_ciclo) == (STATUS_NORMAL, True, False)
    assert d.transicao == Transicao(de=("encerrado",), para="ativo", motivo="lead_voltou")


def test_an_ended_thread_with_no_recorded_exit_time_reopens_as_a_new_cycle():
    d = _d("ligado", _thread(), _part("encerrado", saiu_em=None))
    assert d.novo_ciclo is True and d.transicao is not None


# ── re-engagement ──────────────────────────────────────────────────────────


@pytest.mark.parametrize("modo", ["ligado", "drenando"])
def test_reengagement_runs_for_an_active_participant_and_persists_no_inbound(modo):
    d = _d(modo, _thread(), _part("ativo"), "reengajamento")
    assert (d.status, d.persistir_inbound, d.executar_llm, d.transicao, d.criar_thread) == (STATUS_NORMAL, False, True, None, False)


def test_reengagement_is_ignored_when_off():
    d = _d("desligado", _thread(), _part("ativo"), "reengajamento")
    assert (d.status, d.persistir_inbound, d.executar_llm) == (STATUS_REENGAJAMENTO_IGNORADO, False, False)


@pytest.mark.parametrize("modo", ["ligado", "drenando", "desligado"])
@pytest.mark.parametrize("estado", [None, "pausado", "concluido", "encerrado", "transferido"])
def test_reengagement_is_ignored_unless_the_participant_is_active(modo, estado):
    d = _d(modo, _thread(), _part(estado) if estado else None, "reengajamento")
    assert d.status == STATUS_REENGAJAMENTO_IGNORADO and not d.executar_llm and not d.persistir_inbound


@pytest.mark.parametrize("modo", ["ligado", "drenando", "desligado"])
def test_reengagement_with_no_thread_never_creates_one(modo):
    d = _d(modo, None, None, "reengajamento")
    assert d.status == STATUS_REENGAJAMENTO_IGNORADO and not d.criar_thread


def test_reengagement_while_draining_stops_once_the_thread_is_idle_past_the_window_and_changes_no_state():
    d = _d("drenando", _thread(lead_em=OCIOSA), _part("ativo"), "reengajamento", dreno_inatividade_dias=7)
    assert (d.status, d.executar_llm, d.transicao) == (STATUS_REENGAJAMENTO_IGNORADO, False, None)


def test_reengagement_while_on_ignores_the_drain_window():
    d = _d("ligado", _thread(lead_em=OCIOSA), _part("ativo"), "reengajamento")
    assert d.status == STATUS_NORMAL and d.executar_llm


# ── guards on the function itself ──────────────────────────────────────────


def test_an_unknown_trigger_is_a_programming_error_not_a_silent_default():
    with pytest.raises(ValueError):
        decidir("ligado", None, None, "webhook", AGORA)


def test_an_unknown_participant_state_is_a_programming_error_not_a_reply():
    with pytest.raises(ValueError):
        _d("ligado", _thread(), _part("hibernando"))


def test_only_a_normal_decision_ever_runs_the_model():
    for modo in ("ligado", "drenando", "desligado"):
        for thread in (None, _thread(), _thread(outro_ativo=True)):
            for estado in (None, "ativo", "pausado", "concluido", "encerrado", "transferido"):
                for gatilho in ("mensagem", "reengajamento"):
                    d = _d(modo, thread, _part(estado) if estado else None, gatilho)
                    assert d.executar_llm == (d.status == STATUS_NORMAL), (modo, thread, estado, gatilho, d)
                    if d.executar_llm:
                        assert modo in ("ligado", "drenando")
                        assert not (modo == "drenando" and d.criar_thread)  # a draining agent never opens a thread
