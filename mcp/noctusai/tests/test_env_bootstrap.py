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
from unittest.mock import patch

import pytest

import env_bootstrap
from env_bootstrap import (
    get_loaded_keys,
    load_repo_env,
    redact_secrets_in_text,
    sanitize_subprocess_env,
)


@pytest.fixture(autouse=True)
def _restore_environ():
    """`load_repo_env` writes loaded keys into the real `os.environ`, and
    `monkeypatch.delenv(..., raising=False)` records nothing for a key that
    was never set — so without this, the fake `SUPABASE_*` values below
    outlive the test and every later test that builds a Supabase client
    fails with "Invalid API key" (CI, 2026-09-14). Also snapshots/restores
    the module-level `_loaded_keys` set `load_repo_env` writes into — the
    same leak shape, one layer up: a probe key `load_repo_env` records in
    one test must not make a LATER test think it was actually injected
    from `.env` (it wasn't; it was set directly via `monkeypatch.setenv`)."""
    before = frozenset(env_bootstrap._loaded_keys)
    with patch.dict(os.environ):
        yield
    env_bootstrap._loaded_keys.clear()
    env_bootstrap._loaded_keys.update(before)


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


class TestGetLoadedKeys:
    """`get_loaded_keys()` names exactly what `load_repo_env` injected from
    `.env` — never a value, and never a key that was already set before it
    ran (`override=False` means that key was NOT this call's doing)."""

    def test_records_keys_actually_injected_from_dotenv(self, tmp_path, probe_env_var):
        env_bootstrap._loaded_keys.clear()
        (tmp_path / ".env").write_text(f"{probe_env_var}=from-dotenv\n")

        load_repo_env(tmp_path)

        assert probe_env_var in get_loaded_keys()

    def test_does_not_record_a_key_already_set_before_the_call(
        self, tmp_path, probe_env_var, monkeypatch
    ):
        env_bootstrap._loaded_keys.clear()
        monkeypatch.setenv(probe_env_var, "from-real-env")
        (tmp_path / ".env").write_text(f"{probe_env_var}=from-dotenv\n")

        load_repo_env(tmp_path)

        assert probe_env_var not in get_loaded_keys()

    def test_empty_before_any_load(self):
        env_bootstrap._loaded_keys.clear()

        assert get_loaded_keys() == frozenset()


class TestSanitizeSubprocessEnv:
    """The subprocess-env leg of the 2026-09-27 fix: a gate subprocess must
    not inherit whatever `load_repo_env` pulled in from `.env`."""

    def test_strips_a_dotenv_injected_key(self, tmp_path, probe_env_var):
        env_bootstrap._loaded_keys.clear()
        (tmp_path / ".env").write_text(f"{probe_env_var}=super-secret-value\n")
        load_repo_env(tmp_path)
        assert os.environ.get(probe_env_var) == "super-secret-value"

        sanitized = sanitize_subprocess_env()

        assert probe_env_var not in sanitized

    def test_keeps_everything_else(self, tmp_path, probe_env_var, monkeypatch):
        env_bootstrap._loaded_keys.clear()
        monkeypatch.setenv("NOC_TEST_KEEP_ME", "still-here")
        (tmp_path / ".env").write_text(f"{probe_env_var}=super-secret-value\n")
        load_repo_env(tmp_path)

        sanitized = sanitize_subprocess_env()

        assert sanitized.get("NOC_TEST_KEEP_ME") == "still-here"
        assert "PATH" in sanitized  # the harness genuinely needs this

    def test_extra_strip_removes_additional_named_keys(self):
        env_bootstrap._loaded_keys.clear()
        base = {"PATH": "/usr/bin", "NOC_HAND_SET_SECRET": "x"}

        sanitized = sanitize_subprocess_env(base, extra_strip=["NOC_HAND_SET_SECRET"])

        assert sanitized == {"PATH": "/usr/bin"}

    def test_does_not_mutate_the_real_os_environ(self, tmp_path, probe_env_var):
        env_bootstrap._loaded_keys.clear()
        (tmp_path / ".env").write_text(f"{probe_env_var}=super-secret-value\n")
        load_repo_env(tmp_path)

        sanitize_subprocess_env()

        assert os.environ.get(probe_env_var) == "super-secret-value"


class TestRedactSecretsInText:
    """The redaction backstop: a gate `summary` must never carry a real
    secret value or a recognizable token shape, whether or not the
    subprocess-env leg above already stopped it at the source."""

    def test_masks_a_known_dotenv_loaded_value(self, tmp_path, probe_env_var):
        env_bootstrap._loaded_keys.clear()
        secret_value = "re_totally_fake_resend_key_abc123"
        (tmp_path / ".env").write_text(f"{probe_env_var}={secret_value}\n")
        load_repo_env(tmp_path)

        text = f"assert {{'api_key': '{secret_value}'}} is None"
        redacted = redact_secrets_in_text(text)

        assert secret_value not in redacted

    def test_masks_secret_named_env_value_even_without_dotenv(self, monkeypatch):
        env_bootstrap._loaded_keys.clear()
        monkeypatch.setenv("NOC_TEST_API_TOKEN", "hand-set-not-from-dotenv")

        redacted = redact_secrets_in_text("token=hand-set-not-from-dotenv")

        assert "hand-set-not-from-dotenv" not in redacted

    def test_does_not_mask_short_non_secret_values(self, monkeypatch):
        env_bootstrap._loaded_keys.clear()
        monkeypatch.setenv("NOC_TEST_FLAG_TOKEN", "on")  # < min maskable length

        redacted = redact_secrets_in_text("flag is on")

        assert redacted == "flag is on"

    @pytest.mark.parametrize(
        "raw,masked_prefix",
        [
            ("re_1234567890abcdef", "re_***"),
            ("sk-1234567890abcdef1234", "sk-***"),
            ("sk-ant-api03-abc123def456", "sk-ant-***"),
            ("ghp_abcdefghijklmnopqrstuvwxyz012345", "ghp_***"),
            ("eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dQw4w9WgXcQ", "eyJ***"),
        ],
    )
    def test_masks_common_token_shapes_by_pattern_alone(self, raw, masked_prefix):
        env_bootstrap._loaded_keys.clear()

        redacted = redact_secrets_in_text(f"unexpected value: {raw}")

        assert raw not in redacted
        assert masked_prefix in redacted

    def test_sk_ant_is_masked_as_anthropic_not_generic_sk(self):
        env_bootstrap._loaded_keys.clear()
        raw = "sk-ant-api03-abc123def456ghijklmnop"

        redacted = redact_secrets_in_text(f"key={raw}")

        assert "sk-ant-***" in redacted
        assert "sk-***" not in redacted

    def test_clean_text_with_no_secrets_passes_through_unchanged(self):
        env_bootstrap._loaded_keys.clear()

        text = "6232 passed, 0 failed in 42.11s"

        assert redact_secrets_in_text(text) == text

    def test_none_and_empty_text_are_returned_as_is(self):
        assert redact_secrets_in_text("") == ""

    def test_longer_known_value_masked_before_a_shorter_overlapping_one(
        self, monkeypatch
    ):
        """A shorter secret value that happens to be a PREFIX of a longer
        one must not partially clobber the longer one's occurrence — masked
        longest-first."""
        env_bootstrap._loaded_keys.clear()
        monkeypatch.setenv("NOC_TEST_SHORT_SECRET", "abcdef")
        monkeypatch.setenv("NOC_TEST_LONG_SECRET", "abcdefghijklmno")

        redacted = redact_secrets_in_text("value=abcdefghijklmno")

        assert "abcdefghijklmno" not in redacted
        assert redacted.count("***REDACTED***") == 1
