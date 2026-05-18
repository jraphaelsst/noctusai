"""Contract tests for scripts/merge-debt-monitor.sh.

The canonical sibling monitors (disk-usage-monitor.sh, mole.sh) have NO
colocated test file — they are validated by invocation. This brief
explicitly authorizes a test, so we match the only available convention:
invoke the real script and assert the OUTPUT contract (exit-code semantics,
--json shape, --help, bad-arg) rather than reaching into bash internals.

The script is read-only against git, so running it in CI is side-effect
free. Severity-band tests drive the script against synthetic ephemeral git
repos so the assertions are deterministic regardless of the live backlog.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts" / "merge-debt-monitor.sh"


def _run(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        cwd=str(cwd or REPO_ROOT),
        capture_output=True,
        text=True,
    )


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=str(repo),
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.fixture
def synthetic_repo(tmp_path: Path):
    """A throwaway git repo with a `main` ref and a feature branch HEAD.

    Returns a factory: build(n_commits, n_closed) shapes the
    origin/main..HEAD range so severity bands are deterministic. `main`
    stands in for `origin/main` (the script falls back to `main` when the
    remote ref is absent).
    """

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
                msg = f"chore(archive): close proj-{i} — git mv to archive/2026-05-17/0{i}"
                made_closed += 1
            else:
                msg = f"feat: change {i}"
            _git(repo, "commit", "-qm", msg)
        return repo

    return build


def test_script_exists_and_executable():
    assert SCRIPT.exists(), f"missing {SCRIPT}"
    assert SCRIPT.stat().st_mode & 0o111, "script not executable"


def test_help_exits_zero_and_describes_policy():
    r = _run("--help")
    assert r.returncode == 0, r.stderr
    assert "phased-push" in r.stdout
    assert "merge-debt-monitor.sh" in r.stdout


def test_bad_arg_exits_two():
    r = _run("--nope")
    assert r.returncode == 2
    assert "Unknown arg" in r.stderr


def test_live_run_against_real_tree_is_sane():
    """Read-only invocation against the actual repo never errors hard."""
    r = _run("--json")
    assert r.returncode in (0, 1, 2, 3), f"unexpected exit {r.returncode}: {r.stderr}"
    payload = json.loads(r.stdout)
    assert set(payload) == {
        "severity",
        "branch",
        "base",
        "commits_ahead",
        "closed_projects_unmerged",
        "exit_code",
        "next_action",
    }
    assert payload["severity"] in ("OK", "CAUTION", "WARNING", "CRITICAL")
    assert payload["commits_ahead"] >= 0
    assert payload["closed_projects_unmerged"] >= 0
    assert payload["exit_code"] == r.returncode


def test_band_ok(synthetic_repo):
    repo = synthetic_repo(n_commits=3, n_closed=0)
    r = _run("--json", cwd=repo)
    p = json.loads(r.stdout)
    assert p["severity"] == "OK"
    assert r.returncode == 0
    assert p["commits_ahead"] == 3
    assert p["closed_projects_unmerged"] == 0


def test_band_caution_on_commit_volume(synthetic_repo):
    # 25 commits, zero closed → CAUTION (COMMITS_CAUTION=25).
    repo = synthetic_repo(n_commits=25, n_closed=0)
    r = _run("--json", cwd=repo)
    p = json.loads(r.stdout)
    assert p["severity"] == "CAUTION"
    assert r.returncode == 1


def test_band_warning_on_one_closed_project(synthetic_repo):
    # A single closed project unmerged is WARNING regardless of commit count.
    repo = synthetic_repo(n_commits=4, n_closed=1)
    r = _run("--json", cwd=repo)
    p = json.loads(r.stdout)
    assert p["severity"] == "WARNING"
    assert r.returncode == 2
    assert p["closed_projects_unmerged"] == 1


def test_band_critical_on_three_closed_projects(synthetic_repo):
    repo = synthetic_repo(n_commits=6, n_closed=3)
    r = _run("--json", cwd=repo)
    p = json.loads(r.stdout)
    assert p["severity"] == "CRITICAL"
    assert r.returncode == 3
    assert p["closed_projects_unmerged"] == 3


def test_band_critical_on_commit_volume(synthetic_repo):
    # 60 commits, zero closed → CRITICAL (COMMITS_CRITICAL=60).
    repo = synthetic_repo(n_commits=60, n_closed=0)
    r = _run("--json", cwd=repo)
    p = json.loads(r.stdout)
    assert p["severity"] == "CRITICAL"
    assert r.returncode == 3


def test_human_summary_shape(synthetic_repo):
    repo = synthetic_repo(n_commits=4, n_closed=1)
    r = _run(cwd=repo)
    assert "Merge-debt monitor" in r.stdout
    assert "Closed projects unmerged: 1" in r.stdout
    assert "Severity:" in r.stdout
    assert "next_action:" in r.stdout
