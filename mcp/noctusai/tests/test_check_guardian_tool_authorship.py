"""check_guardian_tool_authorship: the lease holder never stages steward tooling.

Real lease files in tmp dirs via StewardStore; session/clock/root injected.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.compliance import (  # noqa: E402
    GUARDIAN_PROTECTED_TOOL_FILES,
    check_guardian_tool_authorship,
)
from tools.noctus.dev.release_steward import StewardStore  # noqa: E402

RS, TB = GUARDIAN_PROTECTED_TOOL_FILES


def _claim(root: Path, sid: str = "sess-guardian-1") -> None:
    res = StewardStore(root).claim(sid, name="guardian", reason="test")
    assert res.get("ok"), res


def _check(root, staged, sid="sess-guardian-1", now=None, events=None):
    ev = events if events is not None else root / "events.ndjson"
    os.environ["NOCTUS_GUARD_EVENT_LOG"] = str(ev)
    try:
        return check_guardian_tool_authorship(staged=staged, session_id=sid, lease_root=root, now=now)
    finally:
        os.environ.pop("NOCTUS_GUARD_EVENT_LOG", None)


def _events(root: Path) -> list[dict]:
    p = root / "events.ndjson"
    return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []


class TestCheckGuardianToolAuthorship:
    def test_holder_staging_release_steward_is_refused(self, tmp_path):
        _claim(tmp_path)
        issues = _check(tmp_path, [RS, "README.md"])
        assert len(issues) == 1 and issues[0]["severity"] == "high"
        assert RS in issues[0]["file"] and "guardian" in issues[0]["issue"]
        assert "tooling branch steward" in issues[0]["issue"]
        assert any(e.get("outcome") == "deny" for e in _events(tmp_path))


    def test_holder_staging_task_branch_is_refused(self, tmp_path):
        _claim(tmp_path)
        assert len(_check(tmp_path, [TB])) == 1


    def test_holder_staging_other_files_passes(self, tmp_path):
        _claim(tmp_path)
        assert _check(tmp_path, ["mcp/noctusai/tools/noctus/dev/compliance.py", "x.md"]) == []


    def test_non_holder_passes(self, tmp_path):
        _claim(tmp_path)
        assert _check(tmp_path, [RS, TB], sid="some-other-session") == []


    def test_no_lease_file_passes_and_records_why(self, tmp_path):
        assert _check(tmp_path, [RS]) == []
        ev = _events(tmp_path)
        assert ev and "no-lease" in json.dumps(ev[-1])


    def test_expired_lease_is_not_a_holder(self, tmp_path):
        _claim(tmp_path)
        later = time.time() + 10 * 24 * 3600
        assert _check(tmp_path, [RS], now=later) == []


# ── P3 (adversarial review): renames must not hide a protected file; the CLI honours --worktree-path ──────────

import subprocess  # noqa: E402

_GENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}


def _git(repo: Path, *a: str) -> None:
    subprocess.run(["git", *a], cwd=repo, check=True, capture_output=True, env=_GENV)


def _repo_with_tooling(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / Path(RS).parent).mkdir(parents=True)
    repo.joinpath(RS).write_text("# steward tooling\n" * 20)
    repo.joinpath(TB).write_text("# task branch\n" * 20)
    _git(repo, "init", "-q", "-b", "dev")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "init")
    return repo


class TestRenamesAndWorktreePath:
    def test_staging_a_rename_of_protected_tooling_is_still_a_hit(self, tmp_path):
        """git's rename detection reports only the NEW name, so moving release_steward.py away evaded the keeper."""
        repo = _repo_with_tooling(tmp_path / "w")
        _claim(tmp_path)
        _git(repo, "mv", RS, str(Path(RS).parent / "renamed_elsewhere.py"))
        os.environ["NOCTUS_GUARD_EVENT_LOG"] = str(tmp_path / "ev.ndjson")
        try:
            issues = check_guardian_tool_authorship(repo_root=repo, session_id="sess-guardian-1", lease_root=tmp_path)
        finally:
            os.environ.pop("NOCTUS_GUARD_EVENT_LOG", None)
        assert len(issues) == 1 and RS in issues[0]["file"]

    def test_the_cli_judges_the_worktree_path_it_is_given(self, tmp_path):
        repo = _repo_with_tooling(tmp_path / "w")
        _claim(tmp_path)
        repo.joinpath(TB).write_text("# edited by the guardian\n")
        _git(repo, "add", "-A")
        cli = Path(__file__).resolve().parents[1] / "cli.py"
        env = {**os.environ, "NOCTUS_STEWARD_DIR": str(tmp_path), "CLAUDE_CODE_SESSION_ID": "sess-guardian-1",
               "NOCTUS_GUARD_EVENT_LOG": str(tmp_path / "ev2.ndjson"), "NOCTUS_HOOK_QUIET": "1"}
        r = subprocess.run([sys.executable, str(cli), "--check-guardian-tool-authorship", "--worktree-path", str(repo)],
                           capture_output=True, text=True, env=env, cwd=tmp_path)
        assert r.returncode == 1, (r.stdout, r.stderr)
        assert TB in r.stdout
