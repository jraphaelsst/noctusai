"""The scoped toolkit stage's budget is DERIVED from measured per-file cost, never a flat constant (2026-11-15).

Evidence (~/.noctus/hw-admission.ndjson `deliverable:feat/keeper-node-toolchain`, head e2d33579e, 230 scoped test files):
the stage hit the generic `ci_parity:suite:` 600 s row, timed out at 600 s and again at 900 s (deliverable 1919.7 s =
~420 s of other stages + 1500 s), and finished in <= 1170 s once re-run with a hand-set 2400 s budget (1593.4 s - ~420 s)
= 5.1 s/file on a loaded laptop.
"""
from __future__ import annotations

import pytest

from tools.noctus.dev import gate_budget as gb
from tools.noctus.dev import release_steward as RS

GATE = "ci_parity:suite:mcp_toolkit_tests:scoped"
MEASURED_STAGE_S, MEASURED_FILES = 1170, 230


class TestTheScopedToolkitStageIsNoLongerOnTheFlatPrefixRow:
    def test_it_follows_its_declared_row_not_the_600s_suite_prefix(self):
        assert gb.resolve_gate_budget(GATE) == gb.GATE_BUDGETS_S["mcp_toolkit_tests:scoped"] != gb.GATE_BUDGETS_S["ci_parity:suite:"]

    def test_the_measured_230_file_stage_fits_inside_the_first_attempt(self):
        assert gb.resolve_gate_budget(GATE, files=MEASURED_FILES) >= MEASURED_STAGE_S * 1.4

    def test_the_budget_scales_with_the_selected_files(self):
        small, big = gb.resolve_gate_budget(GATE, files=10), gb.resolve_gate_budget(GATE, files=230)
        assert small < 300 < big
        assert big == round(gb.PER_FILE_FIXED_S + 230 * gb.PER_FILE_S["mcp_toolkit_tests:scoped"] * gb.PER_FILE_HEADROOM)

    def test_the_bare_gate_name_the_integrate_sweep_uses_is_sized_the_same_way(self):
        assert gb.resolve_gate_budget("mcp_toolkit_tests:scoped", files=230) == gb.resolve_gate_budget(GATE, files=230)

    def test_an_explicit_override_still_wins(self, monkeypatch):
        monkeypatch.setenv("NOCTUS_GATE_BUDGETS_JSON", '{"%s": 77}' % GATE)
        assert gb.resolve_gate_budget(GATE, files=230) == 77

    def test_other_suites_are_untouched_by_the_file_count(self):
        assert gb.resolve_gate_budget("ci_parity:suite:db-guards:core", files=50) == gb.GATE_BUDGETS_S["ci_parity:suite:"]


class TestCountTestFiles:
    def test_counts_distinct_files_not_node_ids(self):
        argv = ["-m", "pytest", "mcp/noctusai/tests/test_a.py", "mcp/noctusai/tests/test_a.py::T::t", "tests/test_b.py", "-q"]
        assert gb.count_test_files(argv) == 2


class TestMeasuredCostReplacesTheSeed:
    def _rec(self, elapsed, files=100, completed=True, gate="mcp_toolkit_tests:scoped"):
        return {"gate": gate, "files": files, "elapsed_s": elapsed, "completed": completed}

    def test_below_three_records_the_seed_stands(self):
        assert gb.p90_per_file_s([self._rec(560), self._rec(560)], "mcp_toolkit_tests:scoped") is None

    def test_p90_of_measured_per_file_cost(self):
        recs = [self._rec(60 + 100 * c) for c in (2, 3, 4, 5, 6, 7, 8, 9, 10, 11)]
        assert gb.p90_per_file_s(recs, "mcp_toolkit_tests:scoped") == 11.0

    def test_timeouts_small_runs_and_other_gates_are_not_evidence(self):
        recs = [self._rec(9999, completed=False), self._rec(100, files=3), self._rec(100, gate="other")] * 3
        assert gb.p90_per_file_s(recs, "mcp_toolkit_tests:scoped") is None

    def test_a_measured_cost_sizes_the_budget(self):
        assert gb.resolve_gate_budget(GATE, files=100, per_file_s=8.0) == round(60 + 100 * 8.0 * 1.5)


class TestTimingStore:
    def test_round_trips_and_a_missing_store_is_empty(self, tmp_path):
        store = tmp_path / "t.ndjson"
        assert RS.read_stage_timings(store) == []
        RS.record_stage_timing(store, {"gate": "g", "files": 3, "elapsed_s": 1.0, "completed": True})
        (row,) = RS.read_stage_timings(store)
        assert row["gate"] == "g" and row["ts"]


class TestTimeoutReportsEvidence:
    PARTIAL = (
        "tests/test_a.py::TestA::test_one PASSED [  1%]\n"
        "tests/test_b.py::TestB::test_slow \n"
    )

    def test_running_tests_are_the_item_lines_with_no_verdict(self):
        assert RS.running_tests(self.PARTIAL) == ["tests/test_b.py::TestB::test_slow"]
        assert RS.running_tests(self.PARTIAL.encode()) == ["tests/test_b.py::TestB::test_slow"]  # TimeoutExpired gives bytes

    def test_dots_only_output_names_nothing_rather_than_guessing(self):
        assert RS.running_tests("....F...\n") == []

    def test_the_message_has_elapsed_budget_basis_and_running_tests(self):
        msg = str(RS._CiParityTimeout(GATE, [1819, 2728], 4547.2, "derived (60s + 230 files x per-file cost x 1.5)",
                                      ["tests/test_b.py::TestB::test_slow"]))
        assert "4547s spent in total" in msg and "1819s" in msg and "2728s" in msg
        assert "derived (60s + 230 files" in msg and "still running when killed: tests/test_b.py::TestB::test_slow" in msg
        assert "NOCTUS_GATE_BUDGETS_JSON" in msg

    def test_unknown_running_tests_say_so(self):
        assert "still running: unknown" in str(RS._CiParityTimeout(GATE, [1, 2], 3.0, "", []))


@pytest.mark.parametrize("gate", ["mcp_toolkit_tests:scoped"])
def test_the_per_file_seed_is_a_declared_gate(gate):
    assert gate in gb.PER_FILE_S and gb.declared_gate_budget(gate) is not None
