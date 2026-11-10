"""The eval-loop gate's pure rules (owner spec 2026-11-09, G1-G7): improvement, overcalls, the stop rules and their order,
checkpoints, and the admission refusals (G6 / G7). No IO."""
from __future__ import annotations

from uuid import uuid4

from app.studio.eval_loop import (
    LoopDef, Rodada, avaliar_rodada, checar_admissao, checkpoints_atingidos, melhorou, partes_alteradas, serie_de_scores,
)


def _loop(**kw) -> LoopDef:
    base = dict(id=uuid4(), suite="comportamento", rodadas_planejadas=30, alvo=1.0, piso=0.8, orcamento_usd=20.0)
    return LoopDef(**{**base, **kw})


def _r(seq, score, *, h="h0", custo=1.0, falhas=(), status="concluida", partes=None) -> Rodada:
    return Rodada(seq=seq, run_id=uuid4(), run_tipo="comportamento", compiled_hash=h, status=status, score=score,
                  custo_usd=custo, falhas=tuple(falhas), partes=partes)


def _fechar(loop, anteriores, seq, score, **kw):
    kw.setdefault("status", "concluida")
    kw.setdefault("custo_usd", 1.0)
    kw.setdefault("falhas", ())
    kw.setdefault("compiled_hash", "h0")
    return avaliar_rodada(loop, anteriores, seq=seq, score=score, **kw)


class TestImprovementAndOvercalls:  # G5
    def test_first_scored_round_is_the_baseline_not_an_overcall(self):
        d = _fechar(_loop(), [], 1, 0.5)
        assert d.melhorou is None and d.overcall is False and d.sem_melhora_seguidas == 0

    def test_a_round_that_raises_the_best_score_improved(self):
        assert melhorou([_r(1, 0.5), _r(2, 0.6)], 0.7) is True

    def test_equal_or_lower_than_the_best_is_an_overcall(self):
        loop, ant = _loop(), [_r(1, 0.6), _r(2, 0.7)]
        assert _fechar(loop, ant, 3, 0.7).overcall is True   # equal
        assert _fechar(loop, ant, 3, 0.65).overcall is True  # below the best (not just below the last)

    def test_float_noise_is_not_an_improvement(self):
        assert melhorou([_r(1, 0.7)], 0.7 + 1e-12) is False

    def test_an_unscored_round_is_neutral_but_still_costs(self):
        loop = _loop(gasto_usd=3.0)
        d = _fechar(loop, [_r(1, 0.5), _r(2, 0.5)], 3, None, status="falhou", custo_usd=2.0)
        assert d.melhorou is None and d.overcall is False and d.gasto_usd == 5.0
        assert d.sem_melhora_seguidas == 1 and d.parada is None  # the streak is untouched by the neutral round


class TestStopRules:
    def test_g3_stops_at_100_percent_and_concludes(self):
        d = _fechar(_loop(), [_r(1, 0.9)], 2, 1.0)
        assert d.parada.motivo == "alvo_atingido" and d.parada.status == "concluido"

    def test_g4_two_consecutive_flat_rounds_stop_the_loop_with_the_reason_payload(self):
        loop = _loop()
        ant = [_r(1, 0.6, h="a", partes={"secao:x": "1"}), _r(2, 0.7, h="b", partes={"secao:x": "2"}),
               _r(3, 0.7, h="c", partes={"secao:x": "3"})]
        d = _fechar(loop, ant, 4, 0.69, compiled_hash="d", partes={"secao:x": "4"})
        assert d.sem_melhora_seguidas == 2
        assert d.parada.motivo == "sem_melhora" and d.parada.status == "parado"
        det = d.parada.detalhe
        assert det["seguidas"] == 2 and det["hash_anterior"] == "c" and det["hash_atual"] == "d"
        assert det["conteudo_mudou"] is True and det["partes_alteradas"] == ["secao:x"]

    def test_g4_reports_an_unchanged_hash_between_the_flat_rounds(self):
        ant = [_r(1, 0.6, h="a"), _r(2, 0.6, h="a")]
        d = _fechar(_loop(), ant, 3, 0.6, compiled_hash="a")
        assert d.parada.motivo == "sem_melhora" and d.parada.detalhe["conteudo_mudou"] is False

    def test_one_flat_round_does_not_stop(self):
        d = _fechar(_loop(), [_r(1, 0.6), _r(2, 0.7)], 3, 0.7)
        assert d.overcall is True and d.sem_melhora_seguidas == 1 and d.parada is None

    def test_an_improvement_resets_the_streak(self):
        d = _fechar(_loop(), [_r(1, 0.6), _r(2, 0.6), _r(3, 0.7)], 4, 0.7)
        assert d.sem_melhora_seguidas == 1 and d.parada is None

    def test_g4_applies_above_the_floor_too(self):
        d = _fechar(_loop(piso=0.8), [_r(1, 0.9), _r(2, 0.9)], 3, 0.9)
        assert d.parada.motivo == "sem_melhora"

    def test_g7_budget_stops_the_loop_for_an_owner_decision(self):
        d = _fechar(_loop(orcamento_usd=20.0, gasto_usd=19.0), [_r(1, 0.5, custo=19.0)], 2, 0.6, custo_usd=1.5)
        assert d.parada.motivo == "orcamento_atingido" and d.parada.status == "parado" and d.gasto_usd == 20.5

    def test_budget_wins_over_no_improvement_but_the_target_wins_over_both(self):
        loop = _loop(orcamento_usd=5.0, gasto_usd=4.5)
        assert _fechar(loop, [_r(1, 0.6), _r(2, 0.6)], 3, 0.6, custo_usd=1.0).parada.motivo == "orcamento_atingido"
        assert _fechar(loop, [_r(1, 0.6), _r(2, 0.6)], 3, 1.0, custo_usd=1.0).parada.motivo == "alvo_atingido"

    def test_the_planned_rounds_running_out_conclude_the_loop(self):
        loop = _loop(rodadas_planejadas=3)
        d = _fechar(loop, [_r(1, 0.5), _r(2, 0.6)], 3, 0.7)
        assert d.parada.motivo == "rodadas_esgotadas" and d.parada.status == "concluido"

    def test_g2_checkpoints_at_5_10_15_only_within_the_planned_rounds(self):
        loop = _loop(rodadas_planejadas=12)
        ant5 = [_r(i, 0.1 * i) for i in range(1, 5)]
        assert _fechar(loop, ant5, 5, 0.5).checkpoint == 5
        assert _fechar(loop, [_r(i, 0.05 * i) for i in range(1, 10)], 10, 0.6).checkpoint == 10
        assert [c["rodada"] for c in checkpoints_atingidos(loop, [])] == [5, 10]  # 15 > 12: not a checkpoint of this loop

    def test_checkpoints_report_score_and_spend_once_reached(self):
        loop = _loop(rodadas_planejadas=30)
        rs = [_r(i, 0.1 * i, custo=2.0) for i in range(1, 6)]
        cps = {c["rodada"]: c for c in checkpoints_atingidos(loop, rs)}
        assert cps[5]["atingido"] is True and cps[5]["gasto_usd"] == 10.0 and cps[10]["atingido"] is False


class TestAdmission:  # G6 / G7 + the loop's own state
    def _ok(self, loop=None, rodadas=(), h="h1", passes=5):
        return checar_admissao(loop or _loop(), list(rodadas), compiled_hash=h, limite_passes_consolidacao=passes)

    def test_a_fresh_loop_admits(self):
        assert self._ok() is None

    def test_a_closed_loop_refuses(self):
        r = self._ok(_loop(status="parado", motivo_parada="sem_melhora"))
        assert r.code == "loop_encerrado" and "sem_melhora" in r.mensagem

    def test_a_round_in_flight_refuses(self):
        assert self._ok(rodadas=[_r(1, None, status="executando")]).code == "rodada_em_andamento"

    def test_a_spent_budget_refuses(self):
        assert self._ok(_loop(gasto_usd=20.0)).code == "orcamento_do_loop_atingido"

    def test_exhausted_rounds_refuse(self):
        assert self._ok(_loop(rodadas_planejadas=1), [_r(1, 0.5, h="h0")]).code == "rodadas_esgotadas"

    def test_g6_unchanged_hash_after_a_round_with_failures_is_refused_with_the_failing_cases(self):
        r = self._ok(rodadas=[_r(1, 0.6, h="h1", falhas=("caso-a", "caso-b"))], h="h1")
        assert r.code == "hash_inalterado" and "caso-a" in r.mensagem and "rodada 1" in r.mensagem

    def test_g6_changed_hash_is_admitted(self):
        assert self._ok(rodadas=[_r(1, 0.6, h="h0", falhas=("caso-a",))], h="h1") is None

    def test_g6_clean_reruns_on_the_same_hash_are_allowed_up_to_the_consolidation_passes(self):
        limpas = [_r(i, 0.9 + i * 0.001, h="h1") for i in range(1, 5)]
        assert self._ok(_loop(), limpas, h="h1", passes=5) is None  # 4 clean passes < 5
        r = self._ok(_loop(), limpas + [_r(5, 0.95, h="h1")], h="h1", passes=5)
        assert r.code == "hash_inalterado" and "5 rodadas" in r.mensagem  # beyond the consolidation passes


def test_helpers():
    assert serie_de_scores([_r(2, 0.7), _r(1, 0.5), _r(3, None, status="falhou")]) == [0.5, 0.7]
    assert partes_alteradas({"a": "1", "b": "2"}, {"a": "1", "b": "3", "c": "9"}) == ["b", "c"]
    assert partes_alteradas(None, {"a": "1"}) is None
