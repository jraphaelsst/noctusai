"""A trial merge must never run with the primary checkout as cwd: git creates
`.merge_file_*` (custom merge-driver scratch) in the process cwd (2026-11-09)."""
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.mole import _sweep_merge_scratch  # noqa: E402
from tools.noctus.dev.task_branch import _trial_merge_tree  # noqa: E402


def _git(cwd, *a):
    return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True, check=True).stdout


def _repo(tmp_path):
    r = tmp_path / "r"
    r.mkdir()
    _git(r, "init", "-q", "-b", "main")
    _git(r, "config", "user.email", "a@b")
    _git(r, "config", "user.name", "a")
    (r / ".gitattributes").write_text("*.txt merge=slow\n")
    (r / "f.txt").write_text("a\nb\nc\n")
    _git(r, "add", "-A")
    _git(r, "commit", "-qm", "base")
    _git(r, "checkout", "-qb", "x")
    (r / "f.txt").write_text("a\nX\nc\n")
    _git(r, "commit", "-qam", "x")
    _git(r, "checkout", "-q", "main")
    (r / "f.txt").write_text("a\nY\nc\n")
    _git(r, "commit", "-qam", "y")
    drv = tmp_path / "drv.sh"
    drv.write_text("#!/bin/sh\nsleep 1.5\nexit 1\n")
    drv.chmod(0o755)
    _git(r, "config", "merge.slow.driver", f"{drv} %O %A %B %P")
    return r


def _run_probe_and_watch(repo, probe):
    seen: list[str] = []
    stop = threading.Event()

    def watch():
        while not stop.is_set():
            seen.extend(p.name for p in repo.glob(".merge_file_*"))
            time.sleep(0.05)

    t = threading.Thread(target=watch)
    t.start()
    try:
        probe()
    finally:
        stop.set()
        t.join()
    return seen


def test_trial_merge_tree_leaves_no_scratch_in_the_work_tree(tmp_path):
    repo = _repo(tmp_path)

    def git(*a, cwd=None):
        r = subprocess.run(["git", *a], cwd=cwd or repo, capture_output=True, text=True)
        return r.returncode, r.stdout, r.stderr

    seen = _run_probe_and_watch(repo, lambda: _trial_merge_tree(git, "main", "x"))
    assert seen == []


def test_plain_merge_tree_with_primary_cwd_does_litter_so_the_test_can_fail(tmp_path):
    """Red control: the pre-fix shape (cwd = work tree) is what littered."""
    repo = _repo(tmp_path)
    seen = _run_probe_and_watch(
        repo, lambda: subprocess.run(["git", "merge-tree", "--write-tree", "main", "x"],
                                     cwd=repo, capture_output=True))
    assert seen


def test_unresolvable_git_dir_skips_the_probe(tmp_path):
    calls = []

    def git(*a, cwd=None):
        calls.append((a, cwd))
        return 1, "", "no"

    rc, _o, _e = _trial_merge_tree(git, "a", "b")
    assert rc == 2 and all(a[0] != "merge-tree" for a, _c in calls)


def test_mole_sweeps_only_stale_scratch(tmp_path):
    import os
    old, new = tmp_path / ".merge_file_Old123", tmp_path / ".merge_file_New123"
    other = tmp_path / ".merge_file_notscratch.txt"
    for f in (old, new, other):
        f.write_text("x")
    os.utime(old, (time.time() - 3600,) * 2)
    os.utime(other, (time.time() - 3600,) * 2)
    log: list[str] = []
    _sweep_merge_scratch(tmp_path, True, log)
    assert old.exists()  # dry run
    _sweep_merge_scratch(tmp_path, False, log)
    assert not old.exists() and new.exists() and other.exists()
