"""noctus.dev.hw_admission — budget resolution, admission verdicts, slots, log."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from tools.noctus.dev import hw_admission as hw

KNOBS = {"max_heavy": 1, "min_cpu_idle_pct": 50, "cpu_sample_s": 1, "min_reclaimable_mb": 1536,
         "max_swapout_per_s": 50, "max_claude_sessions_advisory": 3, "wait_s": 0, "poll_s": 0}
GOOD = {"cpu_idle_pct": 80.0, "reclaimable_mb": 3000, "swapout_per_s": 0.0, "claude_sessions": 2}


@pytest.fixture()
def env(tmp_path, monkeypatch):
    budget = tmp_path / "budget.json"
    budget.write_text(json.dumps({
        "phase": "build",
        "phases": {"build": KNOBS, "big": {**KNOBS, "max_heavy": 2}},
        "hosts": {"box-a": {"phase": "big", "overrides": {"min_reclaimable_mb": 4096}}},
    }))
    monkeypatch.setenv("NOCTUS_HW_BUDGET_PATH", str(budget))
    monkeypatch.setenv("NOCTUS_HW_SLOT_DIR", str(tmp_path / "slots"))
    monkeypatch.setenv("NOCTUS_HW_LOG", str(tmp_path / "log.ndjson"))
    monkeypatch.delenv("NOCTUS_HW_PHASE", raising=False)
    monkeypatch.delenv("NOCTUS_HW_SLOT_HELD", raising=False)
    return tmp_path


def _rows(env):
    p = env / "log.ndjson"
    return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []


class TestBudget:
    def test_default_phase(self, env):
        b = hw.load_budget(host="unknown-host")
        assert b["phase"] == "build" and b["max_heavy"] == 1

    def test_host_profile_and_override(self, env):
        b = hw.load_budget(host="box-a")
        assert b["phase"] == "big" and b["max_heavy"] == 2 and b["min_reclaimable_mb"] == 4096

    def test_env_phase_wins(self, env, monkeypatch):
        monkeypatch.setenv("NOCTUS_HW_PHASE", "big")
        assert hw.load_budget(host="unknown-host")["phase"] == "big"

    def test_unknown_phase_is_an_error_not_no_gate(self, env, monkeypatch):
        monkeypatch.setenv("NOCTUS_HW_PHASE", "nope")
        with pytest.raises(hw.BudgetError):
            hw.load_budget()

    def test_missing_file_is_an_error(self, env, monkeypatch):
        monkeypatch.setenv("NOCTUS_HW_BUDGET_PATH", str(env / "absent.json"))
        with pytest.raises(hw.BudgetError):
            hw.load_budget()

    def test_repo_budget_file_is_valid(self, monkeypatch):
        monkeypatch.delenv("NOCTUS_HW_BUDGET_PATH", raising=False)
        b = hw.load_budget(host="any-host")
        assert b["phase"] == "build" and b["max_heavy"] >= 1


class TestEvaluate:
    def test_all_good_admits(self):
        assert hw.evaluate(GOOD, KNOBS) == []

    @pytest.mark.parametrize("key,val,needle", [
        ("cpu_idle_pct", 45.0, "cpu_idle"),
        ("reclaimable_mb", 1000, "reclaimable"),
        ("swapout_per_s", 50.0, "swapout"),
    ])
    def test_each_condition_blocks(self, key, val, needle):
        why = hw.evaluate({**GOOD, key: val}, KNOBS)
        assert len(why) == 1 and needle in why[0]

    def test_probe_error_never_admits(self):
        assert hw.evaluate({"probe_error": "boom"}, KNOBS)

    def test_session_advisory_is_not_a_block(self):
        m = {**GOOD, "claude_sessions": 9}
        assert hw.evaluate(m, KNOBS) == [] and hw.advisories(m, KNOBS)


class TestSlot:
    def test_admitted_logs_run(self, env):
        with hw.heavy_slot("pytest:x", probe_fn=lambda s: GOOD) as adm:
            assert adm.admitted and adm.verdict == "admitted"
            assert os.environ["NOCTUS_HW_SLOT_HELD"]
            assert hw.holders()[0]["job"] == "pytest:x"
        assert "NOCTUS_HW_SLOT_HELD" not in os.environ
        assert [r["event"] for r in _rows(env)] == ["ran"]
        assert hw.holders() == []

    def test_bad_metrics_wait_then_refuse_without_running(self, env):
        with hw.heavy_slot("vitest:y", probe_fn=lambda s: {**GOOD, "reclaimable_mb": 10}) as adm:
            assert not adm.admitted and adm.verdict == "waiting_for_slot"
            assert "reclaimable" in adm.blocked_by[0]
        assert [r["event"] for r in _rows(env)] == ["not_admitted"]
        assert hw.holders() == []   # a refused probe releases the slot

    def test_slot_is_machine_wide_across_processes(self, env):
        code = textwrap.dedent(f"""
            import sys, time; sys.path.insert(0, {str(Path(hw.__file__).parents[3])!r})
            from tools.noctus.dev import hw_admission as hw
            with hw.heavy_slot("other-session", probe_fn=lambda s: {GOOD!r}) as a:
                print("held", flush=True); time.sleep(30)
        """)
        p = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, text=True, env=os.environ.copy())
        try:
            assert p.stdout.readline().strip() == "held"
            with hw.heavy_slot("me", probe_fn=lambda s: GOOD) as adm:
                assert not adm.admitted and "other-session" in adm.blocked_by[0]
        finally:
            p.kill()
            p.wait()
        with hw.heavy_slot("me", probe_fn=lambda s: GOOD) as adm:   # dead holder frees the slot
            assert adm.admitted

    def test_child_inherits_parent_slot(self, env, monkeypatch):
        monkeypatch.setenv("NOCTUS_HW_SLOT_HELD", "/some/slot")
        with hw.heavy_slot("nested", probe_fn=lambda s: {"probe_error": "never called"}) as adm:
            assert adm.admitted and adm.verdict == "inherited"

    def test_budget_error_refuses(self, env, monkeypatch):
        monkeypatch.setenv("NOCTUS_HW_BUDGET_PATH", str(env / "absent.json"))
        with hw.heavy_slot("x") as adm:
            assert not adm.admitted and adm.verdict == "budget_error"

    def test_run_command_exit_75_when_no_slot(self, env, monkeypatch):
        # The blocker holds the only slot; drop the inherited-slot marker so
        # run_command competes like a separate process would.
        with hw.heavy_slot("blocker", probe_fn=lambda s: GOOD):
            monkeypatch.delenv("NOCTUS_HW_SLOT_HELD")
            assert hw.run_command("cmd", [sys.executable, "-c", "raise SystemExit(0)"], wait_s=0) == 75


class TestReport:
    def test_report_summarizes_by_job(self, env):
        for _ in range(2):
            with hw.heavy_slot("pytest:core", probe_fn=lambda s: GOOD):
                pass
        with hw.heavy_slot("pytest:core", probe_fn=lambda s: {**GOOD, "swapout_per_s": 99}):
            pass
        r = hw.report()
        assert r["runs"] == 2 and r["not_admitted"] == 1 and r["by_job"]["pytest:core"]["runs"] == 2


class TestRecheckTimer:
    NOW = 1_800_000_000.0

    def _series(self, pattern, start_ago, step=60):
        from datetime import datetime, timezone
        t0 = self.NOW - start_ago
        return [{"event": "sample", "overloaded": o,
                 "ts": datetime.fromtimestamp(t0 + i * step, timezone.utc).isoformat()}
                for i, o in enumerate(pattern)]

    def test_no_episode_falls_back_to_default(self):
        r = hw.recheck_timer(now=self.NOW, rows=self._series([False] * 5, 3600))
        assert r["recheck_s"] == 900 and r["episodes_7d"] == 0

    def test_median_episode_plus_margin(self):
        # two 10-min episodes three days ago -> 600 s x 1.1 = 660 s
        rows = self._series(([True] * 10 + [False]) * 2, 3 * 86400)
        r = hw.recheck_timer(now=self.NOW, rows=rows)
        assert r["recheck_s"] == 660 and r["episodes_7d"] == 2 and not r["pattern_changed"]

    def test_clamped(self):
        rows = self._series([True, False], 3 * 86400, step=5)
        assert hw.recheck_timer(now=self.NOW, rows=rows)["recheck_s"] == hw.RECHECK_MIN_S

    def test_pattern_change_flagged(self):
        old = self._series(([True] * 10 + [False]) * 3, 4 * 86400)     # 600 s episodes
        new = self._series([True] * 40 + [False], 3 * 3600)             # one 2400 s episode today
        r = hw.recheck_timer(now=self.NOW, rows=old + new)
        assert r["pattern_changed"] and r["median_episode_24h_s"] == 2400

    def test_samples_outside_window_ignored(self):
        rows = self._series([True] * 10 + [False], 8 * 86400)
        assert hw.recheck_timer(now=self.NOW, rows=rows)["episodes_7d"] == 0


class TestGateSweepAdmission:
    """gate_sweep._run_gates with an injected `admit` (the real one is
    hw_admission.heavy_slot; here a scripted stand-in, passed as a parameter)."""

    def _spec(self, name):
        from tools.noctus.dev.gate_sweep import GateSpec
        return GateSpec(name, ["true"], Path("."), [])

    def _admit(self, admitted, seen):
        import contextlib

        @contextlib.contextmanager
        def admit(job):
            seen.append(job)
            yield hw.Admission(job, admitted, "admitted" if admitted else "waiting_for_slot",
                               blocked_by=[] if admitted else ["reclaimable 900MB < 1536MB"])
        return admit

    def test_refused_gate_is_not_run_and_inconclusive(self):
        from tools.noctus.dev import gate_sweep as gs
        ran, seen = [], []
        gates = gs._run_gates([self._spec("pytest:core")], lambda sp: ran.append(sp) or (0, "ok", 1.0),
                              admit=self._admit(False, seen))
        assert ran == [] and seen == ["gate:pytest:core"]
        assert gates[0]["ran"] is False and gates[0]["waiting_for_slot"]["verdict"] == "waiting_for_slot"
        assert gs._verdict(gates) == "inconclusive"

    def test_admitted_gate_runs(self):
        from tools.noctus.dev import gate_sweep as gs
        gates = gs._run_gates([self._spec("vitest:x")], lambda sp: (0, "ok", 1.0),
                              admit=self._admit(True, []))
        assert gates[0]["ran"] and gs._verdict(gates) == "green"

    def test_no_admit_means_ungated(self):
        from tools.noctus.dev import gate_sweep as gs
        gates = gs._run_gates([self._spec("vitest:x")], lambda sp: (0, "ok", 1.0))
        assert gates[0]["ran"] and "waiting_for_slot" not in gates[0]

    def test_workers_capped_at_max_heavy(self, env):
        from tools.noctus.dev import gate_sweep as gs
        assert gs._heavy_cap() == 1
