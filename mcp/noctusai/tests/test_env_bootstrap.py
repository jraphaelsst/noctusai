"""``env_bootstrap.load_repo_env`` — the ONE dotenv-loading path shared by the
MCP server (`server.py`) and the CLI/hooks (`cli.py`).

🔴 THE BUG THIS PINS (root-caused 2026-09-14) — the MCP server loaded the
repo-root ``.env`` at import time (fixed 2026-08-31), but ``cli.py`` (which
``scripts/hooks/pre-push`` invokes directly, never through ``server.py``)
never loaded ``.env`` at all. ``check_migration_applied_ledger_drift`` SKIPped
from the pre-push hook ("no supabase_access_token resolved") even though the
IDENTICAL ``.env``, on the SAME disk, had ``SUPABASE_ACCESS_TOKEN`` set — the
MCP server resolved it fine because it alone called the loader. These tests
prove the shared loader closes that gap for BOTH the plain case (repo_root
IS the primary) and the worktree case (repo_root is a linked worktree with no
``.env`` of its own — the exact shape ``pre-push`` runs `cli.py` under).
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from env_bootstrap import load_repo_env


def _git(*args: str, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


@pytest.fixture
def probe_env_var(monkeypatch):
    """Ensure the probe key starts unset and is cleaned up either way."""
    monkeypatch.delenv("NOC_TEST_ENV_BOOTSTRAP_PROBE", raising=False)
    yield "NOC_TEST_ENV_BOOTSTRAP_PROBE"


class TestLoadRepoEnvDirect:
    """``repo_root`` IS the location holding ``.env`` (the primary-checkout
    shape, and how the MCP server always invokes this)."""

    def test_missing_dotenv_does_not_raise(self, tmp_path, probe_env_var):
        """No `.env` anywhere in the candidate chain -> never raises, and
        loads nothing (booleans on the result reflect whatever the REAL
        process env already has — e.g. a prior test in the same pytest
        process may have loaded real credentials — so this test only
        asserts the loading outcome, not global-env presence flags)."""
        result = load_repo_env(tmp_path)

        assert result.loaded_from == ()

    def test_dotenv_value_applied_when_env_unset(self, tmp_path, probe_env_var):
        (tmp_path / ".env").write_text(f"{probe_env_var}=from-dotenv\n")

        result = load_repo_env(tmp_path)

        assert os.environ.get(probe_env_var) == "from-dotenv"
        assert result.loaded_from == (tmp_path / ".env",)

    def test_env_var_wins_over_dotenv_value(self, tmp_path, probe_env_var, monkeypatch):
        """🔴 PRECEDENCE CONTRACT — `override=False`. An already-set process
        env var always wins over the `.env` file's value for the same key."""
        monkeypatch.setenv(probe_env_var, "from-real-env")
        (tmp_path / ".env").write_text(f"{probe_env_var}=from-dotenv\n")

        load_repo_env(tmp_path)

        assert os.environ.get(probe_env_var) == "from-real-env"

    def test_no_secret_value_is_logged(self, tmp_path, monkeypatch, caplog):
        import logging

        monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
        secret_value = "sb_secret_do_not_log_this_token_xyz123"
        (tmp_path / ".env").write_text(
            "SUPABASE_URL=https://example.supabase.co\n"
            f"SUPABASE_SERVICE_ROLE_KEY={secret_value}\n"
        )

        with caplog.at_level(logging.INFO, logger="env_bootstrap"):
            result = load_repo_env(tmp_path)

        assert result.supabase_service_role_key_present is True
        assert os.environ.get("SUPABASE_SERVICE_ROLE_KEY") == secret_value
        for record in caplog.records:
            assert secret_value not in record.message, (
                "the .env loader logged a secret VALUE — it must only log "
                "key names/counts/booleans, never contents"
            )


class TestLoadRepoEnvWorktreeFallback:
    """🔴 THE EXACT SHAPE OF THE INCIDENT — `repo_root` is a linked git
    worktree (no `.env` of its own; gitignored, never part of a worktree
    checkout). `cli.py`, invoked by `scripts/hooks/pre-push` from inside a
    worktree, resolves `settings.REPO_ROOT` to that worktree by design
    (KB § architect/seed-workspace.md worktree-boundary detection) — so the
    loader MUST fall back to the PRIMARY checkout's `.env` via
    `git rev-parse --git-common-dir`, or the credential never resolves from
    the hook path at all, regardless of what's in the primary's `.env`.
    """

    @pytest.fixture
    def primary_and_worktree(self, tmp_path, probe_env_var):
        primary = tmp_path / "primary"
        primary.mkdir()
        _git("init", "-q", cwd=primary)
        _git("config", "user.email", "test@example.com", cwd=primary)
        _git("config", "user.name", "test", cwd=primary)
        (primary / "README.md").write_text("seed\n")
        _git("add", "README.md", cwd=primary)
        _git("commit", "-q", "-m", "init", cwd=primary)
        (primary / ".env").write_text(f"{probe_env_var}=from-primary-dotenv\n")

        worktree = tmp_path / "worktree"
        _git("worktree", "add", "-q", str(worktree), "-b", "feat/probe", cwd=primary)

        assert not (worktree / ".env").exists(), "fixture sanity: worktrees never carry .env"
        return primary, worktree

    def test_resolves_primary_dotenv_from_worktree_root(
        self, primary_and_worktree, probe_env_var
    ):
        primary, worktree = primary_and_worktree

        result = load_repo_env(worktree)

        assert os.environ.get(probe_env_var) == "from-primary-dotenv"
        assert result.loaded_from == (primary / ".env",)
        assert result.attempted == (worktree, primary)

    def test_worktree_own_dotenv_takes_precedence_when_present(
        self, primary_and_worktree, probe_env_var
    ):
        """If a worktree ever DID carry its own `.env` (hand-placed, not the
        gitignored norm) with the SAME key as the primary's, the worktree's
        value wins — `repo_root` is tried FIRST and `override=False` means
        whichever candidate sets a key first keeps it. Both files still get
        loaded (a real union of keys — a hand-placed partial worktree `.env`
        shouldn't hide unrelated keys only the primary's `.env` carries)."""
        primary, worktree = primary_and_worktree
        (worktree / ".env").write_text(f"{probe_env_var}=from-worktree-dotenv\n")

        result = load_repo_env(worktree)

        assert os.environ.get(probe_env_var) == "from-worktree-dotenv"
        assert result.loaded_from == (worktree / ".env", primary / ".env")


class TestCandidateRootsNonGitDir:
    def test_non_git_dir_falls_back_to_itself_only(self, tmp_path):
        from env_bootstrap import _candidate_roots

        roots = _candidate_roots(tmp_path)

        assert roots == (tmp_path.resolve(),)
