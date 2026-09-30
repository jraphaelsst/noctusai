"""salvage_worktree stage_all / paths: a caller that can write into the
worktree but not run git there still finishes a commit end to end."""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.salvage_worktree import salvage_worktree  # noqa: E402


def _repo(tmp_path):
    def g(*a):
        return subprocess.run(["git", "-C", str(tmp_path), *a], check=True, capture_output=True, text=True).stdout
    g("init", "-q")
    g("config", "user.email", "t@t")
    g("config", "user.name", "t")
    (tmp_path / "seed.txt").write_text("x")
    g("add", "-A")
    g("commit", "-q", "-m", "init")
    return g


def test_default_nothing_staged_refuses(tmp_path):
    _repo(tmp_path)
    (tmp_path / "a.txt").write_text("a")
    r = salvage_worktree(str(tmp_path), "m")
    assert r["ok"] is False and r["divergence_suspected"]


def test_stage_all_commits_everything(tmp_path):
    g = _repo(tmp_path)
    (tmp_path / "a.txt").write_text("a")
    (tmp_path / "b.txt").write_text("b")
    r = salvage_worktree(str(tmp_path), "m", stage_all=True)
    assert r["ok"] and sorted(r["staged_files"]) == ["a.txt", "b.txt"]
    assert g("status", "--porcelain").strip() == ""


def test_paths_commits_only_those(tmp_path):
    g = _repo(tmp_path)
    (tmp_path / "a.txt").write_text("a")
    (tmp_path / "b.txt").write_text("b")
    r = salvage_worktree(str(tmp_path), "m", paths=["a.txt"], expect_markers=[["a.txt", "a"]])
    assert r["ok"] and r["staged_files"] == ["a.txt"]
    assert "b.txt" in g("status", "--porcelain")


def test_bad_path_reports_error(tmp_path):
    _repo(tmp_path)
    r = salvage_worktree(str(tmp_path), "m", paths=["nope.txt"])
    assert r["ok"] is False and "git add failed" in r["error"]
