"""Steward toolkit by construction (2026-11-15): the repo root never follows the cwd (1), a stale toolkit checkout is
fixed or refused loudly (2), scoped checks run on TWO budgets - queue and run (3) - and every heavy-slot caller reports
its wait (4).

Seams only: real git in tmp dirs, injected check/clock/probe/sleep. Nothing of ours is monkeypatched.
"""
from __future__ import annotations

import json
import subprocess
import threading
import time
from pathlib import Path

import pytest

import node_toolchain
from tools.noctus.dev import gate_sweep as gs
from tools.noctus.dev import hw_admission as hw
from tools.noctus.dev import release_steward as rs
from tools.noctus.dev import toolkit_freshness as tf
from tools.noctus.dev import version_guard as vg

SESSION = "11111111-aaaa"


def git(cwd: Path, *args: str) -> str:
    r = subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "-c", "commit.gpgsign=false", *args],
                       cwd=cwd, capture_output=True, text=True, check=True)
    return r.stdout.strip()


def commit(cwd: Path, rel: str, text: str) -> None:
    f = cwd / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(text)
    git(cwd, "add", "-A")
    git(cwd, "commit", "-q", "-m", f"change {rel}")


# ── 1: the repo root is the toplevel, never the cwd ──────────────────────────────────────────────────────────────
def _node(root: Path, pglite: bool) -> None:
    d = root / "mcp" / "noctusai" / "node"
    d.mkdir(parents=True)
    (d / "package-lock.json").write_text("lock-a")
    if pglite:
        (d / "node_modules" / "@electric-sql" / "pglite").mkdir(parents=True)


class TestRepoRootIsTheToplevel:
    def test_link_pglite_from_a_subdirectory_resolves_the_same_source(self, tmp_path):
        src, export = tmp_path / "src", tmp_path / "export"
        src.mkdir()
        git(src, "init", "-q", "-b", "dev")
        _node(src, True)
        _node(export, False)
        # the cwd the fresh-subprocess fallback runs from: mcp/noctusai -> used to double to mcp/noctusai/mcp/noctusai/node
        assert rs.link_pglite(export, src / "mcp" / "noctusai") == ""
        assert (export / "mcp/noctusai/node/node_modules/@electric-sql/pglite").is_dir()

    def test_repo_toplevel_from_a_subdirectory_and_outside_a_repo(self, tmp_path):
        (tmp_path / "r" / "a" / "b").mkdir(parents=True)
        git(tmp_path / "r", "init", "-q")
        assert node_toolchain.repo_toplevel(tmp_path / "r" / "a" / "b").resolve() == (tmp_path / "r").resolve()
        plain = tmp_path / "plain"
        plain.mkdir()
        assert node_toolchain.repo_toplevel(plain) == plain

    def test_version_guard_from_a_subdirectory_reads_the_repo_root_version(self, tmp_path, monkeypatch):
        git(tmp_path, "init", "-q", "-b", "dev")
        commit(tmp_path, "VERSION", "1.0.0\n")
        (tmp_path / "VERSION").write_text("2.0.0\n")
        sub = tmp_path / "mcp" / "noctusai"
        sub.mkdir(parents=True)
        monkeypatch.chdir(sub)
        res = vg.check_version_bump()
        assert res["status"] == "major_unauthorized" and res["current"] == "2.0.0"


# ── 2: the toolkit checkout vs origin/dev ────────────────────────────────────────────────────────────────────────
@pytest.fixture()
def world(tmp_path):
    """origin (bare) + a clone `tools` that plays the steward's toolkit checkout."""
    origin = tmp_path / "origin.git"
    seed = tmp_path / "seed"
    seed.mkdir()
    git(seed, "init", "-q", "-b", "dev")
    commit(seed, "mcp/noctusai/tools/a.py", "x = 1\n")
    git(tmp_path, "clone", "-q", "--bare", str(seed), str(origin))
    git(seed, "remote", "add", "origin", str(origin))
    tools = tmp_path / "tools"
    git(tmp_path, "clone", "-q", str(origin), str(tools))
    return type("W", (), {"seed": seed, "origin": origin, "tools": tools})


def push_dev(w, rel: str, text: str) -> None:
    commit(w.seed, rel, text)
    git(w.seed, "push", "-q", "origin", "dev")
    git(w.tools, "fetch", "-q", "origin")


class TestToolkitCheckoutBehindOrigin:
    def test_current_checkout_is_silent(self, world):
        v = tf.behind_origin(world.tools)
        assert v["status"] == "current" and v["behind"] == 0 and not v["refuse"] and v["message"] == ""

    def test_a_tools_change_on_dev_refuses_below_the_commit_threshold(self, world):
        push_dev(world, "mcp/noctusai/tools/b.py", "y = 1\n")
        v = tf.behind_origin(world.tools)
        assert v["status"] == "behind" and v["behind"] == 1 and v["refuse"]
        assert v["tools_changed"] == ["mcp/noctusai/tools/b.py"]
        assert "1 commit(s) behind origin/dev" in v["message"] and "merge --ff-only origin/dev" in v["message"]

    def test_unrelated_commits_only_warn_until_the_threshold(self, world):
        push_dev(world, "docs/x.md", "1\n")
        v = tf.behind_origin(world.tools)
        assert v["status"] == "behind" and not v["refuse"] and "behind" in v["message"]
        for i in range(2, 5):
            push_dev(world, "docs/x.md", f"{i}\n")
        assert not tf.behind_origin(world.tools)["refuse"]
        assert tf.behind_origin(world.tools, threshold=4)["refuse"]

    def test_ensure_current_fast_forwards_a_clean_branch_checkout(self, world):
        push_dev(world, "mcp/noctusai/tools/b.py", "y = 1\n")
        v = tf.ensure_current(world.tools, fetch=False)
        assert v["fast_forwarded"] and v["status"] == "current" and not v["refuse"]
        assert (world.tools / "mcp/noctusai/tools/b.py").is_file()

    def test_ensure_current_fetches_and_fast_forwards_a_detached_checkout(self, world):
        git(world.tools, "checkout", "-q", "--detach", "HEAD")
        commit(world.seed, "mcp/noctusai/tools/b.py", "y = 1\n")
        git(world.seed, "push", "-q", "origin", "dev")   # NOT fetched into the checkout yet
        v = tf.ensure_current(world.tools)
        assert v["fast_forwarded"] and v["status"] == "current" and v["detached"]

    def test_a_dirty_checkout_is_not_touched_and_refuses_with_the_fix(self, world):
        push_dev(world, "mcp/noctusai/tools/b.py", "y = 1\n")
        (world.tools / "mcp/noctusai/tools/a.py").write_text("x = 2\n")
        v = tf.ensure_current(world.tools, fetch=False)
        assert not v["fast_forwarded"] and v["refuse"] and not v["can_fast_forward"]
        assert "local work" in v["fix"] and (world.tools / "mcp/noctusai/tools/a.py").read_text() == "x = 2\n"

    def test_outside_a_repository_is_unknown_never_a_refusal(self, tmp_path):
        v = tf.behind_origin(tmp_path)
        assert v["status"] == "unknown" and not v["refuse"] and "cannot resolve" in v["message"]


def _store(tmp_path, toolkit_check, **kw):
    return rs.StewardStore(tmp_path, clock=lambda: 1_800_000_000.0, progress=lambda m: None,
                           toolkit_check=toolkit_check, **kw)


BEHIND = {"status": "behind", "behind": 182, "refuse": True, "root": "/x", "fix": "git -C /x checkout --detach origin/dev",
          "message": "steward toolkit is 182 commit(s) behind origin/dev. Fix: git -C /x checkout --detach origin/dev"}


class TestStewardRefusesAStaleToolkit:
    def test_claim_is_refused_naming_the_fix_and_no_lease_is_written(self, tmp_path):
        s = _store(tmp_path, lambda ff: dict(BEHIND))
        r = rs.run_action("claim", SESSION, store=s, name="n", reason="r")
        assert r["ok"] is False and r["status"] == "refused_toolkit_behind"
        assert "182 commit(s) behind origin/dev" in r["error"] and "checkout --detach origin/dev" in r["error"]
        assert s._read_lease() is None

    def test_claim_asks_for_the_fix_by_construction_and_reports_the_fast_forward(self, tmp_path):
        asked: list[bool] = []

        def check(ff):
            asked.append(ff)
            return {"status": "current", "behind": 0, "refuse": False, "root": "/x", "message": "",
                    "fast_forwarded": True, "fast_forwarded_commits": 182}
        s = _store(tmp_path, check)
        r = rs.run_action("claim", SESSION, store=s, name="n", reason="r")
        assert r["ok"] and asked == [True]
        assert any("fast-forwarded 182 commit(s)" in w for w in r["warnings"])

    def test_the_scoped_run_is_refused_but_status_only_warns(self, tmp_path):
        s = _store(tmp_path, lambda ff: dict(BEHIND))
        r = rs.run_action("deliverable", SESSION, store=s, slug="x", run_scoped=True)
        assert r["status"] == "refused_toolkit_behind"
        st = rs.run_action("status", SESSION, store=s)
        assert st.get("status") != "refused_toolkit_behind" and any("182 commit(s)" in w for w in st["warnings"])

    def test_an_unreadable_probe_warns_and_never_blocks(self, tmp_path):
        def boom(ff):
            raise OSError("no git")
        r = rs.run_action("status", SESSION, store=_store(tmp_path, boom))
        assert any("UNMEASURED" in w for w in r["warnings"])


# ── 3: two budgets, queue and run ────────────────────────────────────────────────────────────────────────────────
def _scoped(tmp_path, holder, **kw):
    return rs.StewardStore(tmp_path, clock=lambda: 1_800_000_000.0, resolve_head=lambda b: "a" * 40, default_ttl_s=7200,
                           progress=lambda m: None, scoped_queues=True, queue_grace_s=0.0,
                           scoped_check=lambda b, h: holder[0](b, h), **kw)


class TestQueueAndRunBudgetsAreSeparate:
    def test_a_long_queue_wait_does_not_eat_the_run_budget(self, tmp_path):
        holder: list = [None]
        s = _scoped(tmp_path, holder, scoped_queue_s=5.0, scoped_deadline_s=0.5)

        def check(b, h):
            time.sleep(0.8)         # queued longer than the whole run budget
            s.mark_admitted()
            return {"ok": True, "detail": "green", "verdict_ref": "ci-parity:" + "b" * 32}
        holder[0] = check
        res = s._run_scoped("feat/x", "a" * 40)
        assert res["ok"] is True and "budget_exhausted" not in res

    def test_the_queue_budget_running_out_says_queue_and_gives_a_retry_hint(self, tmp_path):
        gate = threading.Event()
        holder: list = [lambda b, h: (gate.wait(5), {"ok": True})[1]]
        try:
            res = _scoped(tmp_path, holder, scoped_queue_s=0.3, scoped_deadline_s=60.0)._run_scoped("feat/x", "a" * 40)
        finally:
            gate.set()
        assert res["ok"] is False and res["budget_exhausted"] == "queue" and res["retry_after_s"] > 0
        assert "QUEUE budget" in res["detail"] and "never started" in res["detail"] and rs.SCOPED_QUEUE_ENV in res["detail"]

    def test_the_run_budget_running_out_says_run_and_counts_from_admission(self, tmp_path):
        gate = threading.Event()
        holder: list = [None]
        s = _scoped(tmp_path, holder, scoped_queue_s=60.0, scoped_deadline_s=0.4)

        def check(b, h):
            s.mark_admitted()
            gate.wait(5)
            return {"ok": True}
        holder[0] = check
        try:
            res = s._run_scoped("feat/x", "a" * 40)
        finally:
            gate.set()
        assert res["budget_exhausted"] == "run" and "RUN budget" in res["detail"] and "wall-clock deadline" in res["detail"]
        assert res["retry_after_s"] > 0 and rs.SCOPED_DEADLINE_ENV in res["detail"]

    def test_the_run_budget_is_derived_unless_the_override_is_given(self, tmp_path):
        derived = rs.StewardStore(tmp_path / "a", progress=lambda m: None, scoped_check=lambda b, h: {"ok": True})
        assert derived.scoped_deadline_s == rs.SCOPED_RUN_DEFAULT_S
        derived.size_run_budget(1234.0)
        assert derived.scoped_deadline_s == 1234.0
        pinned = rs.StewardStore(tmp_path / "b", progress=lambda m: None, scoped_check=lambda b, h: {"ok": True},
                                 scoped_deadline_s=77.0)
        pinned.size_run_budget(1234.0)
        assert pinned.scoped_deadline_s == 77.0

    def test_env_knobs(self):
        assert rs._scoped_queue_s({}) == rs.SCOPED_QUEUE_DEFAULT_S == 3 * 3600
        assert rs._scoped_queue_s({rs.SCOPED_QUEUE_ENV: "90"}) == 90.0
        assert rs._scoped_deadline_s({}) is None and rs._scoped_deadline_s({rs.SCOPED_DEADLINE_ENV: "120"}) == 120.0

    def test_the_derived_run_budget_follows_gate_budget_costs(self):
        seen: list[str] = []

        def budget(gate, files=None):
            seen.append(gate)
            return 100

        class S:
            label, argv = "x", ["-m", "pytest", "tests/test_a.py"]
        total = rs.derive_run_budget_s(budget, n_flags=2, n_prime=1, has_tests=True, has_live=False,
                                       suites=[("ci_parity:suite:x", S)], suite_budget_s=1800)
        # every stage: first + the x1.5 retry = 250; export x2, 1 prime, 2 keepers, pytest, 1 suite
        assert total == 250 * (2 + 1 + 2 + 1 + 1)
        assert {"ci_parity:export", "ci_parity:pytest", "ci_parity:suite:x"} <= set(seen)

    def test_the_suite_budget_caps_the_suite_share(self):
        class S:
            label, argv = "s", ["-m", "pytest"]
        total = rs.derive_run_budget_s(lambda g, files=None: 1000, n_flags=0, n_prime=0, has_tests=False, has_live=False,
                                       suites=[(f"ci_parity:suite:{i}", S) for i in range(10)], suite_budget_s=1800)
        assert total == 2500 * 2 + (1800 + 2500)


# ── 4: progress by construction in every heavy-slot caller ───────────────────────────────────────────────────────
KNOBS = {"max_heavy": 1, "min_cpu_idle_pct": 50, "cpu_sample_s": 1, "min_reclaimable_mb": 1536,
         "max_swapout_per_s": 50, "max_claude_sessions_advisory": 3, "wait_s": 0, "poll_s": 0}
GOOD = {"cpu_idle_pct": 80.0, "reclaimable_mb": 3000, "swapout_per_s": 0.0, "claude_sessions": 2}


@pytest.fixture()
def hw_env(tmp_path, monkeypatch):
    budget = tmp_path / "budget.json"
    budget.write_text(json.dumps({"phase": "build", "phases": {"build": KNOBS}, "hosts": {}}))
    for k, v in (("NOCTUS_HW_BUDGET_PATH", budget), ("NOCTUS_HW_SLOT_DIR", tmp_path / "slots"),
                 ("NOCTUS_HW_LOG", tmp_path / "log.ndjson"), ("NOCTUS_HW_QUEUE_DIR", tmp_path / "queue"),
                 ("NOCTUS_HW_SUSPEND", tmp_path / "no-suspend-flag")):
        monkeypatch.setenv(k, str(v))
    monkeypatch.delenv("NOCTUS_HW_PHASE", raising=False)
    monkeypatch.delenv("NOCTUS_HW_SLOT_HELD", raising=False)


class TestHeavySlotCallersReportTheirWait:
    def test_the_real_gate_sweep_admit_is_the_progress_reporting_one(self):
        assert gs._resolve_admit(gs._AUTO_ADMIT, None) is hw.queued_heavy_slot
        assert gs._resolve_admit(gs._AUTO_ADMIT, object()) is None   # an injected runner stays ungated

    def test_the_integrate_admit_prints_a_wait_line_naming_the_holder(self, hw_env, capsys):
        holder = hw._try_slot(1, "other-job")
        try:
            admit = hw.shared_deadline_admit(0.2)
            with admit("gate:x", probe_fn=lambda s: GOOD, sleep=lambda s: None, progress_every_s=0) as adm:
                assert not adm.admitted
        finally:
            holder[0].close()
        err = capsys.readouterr().err
        assert "HW-WAIT" in err and "other-job" in err and "gate:x" in err

    def test_an_explicit_progress_wins_and_none_silences(self, hw_env, capsys):
        holder = hw._try_slot(1, "other-job")
        got: list[str] = []
        try:
            with hw.queued_heavy_slot("a", wait_s=0.2, probe_fn=lambda s: GOOD, sleep=lambda s: None,
                                      progress=got.append, progress_every_s=0):
                pass
            with hw.queued_heavy_slot("b", wait_s=0.2, probe_fn=lambda s: GOOD, sleep=lambda s: None, progress=None):
                pass
        finally:
            holder[0].close()
        assert got and "HW-WAIT" not in capsys.readouterr().err


# ── 5: the composed-tree probe honours registered merge drivers ───────────────────────────────────────────────────
INV = "KNOWLEDGE-BASE/CONTEXT/PATTERNS/common/gate-alignment-inventory.json"


def _inv(gates: dict) -> str:
    return json.dumps({"gates": gates, "decisions": []}, indent=1, ensure_ascii=False) + "\n"


@pytest.fixture()
def inv_repo(tmp_path):
    r = tmp_path / "r"
    r.mkdir()
    git(r, "init", "-q", "-b", "dev")
    (r / ".gitattributes").write_text(f"{INV} merge=gate-inventory\n")
    commit(r, INV, _inv({"g0": {"v": 1}}))
    return r


def _two_sides(r: Path, dev_gates: dict, head_gates: dict) -> None:
    git(r, "checkout", "-q", "dev")
    commit(r, INV, _inv(dev_gates))
    git(r, "checkout", "-q", "-b", "side", "HEAD~1")
    commit(r, INV, _inv(head_gates))


class TestComposedTreeHonoursMergeDrivers:
    def test_plain_merge_tree_alone_reports_the_conflict_the_driver_resolves(self, inv_repo):
        _two_sides(inv_repo, {"g0": {"v": 1}, "gA": {"v": 2}}, {"g0": {"v": 1}, "gB": {"v": 3}})
        rc, _o, _e = rs._subprocess_git(inv_repo)("merge-tree", "--write-tree", "dev", "side")
        assert rc == 1   # the false alarm: merge-tree runs no external driver

    def test_two_branches_each_adding_a_different_gate_are_not_a_conflict(self, inv_repo):
        _two_sides(inv_repo, {"g0": {"v": 1}, "gA": {"v": 2}}, {"g0": {"v": 1}, "gB": {"v": 3}})
        g = rs._subprocess_git(inv_repo)
        cm = rs.compose_merge(g, "dev", "side", attr_tree="dev")
        assert cm["rc"] == 0 and cm["conflicts"] == []
        assert cm["resolved_by_driver"] == [{"path": INV, "driver": "gate-inventory"}]
        merged = json.loads(git(inv_repo, "show", f"{cm['tree']}:{INV}"))
        assert set(merged["gates"]) == {"g0", "gA", "gB"}

    def test_a_same_key_change_on_both_sides_is_still_a_conflict(self, inv_repo):
        _two_sides(inv_repo, {"g0": {"v": 9}}, {"g0": {"v": 8}})
        cm = rs.compose_merge(rs._subprocess_git(inv_repo), "dev", "side", attr_tree="dev")
        assert cm["rc"] == 1 and cm["conflicts"] == [INV] and cm["resolved_by_driver"] == []

    def test_a_conflict_in_a_path_without_a_driver_stands(self, inv_repo):
        commit(inv_repo, "plain.txt", "one\n")
        git(inv_repo, "checkout", "-q", "-b", "p1")
        commit(inv_repo, "plain.txt", "two\n")
        git(inv_repo, "checkout", "-q", "dev")
        commit(inv_repo, "plain.txt", "three\n")
        cm = rs.compose_merge(rs._subprocess_git(inv_repo), "dev", "p1", attr_tree="dev")
        assert cm["rc"] == 1 and cm["conflicts"] == ["plain.txt"]

    def test_merge_tree_sha_the_scoped_run_composes_through_the_drivers_too(self, inv_repo):
        _two_sides(inv_repo, {"g0": {"v": 1}, "gA": {"v": 2}}, {"g0": {"v": 1}, "gB": {"v": 3}})
        tree, why = rs.merge_tree_sha("side", inv_repo, base="dev")
        assert tree and why == ""
