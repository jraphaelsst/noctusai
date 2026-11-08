"""Staleness loop of the BR tax-parameter registry: the report tool, its telemetry + `finance_param_fresh`
reconcile predicate, and the two keepers (`check_finance_params_schema`, `check_tax_canon_no_inline_params`).

Fixtures build a throw-away tree carrying a COPY of the real registry.py + fixture YAML, so every test runs the
real loader against a controlled clock.
"""
from __future__ import annotations

import json
import shutil
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from settings import REPO_ROOT  # noqa: E402
from tools.noctus.dev import auto_improvement as ai  # noqa: E402
from tools.noctus.dev import finance_params_staleness as fps  # noqa: E402
from tools.noctus.dev.compliance import (  # noqa: E402
    check_finance_params_schema,
    check_tax_canon_no_inline_params,
    write_tax_canon_baseline,
)

TODAY = date(2026, 11, 7)
POLICY = "max_age_dias: {norma: 365, orgao_oficial: 180, publicacao_tecnica: 90, especialista: 90}\nhorizonte_vigencia_dias: 45\n"


def _row(key="simples.fator_r.limiar", value='"0.28"', unit="ratio", de="2018-01-01", ate="null", tier="norma",
         verificado="2026-11-01", urls='["https://a.gov.br"]'):
    return (f"  - key: {key}\n    value: {value}\n    unit: {unit}\n    scope: {{regime: [simples]}}\n"
            f"    vigencia_de: {de}\n    vigencia_ate: {ate}\n    norma: \"Norma X\"\n    fonte_url: {urls}\n"
            f"    tier: {tier}\n    verificado_em: {verificado}\n    verificado_por: \"t\"\n    revalidar_em: null\n")


def make_tree(tmp_path: Path, *rows: str) -> Path:
    pdir = tmp_path / fps.PARAMS_REL
    pdir.mkdir(parents=True)
    shutil.copy(REPO_ROOT / fps.PARAMS_REL / "registry.py", pdir / "registry.py")
    (pdir / "_policy.yaml").write_text(POLICY)
    (pdir / "simples.yaml").write_text("rows:\n" + "".join(rows))
    return tmp_path


class TestReport:
    def test_fresh_is_ok(self, tmp_path):
        rep = fps.report(TODAY, make_tree(tmp_path, _row()))
        assert rep["status"] == "ok" and not rep["escalate"] and rep["counts"]["stale_keys"] == 0

    def test_verificacao_vencida_not_escalating(self, tmp_path):
        rep = fps.report(TODAY, make_tree(tmp_path, _row(verificado="2025-01-01")))
        assert rep["status"] == "stale" and not rep["escalate"]
        row = rep["grouped"]["verificacao_vencida"][0]
        assert row["key"] == "simples.fator_r.limiar" and row["norma"] == "Norma X" and row["fonte_url"] and row["dias"] > 0

    def test_vigencia_terminando_far_does_not_escalate(self, tmp_path):
        rep = fps.report(TODAY, make_tree(tmp_path, _row(ate="2026-12-20")))  # 43 days
        assert list(rep["grouped"]) == ["vigencia_terminando"] and rep["escalate"] is False

    def test_vigencia_terminando_close_escalates(self, tmp_path):
        rep = fps.report(TODAY, make_tree(tmp_path, _row(ate="2026-11-20")))  # 13 days
        assert rep["escalate"] is True and rep["status"] == "escalate"

    def test_vigencia_encerrada_sem_sucessor_escalates(self, tmp_path):
        rep = fps.report(TODAY, make_tree(tmp_path, _row(ate="2026-10-01")))
        assert "vigencia_encerrada_sem_sucessor" in rep["grouped"] and rep["escalate"] is True

    def test_successor_clears_the_ending_row(self, tmp_path):
        old = _row(ate="2026-11-20")
        new = _row(de="2026-11-21", value='"0.30"')
        rep = fps.report(TODAY, make_tree(tmp_path, old, new))
        assert rep["status"] == "ok"

    def test_unreadable_registry_is_inconclusive_not_green(self, tmp_path):
        tree = make_tree(tmp_path, _row())
        (tree / fps.PARAMS_REL / "simples.yaml").write_text("rows: [not: valid")
        rep = fps.report(TODAY, tree)
        assert rep["status"] == "inconclusive" and rep["ok"] is False and rep["error"]


class TestTelemetry:
    @pytest.fixture
    def ledger(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ai, "CACHE_DIR", tmp_path / "c")
        monkeypatch.setattr(ai, "CACHE_PATH", tmp_path / "c" / "ai.sqlite")
        monkeypatch.setattr(ai, "LEDGER_PATH", tmp_path / "ph" / "auto-improvement.ndjson")
        return ai.LEDGER_PATH

    def test_log_writes_one_drift_per_key_with_closure_predicate_and_summary(self, tmp_path, ledger):
        tree = make_tree(tmp_path / "t", _row(verificado="2025-01-01"))
        rep = fps.report(TODAY, tree)
        out = fps.log_telemetry(rep, TODAY)
        assert out["logged"] == ["simples.fator_r.limiar"] and not out["errors"]
        rows = [json.loads(line) for line in ledger.read_text().splitlines()]
        drift = [r for r in rows if r["kind"] == "drift"]
        assert len(drift) == 1 and drift[0]["target"] == "finance-params:simples.fator_r.limiar"
        assert drift[0]["resolve_when"] == "finance_param_fresh:simples.fator_r.limiar"
        assert any(r["target"] == "finance-params:run-summary" and "stale=1" in r["description"] for r in rows)
        # a second run does not duplicate the still-open drift row
        assert fps.log_telemetry(rep, TODAY)["logged"] == []

    def test_predicate_flips_when_registry_is_fresh(self, tmp_path):
        key = "simples.fator_r.limiar"
        stale_tree = make_tree(tmp_path / "a", _row(verificado="2020-01-01"))
        ok, _ = ai._eval_predicate(f"finance_param_fresh:{key}", [], {}, stale_tree)
        assert ok is False
        fresh_tree = make_tree(tmp_path / "b", _row(verificado=date.today().isoformat()))
        ok, detail = ai._eval_predicate(f"finance_param_fresh:{key}", [], {}, fresh_tree)
        assert ok is True, detail

    def test_predicate_unreadable_registry_is_loud_false(self, tmp_path):
        ok, detail = ai._eval_predicate("finance_param_fresh:x.y", [], {}, tmp_path)
        assert ok is False and "unreadable" in detail


class TestFinanceParamsSchema:
    def test_real_registry_is_clean(self):
        assert check_finance_params_schema(REPO_ROOT) == []

    def test_no_registry_in_tree_is_skipped(self, tmp_path):
        assert check_finance_params_schema(tmp_path) == []

    def test_clean_fixture(self, tmp_path):
        assert check_finance_params_schema(make_tree(tmp_path, _row())) == []

    def test_float_value_fires(self, tmp_path):
        issues = check_finance_params_schema(make_tree(tmp_path, _row(value="0.28", unit="text")))
        assert len(issues) == 1 and "float" in issues[0]["issue"]

    def test_especialista_single_url_fires(self, tmp_path):
        issues = check_finance_params_schema(make_tree(tmp_path, _row(tier="especialista")))
        assert issues and "especialista" in issues[0]["issue"]

    def test_future_verificado_em_fires(self, tmp_path):
        issues = check_finance_params_schema(make_tree(tmp_path, _row(verificado="2999-01-01")))
        assert issues and "future" in issues[0]["issue"]

    def test_overlap_fires(self, tmp_path):
        issues = check_finance_params_schema(make_tree(tmp_path, _row(), _row(de="2020-01-01")))
        assert issues and "overlapping" in issues[0]["issue"]

    def test_unknown_family_file_fires(self, tmp_path):
        tree = make_tree(tmp_path, _row())
        (tree / fps.PARAMS_REL / "typo_family.yaml").write_text("rows: []\n")
        issues = check_finance_params_schema(tree)
        assert any("not a known family" in i["issue"] for i in issues)


CANON_REL = "KNOWLEDGE-BASE/CONTEXT/PATTERNS/finance/br-tax-advisor-canon.md"


def with_canon(tree: Path, text: str) -> Path:
    p = tree / CANON_REL
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    return tree


class TestTaxCanonNoInlineParams:
    def _tree(self, tmp_path, canon):
        return with_canon(make_tree(tmp_path, _row(), _row(key="mei.teto", value="8100000", unit="brl_centavos")), canon)

    def test_canon_absent_is_skipped(self, tmp_path):
        assert check_tax_canon_no_inline_params(make_tree(tmp_path, _row())) == []

    def test_bare_literal_fires(self, tmp_path):
        issues = check_tax_canon_no_inline_params(self._tree(tmp_path, "Fator R >= 28% => Anexo III.\n"))
        assert len(issues) == 1 and "simples.fator_r.limiar" in issues[0]["issue"] and issues[0]["file"].endswith(":1")

    def test_literal_next_to_key_passes(self, tmp_path):
        assert check_tax_canon_no_inline_params(self._tree(tmp_path, "Fator R >= 28% (`simples.fator_r.limiar`).\n")) == []

    def test_brl_literal_fires_and_mil_form_matches(self, tmp_path):
        issues = check_tax_canon_no_inline_params(self._tree(tmp_path, "Teto R$ 81.000,00 por ano.\nTeto R$ 81 mil.\n"))
        assert len(issues) == 2

    def test_unrelated_numbers_and_fences_and_escape_pass(self, tmp_path):
        canon = ("Aliquota 6% e R$ 180 mil de RBT12.\n```\nFator 28%\n```\n"
                 "Fator 28% <!-- noc-allow: tax-literal - historical 2017 rule -->\n")
        assert check_tax_canon_no_inline_params(self._tree(tmp_path, canon)) == []

    def test_baseline_tolerates_existing_and_shrinks_never_grows(self, tmp_path):
        tree = self._tree(tmp_path, "Fator R >= 28%.\n")
        assert write_tax_canon_baseline("init", tree)["entries"] == 1
        assert check_tax_canon_no_inline_params(tree) == []
        assert write_tax_canon_baseline("init", tree)["ok"] is False  # never grows
        with_canon(tree, "Fator R >= 28%.\nNovo 28% aqui.\n")
        assert len(check_tax_canon_no_inline_params(tree)) == 1  # only the NEW line
        with_canon(tree, "limpo\n")
        assert write_tax_canon_baseline("shrink", tree)["entries"] == 0

    def test_unreadable_registry_is_a_finding_not_a_pass(self, tmp_path):
        tree = self._tree(tmp_path, "28%\n")
        (tree / fps.PARAMS_REL / "simples.yaml").write_text("rows: [broken")
        issues = check_tax_canon_no_inline_params(tree)
        assert issues and "cannot compare" in issues[0]["issue"]
