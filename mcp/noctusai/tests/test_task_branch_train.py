"""Colocated tests for `task_branch action='train'` (merge-all-before-integrating).

Pure helpers + fakes for the rider teardown, plus ONE real-git test: a tmp repo,
3 feature branches, one real conflict (left in progress, then resolved, then the
train re-run is idempotent)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import task_branch as T  # noqa: E402
from tools.noctus.dev import task_branch_train as TR  # noqa: E402


def test_train_slug_is_prefixed_and_idempotent():
    assert TR.train_slug("wave3", "20261024") == "train-wave3"
    assert TR.train_slug("train-wave3", "20261024") == "train-wave3"
    assert TR.train_slug(None, "20261024") == "train-20261024"


def test_parse_train_riders_oldest_first_dedup_ignores_noise():
    subjects = ["train(w): merge feat/c", "fix(docs): combine", "Merge branch 'x'",
                "train(w): merge feat/b", "train(w): merge feat/a", "train(w): merge feat/b"]
    assert TR.parse_train_riders(subjects) == ["b", "a", "c"]
    assert TR.parse_train_riders(["feat: nothing"]) == []
    assert TR.parse_train_riders(["Merge branch 'feat/c' into feat/train-w"]) == ["c"]


def test_merge_subject_roundtrips_through_the_parser():
    assert TR.parse_train_riders([TR.merge_subject("train-w3", "c1")]) == ["c1"]


def test_overlap_and_least_conflict_first_ordering():
    f = {"a": {"x", "y"}, "b": {"y", "z"}, "c": {"q"}}
    assert TR.overlap_files(f) == {"y": ["a", "b"]}
    assert TR.order_least_conflict_first(f) == ["c", "a", "b"]


def test_suggest_tests_maps_overlap_to_narrow_targets():
    have = {"products/p/backend/tests", "mcp/noctusai/tests/test_task_branch.py"}
    out = TR.suggest_tests(["products/p/backend/app/x.py",
                            "mcp/noctusai/tools/noctus/dev/task_branch.py", "README.md"],
                           lambda r: r in have)
    assert out == ["products/p/backend/tests", "mcp/noctusai/tests/test_task_branch.py"]
    assert TR.suggest_tests(["KNOWLEDGE-BASE/a.md"], lambda r: True) == []


def test_riders_teardown_cleans_each_rider_via_cleanup_action():
    calls = []

    def git(*a, cwd=None):
        return (0, "train(w): merge feat/b\ntrain(w): merge feat/a\n", "")

    def fn(**kw):
        calls.append(kw["slug"])
        return {"status": "cleaned", "pointer": {"status": "updated"}}

    res = T._train_riders_after_integrate(git, fn, "d0", "h0", True, {"remote": "origin"})
    assert calls == ["a", "b"] and [r["status"] for r in res] == ["cleaned", "cleaned"]
    kept = T._train_riders_after_integrate(git, fn, "d0", "h0", False, {})
    assert [r["status"] for r in kept] == ["kept", "kept"]


def test_train_action_is_a_write_only_when_confirmed():
    assert T._task_branch_is_write({"action": "train", "confirm": True})
    assert not T._task_branch_is_write({"action": "train", "confirm": False})


def _sh(cwd, *cmd):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    assert r.returncode == 0, (cmd, r.stderr)
    return r.stdout


def test_real_git_train_three_branches_one_conflict(tmp_path):
    origin, primary = tmp_path / "origin.git", tmp_path / "primary"
    _sh(tmp_path, "git", "init", "--bare", "-b", "dev", str(origin))
    _sh(tmp_path, "git", "clone", str(origin), str(primary))
    for k, v in (("user.email", "t@t"), ("user.name", "t")):
        _sh(primary, "git", "config", k, v)
    (primary / "README.md").write_text("base\n")
    (primary / "ONE.md").write_text("one\n")
    _sh(primary, "git", "add", "-A")
    _sh(primary, "git", "commit", "-m", "base")
    _sh(primary, "git", "push", "origin", "HEAD:dev")
    _sh(primary, "git", "fetch", "origin")
    wtd = primary / ".claude" / "worktrees"
    wtd.mkdir(parents=True)

    def mk(slug, fname, text):
        _sh(primary, "git", "worktree", "add", str(wtd / slug), "-b", f"feat/{slug}", "origin/dev")
        (wtd / slug / fname).write_text(text)
        _sh(wtd / slug, "git", "add", "-A")
        _sh(wtd / slug, "git", "commit", "-m", slug)

    mk("a", "A.md", "a\n")
    mk("b", "README.md", "from b\n")
    mk("c", "README.md", "from c\n")

    def runner(cmd, cwd=None):
        r = subprocess.run(cmd, cwd=cwd or str(primary), capture_output=True, text=True)
        return r.returncode, r.stdout, r.stderr

    def git(*a, cwd=None):
        return T._git(runner, *a, cwd=cwd)

    def start_fn(tslug):
        wt = wtd / tslug
        if not wt.exists():
            _sh(primary, "git", "worktree", "add", str(wt), "-b", f"feat/{tslug}", "origin/dev")
        return {"status": "started"}

    kw = dict(tb=T, git=git, runner=runner, remote="origin", dev_branch="dev",
              branch_prefix="feat/", worktrees_dir=".claude/worktrees",
              primary_root=str(primary), name="t", order="given", today="20261024",
              start_fn=start_fn, exists=lambda r: (primary / r).exists())

    cands = TR.run_train(slugs=None, confirm=False, **kw)
    assert cands["status"] == "candidates" and {c["slug"] for c in cands["candidates"]} == {"a", "b", "c"}

    plan = TR.run_train(slugs=["a", "b", "c"], confirm=False, **kw)
    assert plan["status"] == "planned" and plan["overlap_files"] == {"README.md": ["b", "c"]}
    assert plan["train"] == "train-t"

    r = TR.run_train(slugs=["a", "b", "c"], confirm=True, **kw)
    assert r["status"] == "conflict" and r["slug"] == "c"
    assert r["files"] == ["README.md"] and r["merged"] == ["a", "b"]
    assert (wtd / "train-t" / ".git").exists()
    # in-progress merge is NOT auto-resolved / aborted
    assert "<<<<<<<" in (wtd / "train-t" / "README.md").read_text()
    again = TR.run_train(slugs=["a", "b", "c"], confirm=True, **kw)
    assert again["status"] == "conflict" and "in progress" in again["message"]

    (wtd / "train-t" / "README.md").write_text("from b and c\n")
    _sh(wtd / "train-t", "git", "add", "README.md")
    _sh(wtd / "train-t", "git", "commit", "--no-edit")
    done = TR.run_train(slugs=["a", "b", "c"], confirm=True, **kw)
    assert done["status"] == "merged" and done["merged"] == [] and done["skipped"] == ["a", "b", "c"]
    subjects = _sh(wtd / "train-t", "git", "log", "--merges", "--format=%s").splitlines()
    assert TR.parse_train_riders(subjects) == ["a", "b", "c"]


def test_dirty_rider_is_refused(tmp_path):
    primary = tmp_path / "p"
    primary.mkdir()
    _sh(primary, "git", "init", "-b", "dev")
    _sh(primary, "git", "config", "user.email", "t@t")
    _sh(primary, "git", "config", "user.name", "t")
    (primary / "f").write_text("x")
    _sh(primary, "git", "add", "-A")
    _sh(primary, "git", "commit", "-m", "base")
    _sh(primary, "git", "branch", "origin-dev")
    _sh(primary, "git", "worktree", "add", str(primary / ".claude/worktrees/a"), "-b", "feat/a")
    (primary / ".claude/worktrees/a/dirty").write_text("u")

    def runner(cmd, cwd=None):
        r = subprocess.run(cmd, cwd=cwd or str(primary), capture_output=True, text=True)
        return r.returncode, r.stdout, r.stderr

    def git(*a, cwd=None):
        if a[0] == "fetch":
            return 0, "", ""
        if a[:2] == ("rev-parse", "origin/dev"):
            return runner(["git", "rev-parse", "dev"], cwd)
        return T._git(runner, *a, cwd=cwd)

    r = TR.run_train(tb=T, git=git, runner=runner, remote="origin", dev_branch="dev",
                     branch_prefix="feat/", worktrees_dir=".claude/worktrees",
                     primary_root=str(primary), slugs=["a"], name="x", order="given",
                     confirm=True, today="d", start_fn=lambda s: {"status": "started"},
                     exists=lambda r: False)
    assert r["status"] == "refused" and "uncommitted" in r["refused"][0]["reason"]


def test_real_git_resolutions_survive_dev_moving(tmp_path):
    """Live 2026-10-24: a train with a resolved conflict, then dev moved. A bare
    `rebase --rebase-merges` re-runs the merge and re-conflicts; after
    `sync_with_dev` the same rebase keeps the recorded resolution."""
    repo = tmp_path / "r"
    repo.mkdir()
    g = lambda *a: _sh(repo, "git", *a)  # noqa: E731
    g("init", "-q", "-b", "dev")
    g("config", "user.email", "t@t"); g("config", "user.name", "t")
    (repo / "f").write_text("a\n"); g("add", "f"); g("commit", "-qm", "base")
    g("checkout", "-qb", "x"); (repo / "f").write_text("x\n"); g("commit", "-qam", "x")
    g("checkout", "-qb", "y", "dev"); (repo / "f").write_text("y\n"); g("commit", "-qam", "y")
    g("checkout", "-qb", "t", "dev"); g("merge", "-q", "--no-ff", "--no-edit", "x")
    assert subprocess.run(["git", "merge", "-q", "--no-edit", "y"], cwd=repo, capture_output=True).returncode != 0
    (repo / "f").write_text("xy\n"); g("commit", "-qam", "resolved")
    g("checkout", "-q", "dev"); (repo / "z").write_text("z\n"); g("add", "z"); g("commit", "-qm", "z")
    g("checkout", "-q", "t")

    def runner(cmd, cwd=None):
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
        return r.returncode, r.stdout, r.stderr

    bare = subprocess.run(["git", "rebase", "--rebase-merges", "dev"], cwd=repo, capture_output=True)
    assert bare.returncode != 0  # the failure mode this guards against
    g("rebase", "--abort")
    assert TR.sync_with_dev(runner, str(repo), "dev") == []
    g("rebase", "--rebase-merges", "dev")
    assert (repo / "f").read_text() == "xy\n" and (repo / "z").exists()
