"""Eval-loop orchestration over the Fake store + the Fake notification sink: opening/closing rounds, the mid-flight stop
notification (reason payload), G6 admission, G7 budget clamp, reconciliation of a stuck round, manual stop, the read model."""
from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.notifications import FakeNotificationSink
from app.stores.studio_eval_consolidacao import FakeConsolidacaoStore
from app.stores.studio_eval_loops import FakeLoopStore
from app.studio.eval_loop_service import KIND_CHECKPOINT, KIND_PARADA, EvalLoopService, RunResumo

ORG, AGENT, OWNER = uuid4(), uuid4(), uuid4()


class W:
    def __init__(self, *, rodadas=30, orcamento=20.0, piso=0.8, alvo=1.0):
        self.loops = FakeLoopStore()
        self.sink = FakeNotificationSink(admin_ids=["admin-1"])
        self.svc = EvalLoopService(self.loops, self.sink, FakeConsolidacaoStore())
        self.loop = self.loops.create_loop(ORG, AGENT, agente_chave="agente-base", suite="comportamento", rodadas_planejadas=rodadas,
                                           alvo=alvo, piso=piso, orcamento_usd=orcamento, started_by=OWNER)

    def rodada(self, h="h0", partes=None, *, tipo="comportamento"):
        run_id = uuid4()
        self.svc.abrir(ORG, self.loop.id, run_id=run_id, run_tipo=tipo, compiled_hash=h, partes=partes)
        return run_id

    def fechar(self, run_id, score, *, custo=1.0, falhas=(), status="concluida", h="h0", tipo="comportamento"):
        return self.svc.fechar_por_run(ORG, RunResumo(run_id=run_id, run_tipo=tipo, status=status, score=score, custo_usd=custo,
                                                      falhas=tuple(falhas), compiled_hash=h))

    def estado(self):
        return self.svc.estado(ORG, AGENT, self.loop.id)


def test_g1_g2_a_new_loop_carries_target_floor_and_planned_rounds():
    w = W(rodadas=12, piso=0.8)
    e = w.estado()
    assert (e["alvo"], e["piso"], e["rodadas_planejadas"], e["status"]) == (1.0, 0.8, 12, "ativo")
    assert [c["rodada"] for c in e["checkpoints"]] == [5, 10] and not any(c["atingido"] for c in e["checkpoints"])


def test_g4_two_flat_rounds_stop_the_loop_and_notify_mid_flight_with_the_reason():
    w = W()
    w.fechar(w.rodada("h1"), 0.6, falhas=("caso-a", "caso-b"), h="h1")
    w.fechar(w.rodada("h2"), 0.7, falhas=("caso-a",), h="h2")
    w.fechar(w.rodada("h3"), 0.7, falhas=("caso-a",), h="h3")  # flat #1
    assert w.sink.sent == []  # one flat round is only an overcall: nothing is sent yet
    d = w.fechar(w.rodada("h4"), 0.69, falhas=("caso-a",), custo=2.5, h="h4")  # flat #2
    assert d.parada.motivo == "sem_melhora"
    e = w.estado()
    assert e["status"] == "parado" and e["motivo_parada"] == "sem_melhora" and e["detalhe_parada"]["seguidas"] == 2
    [n] = w.sink.sent
    assert n["user_id"] == "admin-1" and n["kind"] == KIND_PARADA and n["org_id"] is None
    assert "agente-base" in n["title"]
    msg = n["message"]
    assert "60% → 70% → 70% → 69%" in msg and "2 rodadas seguidas sem melhora" in msg
    assert "caso-a" in msg and "rodada 4" in msg and "US$ 5.50 de US$ 20.00" in msg
    meta = n["metadata"]
    assert meta["motivo"] == "sem_melhora" and meta["serie"] == [0.6, 0.7, 0.7, 0.69]
    assert meta["hashes"] == ["h1", "h2", "h3", "h4"] and meta["casos_falhando"] == ["caso-a"]
    assert meta["gasto_usd"] == 5.5 and meta["dedup_key"].endswith(":parada")
    assert [o["rodada"] for o in meta["overcalls"]] == [3, 4]


def test_g4_message_says_when_the_content_did_not_change_between_the_flat_rounds():
    w = W()
    for score, falhas in [(0.6, ("a",)), (0.6, ("a",)), (0.6, ("a",))]:
        w.fechar(w.rodada("h1"), score, falhas=falhas, h="h1")
    [n] = w.sink.sent
    assert "não mudou" in n["message"] and "mesmo hash" in n["message"]


def test_g4_message_names_the_parts_that_changed_when_known():
    w = W()
    w.fechar(w.rodada("h1", {"secao:a": "1"}), 0.6, h="h1")
    w.fechar(w.rodada("h2", {"secao:a": "2"}), 0.6, h="h2")
    w.fechar(w.rodada("h3", {"secao:a": "3"}), 0.6, h="h3")
    assert "secao:a" in w.sink.sent[0]["message"]


def test_g3_stop_at_100_concludes_and_notifies_success():
    w = W()
    w.fechar(w.rodada(), 0.9)
    w.fechar(w.rodada("h1"), 1.0, h="h1")
    e = w.estado()
    assert e["status"] == "concluido" and e["motivo_parada"] == "alvo_atingido"
    assert "concluído" in w.sink.sent[0]["title"]


def test_g5_overcalls_are_flagged_and_listed_with_their_cost():
    w = W()
    w.fechar(w.rodada("h0"), 0.7, custo=1.0)
    r2 = w.rodada("h1")
    w.fechar(r2, 0.7, custo=2.25, h="h1")
    e = w.estado()
    assert [o["rodada"] for o in e["overcalls"]] == [2] and e["custo_overcalls_usd"] == 2.25
    assert [s["overcall"] for s in e["serie"]] == [False, True]


def test_g7_budget_reached_stops_the_loop_for_an_owner_decision():
    w = W(orcamento=5.0)
    w.fechar(w.rodada(), 0.5, custo=3.0)
    d = w.fechar(w.rodada("h1"), 0.6, custo=2.5, h="h1")
    assert d.parada.motivo == "orcamento_atingido"
    e = w.estado()
    assert e["status"] == "parado" and e["gasto_usd"] == 5.5 and e["restante_usd"] == 0.0
    assert "orçamento" in w.sink.sent[0]["message"]
    with pytest.raises(HTTPException) as exc:
        w.svc.admitir(ORG, AGENT, w.loop.id, suite="comportamento", compiled_hash="h9", limite_usd=2.0)
    assert exc.value.status_code == 409 and exc.value.detail["code"] == "loop_encerrado"


def test_g7_the_run_cost_cap_is_clamped_to_what_the_budget_has_left():
    w = W(orcamento=10.0)
    w.fechar(w.rodada(), 0.5, custo=9.0)
    a = w.svc.admitir(ORG, AGENT, w.loop.id, suite="comportamento", compiled_hash="h1", limite_usd=2.0)
    assert a.limite_usd == 1.0


def test_g6_unchanged_hash_with_failures_is_a_409_with_a_ptbr_message():
    w = W()
    w.fechar(w.rodada("h1"), 0.6, falhas=("caso-a",), h="h1")
    with pytest.raises(HTTPException) as exc:
        w.svc.admitir(ORG, AGENT, w.loop.id, suite="comportamento", compiled_hash="h1", limite_usd=2.0)
    assert exc.value.status_code == 409 and exc.value.detail["code"] == "hash_inalterado"
    assert "caso-a" in exc.value.detail["detail"] and "Corrija" in exc.value.detail["detail"]


def test_a_round_in_flight_blocks_the_next_start():
    w = W()
    w.rodada()
    with pytest.raises(HTTPException) as exc:
        w.svc.admitir(ORG, AGENT, w.loop.id, suite="comportamento", compiled_hash="h1", limite_usd=2.0)
    assert exc.value.detail["code"] == "rodada_em_andamento"


def test_a_stuck_round_whose_run_already_ended_is_reconciled_at_the_next_admission():
    w = W()
    run = w.rodada("h1")
    resumo = RunResumo(run_id=run, run_tipo="comportamento", status="falhou", score=None, custo_usd=0.4, falhas=(), compiled_hash="h1")
    a = w.svc.admitir(ORG, AGENT, w.loop.id, suite="comportamento", compiled_hash="h2", limite_usd=2.0,
                      ler_resumo=lambda rid: resumo if rid == run else None)
    assert a.limite_usd == 2.0
    e = w.estado()
    assert e["serie"][0]["status"] == "falhou" and e["serie"][0]["score"] is None and e["gasto_usd"] == 0.4


def test_closing_is_idempotent_and_a_run_without_a_loop_is_ignored():
    w = W()
    run = w.rodada()
    assert w.fechar(run, 0.5) is not None
    assert w.fechar(run, 0.5) is None
    assert w.estado()["gasto_usd"] == 1.0  # the cost was added once
    assert w.svc.fechar_por_run(ORG, RunResumo(uuid4(), "comportamento", "concluida", 0.5, 1.0, (), "h")) is None


def test_the_hook_never_raises_into_a_finished_run_but_logs():
    w = W()

    def boom():
        raise RuntimeError("db down")

    w.svc.fechar_sem_falhar(ORG, boom, run_id=uuid4(), run_tipo="comportamento")  # no exception


def test_checkpoint_5_notifies_progress_without_stopping():
    w = W(rodadas=30)
    for i in range(1, 6):
        w.fechar(w.rodada(f"h{i}"), 0.1 * i, h=f"h{i}")
    [n] = w.sink.sent
    assert n["kind"] == KIND_CHECKPOINT and "rodada 5" in n["title"]
    assert w.estado()["status"] == "ativo"
    assert w.estado()["checkpoints"][0] == {"rodada": 5, "atingido": True, "score": 0.5, "gasto_usd": 5.0}


def test_notification_failure_is_logged_and_never_undoes_the_stop(caplog):
    w = W()
    w.sink.fail_with = RuntimeError("core down")
    w.fechar(w.rodada("h1"), 1.0, h="h1")
    assert w.estado()["status"] == "concluido"
    assert "notificacao_falhou" in caplog.text


def test_no_platform_admin_is_logged_loudly_not_silently(caplog):
    w = W()
    w.sink.admin_ids = []
    w.fechar(w.rodada("h1"), 1.0, h="h1")
    assert "notificacao_sem_destinatario" in caplog.text


def test_manual_stop_and_stop_of_a_closed_loop():
    w = W()
    rec = w.svc.parar(ORG, AGENT, w.loop.id, motivo="vou rever o prompt")
    assert rec.status == "parado" and rec.motivo_parada == "parado_manualmente" and rec.detalhe_parada == {"motivo_texto": "vou rever o prompt"}
    with pytest.raises(HTTPException) as exc:
        w.svc.parar(ORG, AGENT, w.loop.id, motivo=None)
    assert exc.value.status_code == 409 and exc.value.detail["code"] == "loop_ja_encerrado"


def test_a_loop_of_another_suite_or_org_is_refused_or_not_found():
    w = W()
    with pytest.raises(HTTPException) as exc:
        w.svc.admitir(ORG, AGENT, w.loop.id, suite="mecanismo", compiled_hash="h", limite_usd=2.0)
    assert exc.value.status_code == 422 and exc.value.detail["code"] == "loop_suite_invalida"
    with pytest.raises(HTTPException) as exc:
        w.svc.estado(uuid4(), AGENT, w.loop.id)
    assert exc.value.status_code == 404


def test_one_active_loop_per_agent_and_suite():
    from app.stores._db_errors import StudioConflict

    w = W()
    with pytest.raises(StudioConflict) as exc:  # another user: the (agent, suite) slot is taken
        w.loops.create_loop(ORG, AGENT, agente_chave="agente-base", suite="comportamento", rodadas_planejadas=5, alvo=1.0, piso=0.8,
                            orcamento_usd=5.0, started_by=uuid4())
    assert exc.value.code == "loop_ativo_existente"
    with pytest.raises(StudioConflict) as exc:  # the SAME user may not hold two loops, even on the other suite (migration 087)
        w.loops.create_loop(ORG, AGENT, agente_chave="agente-base", suite="mecanismo", rodadas_planejadas=5, alvo=1.0, piso=0.8,
                            orcamento_usd=5.0, started_by=OWNER)
    assert exc.value.code == "loop_ativo_do_usuario"
    w.loops.create_loop(ORG, AGENT, agente_chave="agente-base", suite="mecanismo", rodadas_planejadas=5, alvo=1.0, piso=0.8,
                        orcamento_usd=5.0, started_by=uuid4())  # the other suite is free for another user


def test_the_configured_target_95_stops_the_loop_and_the_message_names_95_not_100():
    w = W(alvo=0.95, rodadas=10)
    w.fechar(w.rodada(), 0.7)
    d = w.fechar(w.rodada("h1"), 0.95, h="h1")
    assert d.parada.motivo == "alvo_atingido" and w.estado()["status"] == "concluido" and w.estado()["alvo"] == 0.95
    assert "alvo 95%" in w.sink.sent[-1]["message"] and "100%" not in w.sink.sent[-1]["message"]


def test_just_below_the_configured_target_keeps_the_loop_going():
    w = W(alvo=0.95)
    assert w.fechar(w.rodada(), 0.94).parada is None and w.estado()["status"] == "ativo"


def test_the_configured_max_rounds_stop_the_loop_and_the_message_names_the_target():
    w = W(alvo=0.95, rodadas=3)
    for i, sc in enumerate((0.5, 0.6, 0.7)):
        d = w.fechar(w.rodada(f"h{i}"), sc, h=f"h{i}")
    assert d.parada.motivo == "rodadas_esgotadas" and w.estado()["motivo_parada"] == "rodadas_esgotadas"
    assert "3 rodadas planejadas" in w.sink.sent[-1]["message"] and "sem chegar a 95%" in w.sink.sent[-1]["message"]
