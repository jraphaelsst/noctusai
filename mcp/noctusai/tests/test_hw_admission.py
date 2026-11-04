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
    monkeypatch.setenv("NOCTUS_HW_QUEUE_DIR", str(tmp_path / "queue"))
    monkeypatch.setenv("NOCTUS_HW_SUSPEND", str(tmp_path / "no-suspend-flag"))  # never the real ~/.noctus switch
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


class TestReportWindow:
    def test_window_filters_rows(self, env):
        log = env / "log.ndjson"
        log.write_text("\n".join(json.dumps(r) for r in [
            {"ts": "2026-11-04T01:00:00+00:00", "event": "sample", "overloaded": True},
            {"ts": "2026-11-04T03:00:00+00:00", "event": "sample", "overloaded": False},
            {"ts": "2026-11-04T03:30:00+00:00", "event": "ran", "job": "pytest:core", "waited_s": 5, "duration_s": 60},
        ]) + "\n")
        before = hw.report(until="2026-11-04T02:00:00+00:00")
        after = hw.report(since="2026-11-04T02:00:00+00:00")
        assert before["samples"] == 1 and before["overloaded_pct"] == 100.0 and before["runs"] == 0
        assert after["samples"] == 1 and after["overloaded_pct"] == 0.0 and after["runs"] == 1

    def test_standalone_copy_needs_explicit_budget(self, tmp_path, monkeypatch):
        import shutil
        dst = tmp_path / "hw_copy.py"
        shutil.copy(hw.__file__, dst)
        monkeypatch.delenv("NOCTUS_HW_BUDGET_PATH", raising=False)
        out = subprocess.run([sys.executable, str(dst), "status"], capture_output=True, text=True)
        assert out.returncode == 0 and "budget_error" in out.stdout and "NOCTUS_HW_BUDGET_PATH" in out.stdout


class TestTrialSchedule:
    T0 = "2026-11-04T05:45:00Z"

    @pytest.fixture()
    def sched(self, env, monkeypatch):
        monkeypatch.setenv("NOCTUS_HW_ABORTS", str(env / "aborts.json"))
        b = json.loads((env / "budget.json").read_text())
        b["phases"]["trial"] = {**KNOBS, "max_heavy": 2, "min_cpu_idle_pct": 25}
        b["schedule"] = [{"phase": "trial", "from": self.T0, "until": "2026-11-04T07:45:00Z",
                          "hosts": ["box-b"],
                          "abort": {"reclaimable_mb_below": 500, "swapout_at_least": 50, "consecutive": 3}}]
        (env / "budget.json").write_text(json.dumps(b))
        return env

    def at(self, iso):
        return hw._iso(iso)

    def test_inside_window_selects_trial(self, sched):
        b = hw.load_budget(host="box-b", now=self.at("2026-11-04T06:00:00Z"))
        assert b["phase"] == "trial" and b["max_heavy"] == 2 and b["trial"]["phase"] == "trial"

    def test_outside_window_and_other_host_unaffected(self, sched):
        assert hw.load_budget(host="box-b", now=self.at("2026-11-04T05:44:59Z"))["phase"] == "build"
        assert hw.load_budget(host="box-b", now=self.at("2026-11-04T07:45:00Z"))["phase"] == "build"
        assert hw.load_budget(host="other", now=self.at("2026-11-04T06:00:00Z"))["phase"] == "build"

    def test_env_phase_still_wins(self, sched, monkeypatch):
        monkeypatch.setenv("NOCTUS_HW_PHASE", "build")
        assert hw.load_budget(host="box-b", now=self.at("2026-11-04T06:00:00Z"))["phase"] == "build"

    def test_abort_after_n_breaching_samples_falls_back(self, sched):
        b = hw.load_budget(host="box-b", now=self.at("2026-11-04T06:00:00Z"))
        bad = {**GOOD, "reclaimable_mb": 300}
        hw._log({"event": "sample", "phase": "trial", "metrics": bad})
        assert hw._check_trial_abort(b, bad) is None          # 2 of 3 — not yet
        hw._log({"event": "sample", "phase": "trial", "metrics": bad})
        rec = hw._check_trial_abort(b, bad)                    # 3 of 3 — abort
        assert rec and rec["phase"] == "trial"
        assert hw.load_budget(host="box-b", now=self.at("2026-11-04T06:30:00Z"))["phase"] == "build"
        assert any(r["event"] == "trial_aborted" for r in _rows(sched))

    def test_one_good_sample_resets_the_abort_count(self, sched):
        b = hw.load_budget(host="box-b", now=self.at("2026-11-04T06:00:00Z"))
        bad = {**GOOD, "swapout_per_s": 80}
        hw._log({"event": "sample", "phase": "trial", "metrics": bad})
        hw._log({"event": "sample", "phase": "trial", "metrics": GOOD})
        assert hw._check_trial_abort(b, bad) is None

    def test_ungated_samples_neither_count_nor_break_the_streak(self, sched):
        """2026-11-04 17:56Z: zero slots held, swap 3023/s from ungated load."""
        b = hw.load_budget(host="box-b", now=self.at("2026-11-04T06:00:00Z"))
        bad = {**GOOD, "swapout_per_s": 3000}
        hw._log({"event": "sample", "phase": "trial", "busy_slots": 1, "metrics": bad})
        hw._log({"event": "sample", "phase": "trial", "busy_slots": 0, "metrics": bad})
        assert hw._check_trial_abort(b, bad, busy_slots=0) is None       # ungated: never aborts
        hw._log({"event": "sample", "phase": "trial", "busy_slots": 2, "metrics": bad})
        rec = hw._check_trial_abort(b, bad, busy_slots=1)                 # 3rd GATED breach
        assert rec and rec["phase"] == "trial"

    def test_count_ungated_opt_in_restores_machine_wide_counting(self, sched):
        b = hw.load_budget(host="box-b", now=self.at("2026-11-04T06:00:00Z"))
        b["trial"]["abort"] = {**b["trial"]["abort"], "count_ungated": True}
        bad = {**GOOD, "swapout_per_s": 3000}
        for _ in range(2):
            hw._log({"event": "sample", "phase": "trial", "busy_slots": 0, "metrics": bad})
        assert hw._check_trial_abort(b, bad, busy_slots=0)

    def test_report_splits_by_phase(self, sched):
        hw._log({"event": "sample", "phase": "build", "overloaded": False, "metrics": GOOD})
        hw._log({"event": "sample", "phase": "trial", "overloaded": True, "metrics": GOOD})
        hw._log({"event": "ran", "phase": "trial", "job": "j", "waited_s": 1, "duration_s": 2,
                 "outcome": {"exit_code": 1}})
        r = hw.report()["by_phase"]
        assert r["build"]["samples"] == 1 and r["trial"]["overloaded"] == 1 and r["trial"]["failed_runs"] == 1

    def test_ran_row_carries_exit_code(self, env):
        with hw.heavy_slot("x", probe_fn=lambda s: GOOD) as adm:
            adm.outcome["exit_code"] = 3
        assert _rows(env)[-1]["outcome"] == {"exit_code": 3}


class TestExplicitAdmit:
    """2026-11-04 bypass: task_branch injects a REAL runner, so the 'injected
    runner => ungated' default silently skipped the heavy slot for every
    merged-tip gate. An explicit `admit` must win, and task_branch must pass it."""

    def test_explicit_admit_wins_over_injected_runner(self):
        from tools.noctus.dev import gate_sweep as gs
        sentinel = object()
        assert gs._resolve_admit(sentinel, run_gate=lambda sp: None) is sentinel
        assert gs._resolve_admit(None, run_gate=None) is None
        assert gs._resolve_admit(gs._AUTO_ADMIT, run_gate=None) is hw.heavy_slot
        assert gs._resolve_admit(gs._AUTO_ADMIT, run_gate=lambda sp: None) is None

    def test_run_gates_named_honours_explicit_admit(self, tmp_path):
        import contextlib
        from tools.noctus.dev import gate_sweep as gs
        seen = []

        @contextlib.contextmanager
        def admit(job):
            seen.append(job)
            yield hw.Admission(job, False, "waiting_for_slot", blocked_by=["test"])

        spec = gs.GateSpec("pytest:x", ["true"], tmp_path, [])
        out = gs._run_gates([spec], lambda sp: (0, "ok", 1.0), admit=gs._resolve_admit(admit, lambda sp: None))
        assert seen == ["gate:pytest:x"] and out[0]["ran"] is False

    def test_task_branch_merged_tip_paths_pass_the_heavy_slot(self):
        import inspect
        from tools.noctus.dev import task_branch as tb
        for fn in (tb._default_merged_tip_check, tb._default_merged_tip_baseline):
            src = inspect.getsource(fn)
            # since 2026-11-04 through ONE shared FIFO deadline (hw_admission.shared_deadline_admit)
            assert "_hw.shared_deadline_admit(" in src, f"{fn.__name__} no longer admits its real runner"


class TestProbeV2:
    """2026-11-04 (noctusai-3d): swap rate was divided by the NOMINAL sample_s,
    so under load (top's startup stretching the interval) it read ~10x high —
    35669/s at 04:02Z. v2 divides by the measured interval and adds MB/s."""

    def test_real_probe_reports_measured_interval_and_mb_rate(self):
        m = hw.probe(1.0)
        if "probe_error" in m:
            pytest.skip(f"probe unavailable on this host: {m['probe_error']}")
        assert m["elapsed_s"] >= 1.0          # the interval it divided by, never below nominal
        assert m["swapout_per_s"] >= 0 and m["swapout_mb_per_s"] >= 0
        if m["swapout_per_s"] == 0:
            assert m["swapout_mb_per_s"] == 0

    def test_every_log_row_carries_probe_version(self, env):
        with hw.heavy_slot("pytest:pv", probe_fn=lambda s: GOOD):
            pass
        rows = [json.loads(ln) for ln in (env / "log.ndjson").read_text().splitlines()]
        assert rows and all(r["probe_version"] == hw.PROBE_VERSION == 2 for r in rows)


class TestJobWorkers:
    def test_budget_value_wins(self):
        assert hw.job_workers({"job_workers": 3, "max_heavy": 1}) == 3

    def test_default_is_cores_over_twice_heavy_never_zero(self):
        n = hw.job_workers({"max_heavy": 1})
        assert n == max(1, (os.cpu_count() or 2) // 2)
        assert hw.job_workers({"max_heavy": 1000}) == 1

    def test_unreadable_budget_caps_at_one(self, env, monkeypatch):
        monkeypatch.setenv("NOCTUS_HW_BUDGET_PATH", str(env / "absent.json"))
        assert hw.job_workers() == 1

    def test_repo_build_phase_caps_at_two(self, monkeypatch):
        monkeypatch.delenv("NOCTUS_HW_BUDGET_PATH", raising=False)
        monkeypatch.setenv("NOCTUS_HW_PHASE", "build")
        assert hw.job_workers() == 2

    def test_cap_argv_shapes(self):
        assert hw.cap_worker_argv(["npm", "test"], 2) == ["npm", "test", "--", "--maxWorkers=2"]
        assert hw.cap_worker_argv(["npx", "playwright", "test"], 2) == \
            ["npx", "playwright", "test", "--workers=2"]
        assert hw.cap_worker_argv(["npm", "test", "--", "--maxWorkers=5"], 2) == \
            ["npm", "test", "--", "--maxWorkers=5"]          # explicit cap is respected
        assert hw.cap_worker_argv(["python", "-m", "pytest"], 2) == ["python", "-m", "pytest"]
        assert hw.cap_worker_argv(["npx", "vite", "build"], 2) == ["npx", "vite", "build"]


class TestGateRunnerAppliesCap:
    def test_default_run_gate_launches_capped_vitest(self, tmp_path, monkeypatch):
        """Real subprocess: a fake `npm` first on PATH prints the argv it got."""
        import stat
        from tools.noctus.dev import gate_sweep as gs
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        npm = bin_dir / "npm"
        npm.write_text('#!/bin/sh\necho "ARGV: $*"\n')
        npm.chmod(npm.stat().st_mode | stat.S_IEXEC)
        monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
        monkeypatch.setenv("NOCTUS_HW_PHASE", "build")
        monkeypatch.delenv("NOCTUS_HW_BUDGET_PATH", raising=False)
        res = gs._default_run_gate(gs.GateSpec("vitest:x", ["npm", "test"], tmp_path), timeout=30)
        assert res[0] == 0
        assert "ARGV: test -- --maxWorkers=2" in res[1]


class TestJobWorkersOnRows:
    """Contract with usage_eval (noctusai-3d, 2026-11-04): `job_workers` is a
    TOP-LEVEL int on ran / not_admitted rows; null when the job has no fan-out."""

    def _rows(self, env):
        return [json.loads(ln) for ln in (env / "log.ndjson").read_text().splitlines()]

    def test_gate_vitest_row_carries_the_cap(self, env):
        with hw.heavy_slot("gate:vitest:sw", probe_fn=lambda s: GOOD):
            pass
        row = [r for r in self._rows(env) if r["event"] == "ran"][-1]
        assert row["job_workers"] == hw.job_workers() and isinstance(row["job_workers"], int)

    def test_pytest_row_is_null(self, env):
        with hw.heavy_slot("gate:pytest:core", probe_fn=lambda s: GOOD):
            pass
        assert [r for r in self._rows(env) if r["event"] == "ran"][-1]["job_workers"] is None

    def test_not_admitted_row_carries_it_too(self, env):
        with hw.heavy_slot("e2e:sw", wait_s=0, probe_fn=lambda s: {**GOOD, "reclaimable_mb": 1},
                           sleep=lambda s: None) as adm:
            assert not adm.admitted
        row = [r for r in self._rows(env) if r["event"] == "not_admitted"][-1]
        assert row["job_workers"] == hw.job_workers()

    def test_run_command_caps_and_records_whatever_the_job_name(self, env, tmp_path, monkeypatch):
        import stat
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        npm = bin_dir / "npm"
        out = tmp_path / "argv.txt"
        npm.write_text(f'#!/bin/sh\necho "$*" > {out}\n')
        npm.chmod(npm.stat().st_mode | stat.S_IEXEC)
        monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
        # run_command probes the real machine; admit deterministically by holding
        # an outer slot (the child inherits it, verdict 'inherited').
        monkeypatch.setenv("NOCTUS_HW_SLOT_HELD", "/outer/slot")
        assert hw.run_command("tests-for-sw", ["npm", "test"], wait_s=0) == 0
        assert out.read_text().strip() == f"test -- --maxWorkers={hw.job_workers()}"


class TestChainedStepCancel:
    def test_abort_cancels_every_chained_later_step(self, env, monkeypatch):
        monkeypatch.setenv("NOCTUS_HW_ABORTS", str(env / "aborts.json"))
        b = json.loads((env / "budget.json").read_text())
        b["phases"]["t2"] = {**KNOBS, "max_heavy": 2}
        b["phases"]["t3"] = {**KNOBS, "max_heavy": 3}
        rule = {"reclaimable_mb_below": 500, "consecutive": 1}
        b["schedule"] = [
            {"phase": "t2", "from": "2026-11-04T05:45:00Z", "until": "2026-11-04T07:45:00Z", "abort": rule},
            {"phase": "t3", "from": "2026-11-04T07:45:00Z", "until": "2026-11-04T08:25:00Z", "abort": rule},
            {"phase": "t2", "from": "2026-11-05T05:45:00Z", "until": "2026-11-05T07:45:00Z", "abort": rule},
        ]
        (env / "budget.json").write_text(json.dumps(b))
        eff = hw.load_budget(host="box-b", now=hw._iso("2026-11-04T06:00:00Z"))
        rec = hw._check_trial_abort(eff, {**GOOD, "reclaimable_mb": 100})
        assert rec["cancelled_steps"] == ["t3@2026-11-04T07:45:00Z"]       # chained step only
        assert hw.load_budget(host="box-b", now=hw._iso("2026-11-04T08:00:00Z"))["phase"] == "build"
        # an unchained later run (next day) is a separate experiment: untouched
        assert hw.load_budget(host="box-b", now=hw._iso("2026-11-05T06:00:00Z"))["phase"] == "t2"


class TestMemoryAwareAdmission:
    ROWS = [
        {"event": "ran", "job": "gate:pytest:social-wiring", "children_peak_rss_mb": m}
        for m in (800, 900, 1000, 1100, 1200, 1300, 1400, 1500, 1600, 2000)
    ] + [{"event": "ran", "job": "gate:pytest:core", "children_peak_rss_mb": 700},
         {"event": "ran", "job": "gate:vitest:igig", "children_peak_rss_mb": None}]

    def test_peak_lookup_prefers_job_then_kind_then_default(self):
        assert hw.expected_peak_mb("gate:pytest:social-wiring", self.ROWS) == (1600.0, "job")  # p90 nearest-rank
        assert hw.expected_peak_mb("gate:pytest:orbity", self.ROWS)[1] == "kind"
        assert hw.expected_peak_mb("gate:vitest:igig", self.ROWS, default=1234) == (1234.0, "default")

    def test_first_heavy_job_is_never_vetoed_on_memory(self):
        assert hw.memory_veto("gate:pytest:social-wiring", {"reclaimable_mb": 1600},
                              {**KNOBS, "memory_veto": True}, others=0, rows=self.ROWS) == []

    def test_second_job_vetoed_when_its_peak_would_breach_the_floor(self):
        why = hw.memory_veto("gate:pytest:social-wiring", {"reclaimable_mb": 2500},
                             {**KNOBS, "memory_veto": True}, others=1, rows=self.ROWS)
        assert why and "expected peak 1600 MB (job)" in why[0]

    def test_second_job_admitted_when_it_fits(self):
        assert hw.memory_veto("gate:pytest:core", {"reclaimable_mb": 2500},
                              {**KNOBS, "memory_veto": True}, others=1, rows=self.ROWS) == []

    def test_heavy_slot_applies_the_veto_alongside_a_running_job(self, env, monkeypatch):
        hw._log({"event": "ran", "job": "gate:pytest:big", "children_peak_rss_mb": 3000})
        b = {**KNOBS, "memory_veto": True, "max_heavy": 2, "phase": "t", "host": "h",
             "budget_path": "x", "trial": None}
        with hw.heavy_slot("other", budget=b, probe_fn=lambda s: GOOD) as first:
            assert first.admitted
            monkeypatch.delenv("NOCTUS_HW_SLOT_HELD")   # the next job is ANOTHER process
            with hw.heavy_slot("gate:pytest:big", budget=b, probe_fn=lambda s: GOOD) as second:
                assert not second.admitted
                assert any(x.startswith("memory:") for x in second.blocked_by)


class TestFifoQueue:
    """2026-11-04: integrate 6 gave up after wait_s while another session's
    predeploys took turns - a polling race has no fairness."""

    def _ticket(self, env, name, pid):
        d = env / "queue"
        d.mkdir(exist_ok=True)
        (d / name).write_text(json.dumps({"pid": pid, "job": "older"}))

    def test_a_live_older_waiter_keeps_the_free_slot_for_itself(self, env):
        self._ticket(env, "00000000000000000001-1-1.json", os.getpid())
        with hw.heavy_slot("gate:x", wait_s=0, probe_fn=lambda s: GOOD) as adm:
            assert not adm.admitted
            assert any("queued: 1 waiter(s) ahead" in w for w in adm.blocked_by)
            assert adm.queue_position == 2
        q = [r for r in _rows(env) if r["event"] == "queued"]
        assert q and q[0]["ahead"] == 1 and q[0]["eta_s"] > 0

    def test_dead_pid_tickets_are_swept_and_do_not_block(self, env):
        dead = subprocess.Popen([sys.executable, "-c", "pass"])
        dead.wait()
        self._ticket(env, "00000000000000000001-1-1.json", dead.pid)
        with hw.heavy_slot("gate:x", wait_s=0, probe_fn=lambda s: GOOD) as adm:
            assert adm.admitted and adm.queue_position == 1
        assert not list((env / "queue").glob("*.json"))

    def test_own_ticket_is_removed_on_admit_and_on_give_up(self, env):
        with hw.heavy_slot("gate:a", wait_s=0, probe_fn=lambda s: GOOD) as adm:
            assert adm.admitted
            assert hw.queue() == []
        with hw.heavy_slot("gate:b", wait_s=0, probe_fn=lambda s: {**GOOD, "cpu_idle_pct": 1.0}) as adm:
            assert not adm.admitted
        assert hw.queue() == []

    def test_queue_lists_live_waiters_oldest_first(self, env):
        self._ticket(env, "00000000000000000002-1-1.json", os.getpid())
        self._ticket(env, "00000000000000000001-1-1.json", os.getpid())
        assert [w["ticket"][:20] for w in hw.queue()] == ["00000000000000000001", "00000000000000000002"]

    def test_shared_deadline_spends_one_budget_across_gates(self):
        clock = [100.0]
        seen = []
        admit = hw.shared_deadline_admit(50.0, now=lambda: clock[0],
                                         slot=lambda job, wait_s, **kw: seen.append((job, wait_s)))
        clock[0] = 140.0
        admit("gate:x")
        clock[0] = 200.0
        admit("gate:y")
        assert seen == [("gate:x", 10.0), ("gate:y", 0.0)]


class TestCpuAndSlotGatesOnly:
    """2026-11-04 ~23:15Z owner: the memory veto held the 2nd slot empty at
    63-80% CPU idle and the FIFO head blocked everyone. Admission = CPU % +
    slots; the veto is opt-in per phase; a suspend file is the OFF switch."""

    ROWS = [{"event": "ran", "job": "gate:pytest:big", "children_peak_rss_mb": 3000}]

    def test_memory_veto_is_off_unless_the_phase_opts_in(self):
        assert hw.memory_veto("gate:pytest:big", {"reclaimable_mb": 1600},
                              {**KNOBS, "memory_veto": False}, others=1, rows=self.ROWS) == []
        assert hw.memory_veto("gate:pytest:big", {"reclaimable_mb": 1600},
                              {k: v for k, v in KNOBS.items() if k != "memory_veto"},
                              others=1, rows=self.ROWS) == []

    def test_second_slot_is_used_when_cpu_allows(self, env, monkeypatch):
        hw._log({"event": "ran", "job": "gate:pytest:big", "children_peak_rss_mb": 3000})
        b = {**KNOBS, "memory_veto": False, "max_heavy": 2, "phase": "t", "host": "h",
             "budget_path": "x", "trial": None}
        with hw.heavy_slot("other", budget=b, probe_fn=lambda s: GOOD) as first:
            assert first.admitted
            monkeypatch.delenv("NOCTUS_HW_SLOT_HELD")
            with hw.heavy_slot("gate:pytest:big", budget=b, probe_fn=lambda s: GOOD) as second:
                assert second.admitted and second.verdict == "admitted"

    def test_suspend_file_admits_at_once_and_logs_it(self, env, monkeypatch, tmp_path):
        flag = tmp_path / "suspended"
        flag.write_text("owner 2026-11-04 23:15Z: gate is the incident")
        monkeypatch.setenv("NOCTUS_HW_SUSPEND", str(flag))
        with hw.heavy_slot("gate:x", wait_s=0, probe_fn=lambda s: {**GOOD, "cpu_idle_pct": 0}) as adm:
            assert adm.admitted and adm.verdict == "suspended"
        assert any(r["event"] == "suspended_admit" and "incident" in r["reason"] for r in _rows(env))

    def test_suspend_releases_a_waiter_already_in_line(self, env, monkeypatch, tmp_path):
        flag = tmp_path / "suspended"
        monkeypatch.setenv("NOCTUS_HW_SUSPEND", str(flag))
        b = {**KNOBS, "max_heavy": 1, "phase": "t", "host": "h", "budget_path": "x",
             "trial": None, "poll_s": 0, "wait_s": 30}

        def sleep(_s):
            flag.write_text("owner: off")      # the owner flips it while we wait

        with hw.heavy_slot("gate:x", budget=b, sleep=sleep,
                           probe_fn=lambda s: {**GOOD, "cpu_idle_pct": 0}) as adm:
            assert adm.admitted and adm.verdict == "suspended"
        assert not list((env / "queue").glob("*.json")) if (env / "queue").exists() else True
