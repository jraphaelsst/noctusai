"""Tests for `noctus.dev.divergencia_calibrar` — the read-only, verdicts-only
precision recalculation over done social-wiring contracts.

WHAT THESE PIN
--------------
- exactly one of `prod_extractions_path`/`prod_extractions_raw` is required;
- a deal not in `cards.json`, or with no `<numero>.json` answer key, or an
  ambiguous/missing (lado, papel) match, is SKIPPED and named — never
  silently dropped, never guessed at;
- precision is computed per (campo, origem) as acertos/total, verdicts only
  (no personal value ever appears in the return payload);
- `diff_vs_policy` flags a (campo, origem) whose freshly measured ratio
  disagrees with the CURRENT `divergencia_resolucao.PRECISAO` cell by more
  than `diff_threshold`, and flags a cell the policy has never seen at all.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import divergencia_calibrar as dc


def _gabarito(numero: str, *, cpf="412.954.238-98", nome="ANA PAULA SOUZA") -> dict:
    return {
        "folder": {"numero": numero},
        "partes": [
            {
                "lado": "comprador", "papel": "comprador",
                "clientes": {"cpf": cpf, "nome_oficial": nome},
            },
            {
                "lado": "vendedor", "papel": "proprietario",
                "clientes": {"cpf": "303.102.653-55", "nome_oficial": "ALMIR TEIXEIRA"},
            },
        ],
    }


@pytest.fixture
def setup(tmp_path: Path):
    keys_dir = tmp_path / "answer-keys"
    keys_dir.mkdir()
    (keys_dir / "897.json").write_text(json.dumps(_gabarito("897")), encoding="utf-8")
    (keys_dir / "895.json").write_text(
        json.dumps(_gabarito("895", cpf="111.111.111-11")), encoding="utf-8"
    )
    cards_path = tmp_path / "cards.json"
    cards_path.write_text(
        json.dumps({
            "897": {"cliente_id": "c1", "atendimento_id": "a1"},
            "895": {"cliente_id": "c2", "atendimento_id": "a2"},
        }),
        encoding="utf-8",
    )
    return {"answer_keys_dir": str(keys_dir), "cards_path": str(cards_path)}


class TestInputValidation:
    def test_neither_prod_source_raises(self, setup):
        with pytest.raises(ValueError):
            dc.divergencia_calibrar(**setup)

    def test_both_prod_sources_raises(self, setup):
        with pytest.raises(ValueError):
            dc.divergencia_calibrar(
                **setup, prod_extractions_raw=[], prod_extractions_path="x.json",
            )


class TestPrecisionComputation:
    def test_a_perfect_source_scores_100_percent(self, setup):
        registros = [{
            "numero": "897", "lado": "comprador", "papel": "comprador",
            "leituras": {"cpf": [{"valor": "412.954.238-98", "origem": "cnh"}]},
        }]
        out = dc.divergencia_calibrar(**setup, prod_extractions_raw=registros)
        assert out["precisao"]["cpf"]["cnh"] == {"precisao": 1.0, "n": 1}
        assert out["deals_considered"] == 1
        assert out["deals_skipped"] == []
        assert out["leituras_comparadas"] == 1

    def test_a_wrong_reading_lowers_precision(self, setup):
        registros = [
            {
                "numero": "897", "lado": "comprador", "papel": "comprador",
                "leituras": {"cpf": [{"valor": "412.954.238-98", "origem": "cnh"}]},
            },
            {
                "numero": "895", "lado": "comprador", "papel": "comprador",
                # 895's ground-truth cpf is "111.111.111-11" — this reading
                # disagrees.
                "leituras": {"cpf": [{"valor": "999.999.999-99", "origem": "cnh"}]},
            },
        ]
        out = dc.divergencia_calibrar(**setup, prod_extractions_raw=registros)
        assert out["precisao"]["cpf"]["cnh"] == {"precisao": 0.5, "n": 2}
        assert out["deals_considered"] == 2

    def test_cpf_comparison_is_punctuation_insensitive(self, setup):
        registros = [{
            "numero": "897", "lado": "comprador", "papel": "comprador",
            "leituras": {"cpf": [{"valor": "41295423898", "origem": "cnh"}]},
        }]
        out = dc.divergencia_calibrar(**setup, prod_extractions_raw=registros)
        assert out["precisao"]["cpf"]["cnh"]["precisao"] == 1.0

    def test_no_personal_value_ever_appears_in_the_payload(self, setup):
        registros = [{
            "numero": "897", "lado": "comprador", "papel": "comprador",
            "leituras": {"nome_oficial": [{"valor": "ANA PAULA SOUZA", "origem": "cnh"}]},
        }]
        out = dc.divergencia_calibrar(**setup, prod_extractions_raw=registros)
        dump = json.dumps(out)
        assert "ANA PAULA SOUZA" not in dump
        assert "412.954.238-98" not in dump


class TestSkipping:
    def test_a_numero_not_in_cards_json_is_skipped_and_named(self, setup):
        registros = [{
            "numero": "999", "lado": "comprador", "papel": "comprador",
            "leituras": {"cpf": [{"valor": "x", "origem": "cnh"}]},
        }]
        out = dc.divergencia_calibrar(**setup, prod_extractions_raw=registros)
        assert out["deals_skipped"] == [
            {"numero": "999", "motivo": "sem_card_cadastrado"}
        ]
        assert out["precisao"] == {}

    def test_a_numero_with_no_answer_key_file_is_skipped(self, setup):
        cards_path = Path(setup["cards_path"])
        cards = json.loads(cards_path.read_text())
        cards["700"] = {"cliente_id": "c3", "atendimento_id": "a3"}
        cards_path.write_text(json.dumps(cards), encoding="utf-8")
        registros = [{
            "numero": "700", "lado": "comprador", "papel": "comprador",
            "leituras": {"cpf": [{"valor": "x", "origem": "cnh"}]},
        }]
        out = dc.divergencia_calibrar(**setup, prod_extractions_raw=registros)
        assert out["deals_skipped"] == [{"numero": "700", "motivo": "sem_gabarito"}]

    def test_an_ambiguous_lado_papel_is_skipped(self, setup):
        registros = [{
            "numero": "897", "lado": "comprador", "papel": "NAO_EXISTE",
            "leituras": {"cpf": [{"valor": "x", "origem": "cnh"}]},
        }]
        out = dc.divergencia_calibrar(**setup, prod_extractions_raw=registros)
        assert out["deals_skipped"] == [
            {"numero": "897", "motivo": "lado_papel_ambiguo_ou_ausente"}
        ]


class TestDiffVsPolicy:
    def test_a_measured_ratio_far_from_policy_is_flagged(self, setup):
        # divergencia_resolucao.PRECISAO["cpf"]["cnh"] == 1.0 — a freshly
        # measured 0.0 (every reading here disagrees) is well past the
        # default 0.10 threshold.
        registros = [{
            "numero": "897", "lado": "comprador", "papel": "comprador",
            "leituras": {"cpf": [{"valor": "999.999.999-99", "origem": "cnh"}]},
        }]
        out = dc.divergencia_calibrar(**setup, prod_extractions_raw=registros)
        flags = [d for d in out["diff_vs_policy"] if d["campo"] == "cpf" and d["origem"] == "cnh"]
        assert len(flags) == 1
        assert flags[0]["motivo"] == "divergencia_acima_do_limiar"
        assert flags[0]["precisao_atual_na_politica"] == 1.0
        assert flags[0]["precisao_recem_medida"] == 0.0

    def test_a_source_with_no_policy_entry_is_flagged_distinctly(self, setup):
        registros = [{
            "numero": "897", "lado": "comprador", "papel": "comprador",
            "leituras": {"cpf": [{"valor": "412.954.238-98", "origem": "whatsapp_bot"}]},
        }]
        out = dc.divergencia_calibrar(**setup, prod_extractions_raw=registros)
        flags = [d for d in out["diff_vs_policy"] if d["origem"] == "whatsapp_bot"]
        assert flags[0]["motivo"] == "sem_entrada_na_politica_atual"
        assert flags[0]["precisao_atual_na_politica"] is None

    def test_a_ratio_within_threshold_is_not_flagged(self, setup):
        # cnh/cpf policy = 1.0; measuring exactly 1.0 again must not flag.
        registros = [{
            "numero": "897", "lado": "comprador", "papel": "comprador",
            "leituras": {"cpf": [{"valor": "412.954.238-98", "origem": "cnh"}]},
        }]
        out = dc.divergencia_calibrar(**setup, prod_extractions_raw=registros)
        assert out["diff_vs_policy"] == []


def test_policy_loads_when_another_products_app_package_is_already_imported(monkeypatch):
    """Regression (2026-09-29): the calibration tests passed alone and failed
    in the full MCP suite — another test had already put a DIFFERENT
    product's top-level `app` package in `sys.modules`, so a package-name
    import of `app.services.divergencia_resolucao` resolved against it, and
    the old cleanup popped that caller's `app` in turn."""
    import types

    intruso = types.ModuleType("app")
    intruso.__path__ = []  # a package with nothing in it
    monkeypatch.setitem(sys.modules, "app", intruso)

    politica = dc._load_current_policy()

    assert "nome_oficial" in politica
    assert sys.modules["app"] is intruso  # the other caller's package is untouched
