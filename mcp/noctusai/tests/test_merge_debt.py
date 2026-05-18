"""Tests for the noctus.dev.check_merge_debt tool.

Behaviour parity with scripts/merge-debt-monitor.sh: the severity bands
(OK / CAUTION≥25 commits / WARNING≥1 closed-project / CRITICAL≥3 closed OR
≥60 commits) + exit-code 0/1/2/3 mapping, driven against synthetic
ephemeral git repos so assertions are deterministic regardless of the live
backlog.

Distinct from the existing test_merge_debt_monitor.py (which invokes the
shell script); this exercises the native Python port.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.merge_debt import check_merge_debt


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args], cwd=str(repo), check=True,
        capture_output=True, text=True,
    )


@pytest.fixture
def synthetic_repo(tmp_path: Path):
    """Factory: build(n_commits, n_closed) shapes the origin/main..HEAD
    range. `main` stands in for `origin/main` (the tool falls back to
    `main` when the remote ref is absent — same as the shell script)."""

    def build(n_commits: int, n_closed: int) -> Path:
        repo = tmp_path / f"r_{n_commits}_{n_closed}"
        repo.mkdir()
        _git(repo, "init", "-q", "-b", "main")
        _git(repo, "config", "user.email", "t@t.t")
        _git(repo, "config", "user.name", "t")
        (repo / "f").write_text("base\n")
        _git(repo, "add", "f")
        _git(repo, "commit", "-qm", "base")
        _git(repo, "checkout", "-q", "-b", "feature")
        made_closed = 0
        for i in range(n_commits):
            (repo / "f").write_text(f"c{i}\n")
            _git(repo, "add", "f")
            if made_closed < n_closed:
                msg = (
                    f"chore(archive): close proj-{i} — git mv to "
                    f"archive/2026-05-17/0{i}"
                )
                made_closed += 1
            else:
                msg = f"feat: change {i}"
            _git(repo, "commit", "-qm", msg)
        return repo

    return build


def _keys() -> set[str]:
    return {
        "timestamp", "branch", "base", "commits_ahead",
        "closed_projects_unmerged", "severity", "exit_code",
        "status", "next_action",
    }


class TestContract:
    def test_returns_structured_dict(self, synthetic_repo):
        repo = synthetic_repo(n_commits=3, n_closed=0)
        result = check_merge_debt(repo_root=repo)
        assert set(result) == _keys()
        assert result["status"] == result["severity"]
        assert result["base"] in ("origin/main", "main")
        assert result["branch"] == "feature"


class TestSeverityBands:
    def test_ok_band(self, synthetic_repo):
        repo = synthetic_repo(n_commits=3, n_closed=0)
        r = check_merge_debt(repo_root=repo)
        assert r["severity"] == "OK"
        assert r["exit_code"] == 0
        assert r["commits_ahead"] == 3
        assert r["closed_projects_unmerged"] == 0

    def test_caution_on_commit_volume(self, synthetic_repo):
        # 25 commits, zero closed → CAUTION (COMMITS_CAUTION=25).
        repo = synthetic_repo(n_commits=25, n_closed=0)
        r = check_merge_debt(repo_root=repo)
        assert r["severity"] == "CAUTION"
        assert r["exit_code"] == 1

    def test_below_caution_threshold_is_ok(self, synthetic_repo):
        repo = synthetic_repo(n_commits=24, n_closed=0)
        r = check_merge_debt(repo_root=repo)
        assert r["severity"] == "OK"

    def test_warning_on_one_closed_project(self, synthetic_repo):
        # A single closed project unmerged is WARNING regardless of commits.
        repo = synthetic_repo(n_commits=4, n_closed=1)
        r = check_merge_debt(repo_root=repo)
        assert r["severity"] == "WARNING"
        assert r["exit_code"] == 2
        assert r["closed_projects_unmerged"] == 1

    def test_critical_on_three_closed_projects(self, synthetic_repo):
        repo = synthetic_repo(n_commits=6, n_closed=3)
        r = check_merge_debt(repo_root=repo)
        assert r["severity"] == "CRITICAL"
        assert r["exit_code"] == 3
        assert r["closed_projects_unmerged"] == 3

    def test_critical_on_commit_volume(self, synthetic_repo):
        # 60 commits, zero closed → CRITICAL (COMMITS_CRITICAL=60).
        repo = synthetic_repo(n_commits=60, n_closed=0)
        r = check_merge_debt(repo_root=repo)
        assert r["severity"] == "CRITICAL"
        assert r["exit_code"] == 3

    def test_next_action_text_present(self, synthetic_repo):
        repo = synthetic_repo(n_commits=4, n_closed=1)
        r = check_merge_debt(repo_root=repo)
        assert "phase-push" in r["next_action"]


class TestMcpRegistration:
    def test_register_callable(self):
        from tools.noctus.dev.merge_debt import register
        assert callable(register)

    def test_register_wires_tool_onto_a_server(self):
        """The module's own register() wires the tool. (Global build_server()
        wiring lands when the architect adds merge_debt to
        tools/noctus/dev/__init__.py per the integration recipe.)"""
        from mcp.server.fastmcp import FastMCP

        from tools.noctus.dev.merge_debt import register
        s = FastMCP(name="t")
        register(s)
        assert "noctus.dev.check_merge_debt" in s._tool_manager._tools
