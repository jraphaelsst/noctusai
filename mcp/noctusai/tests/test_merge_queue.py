"""merge_queue: the CI-side drain against a REAL git remote (a local bare repo).

Only `gh` is faked — git runs for real, so compose/rebase/merge/FF/ledger-only
replay are exercised exactly as on the runner. The fake CI decides green/red
from the candidate TREE (a file named BREAK makes it red), which is what a real
`Tests & Build` does: judge the composed code, not the entry in isolation.
"""
from __future__ import annotations

import json
import subprocess
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

    def __init__(self, origin: str, red_if=lambda tree: "BREAK" in tree, flaky_once=False):
        self.origin, self.red_if, self.flaky_once = origin, red_if, flaky_once
        self.statuses: dict[str, list[tuple[str, str]]] = {}
        self.dispatched: list[tuple[str, str]] = []
        self.bases: list[str] = []
        self.reruns = 0
        self._runs: dict[str, str] = {}

    def __call__(self, cmd, cwd=None):
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
        if args[:2] == ["run", "view"]:
            sha = self._runs[args[2]]
            tree = sh(self.origin, "git", "ls-tree", "-r", "--name-only", sha)
            red = self.red_if(tree.splitlines())
            if self.flaky_once and self.reruns == 0:
                red = True
            concl = "failure" if red else "success"
            jobs = [{"name": "Product Backend Tests (x)", "conclusion": concl}]
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


def make_queue(w, ci):
    return mq.Queue("o/r", run=ci, run_id="7", poll_s=0, sleep=lambda s: None,
                    workdir=w["runner"], log=lambda m: None)


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
