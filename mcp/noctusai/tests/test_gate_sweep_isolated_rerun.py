"""pytest failing nodeids + re-run-once-alone under load (2026-11-04).

noctusai-04's integrates 4 and 5 each redded on a DIFFERENT timing-sensitive
test that was green in isolation, and the pytest red carried no name at all.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.noctus.dev import gate_sweep as GS  # noqa: E402

PYTEST_OUT = (
    "....F...\n"
    "=========================== short test summary info ============================\n"
    "FAILED tests/test_a.py::TestX::test_y - AssertionError: assert 1 == 2\n"
    "ERROR tests/test_b.py::test_z - fixture 'db' not found\n"
    "1 failed, 1797 passed, 1 error in 61.2s\n"
)
VITEST_OUT = " FAIL  src/organs.test.tsx > organs > status goes to the server\nAssertionError: expected 0 to be 1"


def _busy():
    return (40.0, 8)


def _quiet():
    return (2.0, 8)


def _runner(results, calls):
    def run_gate(spec):
        calls.append(list(spec.argv))
        return results[min(len(calls), len(results)) - 1]
    return run_gate


def _pytest_spec(tmp_path: Path) -> GS.GateSpec:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_a.py").write_text("")
    (tmp_path / "tests" / "test_b.py").write_text("")
    return GS.GateSpec("pytest:core", ["py", "-m", "pytest", "-q"], tmp_path)


def test_pytest_failing_tests_parses_failed_and_error_nodeids():
    assert GS.pytest_failing_tests(PYTEST_OUT) == [
        "tests/test_a.py::TestX::test_y", "tests/test_b.py::test_z"]


def test_pytest_red_names_its_failing_tests_even_on_a_quiet_host(tmp_path):
    calls: list = []
    e = GS._run_one_gate(_pytest_spec(tmp_path), _runner([(1, "x", 60.0, PYTEST_OUT)], calls),
                         None, load_reader=_quiet)
    assert len(calls) == 1 and GS._verdict([e]) == "red"
    assert e["failing_tests"] == ["tests/test_a.py::TestX::test_y", "tests/test_b.py::test_z"]
    assert "tests/test_a.py::TestX::test_y" in e["summary"]


def test_pytest_red_then_green_alone_under_load_is_a_logged_false_red(tmp_path):
    calls: list = []
    e = GS._run_one_gate(_pytest_spec(tmp_path),
                         _runner([(1, "x", 60.0, PYTEST_OUT), (0, "2 passed", 3.0, "2 passed")], calls),
                         None, load_reader=_busy)
    assert calls[1][-2:] == ["tests/test_a.py::TestX::test_y", "tests/test_b.py::test_z"]
    assert e["exit_code"] == 0 and e["false_red"] is True and GS._verdict([e]) == "green"
    assert e["flaky_under_load"]["load_per_core"] == 5.0
    assert "failing_tests" not in e


def test_pytest_red_twice_is_a_real_red_with_both_runs(tmp_path):
    again = "FAILED tests/test_a.py::TestX::test_y - AssertionError\n1 failed, 1 passed\n"
    calls: list = []
    e = GS._run_one_gate(_pytest_spec(tmp_path),
                         _runner([(1, "x", 60.0, PYTEST_OUT), (1, "x", 3.0, again)], calls),
                         None, load_reader=_busy)
    assert GS._verdict([e]) == "red" and "false_red" not in e
    assert e["failing_tests"] == ["tests/test_a.py::TestX::test_y"]
    assert e["rerun_after_failure"]["failing_tests"] == [
        "tests/test_a.py::TestX::test_y", "tests/test_b.py::test_z"]


def test_unaddressable_nodeids_are_not_rerun(tmp_path):
    calls: list = []
    spec = GS.GateSpec("pytest:core", ["py", "-m", "pytest", "-q"], tmp_path)   # no tests/ dir
    e = GS._run_one_gate(spec, _runner([(1, "x", 60.0, PYTEST_OUT)], calls), None, load_reader=_busy)
    assert len(calls) == 1 and GS._verdict([e]) == "red" and "rerun_skipped" in e


def test_rerun_usage_error_keeps_the_first_red(tmp_path):
    calls: list = []
    e = GS._run_one_gate(_pytest_spec(tmp_path),
                         _runner([(1, "x", 60.0, PYTEST_OUT), (4, "usage", 1.0, "ERROR: not found")], calls),
                         None, load_reader=_busy)
    assert GS._verdict([e]) == "red" and e["rerun_no_verdict"]["exit_code"] == 4


def test_vitest_assertion_red_reruns_failing_file_alone_under_load():
    calls: list = []
    spec = GS.GateSpec("vitest:seed/lib/frontend", ["npm", "test"], Path("."))
    e = GS._run_one_gate(spec, _runner([(1, "x", 30.0, VITEST_OUT), (0, "ok", 2.0, "ok")], calls),
                         None, load_reader=_busy)
    assert calls[1] == ["npm", "test", "--", "src/organs.test.tsx", "--no-file-parallelism"]
    assert e["false_red"] is True and GS._verdict([e]) == "green"


def test_vitest_assertion_red_on_quiet_host_is_not_rerun():
    calls: list = []
    spec = GS.GateSpec("vitest:seed/lib/frontend", ["npm", "test"], Path("."))
    e = GS._run_one_gate(spec, _runner([(1, "x", 30.0, VITEST_OUT), (0, "ok", 2.0, "ok")], calls),
                         None, load_reader=_quiet)
    assert len(calls) == 1 and GS._verdict([e]) == "red"


def test_many_failures_are_not_rerun_even_under_load(tmp_path):
    out = "".join(f"FAILED tests/test_a.py::test_{i} - x\n" for i in range(GS.RERUN_MAX_FAILING + 1))
    calls: list = []
    e = GS._run_one_gate(_pytest_spec(tmp_path), _runner([(1, "x", 60.0, out)], calls),
                         None, load_reader=_busy)
    assert len(calls) == 1 and GS._verdict([e]) == "red"
