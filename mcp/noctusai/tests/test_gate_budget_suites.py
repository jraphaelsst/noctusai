"""Scoped-check (`ci_parity:suite:*`) budgets ride the declared per-product rows, never a flat default."""
from __future__ import annotations

import argparse
import sys

import pytest

from tools.noctus.dev import gate_budget as gb


class TestSuiteBudgetsFollowDeclaredRows:
    def test_product_suite_uses_the_declared_pytest_row(self):
        assert gb.resolve_gate_budget("ci_parity:suite:product:social-wiring") == gb.GATE_BUDGETS_S["pytest:social-wiring"]

    def test_seed_suite_uses_the_declared_pytest_row(self):
        assert gb.resolve_gate_budget("ci_parity:suite:seed:seed/lib/backend") == gb.GATE_BUDGETS_S["pytest:seed/lib/backend"]

    def test_undeclared_product_falls_to_the_generic_pytest_row(self):
        assert gb.resolve_gate_budget("ci_parity:suite:product:core") == gb.GATE_BUDGETS_S["pytest:"]

    def test_db_guards_keep_the_suite_prefix_row(self):
        assert gb.resolve_gate_budget("ci_parity:suite:db-guards:core") == gb.GATE_BUDGETS_S["ci_parity:suite:"]

    def test_declared_sw_and_seed_cover_measured_loaded_runs(self):
        # measured (~/.noctus/hw-runs, 2026-11-06..14): full SW suite 684-1025 s quiet, 1285 s + 2208 s under load;
        # seed/lib/backend 277-419 s quiet, 938 s under load (gate-verdicts).
        assert gb.GATE_BUDGETS_S["pytest:social-wiring"] >= 1800
        assert gb.GATE_BUDGETS_S["pytest:seed/lib/backend"] >= 1200
        assert gb.MAX_GATE_BUDGET_S >= gb.GATE_BUDGETS_S["pytest:social-wiring"]

    def test_env_override_still_wins_on_the_ci_parity_name(self, monkeypatch):
        monkeypatch.setenv("NOCTUS_GATE_BUDGETS_JSON", '{"ci_parity:suite:product:social-wiring": 77}')
        assert gb.resolve_gate_budget("ci_parity:suite:product:social-wiring") == 77

    def test_env_override_of_the_declared_row_reaches_the_suite(self, monkeypatch):
        monkeypatch.setenv("NOCTUS_GATE_BUDGETS_JSON", '{"pytest:social-wiring": 91}')
        assert gb.resolve_gate_budget("ci_parity:suite:product:social-wiring") == 91


class TestDidYouMean:
    def _parse(self, argv, capsys):
        import cli
        parser = cli.build_parser()
        with pytest.raises(SystemExit) as e:
            parser.parse_args(argv)
        assert e.value.code == 2
        return capsys.readouterr().err

    def test_abbreviated_flag_names_the_full_flag(self, capsys):
        err = self._parse(["--check-workflow-cli-flag"], capsys)
        assert "did you mean --check-workflow-cli-flags-exist" in err

    def test_typo_flag_gets_a_close_match(self, capsys):
        err = self._parse(["--cleanup-stale-worktree"], capsys)
        assert "did you mean --cleanup-stale-worktrees" in err

    def test_garbage_flag_has_no_false_hint(self, capsys):
        err = self._parse(["--zzzzqqqq"], capsys)
        assert "did you mean" not in err

    def test_steward_run_scoped_help_names_request(self):
        import cli
        act = next(a for a in cli.build_parser()._actions if "--steward-run-scoped" in a.option_strings)
        assert "request" in act.help
