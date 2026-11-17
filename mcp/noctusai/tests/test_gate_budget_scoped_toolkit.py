"""The scoped toolkit stage's budget is DERIVED from the selected files' MEASURED cost, never a flat constant (2026-11-15).

Evidence: `feat/keeper-node-toolchain` (head e2d33579e, 230 scoped test files) hit the generic `ci_parity:suite:` 600 s row, timed out at
600 s and again at 900 s, and needed a hand-set 2400 s budget. Then `feat/scoped-toolkit-budget`'s first, flat s/file model (5.1 s/file)
sized a 27-file selection at 267 s and timed out too (667 s spent; test_task_branch_cleanup_ownership.py still running): per-file
cost is not flat. One measured run of the 232-file selection (4107 tests, 1704 s, rc=0) gave per-file seconds: median 1.75 s,
test_compliance.py alone 389 s. The budget is therefore FIXED + 1.5 x sum(cost of the selected files).
"""
from __future__ import annotations

from tools.noctus.dev import gate_budget as gb
from tools.noctus.dev import release_steward as RS

GATE = "ci_parity:suite:mcp_toolkit_tests:scoped"
MEASURED_232_FILE_RUN_S = 1704
HEAVY = ["test_compliance.py", "test_task_branch_cleanup_ownership.py"]
LIGHT = [f"test_light_{i}.py" for i in range(200)]


class TestTheScopedToolkitStageIsNoLongerOnTheFlatPrefixRow:
    def test_it_follows_its_declared_row_not_the_600s_suite_prefix(self):
        assert gb.resolve_gate_budget(GATE) == gb.GATE_BUDGETS_S["mcp_toolkit_tests:scoped"] != gb.GATE_BUDGETS_S["ci_parity:suite:"]

    def test_the_declared_fallback_covers_the_measured_full_selection(self):
        assert gb.GATE_BUDGETS_S["mcp_toolkit_tests:scoped"] >= MEASURED_232_FILE_RUN_S * 1.4

    def test_a_selection_with_the_heavy_files_gets_their_measured_cost(self):
        b = gb.resolve_gate_budget(GATE, files=HEAVY)
        assert b >= gb.PER_FILE_FIXED_S + 1.5 * (gb.SEED_FILE_S["test_compliance.py"] + gb.SEED_FILE_S["test_task_branch_cleanup_ownership.py"])

    def test_the_27_file_selection_that_timed_out_at_267s_is_no_longer_sized_that_way(self):
        # the failed request: 27 files, 667 s spent without a verdict. Its heavy files alone are seeded far above 267 s.
        files = ["test_task_branch.py", "test_task_branch_cleanup_ownership.py", "test_guardian_pure_push_enqueue.py",
                 "test_check_guardian_tool_authorship.py", "test_lying_loading_state_detector.py", "test_migration_replay.py",
                 "test_check_silent_refusal.py", "test_check_motion_import_boundary.py"] + LIGHT[:19]
        assert gb.resolve_gate_budget(GATE, files=files) > 400

    def test_many_light_files_are_cheap_and_scale_linearly(self):
        assert gb.resolve_gate_budget(GATE, files=LIGHT[:10]) < gb.resolve_gate_budget(GATE, files=LIGHT[:100])
        assert gb.resolve_gate_budget(GATE, files=LIGHT[:10]) == round(gb.PER_FILE_FIXED_S + 1.5 * 10 * gb.DEFAULT_FILE_S)

    def test_the_bare_gate_name_the_integrate_sweep_uses_is_sized_the_same_way(self):
        assert gb.resolve_gate_budget("mcp_toolkit_tests:scoped", files=HEAVY) == gb.resolve_gate_budget(GATE, files=HEAVY)

    def test_an_explicit_override_still_wins(self, monkeypatch):
        monkeypatch.setenv("NOCTUS_GATE_BUDGETS_JSON", '{"%s": 77}' % GATE)
        assert gb.resolve_gate_budget(GATE, files=HEAVY) == 77

    def test_other_suites_are_untouched_by_the_file_list(self):
        assert gb.resolve_gate_budget("ci_parity:suite:db-guards:core", files=HEAVY) == gb.GATE_BUDGETS_S["ci_parity:suite:"]

    def test_the_seed_covers_the_measured_run(self):
        # 26 heavy seeded files + 206 default-cost files must land near the measured 1674 s of test time
        est = gb.estimate_files_s(list(gb.SEED_FILE_S) + [f"test_x_{i}.py" for i in range(206)])
        assert 1500 < est < 1800


class TestTestFiles:
    def test_distinct_basenames_not_node_ids(self):
        argv = ["-m", "pytest", "mcp/noctusai/tests/test_a.py", "mcp/noctusai/tests/test_a.py::T::t", "tests/test_b.py", "-q"]
        assert gb.test_files(argv) == ["test_a.py", "test_b.py"]


class TestMeasuredCostReplacesTheSeed:
    def _rec(self, secs, completed=True, gate="mcp_toolkit_tests:scoped"):
        return {"gate": gate, "completed": completed, "file_s": {"test_compliance.py": secs}}

    def test_a_file_needs_three_observations_before_it_replaces_its_seed(self):
        assert gb.measured_file_costs([self._rec(500), self._rec(500)], "mcp_toolkit_tests:scoped") == {}

    def test_p90_of_the_live_observations(self):
        recs = [self._rec(float(c)) for c in range(100, 110)]
        assert gb.measured_file_costs(recs, "mcp_toolkit_tests:scoped") == {"test_compliance.py": 109.0}

    def test_timeouts_and_other_gates_are_not_evidence(self):
        recs = [self._rec(999, completed=False), self._rec(999, gate="other")] * 3
        assert gb.measured_file_costs(recs, "mcp_toolkit_tests:scoped") == {}

    def test_a_live_measurement_sizes_the_budget(self):
        assert gb.resolve_gate_budget(GATE, files=["test_compliance.py"], measured={"test_compliance.py": 800.0}) == 60 + 1200


class TestDurationsParsing:
    OUT = (
        "12.50s call     tests/test_a.py::TestA::test_one\n"
        "3.00s setup    tests/test_a.py::TestA::test_one\n"
        "0.40s call     mcp/noctusai/tests/test_b.py::test_x\n"
        "tests/test_a.py::TestA::test_one PASSED [ 1%]\n"
    )

    def test_sums_setup_call_teardown_per_file_and_drops_the_light_ones(self):
        assert gb.parse_file_durations(self.OUT) == {"test_a.py": 15.5}


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
        msg = str(RS._CiParityTimeout(GATE, [1819, 2728], 4547.2, "derived (60s + 1.5 x measured seconds of 230 selected files)",
                                      ["tests/test_b.py::TestB::test_slow"]))
        assert "4547s spent in total" in msg and "1819s" in msg and "2728s" in msg
        assert "derived (60s + 1.5 x measured" in msg and "still running when killed: tests/test_b.py::TestB::test_slow" in msg
        assert "NOCTUS_GATE_BUDGETS_JSON" in msg

    def test_unknown_running_tests_say_so(self):
        assert "still running: unknown" in str(RS._CiParityTimeout(GATE, [1, 2], 3.0, "", []))
