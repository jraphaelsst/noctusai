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
import json
import os
import subprocess
import sys
import tempfile
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
        self.verdict_store = tmp_path / "deliverable-verdicts.ndjson"  # the DI seam: never the real ~/.noctus

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

    def vref(self, branch: str = "feat/x", ok: bool = True) -> str:
        """A REAL verdict record (written by the store's own writer) for THIS head; the ref resolves to it."""
        return RS.record_verdict(
            self.verdict_store, head=sh(self.repo, "git", "rev-parse", branch),
            tree=sh(self.repo, "git", "rev-parse", f"{branch}^{{tree}}"), workflow_blob="0" * 40,
            interpreter="test", flags=["--check-x"], tests=["tests/test_x.py::test_y"], ok=ok)

    def enqueue(self, slug: str = "x", confirm: bool = True, log: list | None = None, **kw):
        if "verdict_ref" not in kw:
            kw["verdict_ref"] = self.vref(kw.get("branch") or f"feat/{slug}")
        kw.setdefault("deliverable_kwargs", {"derived_check": self.derived, "verdict_store": self.verdict_store})
        return T.task_branch(action="enqueue", slug=slug, confirm=confirm, run=self.runner(log),
                             primary_root=str(self.repo), **kw)

    def deliverable(self, branch: str = "feat/x", **kw):
        if "verdict_ref" not in kw:
            kw["verdict_ref"] = self.vref(branch)
        kw.setdefault("derived_check", self.derived)
        kw.setdefault("verdict_store", self.verdict_store)
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


def test_a_missing_regenerator_names_where_it_looked(world):
    """2026-11-10: a guardian enqueue (MCP fresh-subprocess path) reported every regenerator "missing at the
    head" for a head that ships cli.py, and it did not reproduce from a shell. The detail must carry enough to
    diagnose the next occurrence on its own: the export dir, whether it exists, the process cwd + TMPDIR, the
    nearest existing parent of the expected path and a sample of what the export does contain."""
    wt = world.worktree()
    (wt / "src" / "b.txt").write_text("b\n")
    world.set_counts(wt)
    world.commit(wt, "feat: b")
    world.push(wt, "feat/x")
    broken = RS.export_derived_check(world.repo, artifacts=(("kb-counts", ("{python}", "{tree}/nope/cli.py", "--check")),))
    art = item(world.deliverable(derived_check=broken), "derived_current")["artifacts"][0]
    diag = art["diagnostics"]
    assert diag["export_dir"].startswith(tempfile.gettempdir()) or "noc-deliverable-" in diag["export_dir"]
    assert diag["export_dir_existed"] is True
    assert diag["cwd"] and "tmpdir" in diag
    assert diag["nearest_existing"].endswith(Path(diag["export_dir"]).name)  # nope/ is absent; the export root is not
    assert "src" in diag["export_top"]
    assert "export=" in art["detail"] and "top=" in art["detail"]


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


def test_scoped_green_needs_a_resolvable_head_bound_verdict_record_or_a_passing_scoped_check(world):
    wt = world.worktree()
    (wt / "src" / "b.txt").write_text("b\n")
    world.set_counts(wt)
    world.commit(wt, "feat: b")
    head = world.push(wt, "feat/x")
    five = item(world.deliverable(verdict_ref=None), "scoped_green")
    assert not five["ok"] and five["n"] == 5 and "no verdict_ref" in five["detail"]
    good = world.vref()
    assert item(world.deliverable(verdict_ref=good), "scoped_green")["ok"]
    # a record for ANOTHER head is not this head's verdict (exact full-sha match)
    other = RS.record_verdict(world.verdict_store, head="0" * 40, tree="1" * 40, workflow_blob="2" * 40,
                              interpreter="t", flags=[], tests=[], ok=True)
    five = item(world.deliverable(verdict_ref=other), "scoped_green")
    assert not five["ok"] and "re-run run_scoped=true on this exact head" in five["detail"]
    # a RED record is refused; a record for the right head but another tree is refused
    five = item(world.deliverable(verdict_ref=world.vref(ok=False)), "scoped_green")
    assert not five["ok"] and "RED" in five["detail"]
    wrong_tree = RS.record_verdict(world.verdict_store, head=head, tree="3" * 40, workflow_blob="2" * 40,
                                   interpreter="t", flags=[], tests=[], ok=True)
    assert "tree" in item(world.deliverable(verdict_ref=wrong_tree), "scoped_green")["detail"]
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
                              derived_check=world.derived, verdict_store=world.verdict_store)
    return RS.StewardStore(root=tmp_path / "steward", deliverable_check=check,
                           resolve_head=lambda b: sh_rc(world.repo, "git", "rev-parse", "--verify", "--quiet", f"refs/heads/{b}").stdout.strip() or None,
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
_SLOW_ONCE_TEST = """

def test_real_tree_slow_once_keeper():
    # first attempt hangs past the stage budget (a loaded machine); a retry finds the marker and is instant
    import time
    marker = ROOT / "slow-once.flag"
    if not marker.exists():
        marker.write_text("1")
        time.sleep(60)
    assert check_manifest() == []
"""
_SLOW_ALWAYS_TEST = """

def test_real_tree_slow_always_keeper():
    import time
    time.sleep(60)
    assert check_manifest() == []
"""
_SCRUBBED_ENV = {"CLAUDE_CODE_SESSION_ID": "sess-123", "CLAUDE_PROJECT_DIR": "/somewhere", "OPENAI_API_KEY": "k"}


def _ci_branch(world, *, rogue_script=False, session_test=False, extra_test=""):
    """A pushed branch whose head carries a tiny CI definition + the keepers it blocks on."""
    wt = world.worktree()
    for rel, text in ((".github/workflows/test.yml", _WORKFLOW), ("mcp/noctusai/cli.py", _CLI),
                      ("mcp/noctusai/tests/test_keepers.py", _KEEPER_TESTS + (_SESSION_TEST if session_test else "") + extra_test),
                      ("scripts/MANIFEST", "tool.sh\n"), ("scripts/tool.sh", "#!/bin/sh\n")):
        (wt / rel).parent.mkdir(parents=True, exist_ok=True)
        (wt / rel).write_text(text)
    if rogue_script:
        (wt / "scripts" / "rogue.sh").write_text("#!/bin/sh\n")  # no manifest row: warning in pre-commit
    world.set_counts(wt)
    world.commit(wt, "ci definition")
    return wt, world.push(wt, "feat/x")


def _parity(world, **env):
    return RS.export_ci_parity_check(world.repo, base_env={**os.environ, **env}, verdict_store=world.verdict_store)(
        "feat/x", sh(world.repo, "git", "rev-parse", "feat/x"))


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
    ok, why = RS.validate_verdict_ref(res["verdict_ref"], head, world.verdict_store)
    assert ok, why
    rec = RS.read_verdict(world.verdict_store, res["verdict_ref"].split(":")[1])
    assert rec["head"] == head and rec["tree"] == sh(world.repo, "git", "rev-parse", "feat/x^{tree}")
    assert rec["workflow_blob"] == sh(world.repo, "git", "rev-parse", f"{head}:.github/workflows/test.yml")
    assert rec["flags"] == res["ran"]["flags"] and rec["tests"] == res["ran"]["tests"] and rec["ok"] is True
    assert rec["interpreter"].startswith(sys.executable)


def test_a_keeper_that_only_warns_in_precommit_but_blocks_in_ci_fails_item_five(world):
    _wt, head = _ci_branch(world, rogue_script=True)
    res = _parity(world, **_SCRUBBED_ENV)
    assert not res["ok"]
    assert "keeper --check-scripts-manifest" in res["detail"]
    assert "test tests/test_keepers.py::test_real_tree_manifest_clean" in res["detail"]
    d = RS.deliverable("feat/x", cwd=world.repo, derived_check=world.derived,
                       scoped_check=RS.export_ci_parity_check(world.repo, verdict_store=world.verdict_store),
                       verdict_ref=world.vref(), verdict_store=world.verdict_store)
    five = item(d, "scoped_green")
    assert d["verdict"] == "needs_resync" and not five["ok"] and "manifest" in five["detail"]
    # the red run minted a RED record: filing it as the verdict is refused too
    assert "RED" in RS.validate_verdict_ref(res["verdict_ref"], head, world.verdict_store)[1]


def test_a_test_that_depends_on_the_session_env_is_run_without_it(world, monkeypatch):
    _ci_branch(world, session_test=True)
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "sess-123")  # this process HAS the var: the dev machine
    # proof the keeper is green on the dev machine ...
    assert subprocess.run([sys.executable, "-c", "import os,sys; sys.exit(0 if os.environ.get('CLAUDE_CODE_SESSION_ID') else 1)"]).returncode == 0
    # ... and red the way CI sees it, because the check scrubs the env
    res = RS.export_ci_parity_check(world.repo, verdict_store=world.verdict_store)("feat/x", sh(world.repo, "git", "rev-parse", "feat/x"))
    assert not res["ok"] and "test_real_tree_session_keeper" in res["detail"]
    assert "keeper --check-advisory" not in res["detail"]  # a continue-on-error step does not block CI


def test_a_missing_workflow_is_unmeasured_never_green(world):
    wt = world.worktree()
    (wt / "src" / "b.txt").write_text("b\n")
    world.commit(wt, "no ci definition")
    head = world.push(wt, "feat/x")
    res = RS.export_ci_parity_check(world.repo, verdict_store=world.verdict_store)("feat/x", head)
    assert not res["ok"] and "UNMEASURED" in res["detail"]
    assert not world.verdict_store.exists()  # an unmeasured run mints no record


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


# =================================================================================================
# fix round 1 (adversarial review) - P1-1: a verdict_ref is a RECORD, not a string
# =================================================================================================

def test_a_forged_verdict_ref_string_is_refused(world):
    """The old shape (`<anything>@<head sha7>#env-scrubbed,ci-keepers`) was accepted on substrings alone."""
    wt = world.worktree()
    (wt / "src" / "b.txt").write_text("b\n")
    world.set_counts(wt)
    world.commit(wt, "feat: b")
    head = world.push(wt, "feat/x")
    for forged in (f"anything@{head[:9]}#env-scrubbed,ci-keepers", f"ci-parity:{'0' * 32}", f"ci-parity@{head}#env-scrubbed,ci-keepers",
                   "ci-parity:not-an-id"):
        five = item(world.deliverable(verdict_ref=forged), "scoped_green")
        assert not five["ok"], forged
        assert "verdict record" in five["detail"] or "free-form" in five["detail"], five["detail"]


def test_enqueue_attests_the_deliverable_verdict_the_pre_push_queue_path_requires(world):
    import json
    wt = world.worktree()
    (wt / "src" / "b.txt").write_text("b\n")
    world.set_counts(wt)
    world.commit(wt, "feat: b")
    head = world.push(wt, "feat/x")
    world.enqueue(confirm=False)
    att = Path(sh(world.repo, "git", "rev-parse", "--path-format=absolute", "--git-common-dir")) / "noc-enqueue" / f"{head}.json"
    assert not att.exists()  # a dry run attests nothing
    assert world.enqueue()["status"] == "queued"
    rec = json.loads(att.read_text())
    assert rec["sha"] == head and rec["ok"] is True and rec["verdict"] == "deliverable" and rec["failing"] == []
    assert rec["ref"] == f"refs/heads/mq/x--{head[:7]}"  # scoped to the ONE ref enqueue pushes to
    assert abs(rec["ts"] - __import__("time").time()) < 120
    # a refused (needs_resync) delivery is neither attested nor pushed
    (wt / "src" / "a.txt").write_text("uncommitted\n")
    other = world.enqueue(slug="x")
    assert other["status"] == "needs_resync"


# =================================================================================================
# P2-1: the trial merge honours DEV's .gitattributes (merge=union, merge drivers) - never the head's
# =================================================================================================

def _dev_with_union_log(world):
    world.dev_commit(".gitattributes", "*.log merge=union\n")
    world.dev_commit("events.log", "a\n")
    sh(world.repo, "git", "fetch", "-q", "origin")


def test_a_branch_behind_dev_on_a_merge_union_file_is_accepted(world):
    """Without dev's attributes the bare-context trial merge text-merged events.log and CONFLICTED: every
    branch touching an append-only ledger was forced to 0-behind (the livelock)."""
    _dev_with_union_log(world)
    wt = world.worktree()
    (wt / "events.log").write_text("a\nbranch\n")
    world.set_counts(wt)
    world.commit(wt, "feat: append to the ledger")
    world.push(wt, "feat/x")
    world.dev_commit("events.log", "a\ndev\n")  # dev appended a different line meanwhile
    d = world.deliverable()
    m = item(d, "merge_buildable")
    assert m["ok"], m
    assert "behind" in m["detail"] and "clean" in m["detail"]


def test_a_head_that_declares_merge_union_on_a_conflicting_file_is_still_needs_resync(world):
    """Attributes come from DEV only: a branch cannot opt its own conflict out by adding merge=union."""
    wt = world.worktree()
    (wt / ".gitattributes").write_text("src/a.txt merge=union\n")
    (wt / "src" / "a.txt").write_text("branch edit\n")
    world.set_counts(wt)
    world.commit(wt, "feat: declare union on my own conflict")
    world.push(wt, "feat/x")
    world.dev_commit("src/a.txt", "dev edit\n")
    m = item(world.deliverable(), "merge_buildable")
    assert not m["ok"] and "src/a.txt" in m["detail"]


_STUB_RENDER_CLI = """\
import pathlib, re, sys
a = sys.argv
src = pathlib.Path(a[a.index("--source") + 1]).read_text()
# like the real renderer: regenerate EVERYTHING between the kb-counts markers (conflict markers included)
out = re.sub(r"(<!-- kb-counts:start:x -->\\n).*?(<!-- kb-counts:end:x -->)", r"\\1N=9\\n\\2", src, flags=re.S)
pathlib.Path(a[a.index("--out") + 1]).write_text(out)
pathlib.Path(a[a.index("--worktree-path") + 1]).joinpath("driver-root-seen.txt").write_text("ran")
"""


def test_the_kb_counts_driver_finds_the_toolkit_when_the_trial_merge_runs_in_the_git_dir(world):
    """The driver used REPO_ROOT=$(git rev-parse --show-toplevel || pwd): in a git dir that is the git dir itself,
    mcp/noctusai/cli.py was 'missing', and every counts-block churn became a conflict."""
    driver = Path(os.environ.get("NOC_MERGE_DRIVER_UNDER_TEST") or Path(__file__).resolve().parents[3] / "scripts" / "hooks" / "merge-kb-counts.sh")
    sh(world.repo, "git", "config", "merge.kb-counts.driver", f"{driver} %O %A %B %P")
    world.dev_commit(".gitattributes", "doc.md merge=kb-counts\n")
    world.dev_commit("mcp/noctusai/cli.py", _STUB_RENDER_CLI)
    world.dev_commit("doc.md", "prose\n<!-- kb-counts:start:x -->\nN=1\n<!-- kb-counts:end:x -->\nmore prose\n")
    sh(world.repo, "git", "fetch", "-q", "origin")
    sh(world.repo, "git", "merge", "-q", "--ff-only", "origin/dev")  # the primary checkout owns the toolkit (stub cli)
    wt = world.worktree()
    (wt / "doc.md").write_text("prose\n<!-- kb-counts:start:x -->\nN=3\n<!-- kb-counts:end:x -->\nmore prose\n")  # counts churn on the branch ...
    world.set_counts(wt)
    world.commit(wt, "feat: counts bump")
    world.push(wt, "feat/x")
    world.dev_commit("doc.md", "prose\n<!-- kb-counts:start:x -->\nN=2\n<!-- kb-counts:end:x -->\nmore prose\n")  # ... and on dev: a text conflict a driver must resolve
    m = item(world.deliverable(), "merge_buildable")
    assert m["ok"], m
    assert (world.repo / "driver-root-seen.txt").read_text() == "ran"  # the primary checkout's toolkit rendered it


# =================================================================================================
# P2-2: the export checks judge the HEAD's seed lib, in the hermetic env
# =================================================================================================

_SEED_ISOLATED_CHECK = (
    "import pathlib, sys\n"
    "import noctusai_lib\n"
    "tree = pathlib.Path(sys.argv[1]).resolve()\n"
    "here = pathlib.Path(noctusai_lib.__file__).resolve()\n"
    "print('noctusai_lib from', here)\n"
    "sys.exit(0 if str(here).startswith(str(tree)) else 1)\n"
)
_NO_SESSION_CHECK = ("import os, sys\n"
                     "sys.exit(1 if os.environ.get('CLAUDE_CODE_SESSION_ID') or os.environ.get('CLAUDE_PROJECT_DIR') else 0)\n")


def _seed_branch(world, *, extra_files=None):
    """A pushed branch that carries its OWN tiny noctusai_lib + the requirements line that locates it."""
    wt = world.worktree()
    for rel, text in ((("seed/lib/backend/noctusai_lib/__init__.py"), "WHO = 'head'\n"),
                      ("mcp/noctusai/requirements.txt", "-e ../../seed/lib/backend\n"), *(extra_files or {}).items()):
        (wt / rel).parent.mkdir(parents=True, exist_ok=True)
        (wt / rel).write_text(text)
    world.set_counts(wt)
    world.commit(wt, "carry my own seed lib")
    return wt, world.push(wt, "feat/x")


def test_the_derived_check_imports_the_heads_seed_lib_not_the_primarys(world):
    _wt, head = _seed_branch(world)
    arts = (("seed-isolated", ("{python}", "-c", _SEED_ISOLATED_CHECK, "{tree}")),)
    res = RS.export_derived_check(world.repo, artifacts=arts)(head)
    assert res["ok"] and res["measured"], res


def test_the_derived_check_runs_in_the_hermetic_scrubbed_env(world, monkeypatch):
    _wt, head = _seed_branch(world)
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "sess-1")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", "/somewhere")
    arts = (("scrubbed", ("{python}", "-c", _NO_SESSION_CHECK)),)
    assert RS.export_derived_check(world.repo, artifacts=arts)(head)["ok"]


def test_the_ci_parity_check_imports_the_heads_seed_lib(world):
    wf = _WORKFLOW.replace("--check-in-a-later-job", "--check-seed-isolated")
    cli = _CLI.replace('if flag == "--check-scripts-manifest":', 'if flag == "--check-seed-isolated":\n'
                       '    import noctusai_lib\n    sys.exit(0 if str(pathlib.Path(noctusai_lib.__file__).resolve()).startswith(str(root.resolve())) else 1)\n'
                       'if flag == "--check-scripts-manifest":').replace('("--stamp", "--check-in-a-later-job")', '("--stamp",)')
    wt, head = _seed_branch(world, extra_files={".github/workflows/test.yml": wf, "mcp/noctusai/cli.py": cli,
                                                "mcp/noctusai/tests/test_keepers.py": _KEEPER_TESTS,
                                                "scripts/MANIFEST": "tool.sh\n", "scripts/tool.sh": "#!/bin/sh\n"})
    res = RS.export_ci_parity_check(world.repo, verdict_store=world.verdict_store)("feat/x", head)
    assert res["ok"], res


def test_an_export_that_differs_from_the_trees_file_list_is_unmeasured(world):
    """export-ignore silently drops files from `git archive`: the checks would judge a different tree."""
    wt = world.worktree()
    (wt / ".gitattributes").write_text("src/hidden.txt export-ignore\n")
    (wt / "src" / "hidden.txt").write_text("not exported\n")
    world.set_counts(wt)
    world.commit(wt, "feat: an export-ignored file")
    head = world.push(wt, "feat/x")
    res = world.derived(head)
    assert not res["ok"] and res["measured"] is False
    assert "src/hidden.txt" in res["detail"] and "export" in res["detail"]


# =================================================================================================
# P3 (adversarial review): small enqueue hardening
# =================================================================================================

def test_enqueue_does_not_write_fetch_head(world):
    wt = world.worktree()
    (wt / "src" / "b.txt").write_text("b\n")
    world.set_counts(wt)
    world.commit(wt, "feat: b")
    world.push(wt, "feat/x")
    fetch_head = Path(sh(world.repo, "git", "rev-parse", "--path-format=absolute", "--git-common-dir")) / "FETCH_HEAD"
    fetch_head.unlink(missing_ok=True)
    assert world.enqueue(confirm=False)["status"] == "planned"
    assert not fetch_head.exists()  # remote-tracking refs may move (release-steward.md G1); FETCH_HEAD may not appear


@pytest.mark.parametrize("bad", ["x;rm -rf ~", "a b", "../escape", "/abs", "x$(id)", "x\\ny"])
def test_enqueue_validates_the_slug_with_the_request_rule(world, bad):
    res = T.task_branch(action="enqueue", slug=bad, confirm=False, run=world.runner(), primary_root=str(world.repo))
    assert res["status"] == "error" and res["exit_code"] == 1
    assert "slug" in res["error"] and "[A-Za-z0-9._/-]" in res["error"]


def test_the_verdict_ref_fallback_only_follows_a_request_for_the_same_branch(world, tmp_path):
    store = RS.StewardStore(root=tmp_path / "steward", resolve_head=lambda b: None)
    store.request("sess-1", "y", branch="docs/y", head_sha="a" * 40, notes="n")
    # hand the recorded request a verdict_ref the way request() does
    store._append_event({"ts": "2026-11-10T00:00:00Z", "event": "request", "slug": "y", "branch": "docs/y",
                         "head_sha": "a" * 40, "verdict_ref": "ci-parity:" + "b" * 32, "requester": {"session_id": "sess-1"}})
    assert T._request_verdict_ref("y", "docs/y", store=store) == "ci-parity:" + "b" * 32
    assert T._request_verdict_ref("y", "feat/y", store=store) is None  # same slug, a DIFFERENT branch: not its verdict


# =================================================================================================
# fix round 2, N-1/N-6/N-7: refs are always fully qualified - a branch or tag NAMED like a ref must not win
# =================================================================================================

def _poison_refnames(world, head: str, old: str):
    """A local branch AND a tag named origin/dev (both at the branch head), and a tag named feat/x at an OLD commit:
    every unqualified `origin/dev` / `feat/x` now resolves to the wrong commit."""
    sh(world.repo, "git", "branch", "origin/dev", head)
    sh(world.repo, "git", "tag", "origin/dev", head)
    sh(world.repo, "git", "tag", "feat/x", old)


def test_a_branch_and_a_tag_named_origin_dev_cannot_make_the_head_read_as_dev(world):
    wt = world.worktree()
    (wt / "src" / "a.txt").write_text("branch edit\n")
    world.set_counts(wt)
    head = world.commit(wt, "feat: edit a")
    world.push(wt, "feat/x")
    old = sh(world.repo, "git", "rev-parse", "origin/dev")
    world.dev_commit("src/a.txt", "dev edit\n")
    _poison_refnames(world, head, old)
    two = item(world.deliverable(), "merge_buildable")
    assert not two["ok"] and "contains" not in two["detail"] and "src/a.txt" in two["detail"], two


def test_poisoned_refnames_cannot_hide_a_migration_collision_either(world):
    mig = "products/p/backend/migrations"
    (world.repo / mig).mkdir(parents=True)
    (world.repo / mig / "001_init.sql").write_text("-- 1\n")
    world.commit(world.repo, "p: 001")
    sh(world.repo, "git", "push", "origin", "dev")
    old = sh(world.repo, "git", "rev-parse", "dev")
    wt = world.worktree()
    (wt / mig).mkdir(parents=True, exist_ok=True)
    (wt / mig / "002_branch.sql").write_text("-- branch 2\n")
    world.set_counts(wt)
    head = world.commit(wt, "p: 002 branch")
    world.push(wt, "feat/x")
    world.dev_commit(f"{mig}/002_dev.sql", "-- dev 2\n")
    _poison_refnames(world, head, old)  # origin/dev now names the HEAD: the migration diff would be empty
    d = world.deliverable(derived_check=lambda h: {"ok": True, "measured": True, "detail": "n/a", "results": []})
    three = item(d, "migrations_free")
    assert item(d, "merge_buildable")["ok"]
    assert not three["ok"] and "number 002" in three["detail"], three  # not "adds no migration"


def test_a_tag_named_like_the_branch_cannot_redirect_what_enqueue_pushes(world):
    wt = world.worktree()
    (wt / "src" / "b.txt").write_text("b\n")
    world.set_counts(wt)
    head = world.commit(wt, "feat: b")
    world.push(wt, "feat/x")
    old = sh(world.repo, "git", "rev-parse", "origin/dev")
    sh(world.repo, "git", "tag", "feat/x", old)  # `git rev-parse feat/x` would now say the OLD commit
    sh(world.repo, "git", "tag", "origin/dev", old)
    res = world.enqueue(verdict_ref=world.vref("refs/heads/feat/x"))
    assert res["status"] == "queued", res
    assert res["enqueued_sha"] == head and res["queue_ref"] == f"mq/x--{head[:7]}"
    assert world.mq_refs() == [f"refs/heads/mq/x--{head[:7]}"]


def test_a_same_name_tag_cannot_make_cleanup_delete_unmerged_work(world):
    wt = world.worktree()
    (wt / "src" / "b.txt").write_text("b\n")
    world.set_counts(wt)
    unmerged = world.commit(wt, "feat: unmerged work")
    sh(world.repo, "git", "tag", "feat/x", sh(world.repo, "git", "rev-parse", "origin/dev"))  # a MERGED commit
    res = T.task_branch(action="cleanup", slug="x", confirm=True, run=world.runner(), primary_root=str(world.repo),
                        caller_session="sess-me")
    assert res["status"] == "blocked" and "not on" in res["reason"], res
    assert sh(world.repo, "git", "rev-parse", "--verify", "refs/heads/feat/x") == unmerged
    assert wt.is_dir()


def test_the_head_is_compared_in_full_not_by_a_seven_char_prefix(world):
    wt = world.worktree()
    (wt / "src" / "b.txt").write_text("b\n")
    world.set_counts(wt)
    head = world.commit(wt, "feat: b")
    world.push(wt, "feat/x")
    lookalike = head[:7] + "0" * 33  # same 7-char prefix, a different commit
    d = world.deliverable(head_sha=lookalike)
    one = item(d, "head_pushed_clean")
    assert not one["ok"] and "request names head" in one["detail"], one
    assert item(world.deliverable(head_sha=head), "head_pushed_clean")["ok"]
    assert item(world.deliverable(head_sha=head[:12]), "head_pushed_clean")["ok"]  # an abbreviation of THIS head is fine


def _attestation(world, sha):
    import json
    p = Path(sh(world.repo, "git", "rev-parse", "--path-format=absolute", "--git-common-dir")) / "noc-enqueue" / f"{sha}.json"
    return json.loads(p.read_text()) if p.exists() else None


def test_a_needs_resync_enqueue_invalidates_an_earlier_ok_attestation(world):
    wt = world.worktree()
    (wt / "src" / "b.txt").write_text("b\n")
    world.set_counts(wt)
    head = world.commit(wt, "feat: b")
    world.push(wt, "feat/x")
    assert world.enqueue(confirm=False)["status"] == "planned"
    # an ok attestation exists for this sha (e.g. a prior enqueue) ...
    assert world.enqueue()["status"] == "queued" and _attestation(world, head)["ok"] is True
    # ... then the contract stops holding (dirty tree): the guardian's re-run must revoke it
    (wt / "src" / "a.txt").write_text("dirty\n")
    assert world.enqueue(confirm=False)["status"] == "needs_resync"
    assert _attestation(world, head)["ok"] is False


def test_a_rejected_push_revokes_its_attestation(world):
    wt = world.worktree()
    (wt / "src" / "b.txt").write_text("b\n")
    world.set_counts(wt)
    head = world.commit(wt, "feat: b")
    world.push(wt, "feat/x")
    hook = world.origin / "hooks" / "pre-receive"
    hook.write_text("#!/bin/sh\necho 'rejected' >&2\nexit 1\n")
    hook.chmod(0o755)
    assert world.enqueue()["status"] == "blocked"
    assert _attestation(world, head)["ok"] is False  # the next raw push of this sha cannot ride a leftover ok


# =================================================================================================
# fix round 2, P2-2 residual: seed isolation covers EVERY seed package the head names, plus noctusai_seed
# =================================================================================================

def test_a_seed_package_the_head_ships_but_does_not_put_on_the_path_is_unmeasured(world):
    """noctusai_seed exists in the head but its requirements line is missing: it would resolve to the PRIMARY's copy."""
    _wt, head = _seed_branch(world, extra_files={"seed/framework/backend/noctusai_seed/__init__.py": "WHO = 'head'\n"})
    res = RS.export_derived_check(world.repo, artifacts=(("noop", ("{python}", "-c", "pass")),))(head)
    assert not res["ok"] and res["measured"] is False
    assert "noctusai_seed" in res["detail"] and "UNMEASURED" in res["detail"]


def test_every_package_under_a_seed_path_the_requirements_name_must_resolve_inside_the_export(world):
    _wt, head = _seed_branch(world, extra_files={
        "seed/framework/backend/noctusai_seed/__init__.py": "WHO = 'head'\n",
        "seed/extra/backend/another_seed_pkg/__init__.py": "WHO = 'head'\n",
        "mcp/noctusai/requirements.txt": "-e ../../seed/lib/backend\n-e ../../seed/framework/backend\n-e ../../seed/extra/backend\n"})
    check = (("seedpkgs", ("{python}", "-c", "import noctusai_lib, noctusai_seed, another_seed_pkg")),)
    res = RS.export_derived_check(world.repo, artifacts=check)(head)
    assert res["ok"] and res["measured"], res


# =================================================================================================
# the cli.py --help check (merge-loss-gate ejection): a bare "%A" in a help string crashes argparse
# =================================================================================================

_GOOD_CLI = "import argparse\np = argparse.ArgumentParser()\np.add_argument('--x', help='fine')\np.parse_args()\n"
_BAD_CLI = ("import argparse\np = argparse.ArgumentParser()\n"
            "p.add_argument('--merge-x', help='merge driver args %O %A %B %P')\n"  # argparse %-formats help: 'A' is not a format
            "p.parse_args()\n")


def _help_events(tmp_path):
    import json
    p = tmp_path / "gate-events.ndjson"
    return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []


def test_a_head_whose_cli_help_crashes_is_needs_resync_naming_the_check(world, tmp_path, monkeypatch):
    monkeypatch.setenv("NOCTUS_GUARD_EVENT_LOG", str(tmp_path / "gate-events.ndjson"))
    wt = world.worktree()
    (wt / "mcp" / "noctusai").mkdir(parents=True)
    (wt / "mcp" / "noctusai" / "cli.py").write_text(_BAD_CLI)
    world.set_counts(wt)
    world.commit(wt, "feat: a help string with a bare %A")
    world.push(wt, "feat/x")
    d = world.deliverable()
    four = item(d, "derived_current")
    assert d["verdict"] == "needs_resync" and not four["ok"], four
    assert "cli.py --help" in four["detail"] and "unsupported format character" in four["detail"], four["detail"]
    row = next(a for a in four["artifacts"] if a["name"] == "cli-help")
    assert row["ok"] is False and row["skipped"] is False
    ev = [e for e in _help_events(tmp_path) if e.get("guard") == "deliverable:cli-help"]
    assert ev and ev[-1]["outcome"] == "deny"


def test_a_clean_cli_help_passes_and_emits_a_pass_row(world, tmp_path, monkeypatch):
    monkeypatch.setenv("NOCTUS_GUARD_EVENT_LOG", str(tmp_path / "gate-events.ndjson"))
    wt = world.worktree()
    (wt / "mcp" / "noctusai").mkdir(parents=True)
    (wt / "mcp" / "noctusai" / "cli.py").write_text(_GOOD_CLI)
    world.set_counts(wt)
    world.commit(wt, "feat: a fine cli")
    world.push(wt, "feat/x")
    four = item(world.deliverable(), "derived_current")
    assert four["ok"], four
    assert next(a for a in four["artifacts"] if a["name"] == "cli-help")["ok"] is True
    assert [e["outcome"] for e in _help_events(tmp_path) if e.get("guard") == "deliverable:cli-help"] == ["pass"]


def test_a_head_that_does_not_touch_cli_py_skips_the_check_and_says_so(world, tmp_path, monkeypatch):
    monkeypatch.setenv("NOCTUS_GUARD_EVENT_LOG", str(tmp_path / "gate-events.ndjson"))
    world.dev_commit("mcp/noctusai/cli.py", _BAD_CLI)  # a broken cli.py ALREADY on dev: not this delivery's doing
    sh(world.repo, "git", "fetch", "-q", "origin")
    wt = world.worktree()
    (wt / "src" / "b.txt").write_text("b\n")
    world.set_counts(wt)
    world.commit(wt, "feat: unrelated")
    world.push(wt, "feat/x")
    four = item(world.deliverable(), "derived_current")
    assert four["ok"], four
    row = next(a for a in four["artifacts"] if a["name"] == "cli-help")
    assert row["skipped"] is True and row["ok"] is True
    assert "skipped" in four["detail"] and "cli.py --help" in four["detail"]
    assert not [e for e in _help_events(tmp_path) if e.get("guard") == "deliverable:cli-help"]


# =================================================================================================
# fix round 3 (first live use): run_scoped must measure the REAL repo shape, say why it failed, and never be ignored
# =================================================================================================

_BANNER = ("\x1b[1m╔" + "═" * 58 + "╗\x1b[0m\n\x1b[1m║                NoctusAI Dev Toolkit                      ║\x1b[0m\n"
           "\x1b[1m╚" + "═" * 58 + "╝\x1b[0m\n")

_GIT_NEEDY_CLI = (
    "import pathlib, subprocess, sys\n"
    f"BANNER = {_BANNER!r}\n"
    "root = pathlib.Path(__file__).resolve().parents[2]\n"
    "flag = sys.argv[1]\n"
    "if flag == '--stamp':\n"
    "    sys.stdout.write(BANNER)\n"
    "    if not (root / '.git').exists():\n"
    "        print('[stamp] git not available - skipping stamp.')\n"
    "        sys.exit(1)\n"
    "    sys.exit(0)\n"
    "if flag == '--check-gitdir-is-the-export':\n"  # the keeper-mirror caches live under <git-common-dir>: never the primary's
    "    gd = subprocess.run(['git', 'rev-parse', '--path-format=absolute', '--git-common-dir'], capture_output=True, text=True, cwd=root).stdout.strip()\n"
    "    sys.exit(0 if gd.startswith(str(root.resolve())) else 1)\n"
    "sys.exit(0)\n")


def test_run_scoped_gives_the_export_a_throwaway_git_repo_like_ci_has(world):
    """CI runs in a checkout: `--stamp-seed-version` needs git and the keeper caches live under the git dir. The export
    has no .git; a throwaway `git init` of the export (a temp dir, never a worktree) provides it."""
    wf = _WORKFLOW.replace("--check-in-a-later-job", "--check-gitdir-is-the-export")
    wt = world.worktree()
    for rel, text in ((".github/workflows/test.yml", wf), ("mcp/noctusai/cli.py", _GIT_NEEDY_CLI),
                      ("mcp/noctusai/tests/test_keepers.py", _KEEPER_TESTS), ("scripts/MANIFEST", "tool.sh\n"),
                      ("scripts/tool.sh", "#!/bin/sh\n")):
        (wt / rel).parent.mkdir(parents=True, exist_ok=True)
        (wt / rel).write_text(text)
    world.set_counts(wt)
    world.commit(wt, "ci definition whose prime step needs git")
    head = world.push(wt, "feat/x")
    before = sh(world.repo, "git", "rev-list", "--all", "--count"), sh(world.repo, "git", "worktree", "list", "--porcelain")
    res = RS.export_ci_parity_check(world.repo, verdict_store=world.verdict_store)("feat/x", head)
    assert res["ok"], res
    assert "--check-gitdir-is-the-export" in res["ran"]["flags"]
    assert (sh(world.repo, "git", "rev-list", "--all", "--count"), sh(world.repo, "git", "worktree", "list", "--porcelain")) == before
    assert RS.validate_verdict_ref(res["verdict_ref"], head, world.verdict_store)[0]


def test_the_meaningful_tail_drops_ansi_and_banner_and_keeps_the_error():
    noisy = (_BANNER + "2026-11-10 04:20:09 | INFO     | [noctusai-mcp-cli] env_bootstrap | env_bootstrap: no repo-root .env\n"
             + "".join(f"progress line {i}\n" for i in range(40)) + "\x1b[91mBoom: the real error\x1b[0m\nTraceback tail\n")
    tail = RS.meaningful_tail(noisy, max_lines=20)
    assert "NoctusAI Dev Toolkit" not in tail and "\x1b" not in tail and "═" not in tail and "env_bootstrap" not in tail
    assert "Boom: the real error" in tail and "Traceback tail" in tail
    assert len(tail.splitlines()) <= 20 and "progress line 39" in tail and "progress line 0" not in tail
    assert RS.meaningful_tail(_BANNER) == ""


def test_a_failing_prime_step_reports_the_real_error_not_the_banner(world):
    wt = world.worktree()
    cli = ("import sys\nsys.stdout.write(%r)\nprint('RealError: the stamp could not be written', file=sys.stderr)\nsys.exit(3)\n" % _BANNER)
    for rel, text in ((".github/workflows/test.yml", _WORKFLOW), ("mcp/noctusai/cli.py", cli)):
        (wt / rel).parent.mkdir(parents=True, exist_ok=True)
        (wt / rel).write_text(text)
    world.set_counts(wt)
    world.commit(wt, "a prime step that fails loudly")
    head = world.push(wt, "feat/x")
    res = RS.export_ci_parity_check(world.repo, verdict_store=world.verdict_store)("feat/x", head)
    assert not res["ok"] and "UNMEASURED" in res["detail"]
    assert "RealError: the stamp could not be written" in res["detail"]
    assert "NoctusAI Dev Toolkit" not in res["detail"] and "\x1b" not in res["detail"]


def test_a_red_keeper_flag_carries_its_own_error_in_the_result(world):
    _wt, head = _ci_branch(world, rogue_script=True)
    res = RS.export_ci_parity_check(world.repo, verdict_store=world.verdict_store)("feat/x", head)
    assert not res["ok"] and "script(s) without a manifest row" in res["detail"]


# -- request(run_scoped=True) is not silently ignored ------------------------------------------------------------

def test_request_run_scoped_runs_the_ci_parity_check_and_files_with_its_ref(world, tmp_path):
    wt = world.worktree()
    (wt / "src" / "b.txt").write_text("b\n")
    world.set_counts(wt)
    world.commit(wt, "feat: b")
    head = world.push(wt, "feat/x")
    calls = []

    def scoped(branch, full_head):
        calls.append((branch, full_head))
        ref = RS.record_verdict(world.verdict_store, head=full_head, tree=sh(world.repo, "git", "rev-parse", f"{full_head}^{{tree}}"),
                                workflow_blob="0" * 40, interpreter="t", flags=["--check-x"], tests=[], ok=True)
        return {"ok": True, "detail": "ran", "verdict_ref": ref}

    store = _store(world, tmp_path)
    store._scoped_check = scoped
    res = store.request("sess-1", "x", run_scoped=True)  # NO verdict_ref given: the run supplies it
    assert res["ok"] and res["status"] == "queued_for_steward", res
    assert calls == [("feat/x", head)]
    assert res["request"]["verdict_ref"].startswith("ci-parity:")
    assert res["scoped"]["verdict_ref"] == res["request"]["verdict_ref"]
    assert res["deliverable"]["verdict"] == "deliverable"


def test_request_run_scoped_with_a_red_run_is_needs_resync_naming_item_five(world, tmp_path):
    wt = world.worktree()
    (wt / "src" / "b.txt").write_text("b\n")
    world.set_counts(wt)
    world.commit(wt, "feat: b")
    world.push(wt, "feat/x")
    store = _store(world, tmp_path)

    def red(branch, full_head):
        ref = RS.record_verdict(world.verdict_store, head=full_head, tree=sh(world.repo, "git", "rev-parse", f"{full_head}^{{tree}}"),
                                workflow_blob="0" * 40, interpreter="t", flags=[], tests=[], ok=False)
        return {"ok": False, "detail": "RED: keeper --check-x", "verdict_ref": ref}
    store._scoped_check = red
    res = store.request("sess-1", "x", run_scoped=True)
    assert res["ok"] is False and res["status"] == "needs_resync" and "scoped_green" in res["failing"]


def test_request_refuses_run_scoped_it_cannot_honour_rather_than_ignoring_it(world, tmp_path):
    wt = world.worktree()
    (wt / "src" / "b.txt").write_text("b\n")
    world.set_counts(wt)
    world.commit(wt, "feat: b")
    world.push(wt, "feat/x")
    store = _store(world, tmp_path)
    store._scoped_check = None
    no_runner = store.request("sess-1", "x", run_scoped=True)
    assert no_runner["ok"] is False and "run_scoped" in no_runner["error"] and "no CI-parity runner" in no_runner["error"]
    train = store.request("sess-1", "x", run_scoped=True, branches=["feat/x", "feat/y"])
    assert train["ok"] is False and "per branch" in train["error"]
    assert store.requests() == {}  # a refused flag files nothing


def test_run_action_passes_run_scoped_through_to_request(world, tmp_path):
    wt = world.worktree()
    (wt / "src" / "b.txt").write_text("b\n")
    world.set_counts(wt)
    world.commit(wt, "feat: b")
    world.push(wt, "feat/x")
    store = _store(world, tmp_path)
    store._scoped_check = None
    res = RS.run_action("request", "sess-1", store=store, slug="x", run_scoped=True)
    assert res["ok"] is False and "run_scoped" in res["error"]  # it reached request() (and was refused there), not dropped


# ── the derived / CI-parity checks run in a SANDBOX (throwaway HOME, no git config, no real ~/.noctus) ────────

_WRITES_HOME_CHECK = (
    "import os, pathlib, subprocess, sys\n"
    "h = pathlib.Path(os.environ['HOME']); (h / '.noctus').mkdir(parents=True, exist_ok=True)\n"
    "(h / '.noctus' / 'x').write_text('delivery wrote me')\n"
    "assert 'NOCTUS_STEWARD_DIR' not in os.environ  # the inherited real dir was dropped\n"
    "assert os.environ['GIT_CONFIG_NOSYSTEM'] == '1'\n"
    "assert pathlib.Path(os.environ['GIT_CONFIG_GLOBAL']).read_text() == ''\n"
    "assert not any(k.startswith('GIT_CONFIG_KEY_') for k in os.environ)\n"
    "print(h)\n"
)


def test_a_delivery_that_writes_home_noctus_writes_the_sandbox_not_the_real_home(world, tmp_path):
    real_home = tmp_path / "real-home"
    (real_home / ".noctus").mkdir(parents=True)
    _wt, head = _seed_branch(world)
    arts = (("writes-home", ("{python}", "-c", _WRITES_HOME_CHECK)),)
    base = {**os.environ, "HOME": str(real_home), "NOCTUS_STEWARD_DIR": str(real_home / ".noctus"),
            "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "core.hooksPath", "GIT_CONFIG_VALUE_0": "/nope"}
    res = RS.export_derived_check(world.repo, artifacts=arts, base_env=base)(head)
    assert res["ok"] and res["measured"], res
    assert sorted(p.name for p in (real_home / ".noctus").iterdir()) == []  # the real ~/.noctus is untouched
    assert str(real_home) not in res["results"][0]["detail"]  # it ran with the throwaway HOME


def test_sandbox_setup_failure_is_unmeasured_never_skipped(world, monkeypatch):
    _wt, head = _seed_branch(world)

    def boom(env, home, ci_env=None):
        raise OSError("disk full")
    monkeypatch.setattr(RS, "sandbox_env", boom)
    res = RS.export_derived_check(world.repo, artifacts=_ARTIFACTS)(head)
    assert not res["ok"] and not res["measured"] and "sandbox setup failed" in res["detail"]


def test_sandbox_env_points_home_into_the_throwaway_dir_and_drops_state_dirs(tmp_path):
    env = RS.sandbox_env({"PATH": "/usr/bin", "HOME": "/real"}, tmp_path)
    assert env["HOME"] == str(tmp_path) and env["GIT_CONFIG_NOSYSTEM"] == "1"
    assert not [k for k in env if k.startswith("NOCTUS_")]
    assert Path(env["GIT_CONFIG_GLOBAL"]).read_text() == ""


# =================================================================================================
# 2026-11-10: the export is the WHOLE tree whatever the caller's cwd (b5's false "regenerator missing")
# =================================================================================================

@pytest.mark.parametrize("how", ["process_cwd", "cwd_arg"])
def test_the_export_is_the_whole_tree_when_called_from_a_subdirectory(tmp_path, monkeypatch, how):
    """`git archive` / `git ls-tree` run in a subdirectory see ONLY that subdirectory, and agree with each other, so
    the completeness check passed while item 4 reported cli.py "missing at the head". The MCP fresh-subprocess
    fallback runs from mcp/noctusai; the export must still be the repository's root tree."""
    repo = tmp_path / "repo"
    (repo / "mcp" / "noctusai").mkdir(parents=True)
    (repo / "mcp" / "noctusai" / "cli.py").write_text("print('cli')\n")
    (repo / "top.txt").write_text("root file\n")
    for args in (["init", "-q", "-b", "dev"], ["config", "user.email", "t@e.st"], ["config", "user.name", "T"],
                 ["add", "-A"], ["commit", "-q", "-m", "init"]):
        subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True).stdout.strip()
    sub = repo / "mcp" / "noctusai"
    out = tmp_path / "export"
    out.mkdir()
    if how == "process_cwd":
        monkeypatch.chdir(sub)
        err = RS._export_tree(head, str(out), None, 60)
    else:
        err = RS._export_tree(head, str(out), sub, 60)
    assert err is None, err
    assert (out / "top.txt").is_file() and (out / "mcp" / "noctusai" / "cli.py").is_file()
    assert not (out / "cli.py").exists()


def test_the_deliverable_git_seam_resolves_path_arguments_from_the_toplevel(tmp_path):
    """Item 3 lists `products/<p>/backend/migrations/` with `git ls-tree <tree> <dir>/`; from a subdirectory that
    pathspec matches NOTHING, so a migration-number collision would pass unseen. The seam runs at the toplevel."""
    repo = tmp_path / "repo"
    (repo / "products" / "p" / "backend" / "migrations").mkdir(parents=True)
    (repo / "products" / "p" / "backend" / "migrations" / "001_a.sql").write_text("select 1;\n")
    (repo / "mcp" / "noctusai").mkdir(parents=True)
    (repo / "mcp" / "noctusai" / "cli.py").write_text("\n")
    for args in (["init", "-q", "-b", "dev"], ["config", "user.email", "t@e.st"], ["config", "user.name", "T"],
                 ["add", "-A"], ["commit", "-q", "-m", "init"]):
        subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)
    git = RS._subprocess_git(repo / "mcp" / "noctusai")
    rc, out, _ = git("ls-tree", "--name-only", "HEAD", "products/p/backend/migrations/")
    assert rc == 0 and out.strip() == "products/p/backend/migrations/001_a.sql"


def test_a_stage_that_times_out_is_retried_once_then_passes_under_the_declared_budget(world, monkeypatch):
    """scoped_green uses the merged-tip budget system: per-stage budget, ONE x1.5 retry. A slow first attempt (the
    loaded-box case) is not an UNMEASURED verdict when the retry fits."""
    _ci_branch(world, extra_test=_SLOW_ONCE_TEST)
    monkeypatch.setenv("NOCTUS_GATE_BUDGETS_JSON", json.dumps({"ci_parity:pytest": 12}))
    res = _parity(world)
    assert res["ok"], res["detail"]
    assert world.verdict_store.exists()


def test_a_stage_that_times_out_twice_is_unmeasured_naming_the_stage_never_green(world, monkeypatch):
    _ci_branch(world, extra_test=_SLOW_ALWAYS_TEST)
    monkeypatch.setenv("NOCTUS_GATE_BUDGETS_JSON", json.dumps({"ci_parity:pytest": 2}))
    res = _parity(world)
    assert not res["ok"] and res["detail"].startswith("UNMEASURED:")
    assert "ci_parity:pytest" in res["detail"] and "x1.5 retry" in res["detail"]
    assert not world.verdict_store.exists()  # an unmeasured run mints no record


def test_every_ci_parity_stage_has_a_declared_budget():
    from tools.noctus.dev import gate_budget as gb
    for gate in ("ci_parity:export", "ci_parity:pytest", "ci_parity:keeper:--check-x", "ci_parity:prime:--stamp"):
        assert gb.declared_gate_budget(gate) is not None, gate
