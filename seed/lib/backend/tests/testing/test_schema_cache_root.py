"""Where `get_schema_map()` looks for migrations — and why the order matters.

These tests exist because the previous resolution order produced a
FALSE GREEN, not a red: a worktree's tests validated the primary
checkout's schema, so a column that existed only in the worktree was
"unknown" and its assertion was silently skipped. Nothing failed. That is
the failure mode worth a dedicated test file.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from noctusai_lib.testing import _schema_cache


def _make_repo(root: Path, *, product: str = "demo", sql: str = "") -> Path:
    """Build the minimal shape `_find_repo_root` recognises."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "CLAUDE.md").write_text("# marker\n")
    migrations = root / "products" / product / "backend" / "migrations"
    migrations.mkdir(parents=True)
    if sql:
        (migrations / "001_init.sql").write_text(sql)
    return root


class TestResolutionOrder:
    def test_env_override_wins_over_everything(self, tmp_path, monkeypatch):
        """It is called an override; it must actually override.

        The old code consulted it only after the `__file__` walk had
        already succeeded — i.e. only when it could not help.
        """
        wanted = _make_repo(tmp_path / "wanted")
        other = _make_repo(tmp_path / "other")
        monkeypatch.setenv("NOCTUSAI_REPO_ROOT", str(wanted))
        monkeypatch.chdir(other)

        assert _schema_cache._find_repo_root() == wanted.resolve()

    def test_cwd_repo_beats_the_installed_packages_repo(self, tmp_path, monkeypatch):
        """The regression this file is named for.

        With no explicit override, the tree the runner is standing in is
        the tree whose migrations it meant.
        """
        monkeypatch.delenv("NOCTUSAI_REPO_ROOT", raising=False)
        worktree = _make_repo(tmp_path / "worktree")
        monkeypatch.chdir(worktree)

        resolved = _schema_cache._find_repo_root()

        assert resolved == worktree.resolve()
        # And specifically NOT the checkout noctusai_lib was imported from.
        assert resolved != _schema_cache._walk_up_for_root(Path(_schema_cache.__file__))

    def test_a_nested_dir_inside_the_repo_still_resolves_to_the_repo(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.delenv("NOCTUSAI_REPO_ROOT", raising=False)
        repo = _make_repo(tmp_path / "repo")
        deep = repo / "products" / "demo" / "backend"
        monkeypatch.chdir(deep)

        assert _schema_cache._find_repo_root() == repo.resolve()

    def test_unrelated_cwd_falls_back_to_this_files_repo(self, tmp_path, monkeypatch):
        """A caller with an unrelated cwd keeps the historical behaviour."""
        monkeypatch.delenv("NOCTUSAI_REPO_ROOT", raising=False)
        elsewhere = tmp_path / "not-a-repo"
        elsewhere.mkdir()
        monkeypatch.chdir(elsewhere)

        assert (
            _schema_cache._find_repo_root()
            == _schema_cache._walk_up_for_root(Path(_schema_cache.__file__))
        )

    def test_explicit_start_is_honoured_before_cwd(self, tmp_path, monkeypatch):
        monkeypatch.delenv("NOCTUSAI_REPO_ROOT", raising=False)
        asked_for = _make_repo(tmp_path / "asked")
        standing_in = _make_repo(tmp_path / "standing")
        monkeypatch.chdir(standing_in)

        assert _schema_cache._find_repo_root(asked_for) == asked_for.resolve()


class TestItActuallyReadsThatRepo:
    def test_the_resolved_repos_migrations_are_the_ones_parsed(
        self, tmp_path, monkeypatch
    ):
        """End-to-end: a column that exists only in the cwd's repo is known.

        This is the assertion whose absence made the original bug silent.
        """
        repo = _make_repo(
            tmp_path / "repo",
            sql="CREATE TABLE demo.widgets (id uuid, coluna_so_daqui text);",
        )
        monkeypatch.setenv("NOCTUSAI_REPO_ROOT", str(repo))
        _schema_cache.reset_cache()
        try:
            schema = _schema_cache.get_schema_map()
            assert "demo.widgets" in schema
            assert "coluna_so_daqui" in schema["demo.widgets"]
        finally:
            _schema_cache.reset_cache()


class TestNoRootAtAll:
    def test_raises_rather_than_guessing(self, tmp_path, monkeypatch):
        monkeypatch.delenv("NOCTUSAI_REPO_ROOT", raising=False)
        nowhere = tmp_path / "nowhere"
        nowhere.mkdir()
        monkeypatch.chdir(nowhere)
        monkeypatch.setattr(_schema_cache, "_walk_up_for_root", lambda _start: None)

        with pytest.raises(RuntimeError, match="could not locate repo root"):
            _schema_cache._find_repo_root()
