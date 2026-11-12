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
    derive_guardian_protected_files,
    check_guardian_tool_authorship,
)
from tools.noctus.dev.release_steward import StewardStore  # noqa: E402

_DEV = "mcp/noctusai/tools/noctus/dev"
RS, TB = f"{_DEV}/release_steward.py", f"{_DEV}/task_branch.py"


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


class TestUnmeasured:
    """N-10: a failed `git diff --cached` must not read as a silent allow (it still does not block)."""

    def test_a_failing_diff_emits_an_unmeasured_row_and_a_warning_and_does_not_block(self, tmp_path, capsys):
        _claim(tmp_path)
        not_a_repo = tmp_path / "plain-dir"
        not_a_repo.mkdir()
        os.environ["NOCTUS_GUARD_EVENT_LOG"] = str(tmp_path / "events.ndjson")
        try:
            issues = check_guardian_tool_authorship(repo_root=not_a_repo, session_id="sess-guardian-1", lease_root=tmp_path)
        finally:
            os.environ.pop("NOCTUS_GUARD_EVENT_LOG", None)
        assert issues == []  # still does not block
        assert "UNMEASURED" in capsys.readouterr().err
        rows = [e for e in _events(tmp_path) if e.get("outcome") == "unmeasured"]
        assert rows and "git diff --cached" in rows[0].get("reason", "")

    def test_a_working_diff_emits_no_unmeasured_row(self, tmp_path, capsys):
        repo = _repo_with_tooling(tmp_path / "w")
        _claim(tmp_path)
        os.environ["NOCTUS_GUARD_EVENT_LOG"] = str(tmp_path / "events.ndjson")
        try:
            assert check_guardian_tool_authorship(repo_root=repo, session_id="sess-guardian-1", lease_root=tmp_path) == []
        finally:
            os.environ.pop("NOCTUS_GUARD_EVENT_LOG", None)
        assert "UNMEASURED" not in capsys.readouterr().err
        assert not [e for e in _events(tmp_path) if e.get("outcome") == "unmeasured"]


# ── the protected set is DERIVED (AST import walk), pinned as a snapshot ──────────────────────────────────────

REPO = Path(__file__).resolve().parents[3]
#: Pinned: a new import reachable from release_steward/task_branch shows up in review as a diff HERE.
EXPECTED_PROTECTED = sorted(f"{_DEV}/{n}.py" for n in (
    "_benign_stash _catalog_scope_guard _ledger_push _ledger_store _pii_guard _push_verdict _transient_retry _vps_ssh "
    "_worktree_staleness auth_false_green_predicate auto_improvement branch_pointer build build_scope cache_backend "
    "cache_backend_postgres ci_scope council_ledger decision_log deploy_pull deploy_verify dispatch_token_log doc_staleness "
    "gate_alignment gate_budget gate_sweep gate_verdict_cache harness_signatures hw_admission ledger_checksums "
    "merge_queue migrate_product migration_directives migration_replay noc_graph_cache orchestrator_inline_cutoff "
    "primary_write_guard prod_consent product_scope query_key_family_predicate release_steward self_patch_predicate "
    "ship_consent symbol_scope task_branch task_branch_train toolkit_freshness vps_exec").split()
) + sorted((
    ".github/workflows/merge-queue.yml", "scripts/hooks/claude-guard-release-steward.py",
    "scripts/hooks/claude-guard-session-heartbeat.py", "scripts/hooks/pre-push"))


class TestDerivedProtectedSet:
    def test_snapshot_of_the_live_tree(self):
        assert list(derive_guardian_protected_files(REPO)) == sorted(EXPECTED_PROTECTED)

    def test_required_members_and_every_path_exists(self):
        got = set(derive_guardian_protected_files(REPO))
        for name in ("merge_queue", "task_branch_train", "_benign_stash", "branch_pointer", "primary_write_guard",
                     "toolkit_freshness", "prod_consent", "ship_consent", "release_steward", "task_branch"):
            assert f"{_DEV}/{name}.py" in got, name
        assert "mcp/noctusai/tools/noctus/dev/compliance.py" not in got  # exempt keeper registry
        assert [p for p in got if not (REPO / p).is_file()] == []

    def test_a_new_import_is_picked_up(self, tmp_path):
        repo = _repo_with_tooling(tmp_path / "w")
        dev = repo / _DEV
        (dev / "extra_gate.py").write_text("x = 1\n")
        (dev / "release_steward.py").write_text("from tools.noctus.dev import extra_gate\n")
        assert f"{_DEV}/extra_gate.py" in derive_guardian_protected_files(repo)

    def test_derivation_failure_fails_closed_for_the_guardian_only(self, tmp_path):
        repo = _repo_with_tooling(tmp_path / "w")
        (repo / RS).write_text("def broken(:\n")
        _git(repo, "add", "-A")  # the keeper judges HEAD + the INDEX, never the working tree
        _claim(tmp_path)
        issues = _check_repo(repo, tmp_path, "sess-guardian-1", [f"{_DEV}/unrelated_tool.py"])
        assert len(issues) == 1 and "cannot derive" in issues[0]["issue"]
        assert _check_repo(repo, tmp_path, "someone-else", [f"{_DEV}/unrelated_tool.py"]) == []


class TestDerivationReadsHeadAndIndexNotTheWorkingTree:
    """P2-1: an edge dropped in an UNSTAGED edit, or a staged deletion, must not shrink the protected set."""

    def _repo_with_extra(self, tmp_path: Path) -> tuple[Path, str]:
        repo = _repo_with_tooling(tmp_path / "w")
        extra = f"{_DEV}/extra_gate.py"
        repo.joinpath(extra).write_text("x = 1\n")
        repo.joinpath(RS).write_text("from tools.noctus.dev import extra_gate\n")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", "wire extra_gate")
        return repo, extra

    def _run(self, repo, tmp_path):
        os.environ["NOCTUS_GUARD_EVENT_LOG"] = str(tmp_path / "ev-hi.ndjson")
        try:
            return check_guardian_tool_authorship(repo_root=repo, session_id="sess-guardian-1", lease_root=tmp_path)
        finally:
            os.environ.pop("NOCTUS_GUARD_EVENT_LOG", None)

    def test_an_unstaged_edge_drop_does_not_unprotect_the_module(self, tmp_path):
        repo, extra = self._repo_with_extra(tmp_path)
        _claim(tmp_path)
        repo.joinpath(RS).write_text("# import dropped, left UNSTAGED\n")
        repo.joinpath(extra).write_text("x = 2  # the staged edit\n")
        _git(repo, "add", extra)
        issues = self._run(repo, tmp_path)
        assert len(issues) == 1 and extra in issues[0]["file"]

    def test_a_staged_deletion_of_a_protected_module_is_refused(self, tmp_path):
        repo, extra = self._repo_with_extra(tmp_path)
        _claim(tmp_path)
        _git(repo, "rm", "-q", extra)
        assert not repo.joinpath(extra).exists()
        issues = self._run(repo, tmp_path)
        assert len(issues) == 1 and extra in issues[0]["file"]

    def test_a_non_guardian_is_not_blocked_by_either_shape(self, tmp_path):
        repo, extra = self._repo_with_extra(tmp_path)
        _git(repo, "rm", "-q", extra)
        os.environ["NOCTUS_GUARD_EVENT_LOG"] = str(tmp_path / "ev-ng.ndjson")
        try:
            assert check_guardian_tool_authorship(repo_root=repo, session_id="someone-else", lease_root=tmp_path) == []
        finally:
            os.environ.pop("NOCTUS_GUARD_EVENT_LOG", None)


def _check_repo(repo, root, sid, staged):
    os.environ["NOCTUS_GUARD_EVENT_LOG"] = str(root / "ev3.ndjson")
    try:
        return check_guardian_tool_authorship(repo_root=repo, staged=staged, session_id=sid, lease_root=root)
    finally:
        os.environ.pop("NOCTUS_GUARD_EVENT_LOG", None)


class TestDerivationIsLazyAndFast:
    """Only the live lease holder, staging something inside the package/anchors, pays for the derivation."""

    @staticmethod
    def _boom(*_a, **_k):
        raise AssertionError("derivation must not run")

    def test_staged_change_outside_the_package_never_derives(self, tmp_path, monkeypatch):
        import tools.noctus.dev.compliance as c
        monkeypatch.setattr(c, "derive_guardian_protected_files", self._boom)
        _claim(tmp_path)  # even the lease holder: nothing staged can be fenced
        assert _check(tmp_path, ["README.md", "products/x/a.py"]) == []

    def test_staged_package_file_without_a_lease_never_derives(self, tmp_path, monkeypatch):
        import tools.noctus.dev.compliance as c
        monkeypatch.setattr(c, "derive_guardian_protected_files", self._boom)
        assert _check(tmp_path, [RS]) == []
        assert _check(tmp_path, [RS], sid="someone-else") == []

    def test_the_holder_does_derive(self, tmp_path, monkeypatch):
        import tools.noctus.dev.compliance as c
        calls = []
        real = c.derive_guardian_protected_files
        monkeypatch.setattr(c, "derive_guardian_protected_files", lambda *a, **k: calls.append(1) or real(*a, **k))
        _claim(tmp_path)
        assert len(_check(tmp_path, [RS])) == 1 and calls

    def test_git_derivation_is_fast_and_equals_the_tree_read(self):
        t = time.time()
        from_git = derive_guardian_protected_files(REPO, from_git=True)
        assert time.time() - t < 3.0
        assert from_git == derive_guardian_protected_files(REPO)
