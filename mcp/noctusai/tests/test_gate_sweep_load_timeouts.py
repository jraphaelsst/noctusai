"""Load-induced vitest timeouts + final gate timeouts (2026-10-24, verdict-channel integrity)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.noctus.dev import gate_sweep as GS  # noqa: E402

FILES = ["src/a.test.tsx", "src/b.test.tsx"]
TIMEOUT_OUT = "\n".join(
    f" FAIL  {f} > suite > case{i}\nError: Test timed out in 11000ms." for i, f in enumerate(FILES))
ASSERT_OUT = " FAIL  src/a.test.tsx > suite > case0\nAssertionError: expected 1 to be 2"


def _run(first, second, calls):
    def run_gate(spec):
        calls.append(list(spec.argv))
        return first if len(calls) == 1 else second
    return run_gate


def _entry(run_gate):
    return GS._run_one_gate(GS.GateSpec("vitest:p", ["npm", "test"], Path(".")), run_gate, None)


def test_timeout_shaped_failure_rerun_serially_on_failing_files_passes_is_not_red():
    calls: list = []
    e = _entry(_run((1, "x", 12.0, TIMEOUT_OUT), (0, "ok", 3.0, "ok"), calls))
    assert len(calls) == 2
    assert calls[1][-1] == "--no-file-parallelism" and FILES[0] in calls[1] and FILES[1] in calls[1]
    assert e["exit_code"] == 0 and e["ran"] and "flaky_under_load" in e
    assert GS._verdict([e]) == "green"


def test_timeout_again_on_rerun_is_inconclusive_never_red():
    calls: list = []
    e = _entry(_run((1, "x", 12.0, TIMEOUT_OUT), (1, "x", 12.0, TIMEOUT_OUT), calls))
    assert e["harness_suspect"]["signature"] == "vitest_timeout_under_load"
    assert GS._verdict([e]) == "inconclusive"


def test_rerun_without_verdict_is_inconclusive():
    calls: list = []
    e = _entry(_run((1, "x", 12.0, TIMEOUT_OUT), (None, "timeout after 5s", 5.0), calls))
    assert GS._verdict([e]) == "inconclusive"


def test_real_assertion_failure_is_not_rerun_and_stays_red():
    calls: list = []
    e = _entry(_run((1, "x", 1.0, ASSERT_OUT), (0, "ok", 1.0, "ok"), calls))
    assert len(calls) == 1 and GS._verdict([e]) == "red"


def test_mixed_timeout_and_assertion_is_not_timeout_shaped():
    out = TIMEOUT_OUT + "\n FAIL  src/c.test.tsx > s > c\nAssertionError: nope"
    assert not GS.vitest_failures_timeout_shaped(out, GS.vitest_failing_tests(out))


def test_rerun_real_failure_stays_red_with_rerun_tests():
    calls: list = []
    e = _entry(_run((1, "x", 1.0, TIMEOUT_OUT), (1, "x", 1.0, ASSERT_OUT), calls))
    assert e["failing_tests"] == ["src/a.test.tsx > suite > case0"] and GS._verdict([e]) == "red"


def test_final_gate_timeout_is_inconclusive_not_incomplete_or_green():
    e = _entry(lambda spec: (None, "timeout after 900s", 900.0))
    assert e["timed_out"] is True and GS._verdict([e]) == "inconclusive"
