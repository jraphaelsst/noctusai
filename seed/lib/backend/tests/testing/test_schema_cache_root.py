"""Where `get_schema_map()` looks for migrations — and why the order matters.

These tests exist because BOTH resolution orders this file has shipped
produced a FALSE GREEN, not a red — each in the opposite scenario:

  - Round 1 (2026-08-23, `__file__`-first): a worktree's tests, invoked
    WITHOUT PYTHONPATH scoped at the worktree, imported the PRIMARY
    checkout's `noctusai_lib` — a column that existed only in the
    worktree was "unknown" and its assertion was silently skipped.
  - Round 2 (2026-09-18, the `cwd`-first fix that followed): invoke
    pytest with an absolute path into a worktree's test file while the
    shell's cwd is still the PRIMARY checkout (the sanctioned
    `noctus.dev.pytest(worktree_path=...)` invocation correctly scopes
    PYTHONPATH, so `__file__` lands in the worktree) — cwd was checked
    FIRST and won anyway, so the mock built its schema from the
    PRIMARY's migrations while validating the WORKTREE's code:
    `MockSchemaError: ... has no column ...` for a column that plainly
    existed, because the invocation was wrong, not the test.

The invariant this file now encodes: `Path(__file__)` is a FACT about
which copy of `noctusai_lib` the interpreter actually loaded (Python
caches one location per package in `sys.modules`), never a guess —
`Path.cwd()` is ambient shell state and only settles disputes when
`__file__` has nothing to say. A disagreement between the two is no
longer silent either way; see `test_a_disagreement_between_file_and_cwd_
roots_is_logged_loudly` below. Same family as verdict-channel integrity
and stale-interpreter detection — KB § PATTERNS/common/methodology-
execution-discipline.md § "resolve the root from the artefact under
evaluation, never from the ambient cwd."
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

    def test_file_own_repo_beats_the_ambient_cwd(self, tmp_path, monkeypatch):
        """Round 2's regression, exactly reproduced: `__file__`'s repo and
        cwd's repo genuinely disagree — the module's own location (a fact
        about what's actually executing) must win, not the shell's cwd
        (which knows nothing about what got imported)."""
        monkeypatch.delenv("NOCTUSAI_REPO_ROOT", raising=False)
        executing_from = _make_repo(tmp_path / "executing-from")
        standing_in = _make_repo(tmp_path / "standing-in")
        monkeypatch.chdir(standing_in)

        resolved = _schema_cache._find_repo_root(
            module_file=str(executing_from / "testing" / "_schema_cache.py")
        )

        assert resolved == executing_from.resolve()
        assert resolved != standing_in.resolve()

    def test_cwd_used_when_file_has_no_resolvable_repo(self, tmp_path, monkeypatch):
        """`__file__` is preferred, not exclusive — when it resolves to
        nowhere recognisable (a caller with an unusual import path), cwd
        still gets the last word rather than the whole lookup failing."""
        monkeypatch.delenv("NOCTUSAI_REPO_ROOT", raising=False)
        elsewhere = tmp_path / "not-a-repo"
        elsewhere.mkdir()
        worktree = _make_repo(tmp_path / "worktree")
        monkeypatch.chdir(worktree)

        resolved = _schema_cache._find_repo_root(
            module_file=str(elsewhere / "_schema_cache.py")
        )

        assert resolved == worktree.resolve()

    def test_a_disagreement_between_file_and_cwd_roots_is_logged_loudly(
        self, tmp_path, monkeypatch, caplog
    ):
        """Silence is what made round 2 cost an hour — a mismatch between
        the two candidates must be visible in the run itself, independent
        of which one wins."""
        import logging

        monkeypatch.delenv("NOCTUSAI_REPO_ROOT", raising=False)
        executing_from = _make_repo(tmp_path / "executing-from")
        standing_in = _make_repo(tmp_path / "standing-in")
        monkeypatch.chdir(standing_in)

        with caplog.at_level(logging.WARNING, logger="noctusai_lib.testing._schema_cache"):
            _schema_cache._find_repo_root(
                module_file=str(executing_from / "testing" / "_schema_cache.py")
            )

        assert any("repo-root candidates disagree" in r.message for r in caplog.records)

    def test_no_warning_when_file_and_cwd_agree(self, tmp_path, monkeypatch, caplog):
        """The common case (running from inside the tree whose
        `noctusai_lib` is loaded) must stay quiet — a warning on every
        normal run would train people to ignore it."""
        import logging

        monkeypatch.delenv("NOCTUSAI_REPO_ROOT", raising=False)
        repo = _make_repo(tmp_path / "repo")
        monkeypatch.chdir(repo)

        with caplog.at_level(logging.WARNING, logger="noctusai_lib.testing._schema_cache"):
            resolved = _schema_cache._find_repo_root(
                module_file=str(repo / "testing" / "_schema_cache.py")
            )

        assert resolved == repo.resolve()
        assert not any("repo-root candidates disagree" in r.message for r in caplog.records)

    def test_a_nested_dir_inside_the_repo_still_resolves_to_the_repo(
        self, tmp_path, monkeypatch
    ):
        """Pure walk-up behaviour, isolated from the file-vs-cwd precedence
        question above: `module_file` neutralised (points nowhere
        resolvable) so cwd's own walk-up-from-a-nested-dir is what's under
        test."""
        monkeypatch.delenv("NOCTUSAI_REPO_ROOT", raising=False)
        elsewhere = tmp_path / "not-a-repo"
        elsewhere.mkdir()
        repo = _make_repo(tmp_path / "repo")
        deep = repo / "products" / "demo" / "backend"
        monkeypatch.chdir(deep)

        assert _schema_cache._find_repo_root(
            module_file=str(elsewhere / "_schema_cache.py")
        ) == repo.resolve()

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
        monkeypatch.setattr(_schema_cache, "_walk_up_for_root", lambda _start: None)  # self-patch-ok: forces "nowhere at all" — __file__ always resolves to a real repo here, so both walk-ups must be forced to fail to reach the RuntimeError under test

        with pytest.raises(RuntimeError, match="could not locate repo root"):
            _schema_cache._find_repo_root()
