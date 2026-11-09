"""Eval consolidation state machine (owner rule 2026-11-09): 5/10 consecutive passes consolidate, 3/6 reconsolidate after an
affecting change, a failure resets, the thresholds are DATA, no declared dependency = affected by any change."""
from __future__ import annotations

from uuid import uuid4

import pytest

from app.studio.consolidacao import (
    DEFAULT_CONFIG, ConfigConsolidacao, EstadoCaso, aplicar_resultado, decidir_selecao, estado_inicial, inferir_depende_de,
    partes_afetadas, resultado_de_status, sugerir_criticidade,
)

CFG = ConfigConsolidacao(dict(DEFAULT_CONFIG))
P0 = {"secao:a": "1", "skill:x": "1", "ferramenta:t": "1", "modelo": "m", "config": "c", "estrutura": "e"}


def _run(est, resultados, crit="normal", partes=P0, deps=("secao:a",), h="h0"):
    for r in resultados:
        ap = aplicar_resultado(est, r, criticidade=crit, cfg=CFG, atuais=partes, hash_atual=h, depende_de=deps)
        est = ap.estado
    return est


class TestThresholds:
    @pytest.mark.parametrize("crit,n", [("normal", 5), ("critico", 10)])
    def test_n_consecutive_passes_consolidate(self, crit, n):
        e = estado_inicial(uuid4(), crit, CFG)
        assert _run(e, ["passou"] * (n - 1), crit).estado == "em_validacao"
        assert _run(e, ["passou"] * n, crit).estado == "consolidado"

    def test_a_failure_resets_the_streak(self):
        e = _run(estado_inicial(uuid4(), "normal", CFG), ["passou"] * 4 + ["falhou"])
        assert (e.estado, e.sequencia) == ("em_validacao", 0)
        assert _run(e, ["passou"] * 4).estado == "em_validacao"
        assert _run(e, ["passou"] * 5).estado == "consolidado"

    def test_thresholds_are_config_rows_not_constants(self):
        cfg = ConfigConsolidacao({**DEFAULT_CONFIG, "consolidar_normal": 2})
        e = estado_inicial(uuid4(), "normal", cfg)
        for _ in range(2):
            e = aplicar_resultado(e, "passou", criticidade="normal", cfg=cfg, atuais=P0, hash_atual="h").estado
        assert e.estado == "consolidado"

    def test_config_missing_a_key_is_refused_not_defaulted(self):
        with pytest.raises(ValueError):
            ConfigConsolidacao({"consolidar_normal": 5})

    def test_neutral_result_neither_counts_nor_resets(self):
        e = _run(estado_inicial(uuid4(), "normal", CFG), ["passou"] * 3 + ["neutro"])
        assert e.sequencia == 3
        assert resultado_de_status("erro") == "neutro" and resultado_de_status("aprovado") == "passou"


class TestRevalidation:
    def _consolidado(self, crit="normal"):
        n = DEFAULT_CONFIG[f"consolidar_{crit}"]
        return _run(estado_inicial(uuid4(), crit, CFG), ["passou"] * n, crit)

    @pytest.mark.parametrize("crit,n", [("normal", 3), ("critico", 6)])
    def test_affected_case_returns_to_consolidado_after_3_or_6(self, crit, n):
        p1 = {**P0, "secao:a": "2"}
        e = self._consolidado(crit)
        first = aplicar_resultado(e, "passou", criticidade=crit, cfg=CFG, atuais=p1, hash_atual="h1", depende_de=["secao:a"])
        assert [t.motivo for t in first.transicoes][0] == "afetado" and first.estado.estado == "revalidar"
        e2 = _run(e, ["passou"] * (n - 1), crit, partes=p1, h="h1")
        assert e2.estado == "revalidar"
        e3 = _run(e, ["passou"] * n, crit, partes=p1, h="h1")
        assert e3.estado == "consolidado"

    def test_failure_during_revalidation_drops_to_em_validacao_with_the_full_threshold(self):
        p1 = {**P0, "secao:a": "2"}
        e = _run(self._consolidado(), ["passou", "falhou"], partes=p1, h="h1")
        assert e.estado == "em_validacao" and e.sequencia == 0 and e.limite == 5

    def test_unaffected_change_leaves_a_consolidated_case_alone(self):
        e = self._consolidado()
        outro = {**P0, "skill:x": "2"}  # not a declared dependency
        rodar, ap = decidir_selecao(e, criticidade="normal", cfg=CFG, depende_de=["secao:a"], atuais=outro)
        assert rodar is False and ap is None

    def test_global_part_change_affects_every_case(self):
        e = self._consolidado()
        rodar, ap = decidir_selecao(e, criticidade="normal", cfg=CFG, depende_de=["secao:a"], atuais={**P0, "modelo": "m2"})
        assert rodar is True and ap.estado.estado == "revalidar" and ap.transicoes[0].partes_afetadas == ("modelo",)

    def test_no_declared_dependency_is_affected_by_any_change(self):
        e = self._consolidado()
        rodar, ap = decidir_selecao(e, criticidade="normal", cfg=CFG, depende_de=None, atuais={**P0, "skill:x": "2"})
        assert rodar is True and ap.estado.estado == "revalidar"

    def test_missing_hashes_fail_safe_to_affected(self):
        e = self._consolidado()
        rodar, _ = decidir_selecao(e, criticidade="normal", cfg=CFG, depende_de=["secao:a"], atuais=None, hash_atual=None)
        assert rodar is True

    def test_identical_parts_skip_a_consolidated_case(self):
        rodar, _ = decidir_selecao(self._consolidado(), criticidade="normal", cfg=CFG, depende_de=None, atuais=dict(P0))
        assert rodar is False

    def test_a_change_mid_streak_restarts_the_streak(self):
        e = _run(estado_inicial(uuid4(), "normal", CFG), ["passou"] * 3)
        e = _run(e, ["passou"], partes={**P0, "secao:a": "2"}, h="h1")
        assert (e.estado, e.sequencia) == ("em_validacao", 1)

    def test_failure_of_a_consolidated_case_run_anyway_is_a_regression(self):
        e = self._consolidado()
        ap = aplicar_resultado(e, "falhou", criticidade="normal", cfg=CFG, atuais=dict(P0), hash_atual="h0", depende_de=["secao:a"])
        assert ap.estado.estado == "em_validacao" and ap.transicoes[-1].motivo == "regressao"


class TestAffectedDetection:
    def test_wildcard_dependency(self):
        assert partes_afetadas(["skill:*"], {"skill:y": "2"}, {"skill:y": "1"}) == ("skill:y",)

    def test_added_or_removed_part_counts_as_changed(self):
        assert partes_afetadas(["ferramenta:t"], {}, {"ferramenta:t": "1"}) == ("ferramenta:t",)
        assert partes_afetadas(["ferramenta:t"], {"ferramenta:t": "1"}, {}) == ("ferramenta:t",)

    def test_hash_change_without_parts_policy(self):
        from app.studio.consolidacao import reconciliar_afetacao

        est = EstadoCaso(uuid4(), "consolidado", 5, 10, None, "h0")
        for pol, esperado in (("dono", "consolidado"), ("conservadora", "revalidar")):
            ap = reconciliar_afetacao(est, criticidade="normal", cfg=CFG, depende_de=["secao:a"], atuais=None, hash_atual="h1", sem_partes=pol)
            assert ap.estado.estado == esperado
        sem_deps = reconciliar_afetacao(est, criticidade="normal", cfg=CFG, depende_de=None, atuais=None, hash_atual="h1", sem_partes="dono")
        assert sem_deps.estado.estado == "revalidar"  # owner's reading: a case whose deps can't be resolved IS affected


class TestProposals:
    def test_criticality_from_tags(self):
        assert sugerir_criticidade(["adversarial"]) == "critico"
        assert sugerir_criticidade(["Firewall-Clientes", "x"]) == "critico"
        assert sugerir_criticidade(["tom"]) == "normal"

    def test_depende_de_heuristic_and_gaps(self):
        conhecidas = ["ferramenta:agendar_visita", "skill:qualificar", "secao:persona", "modelo"]
        deps, _ = inferir_depende_de(tags=["skill:qualificar"], asserts={"ferramentas_incluem": ["agendar_visita"], "ferramentas_proibidas": ["oferecer_imoveis"]},
                                     texto_caso="", partes_conhecidas=conhecidas)
        assert deps == ["ferramenta:agendar_visita", "skill:qualificar"]
        deps, _ = inferir_depende_de(tags=["tom"], asserts={}, texto_caso="o lead pergunta sobre preço", partes_conhecidas=conhecidas)
        assert deps is None  # cannot infer: stays fail-safe
        # a PROHIBITED tool says nothing about which prompt rows drive the behaviour
        deps, _ = inferir_depende_de(tags=[], asserts={"ferramentas_proibidas": ["agendar_visita"]}, texto_caso="", partes_conhecidas=conhecidas)
        assert deps is None
