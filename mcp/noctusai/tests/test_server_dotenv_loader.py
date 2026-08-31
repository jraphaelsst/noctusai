"""``server._load_repo_root_dotenv`` must load the repo-root ``.env`` without
ever clobbering an already-set environment variable, and must not crash when
the file is absent (a fresh clone / CI must still boot).

🔴 THE BUG THIS PINS (root-caused 2026-08-31, recurred every session for two
weeks) — ``.mcp.json`` launches this server with no ``env`` block and no
dotenv loading, so ``SUPABASE_URL`` / ``SUPABASE_SERVICE_ROLE_KEY`` were
absent from the server's environment even though the repo-root ``.env`` has
them, and every catalog-backed tool silently fell back to the checked-in
``deploy/fleet/build-scope.txt`` snapshot every session. This test file
proves the fix mechanically: run it with ``server._load_repo_root_dotenv``
stubbed back to a no-op and it MUST fail (see
``test_env_var_wins_over_dotenv_value`` docstring for the before/after
mutation proof run manually during development).
"""
from __future__ import annotations

import logging

import pytest


def _reload_settings_module(monkeypatch, repo_root):
    """`settings.REPO_ROOT` is resolved once via `workspace.get_noctusai_home()`
    (cached). Rather than fighting that cache, monkeypatch `settings.REPO_ROOT`
    directly on the already-imported module — exactly what `server.py`'s
    `from settings import REPO_ROOT` reads at call time inside the function
    under test (the import happens INSIDE `_load_repo_root_dotenv`, so patching
    the attribute on the `settings` module before calling it is sufficient)."""
    import settings

    monkeypatch.setattr(settings, "REPO_ROOT", repo_root)


class TestLoadRepoRootDotenv:
    def test_missing_dotenv_does_not_raise(self, tmp_path, monkeypatch, caplog):
        """No `.env` at REPO_ROOT -> logs an INFO line and returns; never raises
        (a fresh clone / CI has no `.env` and must still boot)."""
        from server import _load_repo_root_dotenv

        _reload_settings_module(monkeypatch, tmp_path)
        monkeypatch.delenv("NOC_TEST_DOTENV_PROBE", raising=False)

        with caplog.at_level(logging.INFO, logger="server"):
            _load_repo_root_dotenv()  # must not raise

        assert not (tmp_path / ".env").exists()
        assert any("no repo-root .env" in r.message for r in caplog.records)

    def test_dotenv_value_applied_when_env_unset(self, tmp_path, monkeypatch):
        """A key present ONLY in `.env` (not already in the process env) is
        applied to `os.environ`."""
        import os

        from server import _load_repo_root_dotenv

        monkeypatch.delenv("NOC_TEST_DOTENV_PROBE", raising=False)
        (tmp_path / ".env").write_text("NOC_TEST_DOTENV_PROBE=from-dotenv\n")
        _reload_settings_module(monkeypatch, tmp_path)

        _load_repo_root_dotenv()

        assert os.environ.get("NOC_TEST_DOTENV_PROBE") == "from-dotenv"

    def test_env_var_wins_over_dotenv_value(self, tmp_path, monkeypatch):
        """🔴 THE PRECEDENCE CONTRACT — `override=False`. An already-set process
        env var must ALWAYS win over the `.env` file's value for the same key;
        the loader must never clobber a value the caller deliberately set.

        Mutation proof (run manually during development, not asserted here):
        with `override=True` swapped in place of `override=False` in
        `server._load_repo_root_dotenv`, this test FAILS (the dotenv value
        clobbers the real env var); with `override=False` it PASSES.
        """
        import os

        from server import _load_repo_root_dotenv

        monkeypatch.setenv("NOC_TEST_DOTENV_PROBE", "from-real-env")
        (tmp_path / ".env").write_text("NOC_TEST_DOTENV_PROBE=from-dotenv\n")
        _reload_settings_module(monkeypatch, tmp_path)

        _load_repo_root_dotenv()

        assert os.environ.get("NOC_TEST_DOTENV_PROBE") == "from-real-env"

    def test_no_secret_value_is_logged(self, tmp_path, monkeypatch, caplog):
        """The loader may log which catalog KEYS are now present (booleans) and
        a count of newly-loaded keys, but must NEVER emit a secret VALUE."""
        import os

        from server import _load_repo_root_dotenv

        monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
        secret_value = "sb_secret_do_not_log_this_token_xyz123"
        (tmp_path / ".env").write_text(
            f"SUPABASE_URL=https://example.supabase.co\n"
            f"SUPABASE_SERVICE_ROLE_KEY={secret_value}\n"
        )
        _reload_settings_module(monkeypatch, tmp_path)

        with caplog.at_level(logging.INFO, logger="server"):
            _load_repo_root_dotenv()

        assert os.environ.get("SUPABASE_SERVICE_ROLE_KEY") == secret_value
        for record in caplog.records:
            assert secret_value not in record.message, (
                "the .env loader logged a secret VALUE — it must only log "
                "key names/counts/booleans, never contents"
            )
