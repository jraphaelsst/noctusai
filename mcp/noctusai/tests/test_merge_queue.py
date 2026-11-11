"""merge_queue: the CI-side drain against a REAL git remote (a local bare repo).

Only `gh` is faked — git runs for real, so compose/rebase/merge/FF/ledger-only
replay are exercised exactly as on the runner. The fake CI decides green/red
from the candidate TREE (a file named BREAK makes it red), which is what a real
`Tests & Build` does: judge the composed code, not the entry in isolation.
"""
from __future__ import annotations

import json
import subprocess
import threading
from pathlib import Path

import pytest

from tools.noctus.dev import merge_queue as mq


def sh(cwd, *args):
    p = subprocess.run(list(args), cwd=cwd, capture_output=True, text=True)
    assert p.returncode == 0, (args, p.stderr)
    return p.stdout.strip()


def commit(repo, path, text, msg, when):
    f = Path(repo) / path
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(text)
    sh(repo, "git", "add", path)
    env_date = f"{1700000000 + when} +0000"
    subprocess.run(["git", "commit", "-q", "-m", msg], cwd=repo, check=True,
                   env={"GIT_AUTHOR_DATE": env_date, "GIT_COMMITTER_DATE": env_date,
                        "HOME": str(repo), "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
                        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
                        "GIT_COMMITTER_EMAIL": "t@t"})
    return sh(repo, "git", "rev-parse", "HEAD")


class FakeCI:
    """Stands in for `gh`: dispatch, run list/view, rerun, statuses."""

    def __init__(self, origin: str, red_if=lambda tree: "BREAK" in tree, flaky_once=False,
                 failed_log: str = "", failed_job: str = "Product Backend Tests (x)", barrier=None):
        self.origin, self.red_if, self.flaky_once = origin, red_if, flaky_once
        self.barrier = barrier  # parallel tests: every run blocks until ALL peers are in flight = proof of overlap
        self._lock = threading.Lock()
        self.failed_log, self.failed_job = failed_log, failed_job
        self.statuses: dict[str, list[tuple[str, str]]] = {}
        self.dispatched: list[tuple[str, str]] = []
        self.bases: list[str] = []
        self.reruns = 0
        self._runs: dict[str, str] = {}

    def __call__(self, cmd, cwd=None):
        if cmd[:2] == ["gh", "run"] and cmd[2] == "view" and "--log-failed" not in cmd and self.barrier is not None:
            barrier = self.barrier
            if barrier is not None:
                barrier.wait(timeout=10)  # raises (test fails) if the peer never goes in flight
                self.barrier = None  # spent: later single-candidate rounds must not wait for a peer
        with self._lock:
            return self._call(cmd, cwd)

    def _call(self, cmd, cwd=None):
        if cmd[0] == "git":
            p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
            return p.returncode, p.stdout, p.stderr
        args = cmd[1:]
        if args[:2] == ["workflow", "run"]:
            wf, ref = args[2], args[args.index("--ref") + 1]
            self.dispatched.append((wf, ref))
            self.bases.append(args[args.index("-f") + 1] if "-f" in args else "")
            sha = sh(self.origin, "git", "rev-parse", f"refs/heads/{ref}")
            self._runs[str(len(self._runs) + 1)] = sha
            return 0, "", ""
        if args[:2] == ["run", "list"]:
            ref = args[args.index("--branch") + 1]
            sha = sh(self.origin, "git", "rev-parse", f"refs/heads/{ref}")
            rid = [k for k, v in self._runs.items() if v == sha][-1]
            return 0, json.dumps([{"databaseId": int(rid), "headSha": sha}]), ""
        if args[:2] == ["run", "view"] and "--log-failed" in args:
            return 0, self.failed_log, ""
        if args[:2] == ["run", "view"]:
            sha = self._runs[args[2]]
            tree = sh(self.origin, "git", "ls-tree", "-r", "--name-only", sha)
            red = self.red_if(tree.splitlines())
            if self.flaky_once and self.reruns == 0:
                red = True
            concl = "failure" if red else "success"
            jobs = [{"name": self.failed_job, "conclusion": concl}]
            return 0, json.dumps({"status": "completed", "conclusion": concl, "url": "u", "jobs": jobs}), ""
        if args[:2] == ["run", "rerun"]:
            self.reruns += 1
            return 0, "", ""
        if args[0] == "api" and "statuses" in args[3]:
            sha = args[3].rsplit("/", 1)[1]
            fields = dict(a.split("=", 1) for a in args if "=" in a and not a.startswith("repos/"))
            self.statuses.setdefault(sha, []).append((fields["state"], fields["description"]))
            return 0, "", ""
        raise AssertionError(f"unexpected gh call {cmd}")

    def last(self, sha):
        return self.statuses.get(sha, [("none", "")])[-1]


@pytest.fixture
def world(tmp_path):
    origin = tmp_path / "origin.git"
    sh(tmp_path, "git", "init", "-q", "--bare", "-b", "dev", str(origin))
    work = tmp_path / "work"
    sh(tmp_path, "git", "clone", "-q", str(origin), str(work))
    sh(work, "git", "checkout", "-q", "-b", "dev")
    commit(work, "README", "x\n", "init", 1000)
    commit(work, "products/sw/backend/migrations/005_a.sql", "-- a\n", "m5a", 1001)
    commit(work, "products/sw/backend/migrations/005_b.sql", "-- b\n", "m5b (pre-existing dup)", 1002)
    sh(work, "git", "push", "-q", "origin", "dev")
    runner_dir = tmp_path / "runner"
    sh(tmp_path, "git", "clone", "-q", str(origin), str(runner_dir))
    for d in (work, runner_dir):
        sh(d, "git", "config", "user.name", "t")
        sh(d, "git", "config", "user.email", "t@t")
    return {"origin": str(origin), "work": str(work), "runner": str(runner_dir)}


def enqueue(w, slug, files, when, base="origin/dev"):
    work = w["work"]
    sh(work, "git", "fetch", "-q", "origin")
    sh(work, "git", "checkout", "-q", "-B", f"feat/{slug}", base)
    sha = None
    for i, (path, text) in enumerate(files):
        sha = commit(work, path, text, f"{slug} {i}", when + i)
    sh(work, "git", "push", "-q", "origin", f"{sha}:refs/heads/mq/{slug}--{sha[:7]}")
    return sha


def make_queue(w, ci, regen=lambda wt: (True, "")):
    # regen injected: the real one shells out to cli.py --update-kb-counts (absent in tmp repos)
    return mq.Queue("o/r", run=ci, run_id="7", poll_s=0, sleep=lambda s: None,
                    workdir=w["runner"], log=lambda m: None, regen=regen)


_NOREGEN = make_queue.__defaults__[0]  # same injected no-op regen for tests that build Queue directly


def origin_dev(w):
    return sh(w["origin"], "git", "rev-parse", "refs/heads/dev")


def queue_refs(w):
    return sh(w["origin"], "git", "for-each-ref", "--format=%(refname)", "refs/heads/mq/").split()


# ── pure helpers ────────────────────────────────────────────────────────────

def test_parse_and_order_entries_fifo():
    a = mq.parse_entry("mq/feat-a--abc1234", "a" * 40, 20)
    b = mq.parse_entry("mq/b--1234567", "b" * 40, 10)
    assert a.slug == "feat-a" and b.slug == "b"
    assert [e.slug for e in mq.order_entries([a, b])] == ["b", "feat-a"]
    assert mq.parse_entry("other/x", "c" * 40, 1) is None


def test_ledger_only_predicate_matches_ci_paths_ignore():
    assert mq.is_ledger_only(["project-history/branch-tree.ndjson"])
    assert not mq.is_ledger_only(["project-history/branch-tree.ndjson", "README.md"])
    assert not mq.is_ledger_only([])


def test_new_migration_collision_ignores_preexisting_duplicates():
    before = ["products/sw/backend/migrations/005_a.sql", "products/sw/backend/migrations/005_b.sql",
              "products/sw/backend/migrations/320_x.sql"]
    after = before + ["products/sw/backend/migrations/320_y.sql", "products/sw/backend/migrations/321_z.sql"]
    got = mq.new_migration_collisions(before, after)
    assert [(c["number"], len(c["files"])) for c in got] == [("320", 2)]


def test_bisection_halves_then_resets():
    assert mq.next_batch_limit(4, 4, green=False) == 2
    assert mq.next_batch_limit(2, 2, green=False) == 1
    assert mq.next_batch_limit(1, 3, green=False) == 2
    assert mq.next_batch_limit(1, 1, green=True) == mq.DEFAULT_BATCH


def test_post_land_workflows_are_path_scoped():
    assert mq.post_land_workflows(["products/agents/backend/x.py"]) == ["agents-secc-ci.yml"]
    assert mq.post_land_workflows(["products/social-wiring/x.py"]) == []


# ── the drain, against a real git remote ───────────────────────────────────

def test_green_batch_lands_in_fifo_order_and_marks_each_entry(world):
    a = enqueue(world, "a", [("a.txt", "a\n")], 2000)
    b = enqueue(world, "b", [("b.txt", "b\n")], 2100)
    ci = FakeCI(world["origin"])
    res = make_queue(world, ci).drain()
    assert [x["slug"] for x in res.landed] == ["a", "b"]
    tree = sh(world["origin"], "git", "ls-tree", "-r", "--name-only", "dev")
    assert "a.txt" in tree and "b.txt" in tree
    assert ci.last(a)[0] == "success" and ci.last(b)[0] == "success"
    assert queue_refs(world) == []
    assert len(ci.dispatched) == 1  # ONE CI run for the batch
    assert not sh(world["origin"], "git", "for-each-ref", "refs/heads/mq-candidate/")


def test_candidate_run_is_dispatched_with_the_dev_base(world):
    # 2026-11-05: without it the range keepers judged SHA~50..SHA.
    dev_before = sh(world["origin"], "git", "rev-parse", "refs/heads/dev")
    enqueue(world, "a", [("a.txt", "a\n")], 2000)
    ci = FakeCI(world["origin"])
    make_queue(world, ci).drain()
    assert ci.bases == [f"base={dev_before}"]


def test_red_batch_bisects_and_ejects_only_the_culprit(world):
    good = enqueue(world, "good", [("g.txt", "g\n")], 2000)
    bad = enqueue(world, "bad", [("BREAK", "boom\n")], 2100)
    later = enqueue(world, "later", [("l.txt", "l\n")], 2200)
    ci = FakeCI(world["origin"])
    res = make_queue(world, ci).drain()
    assert {x["slug"] for x in res.landed} == {"good", "later"}
    assert [x["slug"] for x in res.ejected] == ["bad"]
    assert ci.last(bad)[0] == "failure" and "ci_red" in ci.last(bad)[1]
    assert ci.last(good)[0] == "success" and ci.last(later)[0] == "success"
    assert "BREAK" not in sh(world["origin"], "git", "ls-tree", "-r", "--name-only", "dev")


def test_conflicting_entry_is_ejected_without_blocking_the_rest(world):
    first = enqueue(world, "first", [("shared.txt", "one\n")], 2000)
    clash = enqueue(world, "clash", [("shared.txt", "two\n")], 2100)
    ci = FakeCI(world["origin"])
    res = make_queue(world, ci).drain()
    assert [x["slug"] for x in res.landed] == ["first"]
    assert res.ejected[0]["slug"] == "clash" and res.ejected[0]["kind"] == "conflict"
    assert ci.last(clash)[0] == "failure"
    assert ci.last(first)[0] == "success"


def test_duplicate_migration_number_is_ejected(world):
    enqueue(world, "m1", [("products/sw/backend/migrations/320_bib.sql", "-- 1\n")], 2000)
    dup = enqueue(world, "m2", [("products/sw/backend/migrations/320_hide.sql", "-- 2\n")], 2100)
    ci = FakeCI(world["origin"])
    res = make_queue(world, ci).drain()
    assert [x["slug"] for x in res.landed] == ["m1"]
    assert res.ejected[0]["kind"] == "migration_collision"
    assert "320" in ci.last(dup)[1]


def test_flaky_red_is_rerun_once_before_judging(world):
    a = enqueue(world, "a", [("a.txt", "a\n")], 2000)
    ci = FakeCI(world["origin"], flaky_once=True)
    res = make_queue(world, ci).drain()
    assert ci.reruns == 1
    assert [x["slug"] for x in res.landed] == ["a"] and ci.last(a)[0] == "success"


def test_ledger_only_dev_advance_is_replayed_without_a_retest(world, monkeypatch):
    a = enqueue(world, "a", [("a.txt", "a\n")], 2000)
    ci = FakeCI(world["origin"])
    q = make_queue(world, ci)
    real_dispatch = q.dispatch_and_wait

    def dispatch_then_ledger_push(ref, sha, base=""):
        out = real_dispatch(ref, sha, base)
        # a peer drains a ledger row straight to dev while CI was running
        sh(world["work"], "git", "fetch", "-q", "origin")
        sh(world["work"], "git", "checkout", "-q", "-B", "ledger", "origin/dev")
        commit(world["work"], "project-history/branch-tree.ndjson", "{}\n", "ledger", 2500)
        sh(world["work"], "git", "push", "-q", "origin", "ledger:dev")
        return out

    q.dispatch_and_wait = dispatch_then_ledger_push  # self-patch-ok: injects a concurrent peer push mid-run (the race under test), no queue logic replaced
    res = q.drain()
    assert [x["slug"] for x in res.landed] == ["a"]
    tree = sh(world["origin"], "git", "ls-tree", "-r", "--name-only", "dev")
    assert "a.txt" in tree and "project-history/branch-tree.ndjson" in tree
    assert len(ci.dispatched) == 1
    assert ci.last(a)[0] == "success"


def test_code_advance_of_dev_forces_a_retest(world):
    a = enqueue(world, "a", [("a.txt", "a\n")], 2000)
    ci = FakeCI(world["origin"])
    q = make_queue(world, ci)
    real_dispatch = q.dispatch_and_wait
    pushed = {"done": False}

    def dispatch_then_code_push(ref, sha, base=""):
        out = real_dispatch(ref, sha, base)
        if not pushed["done"]:
            pushed["done"] = True
            sh(world["work"], "git", "fetch", "-q", "origin")
            sh(world["work"], "git", "checkout", "-q", "-B", "direct", "origin/dev")
            commit(world["work"], "direct.py", "x = 1\n", "legacy direct push", 2500)
            sh(world["work"], "git", "push", "-q", "origin", "direct:dev")
        return out

    q.dispatch_and_wait = dispatch_then_code_push  # self-patch-ok: injects a concurrent peer push mid-run (the race under test), no queue logic replaced
    res = q.drain()
    assert len(ci.dispatched) == 2  # re-tested on top of the moved dev
    assert [x["slug"] for x in res.landed] == ["a"]
    assert ci.last(a)[0] == "success"


def test_entry_carrying_merge_commits_lands_via_no_ff_merge(world):
    work = world["work"]
    sh(work, "git", "fetch", "-q", "origin")
    sh(work, "git", "checkout", "-q", "-B", "side", "origin/dev")
    commit(work, "side.txt", "s\n", "side", 1900)
    sh(work, "git", "checkout", "-q", "-B", "feat/train", "origin/dev")
    commit(work, "t.txt", "t\n", "t", 1950)
    subprocess.run(["git", "merge", "-q", "--no-ff", "--no-edit", "side"], cwd=work, check=True,
                   capture_output=True)
    # dev moves first, so the train is NOT a fast-forward
    other = enqueue(world, "other", [("o.txt", "o\n")], 2000)
    sh(work, "git", "checkout", "-q", "feat/train")
    train_sha = sh(work, "git", "rev-parse", "HEAD")
    sh(work, "git", "push", "-q", "origin", f"{train_sha}:refs/heads/mq/train--{train_sha[:7]}")
    ci = FakeCI(world["origin"])
    res = make_queue(world, ci).drain()
    assert {x["slug"] for x in res.landed} == {"other", "train"}
    tree = sh(world["origin"], "git", "ls-tree", "-r", "--name-only", "dev")
    assert {"o.txt", "t.txt", "side.txt"} <= set(tree.splitlines())
    assert ci.last(other)[0] == "success"


def _train_world(world):
    work = world["work"]
    sh(work, "git", "fetch", "-q", "origin")
    sh(work, "git", "checkout", "-q", "-B", "side", "origin/dev")
    commit(work, "side.txt", "s\n", "side", 1900)
    sh(work, "git", "checkout", "-q", "-B", "feat/train", "origin/dev")
    commit(work, "t.txt", "t\n", "t", 1950)
    subprocess.run(["git", "merge", "-q", "--no-ff", "--no-edit", "side"], cwd=work, check=True,
                   capture_output=True)
    enqueue(world, "other", [("o.txt", "o\n")], 2000)
    sh(work, "git", "checkout", "-q", "feat/train")
    sha = sh(work, "git", "rev-parse", "HEAD")
    sh(work, "git", "push", "-q", "origin", f"{sha}:refs/heads/mq/train--{sha[:7]}")


def test_merge_composition_runs_the_shadow_merge_loss_detector_and_never_ejects(world):
    _train_world(world)
    seen: list[tuple[str, str]] = []
    logs: list[str] = []

    def detector(wt, merge_sha):
        seen.append((wt, merge_sha))
        return "merge-loss: SHADOW DROPPED 1 line(s) - simulated"
    q = mq.Queue("o/r", run=FakeCI(world["origin"]), run_id="7", poll_s=0, sleep=lambda s: None,
                 workdir=world["runner"], log=logs.append, regen=_NOREGEN, merge_loss=detector)
    res = q.drain()
    assert {x["slug"] for x in res.landed} == {"other", "train"} and not res.ejected   # shadow: lands anyway
    assert len(seen) == 1                       # only the --no-ff merge entry, not the plain ones
    assert len(seen[0][1]) == 40
    assert any("[merge-loss]" in m and "SHADOW DROPPED" in m for m in logs)


def test_shadow_detector_without_a_cli_reports_skipped_not_silence(world, tmp_path):
    q = make_queue(world, FakeCI(world["origin"]))
    assert "skipped" in q._merge_loss_shadow(str(tmp_path), "a" * 40)


def test_dry_run_touches_nothing(world):
    enqueue(world, "a", [("a.txt", "a\n")], 2000)
    before = origin_dev(world)
    ci = FakeCI(world["origin"])
    res = make_queue(world, ci).drain(dry_run=True)
    assert res.rounds[0]["dry_run"] and origin_dev(world) == before
    assert len(queue_refs(world)) == 1 and not ci.dispatched


def test_read_status_maps_github_states():
    def run(cmd, cwd=None):
        return 0, json.dumps({"state": "success", "description": "landed in dev as abcdef123",
                              "target_url": "u"}), ""
    st = mq.read_status("o/r", "a" * 40, run=run)
    assert st["state"] == "landed" and st["dev_sha"] == "abcdef123"

    def run_none(cmd, cwd=None):
        return 0, "null", ""
    assert mq.read_status("o/r", "a" * 40, run=run_none)["state"] == "queued"


def test_cli_merge_queue_status_does_not_crash_on_os_shadowing():
    # 2026-11-05 (reported by noctusai-00): main() has a branch-local
    # `import os`, which makes `os` a local name for the whole function, so
    # `--merge-queue status` raised UnboundLocalError before doing anything.
    import os as _os
    import subprocess
    import sys
    from pathlib import Path
    cli = Path(__file__).resolve().parents[1] / "cli.py"
    env = {**_os.environ, "GH_TOKEN": "x", "NOCTUS_HOOK_QUIET": "1"}
    r = subprocess.run([sys.executable, str(cli), "--merge-queue", "status", "--merge-queue-sha", "0" * 40],
                       capture_output=True, text=True, env=env, timeout=120)
    assert "UnboundLocalError" not in r.stderr, r.stderr[-500:]


def test_a_green_half_does_not_reset_bisection_onto_fresh_entries(world):
    """2026-11-05: batch -6 [a, bad] red -> -7 [a] green -> the limit RESET and -8 composed bad with
    three innocent entries, turning their batch red too. Suspects now stay isolated until ejected."""
    a = enqueue(world, "a", [("a.txt", "a\n")], 2000)
    bad = enqueue(world, "bad", [("BREAK", "boom\n")], 2100)
    fresh = [enqueue(world, f"f{i}", [(f"f{i}.txt", "x\n")], 2200 + i) for i in range(3)]
    ci = FakeCI(world["origin"])
    red_trees: list[list[str]] = []
    orig = ci.red_if
    def spy(tree):
        red = orig(tree)
        if red:
            red_trees.append(tree)
        return red
    ci.red_if = spy
    res = make_queue(world, ci).drain(batch_limit=2)
    assert [x["slug"] for x in res.ejected] == ["bad"]
    assert {x["slug"] for x in res.landed} == {"a", "f0", "f1", "f2"}
    # the only red runs are the original batch [a, bad] and the singleton [bad] -- never bad + a fresh entry
    for tree in red_trees:
        assert not any(f"f{i}.txt" in tree for i in range(3)), tree
    assert ci.last(bad)[0] == "failure"
    assert all(ci.last(f)[0] == "success" for f in fresh)


# ── workflow-file entries / rejected pushes (2026-11-05 wedge) ─────────────

WF = ".github/workflows/build-and-push.yml"


def _diverge_dev(world):
    """Move dev so queued entries are not fast-forwards (forces a rebase = a NEW commit object)."""
    work = world["work"]
    sh(work, "git", "checkout", "-q", "dev")
    commit(work, "other.txt", "o\n", "dev moved", 1500)
    sh(work, "git", "push", "-q", "origin", "dev")


def _stale_enqueue(world, slug, files, when):
    base = sh(world["work"], "git", "rev-parse", "origin/dev")
    sh(world["work"], "git", "fetch", "-q", "origin")
    return enqueue(world, slug, files, when, base=base)


def test_workflow_touching_entry_is_pre_ejected_and_the_rest_land(world):
    ok1 = _stale_enqueue(world, "ok1", [("a.txt", "a\n")], 2000)
    wf = _stale_enqueue(world, "wf", [(WF, "name: x\n")], 2100)
    ok2 = _stale_enqueue(world, "ok2", [("b.txt", "b\n")], 2200)
    _diverge_dev(world)
    ci = FakeCI(world["origin"])
    res = make_queue(world, ci).drain()
    assert [x["slug"] for x in res.ejected] == ["wf"]
    assert res.ejected[0]["kind"] == "needs_workflow_token"
    assert {x["slug"] for x in res.landed} == {"ok1", "ok2"}
    assert ci.last(wf)[0] == "failure" and "workflows" in ci.last(wf)[1]
    assert ci.last(ok1)[0] == ci.last(ok2)[0] == "success"
    tree = sh(world["origin"], "git", "ls-tree", "-r", "--name-only", "refs/heads/dev")
    assert WF not in tree.splitlines()


def test_workflow_token_seam_switches_the_pre_eject_off(world):
    _stale_enqueue(world, "wf", [(WF, "name: x\n")], 2100)
    _diverge_dev(world)
    q = mq.Queue("o/r", regen=_NOREGEN, run=FakeCI(world["origin"]), run_id="7", poll_s=0, sleep=lambda s: None,
                 workdir=world["runner"], log=lambda m: None, workflow_token=True)
    res = q.drain()
    assert res.ejected == [] and [x["slug"] for x in res.landed] == ["wf"]


def test_rejected_candidate_push_ejects_instead_of_raising(world):
    bad = enqueue(world, "bad", [("a.txt", "a\n")], 2000)
    ci = FakeCI(world["origin"])

    def rejecting(cmd, cwd=None):
        if cmd[:2] == ["git", "push"] and any(str(c).endswith(":refs/heads/mq-candidate/7-1") for c in cmd):
            return 1, "", "! [remote rejected] x (pre-receive hook declined)"
        return ci(cmd, cwd=cwd)

    q = mq.Queue("o/r", regen=_NOREGEN, run=rejecting, run_id="7", poll_s=0, sleep=lambda s: None,
                 workdir=world["runner"], log=lambda m: None)
    res = q.drain()
    assert res.landed == [] and res.ejected[0]["kind"] == "push_rejected"
    assert "pre-receive" in ci.last(bad)[1]


def test_workflow_permission_rejection_maps_to_the_workflow_reason(world):
    ok = enqueue(world, "ok", [("a.txt", "a\n")], 2000)
    wf = enqueue(world, "wf", [(WF, "name: x\n")], 2100)
    ci = FakeCI(world["origin"])
    n = {"c": 0}

    def rejecting(cmd, cwd=None):
        if cmd[:2] == ["git", "push"] and any(":refs/heads/mq-candidate/" in str(c) for c in cmd) and n["c"] == 0:
            n["c"] += 1
            return 1, "", "! [remote rejected] (refusing to allow a GitHub App to create or update workflow `x.yml` without `workflows` permission)"
        return ci(cmd, cwd=cwd)

    q = mq.Queue("o/r", regen=_NOREGEN, run=rejecting, run_id="7", poll_s=0, sleep=lambda s: None,
                 workdir=world["runner"], log=lambda m: None, workflow_token=True)  # defeat the pre-check so the push itself is rejected
    res = q.drain()
    assert [x["slug"] for x in res.ejected] == ["wf"]
    assert res.ejected[0]["kind"] == "needs_workflow_token"
    assert {x["slug"] for x in res.landed} == {"ok"} and ci.last(ok)[0] == "success"
    assert ci.last(wf)[0] == "failure"
    why = res.ejected[0]["why"]
    assert "github.token" in why and "refusing to allow a GitHub App" in why  # names the refused credential


def test_a_refused_pat_push_says_the_pat_was_refused(world):
    """2026-11-11: the PAT pushed a workflow batch at 16:19 and five entries were ejected at 16:41 with a
    reason that could not say whether the PAT or github.token was refused. The reason now says."""
    enqueue(world, "wf", [(WF, "name: x\n")], 2100)
    ci = FakeCI(world["origin"])
    logs: list[str] = []

    def rejecting(cmd, cwd=None):
        if cmd[:4] == ["git", "-c", f"{mq.EXTRAHEADER_KEY}=", "push"]:
            return 1, "", (f"remote: error: GH013 {cmd[4]}\n ! [remote rejected] (refusing to allow a Personal "
                           "Access Token to create or update workflow `x.yml` without `workflows` permission)")
        return ci(cmd, cwd=cwd)

    q = mq.Queue("o/r", regen=_NOREGEN, run=rejecting, run_id="7", poll_s=0, sleep=lambda s: None,
                 workdir=world["runner"], log=logs.append, push_token=TOK)
    res = q.drain()
    x = res.ejected[0]
    assert x["kind"] == "needs_workflow_token"
    assert "MQ_PUSH_TOKEN (PAT)" in x["why"] and "Personal Access Token" in x["why"] and "re-mint" in x["why"]
    assert TOK not in x["why"] and not any(TOK in m for m in logs)  # the stderr quote is redacted
    assert any("rejected" in m and "Personal Access Token" in m for m in logs)


def test_the_default_drain_log_flushes_every_line(capsys, monkeypatch):
    seen = {}
    monkeypatch.setattr("builtins.print", lambda *a, **k: seen.update(k))
    mq._flush_print("x")
    assert seen.get("flush") is True
    assert mq.Queue("o/r").log is mq._flush_print


# ── MQ_PUSH_TOKEN: the PAT is used ONLY for workflow batches ───────────────

TOK = "github_pat_SECRET123"


def _token_runner(world, ci, pushes, cleared=None):
    """Record every push remote; route the authenticated URL to the local bare origin. A PAT push must arrive as
    `git -c <extraheader>= push <url>` - recorded in `cleared` - and is replayed as a plain local push."""
    def run(cmd, cwd=None):
        if cmd[:4] == ["git", "-c", f"{mq.EXTRAHEADER_KEY}=", "push"]:
            if cleared is not None:
                cleared.append(cmd[4])
            cmd = ["git", *cmd[3:]]
        if cmd[:2] == ["git", "push"]:
            pushes.append(cmd[2])
            if cmd[2].startswith("https://x-access-token:"):
                cmd = [*cmd[:2], world["origin"], *cmd[3:]]
        return ci(cmd, cwd=cwd)
    return mq.Queue("o/r", regen=_NOREGEN, run=run, run_id="7", poll_s=0, sleep=lambda s: None,
                    workdir=world["runner"], log=lambda m: None, push_token=TOK)


def test_workflow_batch_pushes_candidate_and_dev_via_the_token_url_and_lands(world):
    wf = _stale_enqueue(world, "wf", [(WF, "name: x\n")], 2100)
    _diverge_dev(world)
    pushes: list[str] = []
    res = _token_runner(world, FakeCI(world["origin"]), pushes).drain()
    assert res.ejected == [] and [x["slug"] for x in res.landed] == ["wf"]
    assert WF in sh(world["origin"], "git", "ls-tree", "-r", "--name-only", "refs/heads/dev").splitlines()
    assert pushes[:2] == [f"https://x-access-token:{TOK}@github.com/o/r.git"] * 2  # candidate, then dev FF
    assert wf  # enqueued


def test_a_pat_push_clears_the_checkout_github_token_header_and_a_plain_push_keeps_it(world):
    """actions/checkout persists `AUTHORIZATION: basic <github.token>` as http.https://github.com/.extraheader; git
    sends it on the PAT URL too, so an uncleared "PAT" push can authenticate as github.token (no workflows)."""
    wf = _stale_enqueue(world, "wf", [(WF, "name: x\n")], 2100)
    _diverge_dev(world)
    pushes: list[str] = []
    cleared: list[str] = []
    res = _token_runner(world, FakeCI(world["origin"]), pushes, cleared).drain()
    assert [x["slug"] for x in res.landed] == ["wf"] and wf
    assert len(cleared) == 2 and all(u.startswith("https://x-access-token:") for u in cleared)
    q = mq.Queue("o/r", push_token=TOK)
    assert q.push_cmd("origin", "a:b") == ["git", "push", "origin", "a:b"]


def test_non_workflow_batch_with_token_still_pushes_via_the_plain_remote(world):
    enqueue(world, "ok", [("a.txt", "a\n")], 2000)
    pushes: list[str] = []
    res = _token_runner(world, FakeCI(world["origin"]), pushes).drain()
    assert [x["slug"] for x in res.landed] == ["ok"]
    assert not any("x-access-token" in p for p in pushes)


def test_no_token_keeps_the_pre_eject(world):
    _stale_enqueue(world, "wf", [(WF, "name: x\n")], 2100)
    _diverge_dev(world)
    q = make_queue(world, FakeCI(world["origin"]))
    assert q.push_token == "" and q.workflow_token is False
    assert [x["kind"] for x in q.drain().ejected] == ["needs_workflow_token"]


def test_token_never_surfaces_in_errors_statuses_or_verdicts(world):
    bad = enqueue(world, "bad", [(WF, "name: x\n")], 2000)
    ci = FakeCI(world["origin"])
    msg = f"fatal: unable to access 'https://x-access-token:{TOK}@github.com/o/r.git/': 403 {TOK}"

    def run(cmd, cwd=None):
        if cmd[:2] == ["git", "push"] and ":refs/heads/mq-candidate/" in cmd[-1]:
            return 1, "", msg
        return ci(cmd, cwd=cwd)

    q = mq.Queue("o/r", regen=_NOREGEN, run=run, run_id="7", poll_s=0, sleep=lambda s: None,
                 workdir=world["runner"], log=lambda m: None, push_token=TOK)
    res = q.drain()
    blob = json.dumps(res.ejected) + json.dumps(ci.statuses)
    assert res.ejected and TOK not in blob and bad in ci.statuses
    assert TOK not in q._redact(msg) and "***" in q._redact(msg)
    rc = lambda cmd, cwd=None: (1, "", msg)  # noqa: E731
    q2 = mq.Queue("o/r", regen=_NOREGEN, run=rc, workdir=world["runner"], log=lambda m: None, push_token=TOK)
    with pytest.raises(RuntimeError) as ei:
        q2.git("push", f"https://x-access-token:{TOK}@github.com/o/r.git", "x")
    assert TOK not in str(ei.value)


# ── the workflow file itself: kick → dev-only drain ────────────────────────

def test_merge_queue_workflow_splits_kick_from_the_dev_only_drain():
    import yaml
    wf = yaml.safe_load((Path(__file__).resolve().parents[3] / ".github/workflows/merge-queue.yml").read_text())
    jobs = wf["jobs"]
    assert set(jobs) == {"kick", "drain"}
    kick, drain = jobs["kick"], jobs["drain"]
    assert "environment" not in kick and "secrets." not in json.dumps(kick)
    assert kick["if"] == "github.event_name == 'push'" and "timeout-minutes" in kick
    assert drain["environment"] == "merge-queue"
    assert drain["if"] == "github.event_name != 'push' && github.ref == 'refs/heads/dev'"
    step_env = {k: v for st in drain["steps"] for k, v in st.get("env", {}).items()}
    assert step_env["MQ_PUSH_TOKEN"] == "${{ secrets.MQ_PUSH_TOKEN }}"
    assert drain["concurrency"]["cancel-in-progress"] is False and "concurrency" not in wf
    assert json.dumps(drain).count("secrets.") == 1  # only the drain step reads the PAT


# ── kb-counts regeneration at compose ───────────────────────────────────────

def _compose_one(w, regen):
    sha = enqueue(w, "kc", [("a.txt", "a\n")], 5000)
    q = make_queue(w, FakeCI(w["origin"]), regen=regen)
    q.fetch()
    base = q.dev_sha()
    wt = str(Path(w["runner"]).parent / "wt")
    head, applied, ejected = q.compose(q.entries(), base, wt)
    return q, wt, base, head, applied, ejected


def test_compose_commits_regenerated_counts_when_they_change(world):
    def regen(wt):
        p = Path(wt) / "KNOWLEDGE-BASE" / "doc.md"
        p.parent.mkdir(exist_ok=True)
        p.write_text("count=derived\n")
        return True, ""
    q, wt, base, head, applied, ejected = _compose_one(world, regen)
    assert [e.slug for e in applied] == ["kc"] and not ejected
    assert sh(wt, "git", "log", "-1", "--format=%s", head) == "chore(kb-counts): regenerate derived counts at compose [auto]"
    assert sh(wt, "git", "show", f"{head}:KNOWLEDGE-BASE/doc.md") == "count=derived"


def test_compose_commits_a_regenerated_TRACKED_file_first_in_status(world):
    """The real CI shape (2026-11-06 wedge): regen MODIFIES a tracked count file, so
    `git status --porcelain` starts with ' M <path>'. A stripped output ate that
    leading space and `ln[3:]` cut the path to 'NOWLEDGE-BASE/...' -> every drain crashed."""
    enqueue(world, "kc", [("KNOWLEDGE-BASE/CONTEXT/02-LANDSCAPE.md", "count=stale\n")], 5000)
    q = make_queue(world, FakeCI(world["origin"]),
                   regen=lambda wt: ((Path(wt) / "KNOWLEDGE-BASE/CONTEXT/02-LANDSCAPE.md").write_text("count=derived\n"), (True, ""))[1])
    q.fetch()
    base = q.dev_sha()
    wt = str(Path(world["runner"]).parent / "wt")
    head, applied, ejected = q.compose(q.entries(), base, wt)
    assert [e.slug for e in applied] == ["kc"] and not ejected
    assert sh(wt, "git", "show", f"{head}:KNOWLEDGE-BASE/CONTEXT/02-LANDSCAPE.md") == "count=derived"


def test_a_failing_counts_commit_ejects_the_entry_never_crashes_the_drain(world):
    enqueue(world, "kc", [("KNOWLEDGE-BASE/CONTEXT/02-LANDSCAPE.md", "count=stale\n")], 5000)
    ci = FakeCI(world["origin"])

    def run(cmd, cwd=None):
        if cmd[:2] == ["git", "commit"] and "regenerate derived counts" in " ".join(map(str, cmd)):
            return 1, "", "fatal: simulated commit failure"
        return ci(cmd, cwd=cwd)
    q = make_queue(world, run,
                   regen=lambda wt: ((Path(wt) / "KNOWLEDGE-BASE/CONTEXT/02-LANDSCAPE.md").write_text("count=derived\n"), (True, ""))[1])
    q.fetch()
    base = q.dev_sha()
    head, applied, ejected = q.compose(q.entries(), base, str(Path(world["runner"]).parent / "wt"))
    assert applied == [] and ejected[0]["kind"] == "kb_counts_regen"
    assert "simulated commit failure" in ejected[0]["why"]


def test_compose_makes_no_commit_when_counts_unchanged(world):
    q, wt, base, head, applied, ejected = _compose_one(world, lambda wt: (True, ""))
    assert [e.slug for e in applied] == ["kc"]
    assert "regenerate derived counts" not in sh(wt, "git", "log", "--format=%s", f"{base}..{head}")


def test_compose_ejects_with_reason_when_regeneration_fails(world):
    q, wt, base, head, applied, ejected = _compose_one(world, lambda wt: (False, "No module named noctusai_lib"))
    assert applied == [] and head == base
    assert ejected[0]["kind"] == "kb_counts_regen"
    assert "noctusai_lib" in ejected[0]["why"]


# ── derived-ledger conflicts re-derived at compose (not ejected) ─────────────

DERIVED = "project-history/access-tiers/findings.ndjson"


def _compose_pair(w, first_files, second_files, derived_regen, logs):
    enqueue(w, "first", first_files, 6000)
    enqueue(w, "second", second_files, 6100)
    q = mq.Queue("o/r", run=FakeCI(w["origin"]), run_id="7", poll_s=0, sleep=lambda s: None,
                 workdir=w["runner"], log=logs.append, regen=_NOREGEN, derived_regen=derived_regen)
    q.fetch()
    wt = str(Path(w["runner"]).parent / "wt")
    return q, wt, *q.compose(q.entries(), q.dev_sha(), wt)


def test_derived_only_conflict_is_rederived_not_ejected(world):
    calls, logs = [], []

    def regen(wt, ds):
        calls.append(ds["name"])
        (Path(wt) / DERIVED).write_text("derived-from-merged-tree\n")
        return True, ""
    q, wt, head, applied, ejected = _compose_pair(
        world, [(DERIVED, "one\n"), ("a.txt", "a\n")], [(DERIVED, "two\n"), ("b.txt", "b\n")], regen, logs)
    assert [e.slug for e in applied] == ["first", "second"] and not ejected
    assert calls == ["access-tiers"]
    assert sh(wt, "git", "show", f"{head}:{DERIVED}") == "derived-from-merged-tree"
    assert sh(wt, "git", "show", f"{head}:a.txt") == "a" and sh(wt, "git", "show", f"{head}:b.txt") == "b"
    assert len([m for m in logs if m.startswith("[mq-derived-regen] set=access-tiers slug=second")]) == 1


def test_mixed_derived_and_real_conflict_is_still_ejected(world):
    calls, logs = [], []
    q, wt, head, applied, ejected = _compose_pair(
        world, [(DERIVED, "one\n"), ("shared.txt", "one\n")], [(DERIVED, "two\n"), ("shared.txt", "two\n")],
        lambda wt, ds: (calls.append(1), (True, ""))[1], logs)
    assert [e.slug for e in applied] == ["first"]
    assert ejected[0]["slug"] == "second" and ejected[0]["kind"] == "conflict" and "shared.txt" in ejected[0]["why"]
    assert not calls and not [m for m in logs if "mq-derived-regen" in m]


def test_no_conflict_never_invokes_the_derived_regen(world):
    calls, logs = [], []
    q, wt, head, applied, ejected = _compose_pair(
        world, [("a.txt", "a\n")], [("b.txt", "b\n")], lambda wt, ds: (calls.append(1), (True, ""))[1], logs)
    assert [e.slug for e in applied] == ["first", "second"] and not ejected and not calls


def test_derived_regen_failure_ejects_with_its_own_kind(world):
    q, wt, head, applied, ejected = _compose_pair(
        world, [(DERIVED, "one\n")], [(DERIVED, "two\n")], lambda wt, ds: (False, "scanner boom"), [])
    assert [e.slug for e in applied] == ["first"]
    assert ejected[0]["kind"] == "derived_regen" and "scanner boom" in ejected[0]["why"]


def test_derived_set_registry_is_data_and_matches_only_whole_sets():
    assert mq.derived_set_for([DERIVED, "project-history/access-tiers/FINDINGS.md"])["name"] == "access-tiers"
    assert mq.derived_set_for([DERIVED, "README"]) is None and mq.derived_set_for([]) is None


def test_derived_only_commit_empties_after_resolve_is_skipped_not_ejected(world):
    calls, logs = [], []

    def regen(wt, ds):
        calls.append(ds["name"])
        (Path(wt) / DERIVED).write_text("derived-from-merged-tree\n")
        return True, ""
    q, wt, head, applied, ejected = _compose_pair(
        world, [(DERIVED, "one\n"), ("a.txt", "a\n")], [("b.txt", "b\n"), (DERIVED, "two\n")], regen, logs)
    assert [e.slug for e in applied] == ["first", "second"] and not ejected
    assert calls == ["access-tiers"]
    assert sh(wt, "git", "show", f"{head}:b.txt") == "b"
    assert sh(wt, "git", "show", f"{head}:{DERIVED}") == "derived-from-merged-tree"


# ── culprit attribution (2026-11-11): a red batch ejects the one entry whose diff covers the failure ──

def _fail_line(test_id, job="Tooling Tests (pytest)"):
    return f"{job}\tRun pytest\t2026-11-11T10:00:00Z FAILED {test_id} - AssertionError\n"


def _attr_rounds(res):
    return [r.get("attribution", {}).get("path") for r in res.rounds if "attribution" in r]


def test_attribute_culprit_is_pure_and_never_guesses():
    paths = {"mq/a--1": ["mcp/noctusai/tools/x.py"], "mq/b--2": ["products/sw/backend/app/y.py"]}
    ref, why = mq.attribute_culprit(["mcp/noctusai/tests/test_x.py::test_a"], [], paths)
    assert ref == "mq/a--1" and "test_x.py" in why and "mcp/noctusai/tools/x.py" in why
    ref, why = mq.attribute_culprit([], ["Some Unknown Job"], paths)
    assert ref is None and "unreadable" in why


def test_single_attributable_culprit_is_ejected_without_bisect(world):
    good = enqueue(world, "good", [("products/sw/backend/app/g.py", "g\n")], 2000)
    bad = enqueue(world, "bad", [("mcp/noctusai/tools/BREAK.py", "boom\n")], 2100)
    ci = FakeCI(world["origin"], red_if=lambda t: any("BREAK" in p for p in t),
                failed_log=_fail_line("mcp/noctusai/tests/test_thing.py::test_it"), failed_job="MCP Toolkit Tests")
    res = make_queue(world, ci).drain()
    assert [x["slug"] for x in res.ejected] == ["bad"]
    assert res.ejected[0]["kind"] == "ci_red_attributed"
    assert "test_thing.py::test_it" in res.ejected[0]["why"] and "BREAK.py" in res.ejected[0]["why"]
    assert {x["slug"] for x in res.landed} == {"good"}
    assert "attributed" in _attr_rounds(res)
    assert ci.last(bad)[0] == "failure" and "ci_red_attributed" in ci.last(bad)[1]
    assert len(ci.dispatched) == 2  # the red batch + ONE rerun of the rest; a bisect would need more


def test_ambiguous_match_falls_back_to_bisect(world):
    a = enqueue(world, "a", [("mcp/noctusai/tools/a.py", "a\n")], 2000)
    b = enqueue(world, "b", [("mcp/noctusai/tools/BREAK.py", "boom\n")], 2100)
    ci = FakeCI(world["origin"], red_if=lambda t: any("BREAK" in p for p in t),
                failed_log=_fail_line("mcp/noctusai/tests/test_thing.py::test_it"), failed_job="MCP Toolkit Tests")
    logs = []
    q = make_queue(world, ci)
    q.log = logs.append
    res = q.drain()
    assert [x["slug"] for x in res.ejected] == ["b"] and res.ejected[0]["kind"] == "ci_red"
    assert "bisect" in _attr_rounds(res)
    assert any("bisect" in m and "2 entries" in m for m in logs)


def test_unreadable_failure_falls_back_to_bisect(world):
    enqueue(world, "a", [("products/sw/backend/app/a.py", "a\n")], 2000)
    enqueue(world, "b", [("BREAK", "boom\n")], 2100)
    ci = FakeCI(world["origin"], failed_log="garbage with no failures\n", failed_job="Mystery Job")
    logs = []
    q = make_queue(world, ci)
    q.log = logs.append
    res = q.drain()
    assert res.ejected[0]["kind"] == "ci_red" and "bisect" in _attr_rounds(res)
    assert any("unreadable" in m for m in logs)


def test_verify_db_guards_failure_attributes_to_the_migration_entry_of_that_product(world):
    enqueue(world, "code", [("products/agents/backend/app/x.py", "x\n")], 2000)
    enqueue(world, "mig-sw", [("products/sw/backend/migrations/006_s.sql", "-- s\n")], 2050)
    bad = enqueue(world, "mig-agents", [("products/agents/backend/migrations/001_a.sql", "-- BREAK\n"),
                                        ("products/agents/backend/BREAK", "x\n")], 2100)
    ci = FakeCI(world["origin"], failed_job="MCP Toolkit Tests", red_if=lambda t: any("BREAK" in p for p in t),
                failed_log=_fail_line("mcp/noctusai/tests/test_verify_db_guards.py::TestAgentsStudioProbes::test_p",
                                      "MCP Toolkit Tests"))
    res = make_queue(world, ci).drain()
    assert res.ejected[0]["slug"] == "mig-agents" and res.ejected[0]["kind"] == "ci_red_attributed"
    assert "001_a.sql" in res.ejected[0]["why"] and "test_verify_db_guards" in res.ejected[0]["why"]
    assert ci.last(bad)[0] == "failure"


# ── priority lane + parallel product-disjoint candidates (2026-11-11) ─────────

def _ci_runs(ci):
    return [d for d in ci.dispatched if d[0] == mq.CI_WORKFLOW]  # post-land workflow dispatches are not CI runs


def test_areas_and_partition_are_pure_and_conservative():
    assert mq.entry_areas(["products/sw/a.py", "products/agents/b.py"]) == {"sw", "agents"}
    assert mq.entry_areas(["products/sw/a.py", "mcp/x.py"]) == {"sw", mq.SHARED_AREA}
    assert mq.entry_areas(["products/seed/a.py"]) == {mq.SHARED_AREA}
    assert mq.entry_areas([]) == {mq.SHARED_AREA}  # unreadable diff = shared
    es = [mq.Entry(f"mq/{n}--abc1234", "s", n, i) for i, n in enumerate("abcd")]
    paths = {"mq/a--abc1234": ["products/sw/1"], "mq/b--abc1234": ["products/agents/1"],
             "mq/c--abc1234": ["products/sw/2"], "mq/d--abc1234": ["mcp/x"]}
    groups = mq.partition_wave(es, paths, 4)
    assert [[e.slug for e in g] for g in groups] == [["a", "c"], ["b"]]  # same product merges; the shared tail waits
    assert mq.partition_wave(es, paths, 4, k=1) == []  # one group is no wave
    assert mq.partition_wave(es[3:], paths, 4) == [] and mq.partition_wave([es[3], es[0], es[1]], paths, 4) == []
    assert mq.is_priority([".github/dependabot.yml"]) and mq.is_priority(["x"], "t\n\nMQ-Priority: ci is red")
    assert not mq.is_priority(["products/sw/a"], "no trailer MQ-Priority in prose")


def test_github_diff_entry_composes_first_and_alone(world):
    enqueue(world, "old", [("old.txt", "o\n")], 2000)
    enqueue(world, "ciFix", [(".github/dependabot.yml", "x: 1\n")], 2100)
    ci = FakeCI(world["origin"])
    res = make_queue(world, ci).drain()
    assert res.rounds[0]["batch"] == ["ciFix"]  # ahead of the older entry, alone
    assert [x["slug"] for x in res.landed] == ["ciFix", "old"]


def test_priority_trailer_flag_composes_first_and_alone(world):
    enqueue(world, "old", [("old.txt", "o\n")], 2000)
    enqueue(world, "urgent", [("u.txt", "u\n")], 2100)
    sha = sh(world["work"], "git", "rev-parse", "HEAD")
    sh(world["work"], "git", "commit", "-q", "--amend", "-m", "urgent\n\nMQ-Priority: unblocks CI")
    new = sh(world["work"], "git", "rev-parse", "HEAD")
    sh(world["work"], "git", "push", "-q", "origin", f"{new}:refs/heads/mq/urgent--{new[:7]}", f":refs/heads/mq/urgent--{sha[:7]}")
    res = make_queue(world, FakeCI(world["origin"])).drain()
    assert res.rounds[0]["batch"] == ["urgent"]
    assert {x["slug"] for x in res.landed} == {"old", "urgent"}


def test_two_product_disjoint_entries_run_concurrently_and_both_land_without_a_retest(world):
    a = enqueue(world, "a", [("products/sw/a.txt", "a\n")], 2000)
    b = enqueue(world, "b", [("products/agents/b.txt", "b\n")], 2100)
    ci = FakeCI(world["origin"], barrier=threading.Barrier(2))  # both runs must be in flight at once
    res = make_queue(world, ci).drain()
    assert {x["slug"] for x in res.landed} == {"a", "b"} and not res.ejected
    assert len(_ci_runs(ci)) == 2  # two candidates, and NO third run to re-test the second on the new tip
    assert all(r.get("parallel") for r in res.rounds)
    tree = sh(world["origin"], "git", "ls-tree", "-r", "--name-only", "dev")
    assert "products/sw/a.txt" in tree and "products/agents/b.txt" in tree
    assert ci.last(a)[0] == "success" and ci.last(b)[0] == "success"
    assert queue_refs(world) == [] and not sh(world["origin"], "git", "for-each-ref", "refs/heads/mq-candidate/")


def test_shared_entry_never_runs_alongside_another_candidate(world):
    enqueue(world, "p1", [("products/sw/a.txt", "a\n")], 2000)
    enqueue(world, "p2", [("products/agents/b.txt", "b\n")], 2100)
    enqueue(world, "sh", [("mcp/tool.py", "t\n")], 2200)
    ci = FakeCI(world["origin"])
    res = make_queue(world, ci).drain()
    assert {x["slug"] for x in res.landed} == {"p1", "p2", "sh"}
    parallel = [r for r in res.rounds if r.get("parallel")]
    assert sorted(sum((r["batch"] for r in parallel), [])) == ["p1", "p2"]
    shared_round = next(r for r in res.rounds if r["batch"] == ["sh"])
    assert not shared_round.get("parallel") and res.rounds.index(shared_round) == len(res.rounds) - 1


def test_shared_entry_in_front_keeps_the_single_batch(world):
    enqueue(world, "sh", [("mcp/tool.py", "t\n")], 2000)
    enqueue(world, "p1", [("products/sw/a.txt", "a\n")], 2100)
    enqueue(world, "p2", [("products/agents/b.txt", "b\n")], 2200)
    ci = FakeCI(world["origin"])
    res = make_queue(world, ci).drain()
    assert len(_ci_runs(ci)) == 1 and not any(r.get("parallel") for r in res.rounds)
    assert len(res.landed) == 3


def test_a_red_parallel_candidate_ejects_only_itself(world):
    good = enqueue(world, "good", [("products/sw/g.txt", "g\n")], 2000)
    bad = enqueue(world, "bad", [("products/agents/BREAK", "boom\n")], 2100)
    ci = FakeCI(world["origin"], red_if=lambda t: any("BREAK" in p for p in t), barrier=threading.Barrier(2))
    res = make_queue(world, ci).drain()
    assert [x["slug"] for x in res.landed] == ["good"]
    assert [x["slug"] for x in res.ejected] == ["bad"] and res.ejected[0]["kind"] == "ci_red"
    assert ci.last(good)[0] == "success" and ci.last(bad)[0] == "failure"
    assert "BREAK" not in sh(world["origin"], "git", "ls-tree", "-r", "--name-only", "dev")


def test_second_green_whose_derived_files_move_on_the_combined_tree_is_retested(world):
    # counts.md is DERIVED from the whole tree: each candidate wrote 1, the combined tree needs 2 -> not the union
    # of the tested trees, so the second green must NOT land untested; the next round re-tests it on the new tip.
    def regen(wt):
        n = len([p for p in Path(wt, "products").rglob("*.txt")])
        f = Path(wt, "KNOWLEDGE-BASE", "counts.md")
        f.parent.mkdir(exist_ok=True)
        f.write_text(f"n={n}\n")
        return True, ""
    enqueue(world, "a", [("products/sw/a.txt", "a\n")], 2000)
    enqueue(world, "b", [("products/agents/b.txt", "b\n")], 2100)
    ci = FakeCI(world["origin"], barrier=threading.Barrier(2))
    res = make_queue(world, ci, regen=regen).drain()
    assert {x["slug"] for x in res.landed} == {"a", "b"}
    assert len(_ci_runs(ci)) == 3  # a, b in parallel; b re-tested on a's tip
    assert sh(world["origin"], "git", "show", "dev:KNOWLEDGE-BASE/counts.md") == "n=2"


def test_parallel_candidates_that_would_not_recompose_cleanly_stay_queued(world):
    enqueue(world, "a", [("products/sw/a.txt", "a\n")], 2000)
    enqueue(world, "b", [("products/agents/b.txt", "b\n")], 2100)
    ci = FakeCI(world["origin"], barrier=threading.Barrier(2))
    q = make_queue(world, ci)
    real = q.compose
    calls = []

    def compose(batch, base, wt):
        calls.append(base)
        if len(calls) == 3:  # the re-compose of the second green on the new tip
            return base, [], [q._eject_info(batch[0], "conflict", "x")]
        return real(batch, base, wt)

    q.compose = compose  # self-patch-ok: forces the re-compose outcome (a conflict) to prove the fallback; the landing logic itself is untouched
    res = q.drain(max_rounds=1)
    assert len(res.landed) == 1 and not res.ejected  # the other is neither landed untested nor ejected
    assert len(queue_refs(world)) == 1
