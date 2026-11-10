"""The guardian's delivery contract + the pure-push enqueue, proven on REAL git.

Ratified guardian spec (2026-11-10): the guardian never edits, rebases, merges or renumbers a
delivery branch and never runs a mutating git command in a worktree it does not own. Before this,
`task_branch enqueue` ran `merge` + `rebase --rebase-merges` + a kb-counts COMMIT inside the
requester's worktree and, on a conflict, reported "aborted" while leaving rebase state behind.

Every test builds temp repos with subprocess git (a bare "origin" + a primary clone + a branch
worktree). Nothing of ours is monkeypatched: the only injection is the documented DI seams
(`run=`, `deliverable_kwargs=`, `StewardStore(deliverable_check=)`), and the derived-file check is
the REAL export-and-regenerate mechanism pointed at a tiny regenerator that lives in the repo.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import release_steward as RS  # noqa: E402
from tools.noctus.dev import task_branch as T  # noqa: E402

_ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}

#: A real regenerator: `counts.txt` must equal the number of files under `src/` (a stand-in for the
#: kb-counts blocks). Exit 0 = current, 1 = stale - the exact contract the production artifacts follow.
_COUNTS_CHECK = (
    "import pathlib, sys\n"
    "t = pathlib.Path(sys.argv[1])\n"
    "n = len(list((t / 'src').glob('*.txt')))\n"
    "have = (t / 'counts.txt').read_text().strip()\n"
    "print('counts.txt says', have, 'but src/ has', n)\n"
    "sys.exit(0 if have == str(n) else 1)\n"
)
_ARTIFACTS = (("counts", ("{python}", "-c", _COUNTS_CHECK, "{tree}")),)


def sh(cwd: Path, *cmd: str) -> str:
    r = subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True, env=_ENV)
    return r.stdout.strip()


def sh_rc(cwd: Path, *cmd: str) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, env=_ENV)


class World:
    """bare origin + primary clone (`repo`, the guardian's cwd) + helpers."""

    def __init__(self, tmp_path: Path) -> None:
        self.origin = tmp_path / "origin.git"
        self.repo = tmp_path / "repo"
        sh(tmp_path, "git", "init", "--bare", "-b", "dev", str(self.origin))
        sh(tmp_path, "git", "clone", str(self.origin), str(self.repo))
        sh(self.repo, "git", "checkout", "-b", "dev")
        (self.repo / "src").mkdir()
        (self.repo / "src" / "a.txt").write_text("a\n")
        (self.repo / "counts.txt").write_text("1\n")
        self.commit(self.repo, "init")
        sh(self.repo, "git", "push", "origin", "dev")
        self.derived = RS.export_derived_check(self.repo, artifacts=_ARTIFACTS)

    # -- git helpers --------------------------------------------------------------------------
    def commit(self, where: Path, msg: str) -> str:
        sh(where, "git", "add", "-A")
        sh(where, "git", "commit", "-q", "-m", msg)
        return sh(where, "git", "rev-parse", "HEAD")

    def worktree(self, branch: str = "feat/x", name: str = "x") -> Path:
        wt = self.repo / ".claude" / "worktrees" / name
        sh(self.repo, "git", "worktree", "add", "-q", str(wt), "-b", branch, "origin/dev")
        return wt

    def dev_commit(self, rel: str, text: str = "dev\n") -> str:
        """A commit landed on origin/dev by somebody else (via a throwaway clone)."""
        other = self.repo.parent / f"other{len(list(self.repo.parent.glob('other*')))}"
        sh(self.repo.parent, "git", "clone", "-q", str(self.origin), str(other))
        sh(other, "git", "checkout", "-q", "dev")
        (other / rel).parent.mkdir(parents=True, exist_ok=True)
        (other / rel).write_text(text)
        sha = self.commit(other, f"dev: {rel}")
        sh(other, "git", "push", "-q", "origin", "dev")
        return sha

    def push(self, wt: Path, branch: str) -> str:
        sh(wt, "git", "push", "-q", "origin", f"{branch}:refs/heads/{branch}")
        return sh(wt, "git", "rev-parse", "HEAD")

    def set_counts(self, wt: Path) -> None:
        n = len(list((wt / "src").glob("*.txt")))
        (wt / "counts.txt").write_text(f"{n}\n")

    def merge_built_branch(self, wt: Path, n_line: int = 26, n_side: int = 24) -> None:
        """~50 commits incl. two --no-ff merges: a feature line, a side line merged in, then more."""
        for i in range(n_line // 2):
            (wt / "src" / f"line{i}.txt").write_text(f"{i}\n")
            self.commit(wt, f"feat: line {i}")
        base = sh(wt, "git", "rev-parse", "HEAD")
        sh(wt, "git", "checkout", "-q", "-b", "side")
        for i in range(n_side):
            (wt / "src" / f"side{i}.txt").write_text(f"{i}\n")
            self.commit(wt, f"feat: side {i}")
        sh(wt, "git", "checkout", "-q", "feat/x")
        for i in range(n_line // 2, n_line):
            (wt / "src" / f"line{i}.txt").write_text(f"{i}\n")
            self.commit(wt, f"feat: line {i}")
        sh(wt, "git", "merge", "-q", "--no-ff", "-m", "merge side", "side")
        sh(wt, "git", "checkout", "-q", "-b", "side2", base)
        for i in range(3):
            (wt / "src" / f"two{i}.txt").write_text(f"{i}\n")
            self.commit(wt, f"feat: second side {i}")
        sh(wt, "git", "checkout", "-q", "feat/x")
        sh(wt, "git", "merge", "-q", "--no-ff", "-m", "merge second side", "side2")
        (wt / "src" / "tail.txt").write_text("t\n")
        self.commit(wt, "feat: tail")
        self.set_counts(wt)  # derived files regenerated LAST, as a branch steward would
        self.commit(wt, "chore: regenerate counts")

    # -- the calls under test -----------------------------------------------------------------
    def runner(self, log: list | None = None):
        def run(cmd, cwd=None):
            if log is not None:
                log.append((list(cmd), str(cwd) if cwd else None))
            r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd or str(self.repo), env=_ENV)
            return r.returncode, r.stdout or "", r.stderr or ""
        return run

    def vref(self, branch: str = "feat/x", source: str = "gate_sweep://run/7") -> str:
        """A verdict pointer that carries what item 5 demands: env-scrubbed + ci-keepers + THIS head."""
        return RS.format_verdict_ref(source, sh(self.repo, "git", "rev-parse", branch))

    def enqueue(self, slug: str = "x", confirm: bool = True, log: list | None = None, **kw):
        if "verdict_ref" not in kw:
            kw["verdict_ref"] = self.vref(kw.get("branch") or f"feat/{slug}")
        kw.setdefault("deliverable_kwargs", {"derived_check": self.derived})
        return T.task_branch(action="enqueue", slug=slug, confirm=confirm, run=self.runner(log),
                             primary_root=str(self.repo), **kw)

    def deliverable(self, branch: str = "feat/x", **kw):
        if "verdict_ref" not in kw:
            kw["verdict_ref"] = self.vref(branch)
        kw.setdefault("derived_check", self.derived)
        return RS.deliverable(branch, cwd=self.repo, **kw)

    def mq_refs(self) -> list[str]:
        return sorted(r.split("\t")[1] for r in
                      sh(self.repo, "git", "ls-remote", "--heads", "origin", "refs/heads/mq/*").splitlines())


def item(result: dict, name: str) -> dict:
    return next(i for i in result["items"] if i["name"] == name)


@pytest.fixture()
def world(tmp_path):
    return World(tmp_path)


# =================================================================================================
# deliverable(): each item, on real git
# =================================================================================================

def test_a_clean_pushed_branch_that_contains_dev_is_deliverable(world):
    wt = world.worktree()
    (wt / "src" / "b.txt").write_text("b\n")
    world.set_counts(wt)
    world.commit(wt, "feat: b")
    world.push(wt, "feat/x")
    d = world.deliverable()
    assert d["ok"] and d["verdict"] == "deliverable", d["items"]
    assert [i["name"] for i in d["items"]] == list(RS.DELIVERABLE_ITEMS)
    assert "contains origin/dev" in item(d, "merge_buildable")["detail"]


def test_merge_built_branch_of_50_commits_is_deliverable_and_enqueue_pushes_the_exact_sha(world):
    wt = world.worktree()
    world.merge_built_branch(wt)
    head = world.push(wt, "feat/x")
    assert int(sh(world.repo, "git", "rev-list", "--count", "origin/dev..feat/x")) >= 50
    assert sh(world.repo, "git", "rev-list", "--merges", "--count", "origin/dev..feat/x") != "0"
    world.dev_commit("devfiles/d1.txt")  # dev moved on: the branch is now BEHIND yet merge-tree clean
    world.dev_commit("devfiles/d2.txt")
    res = world.enqueue()
    assert res["status"] == "queued", res
    assert res["deliverable"]["verdict"] == "deliverable"
    assert res["enqueued_sha"] == head and res["queue_ref"] == f"mq/x--{head[:7]}"
    assert world.mq_refs() == [f"refs/heads/mq/x--{head[:7]}"]
    assert sh(world.repo, "git", "rev-parse", f"origin/mq/x--{head[:7]}") == head
    assert sh(world.origin, "git", "rev-parse", f"refs/heads/mq/x--{head[:7]}") == head


def test_behind_dev_but_merge_tree_clean_is_accepted_no_zero_behind_livelock(world):
    wt = world.worktree()
    (wt / "src" / "b.txt").write_text("b\n")
    world.set_counts(wt)
    world.commit(wt, "feat: b")
    world.push(wt, "feat/x")
    world.dev_commit("other/file.txt")
    d = world.deliverable()
    assert d["ok"], d["items"]
    m = item(d, "merge_buildable")
    assert m["ok"] and "1 behind origin/dev" in m["detail"] and "merge-tree` is clean" in m["detail"]


def test_behind_dev_with_a_real_conflict_is_needs_resync_naming_item_two(world):
    wt = world.worktree()
    (wt / "src" / "a.txt").write_text("branch edit\n")
    world.commit(wt, "feat: edit a")
    world.push(wt, "feat/x")
    world.dev_commit("src/a.txt", "dev edit\n")
    d = world.deliverable()
    assert d["verdict"] == "needs_resync" and "merge_buildable" in d["failing"]
    m = item(d, "merge_buildable")
    assert m["n"] == 2 and not m["ok"] and "src/a.txt" in m["detail"] and m["conflicts"] == ["src/a.txt"]


def test_unpushed_head_fails_item_one(world):
    wt = world.worktree()
    (wt / "src" / "b.txt").write_text("b\n")
    world.set_counts(wt)
    world.commit(wt, "feat: b")
    world.push(wt, "feat/x")
    (wt / "src" / "c.txt").write_text("c\n")
    world.set_counts(wt)
    world.commit(wt, "feat: c (not pushed)")
    d = world.deliverable()
    one = item(d, "head_pushed_clean")
    assert d["verdict"] == "needs_resync" and not one["ok"] and one["n"] == 1 and "unpushed" in one["detail"]


def test_a_branch_that_was_never_pushed_fails_item_one(world):
    world.worktree()
    d = world.deliverable()
    assert "is not pushed" in item(d, "head_pushed_clean")["detail"]


def test_dirty_tree_fails_item_one_and_untracked_files_do_not(world):
    wt = world.worktree()
    (wt / "src" / "b.txt").write_text("b\n")
    world.set_counts(wt)
    world.commit(wt, "feat: b")
    world.push(wt, "feat/x")
    (wt / "scratch.log").write_text("untracked: not part of the head\n")
    assert world.deliverable()["ok"]
    (wt / "src" / "a.txt").write_text("uncommitted edit\n")
    d = world.deliverable()
    one = item(d, "head_pushed_clean")
    assert not one["ok"] and "dirty tree" in one["detail"] and "src/a.txt" in one["detail"]


def test_stale_derived_file_fails_item_four(world):
    wt = world.worktree()
    (wt / "src" / "b.txt").write_text("b\n")  # counts.txt still says 1
    world.commit(wt, "feat: b without regenerating counts")
    world.push(wt, "feat/x")
    d = world.deliverable()
    four = item(d, "derived_current")
    assert d["verdict"] == "needs_resync" and not four["ok"] and four["n"] == 4
    assert "counts" in four["detail"] and four["artifacts"][0]["measured"] is True


def test_a_missing_regenerator_is_unmeasured_never_green(world):
    wt = world.worktree()
    (wt / "src" / "b.txt").write_text("b\n")
    world.set_counts(wt)
    world.commit(wt, "feat: b")
    world.push(wt, "feat/x")
    broken = RS.export_derived_check(world.repo, artifacts=(("kb-counts", ("{python}", "{tree}/nope/cli.py", "--check")),))
    four = item(world.deliverable(derived_check=broken), "derived_current")
    assert not four["ok"] and "regenerator missing" in four["artifacts"][0]["detail"]
    assert four["artifacts"][0]["measured"] is False


def test_migration_number_claimed_on_dev_fails_item_three_and_a_free_number_passes(world):
    mig = "products/p/backend/migrations"
    (world.repo / mig).mkdir(parents=True)
    (world.repo / mig / "001_init.sql").write_text("-- 1\n")
    world.commit(world.repo, "p: 001")
    sh(world.repo, "git", "push", "origin", "dev")
    wt = world.worktree()
    (wt / mig).mkdir(parents=True, exist_ok=True)
    (wt / mig / "002_branch.sql").write_text("-- branch 2\n")
    world.commit(wt, "p: 002 branch")
    world.push(wt, "feat/x")
    world.dev_commit(f"{mig}/002_dev.sql", "-- dev 2\n")
    d = world.deliverable(derived_check=lambda head: {"ok": True, "measured": True, "detail": "n/a", "results": []})
    three = item(d, "migrations_free")
    assert not three["ok"] and three["n"] == 3 and "number 002" in three["detail"]
    assert three["collisions"][0]["names"] == ["002_branch.sql", "002_dev.sql"]
    # the branch steward renumbers its OWN file on top of dev and re-pushes: free again
    sh(wt, "git", "merge", "-q", "origin/dev")
    sh(wt, "git", "mv", f"{mig}/002_branch.sql", f"{mig}/003_branch.sql")
    world.commit(wt, "p: renumber to 003")
    world.push(wt, "feat/x")
    d = world.deliverable(derived_check=lambda head: {"ok": True, "measured": True, "detail": "n/a", "results": []})
    assert item(d, "migrations_free")["ok"], d["items"]


def test_scoped_green_needs_a_marked_head_bound_verdict_ref_or_a_passing_scoped_check(world):
    wt = world.worktree()
    (wt / "src" / "b.txt").write_text("b\n")
    world.set_counts(wt)
    world.commit(wt, "feat: b")
    head = world.push(wt, "feat/x")
    five = item(world.deliverable(verdict_ref=None), "scoped_green")
    assert not five["ok"] and five["n"] == 5 and "no verdict_ref" in five["detail"]
    good = RS.format_verdict_ref("https://ci.example/run/7", head)
    assert item(world.deliverable(verdict_ref=good), "scoped_green")["ok"]
    # a pointer that does not RECORD the hermetic run + the CI-blocking keeper set is not a verdict
    for bad, why in ((f"https://ci.example/run/7@{head[:9]}", "env-scrubbed, ci-keepers"),
                     (f"x@{head[:9]}#ci-keepers", "env-scrubbed"),
                     (f"x@{head[:9]}#env-scrubbed", "ci-keepers"),
                     ("x@0123456#env-scrubbed,ci-keepers", "does not name the head")):
        five = item(world.deliverable(verdict_ref=bad), "scoped_green")
        assert not five["ok"] and why in five["detail"], (bad, five)
    assert item(world.deliverable(verdict_ref=None, scoped_check=lambda b, h: {"ok": True, "detail": "pytest green"}),
                "scoped_green")["ok"]
    assert not item(world.deliverable(verdict_ref=good, scoped_check=lambda b, h: {"ok": False, "detail": "red"}),
                    "scoped_green")["ok"]


def test_deliverable_is_structurally_read_only():
    guarded = RS._ReadOnlyGit(lambda *a, cwd=None: (0, "", ""))
    for forbidden in ("checkout", "rebase", "merge", "commit", "add", "push", "stash", "reset", "switch", "restore"):
        with pytest.raises(ValueError):
            guarded(forbidden, "x")
    with pytest.raises(ValueError):
        guarded("worktree", "add", "x")
    assert guarded("worktree", "list", "--porcelain") == (0, "", "")
    assert guarded("--no-optional-locks", "status", "--porcelain") == (0, "", "")


def test_the_default_derived_check_runs_every_real_artifact_on_this_repos_head():
    """The production artifact table must be runnable: every artifact is MEASURED (a regenerator that
    exists at the head and exits 0/1), whatever dev's current drift is."""
    root = Path(__file__).resolve().parents[3]
    if not (root / "mcp" / "noctusai" / "cli.py").is_file():
        pytest.skip("not run from a full noc checkout")
    res = RS.export_derived_check(root)("HEAD")
    assert [r["name"] for r in res["results"]] == [n for n, _ in RS.DERIVED_ARTIFACTS]
    assert all(r["measured"] for r in res["results"]), res


# =================================================================================================
# enqueue: a PURE PUSH
# =================================================================================================

def _snapshot(world: World, wt: Path) -> dict:
    def tree_hashes(root: Path) -> dict[str, str]:
        out = {}
        for p in sorted(root.rglob("*")):
            rel = p.relative_to(root).as_posix()
            if rel.startswith(".git") or ".claude/worktrees" in rel or not p.is_file():
                continue
            out[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
        return out

    def state(where: Path) -> dict:
        gd = Path(sh(where, "git", "rev-parse", "--absolute-git-dir"))
        return {
            "status": sh(where, "git", "status", "--porcelain"),
            "head": sh(where, "git", "rev-parse", "HEAD"),
            "symbolic": sh(where, "git", "symbolic-ref", "-q", "HEAD"),
            "files": tree_hashes(where),
            "gitdir_state": sorted(n for n in os.listdir(gd) if n.startswith(("rebase", "MERGE_HEAD", "CHERRY", "REVERT", "AUTO_MERGE"))
                                   or n in ("index.lock",)),
            "index": hashlib.sha256((gd / "index").read_bytes()).hexdigest(),
        }

    # push opportunistically adds a remote-tracking ref for the queue branch: that is the one
    # permitted ref change; everything else must be byte-identical.
    refs = [ln for ln in sh(world.repo, "git", "for-each-ref", "--format=%(refname) %(objectname)").splitlines()
            if "/refs/remotes/origin/mq/" not in ln and not ln.startswith("refs/remotes/origin/mq/")]
    return {"refs": refs, "worktree": state(wt), "primary": state(world.repo),
            "worktree_list": sh(world.repo, "git", "worktree", "list", "--porcelain")}


def test_enqueue_changes_no_file_no_ref_no_head_and_leaves_no_rebase_state(world):
    wt = world.worktree()
    world.merge_built_branch(wt)
    world.push(wt, "feat/x")
    world.dev_commit("devfiles/d1.txt")
    sh(world.repo, "git", "fetch", "-q", "origin")  # so enqueue's own fetch is a no-op
    before = _snapshot(world, wt)
    log: list = []
    for confirm in (False, True):
        res = world.enqueue(confirm=confirm, log=log)
        assert res["status"] in ("planned", "queued"), res
    after = _snapshot(world, wt)
    assert after == before
    assert after["worktree"]["gitdir_state"] == [] and after["primary"]["gitdir_state"] == []
    mutating = {"rebase", "merge", "checkout", "switch", "restore", "commit", "add", "stash", "reset",
                "cherry-pick", "mv", "clean", "apply", "am", "pull"}
    subs = [c[1] for c, _ in log if len(c) > 1 and c[0] == "git"]
    assert not (mutating & set(subs)), subs
    pushes = [(c, cwd) for c, cwd in log if c[:2] == ["git", "push"]]
    assert len(pushes) == 1
    cmd, cwd = pushes[0]
    assert cmd[2] == "origin" and cmd[3].endswith(":refs/heads/" + res["queue_ref"])
    assert cwd is None or Path(cwd).resolve() != wt.resolve()  # never from the branch's worktree


def test_a_conflicted_merge_built_branch_is_refused_and_its_worktree_is_untouched(world):
    """The D1 scenario: a merge-built branch that conflicts with dev. Enqueue used to merge + rebase
    inside the requester's worktree and leave rebase-merge state behind. Now: needs_resync, nothing moved."""
    wt = world.worktree()
    (wt / "src" / "a.txt").write_text("branch edit\n")
    world.commit(wt, "feat: edit a")
    world.merge_built_branch(wt, n_line=6, n_side=4)
    world.push(wt, "feat/x")
    world.dev_commit("src/a.txt", "dev edit\n")
    sh(world.repo, "git", "fetch", "-q", "origin")
    before = _snapshot(world, wt)
    res = world.enqueue()
    assert res["status"] == "needs_resync" and res["exit_code"] == 1, res
    assert "merge_buildable" in res["failing"] and "item 2 merge_buildable" in res["message"]
    assert _snapshot(world, wt) == before
    assert world.mq_refs() == []
    assert not (Path(sh(wt, "git", "rev-parse", "--absolute-git-dir")) / "rebase-merge").exists()


def test_enqueue_refuses_a_dirty_unpushed_or_stale_branch_without_touching_it(world):
    wt = world.worktree()
    (wt / "src" / "b.txt").write_text("b\n")
    world.commit(wt, "feat: b, counts stale, not pushed")
    (wt / "src" / "a.txt").write_text("dirty\n")
    sh(world.repo, "git", "fetch", "-q", "origin")
    before = _snapshot(world, wt)
    res = world.enqueue()
    assert res["status"] == "needs_resync"
    assert set(res["failing"]) == {"head_pushed_clean", "derived_current"}
    assert _snapshot(world, wt) == before and world.mq_refs() == []


def test_enqueue_with_no_verdict_ref_is_refused_on_item_five(world):
    wt = world.worktree()
    (wt / "src" / "b.txt").write_text("b\n")
    world.set_counts(wt)
    world.commit(wt, "feat: b")
    world.push(wt, "feat/x")
    res = world.enqueue(verdict_ref=None)
    assert res["status"] == "needs_resync" and res["failing"] == ["scoped_green"]


def test_enqueue_hook_rejection_is_blocked_and_still_touches_nothing(world):
    wt = world.worktree()
    (wt / "src" / "b.txt").write_text("b\n")
    world.set_counts(wt)
    world.commit(wt, "feat: b")
    world.push(wt, "feat/x")
    hook = world.origin / "hooks" / "pre-receive"
    hook.write_text("#!/bin/sh\necho 'rejected by the remote' >&2\nexit 1\n")
    hook.chmod(0o755)
    sh(world.repo, "git", "fetch", "-q", "origin")
    before = _snapshot(world, wt)
    res = world.enqueue()
    assert res["status"] == "blocked" and res["exit_code"] == 1
    assert _snapshot(world, wt) == before


def test_enqueue_dry_run_names_the_ref_and_pushes_nothing(world):
    wt = world.worktree()
    (wt / "src" / "b.txt").write_text("b\n")
    world.set_counts(wt)
    world.commit(wt, "feat: b")
    head = world.push(wt, "feat/x")
    res = world.enqueue(confirm=False)
    assert res["status"] == "planned" and res["queue_ref"] == f"mq/x--{head[:7]}"
    assert world.mq_refs() == []


# =================================================================================================
# branch resolution: the real branch name, not only feat/<slug>
# =================================================================================================

def test_a_docs_branch_is_delivered_by_its_slug(world):
    wt = world.worktree(branch="docs/y", name="y")
    (wt / "src" / "b.txt").write_text("b\n")
    world.set_counts(wt)
    world.commit(wt, "docs: b")
    head = world.push(wt, "docs/y")
    res = world.enqueue(slug="y", verdict_ref=world.vref("docs/y"))
    assert res["status"] == "queued" and res["branch"] == "docs/y", res
    assert res["branch_resolved_from"] == "resolved"
    assert res["queue_ref"] == f"mq/y--{head[:7]}"


def test_an_explicit_branch_wins_and_an_ambiguous_slug_refuses(world):
    sh(world.repo, "git", "branch", "feat/z", "origin/dev")
    sh(world.repo, "git", "branch", "fix/z", "origin/dev")
    res = world.enqueue(slug="z", confirm=False)
    assert res["status"] == "error" and "matches several branches" in res["error"]
    assert res["candidates"] == ["feat/z", "fix/z"]
    res = world.enqueue(slug="z", confirm=False, branch="fix/z")
    assert res["branch"] == "fix/z" and res["status"] != "error"


def test_resolve_branch_name_defaults_to_feat_when_nothing_exists(world):
    assert RS.resolve_branch_name("nope", git=RS._subprocess_git(world.repo))["branch"] == "feat/nope"
    sh(world.repo, "git", "branch", "chore/only-one", "origin/dev")
    r = RS.resolve_branch_name("only-one", git=RS._subprocess_git(world.repo))
    assert r["branch"] == "chore/only-one" and r["source"] == "resolved"


# =================================================================================================
# request(): the contract runs at filing; a failing branch goes back as needs_resync
# =================================================================================================

def _store(world, tmp_path):
    def check(branch, head_sha, verdict_ref):
        return RS.deliverable(branch, cwd=world.repo, head_sha=head_sha, verdict_ref=verdict_ref,
                              derived_check=world.derived)
    return RS.StewardStore(root=tmp_path / "steward", deliverable_check=check,
                           resolve_branch=lambda s: RS.resolve_branch_name(s, git=RS._subprocess_git(world.repo)))


def test_request_refuses_a_failing_branch_names_the_item_and_files_needs_resync(world, tmp_path):
    wt = world.worktree()
    (wt / "src" / "b.txt").write_text("b\n")
    world.commit(wt, "feat: b, counts stale")  # not pushed, derived stale
    store = _store(world, tmp_path)
    res = store.request("sess-1", "x", verdict_ref=world.vref())
    assert res["ok"] is False and res["status"] == "needs_resync"
    assert set(res["failing"]) == {"head_pushed_clean", "derived_current"}
    assert "item 1 head_pushed_clean" in res["error"]
    assert store.inbox()["pending"] == 0  # a refused delivery never reaches the guardian's drain
    mine = store.mine("sess-1")["requests"]
    assert mine[0]["status"] == "needs_resync" and mine[0]["needs_resync"]["failing"]
    # the branch steward fixes its own branch and re-requests: now it is filed
    world.set_counts(wt)
    world.commit(wt, "chore: counts")
    world.push(wt, "feat/x")
    vref = world.vref()
    ok = store.request("sess-1", "x", verdict_ref=vref)
    assert ok["ok"] and ok["status"] == "queued_for_steward" and ok["deliverable"]["verdict"] == "deliverable"
    assert store.inbox()["pending"] == 1
    assert store.requests()["x"]["verdict_ref"] == vref


def test_request_resolves_a_docs_branch_from_the_slug(world, tmp_path):
    wt = world.worktree(branch="docs/y", name="y")
    (wt / "src" / "b.txt").write_text("b\n")
    world.set_counts(wt)
    world.commit(wt, "docs: b")
    world.push(wt, "docs/y")
    res = _store(world, tmp_path).request("sess-1", "y", verdict_ref=world.vref("docs/y"))
    assert res["ok"] and res["request"]["branch"] == "docs/y"


def test_the_deliverable_action_is_read_only_and_open_to_every_session(world, tmp_path):
    wt = world.worktree()
    (wt / "src" / "b.txt").write_text("b\n")
    world.commit(wt, "feat: b")
    world.push(wt, "feat/x")
    store = _store(world, tmp_path)
    before = _snapshot(world, wt)
    res = RS.run_action("deliverable", "some-other-session", store=store, slug="x")
    assert res["ok"] and res["status"] == "needs_resync" and res["failing"] == ["derived_current", "scoped_green"]
    assert store.requests() == {}  # nothing was filed
    assert _snapshot(world, wt) == before


def test_the_guardian_can_ack_needs_resync_back_to_the_requester(world, tmp_path):
    wt = world.worktree()
    (wt / "src" / "b.txt").write_text("b\n")
    world.set_counts(wt)
    world.commit(wt, "feat: b")
    world.push(wt, "feat/x")
    store = _store(world, tmp_path)
    store.request("req", "x", verdict_ref=world.vref())
    store.claim("guardian", name="guardian", reason="test", claude_pid=os.getpid())
    assert store.ack("guardian", "x", "needs_resync")["ok"] is False  # a reason is required
    res = store.ack("guardian", "x", "needs_resync", note="item 2: dev moved and conflicts")
    assert res["ok"] and res["request"]["status"] == "needs_resync"
    assert store.inbox()["pending"] == 0
    assert store.mine("req")["requests"][0]["status"] == "needs_resync"


# =================================================================================================
# abort paths prove the state is gone
# =================================================================================================

def _conflicted_pair(world):
    wt = world.worktree()
    (wt / "src" / "a.txt").write_text("branch\n")
    world.commit(wt, "feat: a")
    world.push(wt, "feat/x")
    world.dev_commit("src/a.txt", "dev\n")
    sh(world.repo, "git", "fetch", "-q", "origin")
    return wt


def test_integrate_conflict_aborts_and_proves_the_rebase_state_is_gone(world):
    wt = _conflicted_pair(world)
    res = T.task_branch(action="integrate", slug="x", confirm=True, run=world.runner(),
                        primary_root=str(world.repo))
    assert res["status"] == "conflict", res
    assert res["rebase_abort"] == {"aborted": True, "state_left": False}
    gd = Path(sh(wt, "git", "rev-parse", "--absolute-git-dir"))
    assert not (gd / "rebase-merge").exists() and not (gd / "rebase-apply").exists()
    assert sh(wt, "git", "status", "--porcelain") == ""


def test_an_abort_that_did_not_hold_is_reported_stuck_never_aborted(world):
    wt = _conflicted_pair(world)
    real = world.runner()

    def stubborn(cmd, cwd=None):  # git itself refuses to abort: the failure the old code never saw
        if cmd[:3] == ["git", "rebase", "--abort"]:
            return 1, "", "fatal: could not abort"
        return real(cmd, cwd=cwd)

    sh_rc(wt, "git", "rebase", "origin/dev")  # leaves a real rebase-merge/apply dir behind
    out = T._abort_rebase_verified(stubborn, str(wt))
    assert out == {"aborted": False, "state_left": True}
    assert T._abort_rebase_verified(real, str(wt)) == {"aborted": True, "state_left": False}


def test_sync_with_dev_conflict_leaves_no_merge_state(world):
    from tools.noctus.dev import task_branch_train as TR
    wt = _conflicted_pair(world)
    files = TR.sync_with_dev(world.runner(), str(wt), "origin/dev")
    assert files == ["src/a.txt"]
    assert sh_rc(wt, "git", "rev-parse", "-q", "--verify", "MERGE_HEAD").returncode != 0


# =================================================================================================
# item 5: judged the way CI judges it - the CI-blocking keeper set + a hermetic (scrubbed) env
# (D1, merge-queue run 42753204233: a keeper that only WARNS in pre-commit but BLOCKS in CI, and a
#  test that passed locally only because CLAUDE_CODE_SESSION_ID was set)
# =================================================================================================

_WORKFLOW = """\
name: Tests & Build
jobs:
  other-job:
    runs-on: ubuntu-latest
    env:
      NOT_THE_TOOLKIT: "1"
    steps:
      - run: echo hi
  mcp-toolkit-tests:
    runs-on: ubuntu-latest
    env:
      NOCTUS_DISABLE_AUTO_CACHE_PULL: "1"
      MCP_TEST_TOTAL_SHARDS: "4"
    steps:
      - uses: actions/checkout@v7
      - name: Prime hermetic state (version stamp + structural caches; zero OpenAI)
        working-directory: mcp/noctusai
        run: |
          python cli.py --stamp
      - name: Scripts manifest (warns in pre-commit, blocks here)
        run: python mcp/noctusai/cli.py --check-scripts-manifest
      - name: Advisory keeper
        continue-on-error: true
        run: python mcp/noctusai/cli.py --check-advisory
      - name: Range keeper needs a CI-resolved range
        run: python mcp/noctusai/cli.py --check-ranged --range "${{ steps.range.outputs.range }}"
  later-job:
    steps:
      - run: python mcp/noctusai/cli.py --check-in-a-later-job
"""
_CLI = """\
import pathlib, sys
root = pathlib.Path(__file__).resolve().parents[2]
flag = sys.argv[1]
if flag in ("--stamp", "--check-in-a-later-job"):
    sys.exit(0)
if flag == "--check-scripts-manifest":
    rows = (root / "scripts" / "MANIFEST").read_text().split()
    on_disk = [p.name for p in (root / "scripts").iterdir() if p.name != "MANIFEST"]
    missing = [n for n in on_disk if n not in rows]
    print("script(s) without a manifest row:", missing)
    sys.exit(1 if missing else 0)
sys.exit(1)  # --check-advisory / --check-ranged / anything else: would be red if (wrongly) run
"""
_KEEPER_TESTS = """\
import os
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[3]


def check_manifest():
    rows = (ROOT / "scripts" / "MANIFEST").read_text().split()
    return [p.name for p in (ROOT / "scripts").iterdir() if p.name != "MANIFEST" and p.name not in rows]


def check_needs_session():
    # a keeper whose answer silently depends on the dev machine's session env
    return [] if os.environ.get("CLAUDE_CODE_SESSION_ID") else ["no session"]


def test_real_tree_manifest_clean():
    assert check_manifest() == []


def test_unrelated_red_test_is_not_a_keeper_assertion():
    assert 1 + 1 == 3
"""
_SESSION_TEST = """

def test_real_tree_session_keeper():
    assert check_needs_session() == []
"""
_SCRUBBED_ENV = {"CLAUDE_CODE_SESSION_ID": "sess-123", "CLAUDE_PROJECT_DIR": "/somewhere", "OPENAI_API_KEY": "k"}


def _ci_branch(world, *, rogue_script=False, session_test=False):
    """A pushed branch whose head carries a tiny CI definition + the keepers it blocks on."""
    wt = world.worktree()
    for rel, text in ((".github/workflows/test.yml", _WORKFLOW), ("mcp/noctusai/cli.py", _CLI),
                      ("mcp/noctusai/tests/test_keepers.py", _KEEPER_TESTS + (_SESSION_TEST if session_test else "")),
                      ("scripts/MANIFEST", "tool.sh\n"), ("scripts/tool.sh", "#!/bin/sh\n")):
        (wt / rel).parent.mkdir(parents=True, exist_ok=True)
        (wt / rel).write_text(text)
    if rogue_script:
        (wt / "scripts" / "rogue.sh").write_text("#!/bin/sh\n")  # no manifest row: warning in pre-commit
    world.set_counts(wt)
    world.commit(wt, "ci definition")
    return wt, world.push(wt, "feat/x")


def _parity(world, **env):
    return RS.export_ci_parity_check(world.repo, base_env={**os.environ, **env})("feat/x", sh(world.repo, "git", "rev-parse", "feat/x"))


def test_the_ci_blocking_set_is_derived_from_the_workflow_not_hand_listed():
    assert RS.ci_blocking_flags(_WORKFLOW) == ["--check-scripts-manifest", "--check-in-a-later-job"]
    assert RS.ci_prime_flags(_WORKFLOW) == ["--stamp"]
    assert RS.ci_job_env(_WORKFLOW) == {"NOCTUS_DISABLE_AUTO_CACHE_PULL": "1", "MCP_TEST_TOTAL_SHARDS": "4"}


def test_keeper_tests_are_derived_by_ast_from_the_assertions(tmp_path):
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_k.py").write_text(
        _KEEPER_TESTS + _SESSION_TEST + "\n\nclass TestK:\n    def test_live(self):\n        assert mod.check_x(ROOT) == []\n")
    assert RS.ci_keeper_test_ids(tests) == [
        "tests/test_k.py::test_real_tree_manifest_clean", "tests/test_k.py::test_real_tree_session_keeper",
        "tests/test_k.py::TestK::test_live"]


def test_the_hermetic_env_drops_session_vars_and_adds_what_ci_sets():
    env = RS.hermetic_env({"PATH": "/bin", "HOME": "/h", **_SCRUBBED_ENV}, _WORKFLOW)
    assert env["PATH"] == "/bin" and env["CI"] == "true" and env["MCP_TEST_TOTAL_SHARDS"] == "4"
    assert not {"CLAUDE_CODE_SESSION_ID", "CLAUDE_PROJECT_DIR", "OPENAI_API_KEY", "NOT_THE_TOOLKIT"} & set(env)


def test_a_clean_head_passes_the_ci_parity_check_and_it_emits_a_valid_verdict_ref(world):
    _wt, head = _ci_branch(world)
    res = _parity(world, **_SCRUBBED_ENV)
    assert res["ok"], res
    assert res["ran"]["flags"] == ["--check-scripts-manifest"] + ["--check-in-a-later-job"]
    assert res["ran"]["tests"] == ["tests/test_keepers.py::test_real_tree_manifest_clean"]
    ok, why = RS.validate_verdict_ref(res["verdict_ref"], head)
    assert ok, why


def test_a_keeper_that_only_warns_in_precommit_but_blocks_in_ci_fails_item_five(world):
    _wt, head = _ci_branch(world, rogue_script=True)
    res = _parity(world, **_SCRUBBED_ENV)
    assert not res["ok"]
    assert "keeper --check-scripts-manifest" in res["detail"]
    assert "test tests/test_keepers.py::test_real_tree_manifest_clean" in res["detail"]
    d = RS.deliverable("feat/x", cwd=world.repo, derived_check=world.derived,
                       scoped_check=RS.export_ci_parity_check(world.repo), verdict_ref=world.vref())
    five = item(d, "scoped_green")
    assert d["verdict"] == "needs_resync" and not five["ok"] and "manifest" in five["detail"]
    # the same head with a perfect-looking verdict POINTER would pass: that is why the ref must be validated
    assert RS.validate_verdict_ref(world.vref(), head)[0]


def test_a_test_that_depends_on_the_session_env_is_run_without_it(world, monkeypatch):
    _ci_branch(world, session_test=True)
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "sess-123")  # this process HAS the var: the dev machine
    # proof the keeper is green on the dev machine ...
    assert subprocess.run([sys.executable, "-c", "import os,sys; sys.exit(0 if os.environ.get('CLAUDE_CODE_SESSION_ID') else 1)"]).returncode == 0
    # ... and red the way CI sees it, because the check scrubs the env
    res = RS.export_ci_parity_check(world.repo)("feat/x", sh(world.repo, "git", "rev-parse", "feat/x"))
    assert not res["ok"] and "test_real_tree_session_keeper" in res["detail"]
    assert "keeper --check-advisory" not in res["detail"]  # a continue-on-error step does not block CI


def test_a_missing_workflow_is_unmeasured_never_green(world):
    wt = world.worktree()
    (wt / "src" / "b.txt").write_text("b\n")
    world.commit(wt, "no ci definition")
    head = world.push(wt, "feat/x")
    res = RS.export_ci_parity_check(world.repo)("feat/x", head)
    assert not res["ok"] and "UNMEASURED" in res["detail"]


# =================================================================================================
# the pure push goes through the REAL pre-push hook (from the primary checkout, HEAD=dev)
# =================================================================================================

def test_enqueue_pushes_through_the_real_pre_push_hook_from_the_primary(world):
    hook_src = Path(__file__).resolve().parents[3] / "scripts" / "hooks" / "pre-push"
    tool = world.repo / "mcp" / "noctusai"
    (tool / ".venv" / "bin").mkdir(parents=True)
    (tool / ".venv" / "bin" / "python").symlink_to(sys.executable)
    (tool / "cli.py").write_text(
        "import sys\n"
        "# stand-in for the toolkit CLI the hook shells out to: the branch-tree mirror keeper is red for a\n"
        "# name with no pointer (as the real one is for a bare sha); every other keeper is green\n"
        "sys.exit(1 if sys.argv[1] == '--check-branch-tree-mirror' and sys.argv[2] != 'feat/x' else 0)\n")
    hook = world.repo / ".git" / "hooks" / "pre-push"
    hook.write_bytes(hook_src.read_bytes())
    hook.chmod(0o755)
    wt = world.worktree()
    (wt / "src" / "b.txt").write_text("b\n")
    world.set_counts(wt)
    world.commit(wt, "feat: b")
    head = world.push(wt, "feat/x") if False else sh(wt, "git", "rev-parse", "HEAD")
    sh(wt, "git", "push", "-q", "--no-verify", "origin", "feat/x:refs/heads/feat/x")  # the steward's own push, fixture only
    assert sh(world.repo, "git", "rev-parse", "--abbrev-ref", "HEAD") == "dev"
    res = world.enqueue()
    assert res["status"] == "queued", res
    assert world.mq_refs() == [f"refs/heads/mq/x--{head[:7]}"]
