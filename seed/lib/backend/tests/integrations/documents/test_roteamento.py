"""The model routing table: generated (never hand-edited), looked up per
(doc type, field), and moved only by data that clears the minimum-sample +
separation rule (`roteamento_gerador`)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from noctusai_lib.integrations.documents import roteamento
from noctusai_lib.integrations.documents import roteamento_calibracao as calibracao
from noctusai_lib.integrations.documents import roteamento_gerador as gerador

PACOTE = Path(calibracao.__file__).resolve().parent


def _cel(modelo, acertos, leituras=36, documentos=12, tipo="CNH", campo="nome", **kw):
    return {
        "fonte": "t", "modelo": modelo, "tipo": tipo, "campo": campo,
        "leituras": leituras, "documentos": documentos, "acertos": acertos,
        "presentes": kw.get("presentes", acertos), "presentes_corretos": kw.get("pc", acertos),
        "presentes_portao": kw.get("pp", acertos), "corretos_portao": kw.get("cp", acertos),
    }


class TestTheCommittedTableIsItsGeneratorsOutput:
    def test_module_text_equals_the_generator_over_the_committed_evidence(self):
        evidencia = json.loads((PACOTE / "roteamento_evidencia.json").read_text(encoding="utf-8"))
        esperado = gerador.renderizar_modulo(gerador.gerar(evidencia))
        assert (PACOTE / "roteamento_modelos.py").read_text(encoding="utf-8") == esperado, (
            "roteamento_modelos.py was edited by hand or its evidence changed — "
            "regenerate with noctus.dev.roteamento_modelos_recalibrar(escrever=True)"
        )

    def test_evidence_holds_counts_only(self):
        evidencia = json.loads((PACOTE / "roteamento_evidencia.json").read_text(encoding="utf-8"))
        permitidas = {
            "fonte", "modelo", "tipo", "campo", "leituras", "documentos", "acertos",
            "presentes", "presentes_corretos", "presentes_portao", "corretos_portao",
        }
        for c in evidencia["celulas"]:
            assert set(c) <= permitidas

    def test_fable_is_measured_but_never_routed(self):
        t = roteamento.TABELA
        rotas = [*t["por_tipo"].values(), *t["por_campo"].values()]
        assert all("fable" not in r["primario"] and "fable" not in r["fallback"] for r in rotas)
        assert any(k.startswith("claude-fable-5-1|") for k in t["precisao"])
        assert "claude-fable-5-1" in t["excluidos"]


class TestLookup:
    def test_a_measured_type_routes_sonnet_first_opus_fallback(self):
        r = roteamento.rota("cnh")
        assert (r.primario, r.fallback) == ("claude-sonnet-5", "claude-opus-5-5")
        assert r.n_documentos >= 1

    def test_a_field_row_records_its_sample(self):
        r = roteamento.rota("certidao_casamento", "estado_civil")
        assert r.primario == "claude-sonnet-5"
        assert r.n_leituras > 0

    def test_an_unknown_type_gets_the_global_default(self):
        r = roteamento.rota("comprovante_endereco")
        assert r.origem == "padrao"
        assert (r.primario, r.fallback) == (gerador.PRIMARIO_PADRAO, gerador.FALLBACK_PADRAO)

    def test_precision_is_withheld_below_the_minimum_sample(self):
        # RG had 4 documents in the benchmark — under N_MIN_DOCUMENTOS.
        assert roteamento.precisao("claude-sonnet-5", "rg", "nome") is None
        m = roteamento.precisao("claude-sonnet-5", "cnh", "nome")
        assert m is not None and m.suficiente

    def test_routing_governs_anthropic_only(self):
        assert roteamento.roteia(None) and roteamento.roteia("anthropic")
        assert not roteamento.roteia("openai")


class TestGeneratorRules:
    def test_a_clear_separated_win_moves_the_primary(self):
        ev = {"celulas": [_cel("claude-sonnet-5", 18), _cel("claude-opus-5-5", 36)]}
        t = gerador.gerar(ev)
        linha = t["por_tipo"]["CNH"]
        assert (linha["primario"], linha["fallback"], linha["origem"]) == (
            "claude-opus-5-5", "claude-sonnet-5", "medido",
        )

    def test_overlapping_intervals_keep_the_default(self):
        ev = {"celulas": [_cel("claude-sonnet-5", 33), _cel("claude-opus-5-5", 36)]}
        assert gerador.gerar(ev)["por_tipo"]["CNH"]["origem"] == "padrao"

    def test_below_minimum_sample_never_moves(self):
        ev = {"celulas": [
            _cel("claude-sonnet-5", 2, leituras=12, documentos=4),
            _cel("claude-opus-5-5", 12, leituras=12, documentos=4),
        ]}
        linha = gerador.gerar(ev)["por_tipo"]["CNH"]
        assert linha["primario"] == "claude-sonnet-5" and linha["origem"] == "padrao"

    def test_an_excluded_model_is_a_flagged_recommendation_not_a_route(self):
        ev = {"celulas": [
            _cel("claude-sonnet-5", 36), _cel("claude-opus-5-5", 18), _cel("claude-fable-5-1", 36),
        ]}
        t = gerador.gerar(ev)
        assert t["por_tipo"]["CNH"]["fallback"] != "claude-fable-5-1"
        assert any(
            r["modelo"] == "claude-fable-5-1" and r["motivo"] == "modelo_excluido_supera_fallback"
            for r in t["recomendacoes"]
        )

    def test_a_fallback_below_the_precision_threshold_is_flagged(self):
        ev = {"celulas": [
            _cel("claude-sonnet-5", 36),
            _cel("claude-opus-5-5", 30, pp=36, cp=30),
        ]}
        motivos = {r["motivo"] for r in gerador.gerar(ev)["recomendacoes"]}
        assert "fallback_precisao_abaixo_do_limiar" in motivos

    def test_wilson_interval(self):
        lo, hi = gerador.wilson(36, 36)
        assert hi == pytest.approx(1.0) and 0.9 < lo < 0.91

    def test_production_outcomes_count_only_human_resolved_rows(self):
        linhas = [
            {"tipo_documento": "cnh", "campo": "cpf", "documento_id": "d1",
             "modelo_primario": "claude-sonnet-5", "modelo_fallback": "claude-opus-5-5",
             "veredito": "duvidoso", "primario_correto": False, "fallback_correto": True},
            {"tipo_documento": "cnh", "campo": "cpf", "documento_id": "d2",
             "modelo_primario": "claude-sonnet-5", "veredito": "confiavel",
             "primario_correto": None},
        ]
        cel = {c["modelo"]: c for c in gerador.celulas_de_resultados(linhas, fonte="p")}
        assert cel["claude-sonnet-5"]["leituras"] == 1 and cel["claude-sonnet-5"]["acertos"] == 0
        assert cel["claude-opus-5-5"]["acertos"] == 1 and cel["claude-opus-5-5"]["corretos_portao"] == 1

    def test_diff_names_a_moved_row(self):
        a = gerador.gerar({"celulas": [_cel("claude-sonnet-5", 33), _cel("claude-opus-5-5", 36)]})
        b = gerador.gerar({"celulas": [_cel("claude-sonnet-5", 18), _cel("claude-opus-5-5", 36)]})
        assert any(d["chave"] == "CNH" for d in gerador.diff(a, b))
        assert gerador.diff(a, a) == []


class TestRecalibrationDryRun:
    def _bench(self, tmp_path: Path) -> Path:
        b = tmp_path / "bench"
        (b / "results" / "claude-sonnet-5").mkdir(parents=True)
        (b / "corpus.json").write_text(json.dumps([
            {"id": "d1", "tipo": "cnh", "tipo_pipeline": "cnh",
             "exp": {"cpf": "412.954.238-98", "nome": "JOAO CARLOS PEREIRA"}},
        ]), encoding="utf-8")
        (b / "results" / "claude-sonnet-5" / "d1_r1.json").write_text(json.dumps({
            "model": "claude-sonnet-5", "doc": "d1", "run": 1, "usd": 0.02, "exc": None,
            "ladder": [{"source": "ocr", "text": "NOME: JOAO CARLOS PEREIRA\nCPF: 412.954.238-98\n"}],
        }), encoding="utf-8")
        return b

    def test_dry_run_reports_without_writing(self, tmp_path: Path):
        pacote = tmp_path / "pacote"
        pacote.mkdir()
        for nome in ("roteamento_evidencia.json", "roteamento_modelos.py"):
            (pacote / nome).write_bytes((PACOTE / nome).read_bytes())
        antes = (pacote / "roteamento_modelos.py").read_bytes()
        out = calibracao.recalibrar(
            bench_dir=str(self._bench(tmp_path)), bench_fonte="t-bench", pacote=pacote,
        )
        assert out["escrito"] is False
        assert (pacote / "roteamento_modelos.py").read_bytes() == antes
        assert any(f["id"] == "t-bench" for f in out["fontes"])
        assert out["custos"]["claude-sonnet-5"]["usd_por_documento"] is not None

    def test_write_then_rerun_is_a_fixed_point(self, tmp_path: Path):
        pacote = tmp_path / "pacote"
        pacote.mkdir()
        calibracao.recalibrar(
            bench_dir=str(self._bench(tmp_path)), bench_fonte="t-bench", pacote=pacote,
            escrever=True,
        )
        assert calibracao.recalibrar(pacote=pacote)["mudancas"] == []

    def test_a_bench_without_a_source_id_is_refused(self, tmp_path: Path):
        with pytest.raises(ValueError):
            calibracao.recalibrar(bench_dir=str(self._bench(tmp_path)), pacote=tmp_path)
