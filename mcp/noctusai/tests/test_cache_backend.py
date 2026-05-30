"""Tests for the cache_backend abstraction layer (`cache_backend.py`).

These tests lock the Protocol contract + the default SqliteCacheBackend
behavior so future remote-backend implementations have a fixed target.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import sqlite3

import pytest

from tools.noctus.dev import cache_backend as cb


class TestCatalog:
    def test_known_caches_returns_5_names(self):
        names = cb.known_caches()
        assert set(names) == {
            "keeper-patterns",
            "agent-context",
            "auto-improvement",
            "kb-embeddings",
            "code-embeddings",
        }

    def test_known_caches_stable_order(self):
        # Order matters for deterministic refresh sequences.
        assert cb.known_caches() == cb.known_caches()


class TestCachePath:
    def test_resolves_under_dot_claude_cache(self, tmp_path):
        p = cb.cache_path("keeper-patterns", repo_root=tmp_path)
        assert p == tmp_path / ".claude" / "cache" / "keeper-patterns.sqlite"

    def test_unknown_cache_raises_KeyError(self, tmp_path):
        with pytest.raises(KeyError, match="Unknown cache name"):
            cb.cache_path("not-a-cache", repo_root=tmp_path)

    def test_uses_settings_repo_root_by_default(self):
        # No explicit repo_root → falls back to settings.REPO_ROOT.
        p = cb.cache_path("kb-embeddings")
        assert p.name == "kb-embeddings.sqlite"
        assert ".claude/cache" in str(p)


class TestSqliteBackend:
    def test_kind_is_sqlite(self, tmp_path):
        be = cb.SqliteCacheBackend(repo_root=tmp_path)
        assert be.kind() == "sqlite"

    def test_location_returns_file_path(self, tmp_path):
        be = cb.SqliteCacheBackend(repo_root=tmp_path)
        loc = be.location("agent-context")
        assert loc.endswith(".claude/cache/agent-context.sqlite")

    def test_connect_creates_parent_dir(self, tmp_path):
        be = cb.SqliteCacheBackend(repo_root=tmp_path)
        with be.connect("keeper-patterns") as conn:
            assert isinstance(conn, sqlite3.Connection)
        # File created on connect, parent dir auto-mkdir'd.
        assert (tmp_path / ".claude" / "cache").exists()

    def test_connect_applies_wal_mode(self, tmp_path):
        be = cb.SqliteCacheBackend(repo_root=tmp_path)
        with be.connect("keeper-patterns") as conn:
            cur = conn.execute("PRAGMA journal_mode")
            mode = cur.fetchone()[0]
            assert mode.lower() == "wal"

    def test_connect_sets_row_factory_to_Row(self, tmp_path):
        be = cb.SqliteCacheBackend(repo_root=tmp_path)
        with be.connect("keeper-patterns") as conn:
            assert conn.row_factory is sqlite3.Row

    def test_connect_closes_on_exit(self, tmp_path):
        be = cb.SqliteCacheBackend(repo_root=tmp_path)
        with be.connect("keeper-patterns") as conn:
            conn.execute("CREATE TABLE t (x INTEGER)")
            conn.commit()
        # After exit, the connection is closed — re-use raises ProgrammingError.
        with pytest.raises(sqlite3.ProgrammingError):
            conn.execute("SELECT 1")

    def test_connect_roundtrip_persists(self, tmp_path):
        be = cb.SqliteCacheBackend(repo_root=tmp_path)
        with be.connect("keeper-patterns") as conn:
            conn.execute("CREATE TABLE t (x INTEGER)")
            conn.execute("INSERT INTO t VALUES (?)", (42,))
            conn.commit()
        # Reopen — data survives (real file, real persistence).
        with be.connect("keeper-patterns") as conn:
            row = conn.execute("SELECT x FROM t").fetchone()
            assert row["x"] == 42

    def test_unknown_cache_raises_via_connect(self, tmp_path):
        be = cb.SqliteCacheBackend(repo_root=tmp_path)
        with pytest.raises(KeyError):
            with be.connect("not-a-cache"):
                pass


class TestFactory:
    def test_get_backend_default_is_sqlite(self, monkeypatch, tmp_path):
        monkeypatch.delenv(cb._ENV_VAR, raising=False)
        be = cb.get_backend(repo_root=tmp_path)
        assert be.kind() == "sqlite"
        assert isinstance(be, cb.SqliteCacheBackend)

    def test_get_backend_respects_env_var(self, monkeypatch, tmp_path):
        monkeypatch.setenv(cb._ENV_VAR, "sqlite")
        be = cb.get_backend(repo_root=tmp_path)
        assert be.kind() == "sqlite"

    def test_get_backend_case_insensitive(self, monkeypatch, tmp_path):
        monkeypatch.setenv(cb._ENV_VAR, "SQLITE")
        be = cb.get_backend(repo_root=tmp_path)
        assert be.kind() == "sqlite"

    def test_get_backend_unknown_raises_ValueError(self, monkeypatch):
        # "postgres" is now valid (Phase 3.1); use a truly unknown value.
        monkeypatch.setenv(cb._ENV_VAR, "supabase")
        with pytest.raises(ValueError, match="not a valid backend yet"):
            cb.get_backend()

    def test_protocol_isinstance_check(self, tmp_path):
        # Runtime-checkable Protocol — confirms SqliteCacheBackend satisfies.
        be = cb.SqliteCacheBackend(repo_root=tmp_path)
        assert isinstance(be, cb.CacheBackend)


class TestLockingPragmas:
    """The cache-locking discipline: WAL + busy_timeout, applied uniformly.

    Regression guard for the 2026-05-30 pre-push writer-contention incident —
    WAL alone does not serialize writer-vs-writer, so a contending writer hit
    `sqlite3.OperationalError: database is locked`. busy_timeout closes the gap.
    """

    def test_sets_wal_and_busy_timeout(self, tmp_path):
        conn = sqlite3.connect(str(tmp_path / "t.sqlite"))
        try:
            cb.apply_locking_pragmas(conn)
            assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
            assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == cb.CACHE_BUSY_TIMEOUT_MS
        finally:
            conn.close()

    def test_custom_timeout_honored(self, tmp_path):
        conn = sqlite3.connect(str(tmp_path / "t.sqlite"))
        try:
            cb.apply_locking_pragmas(conn, timeout_ms=1234)
            assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 1234
        finally:
            conn.close()

    def test_default_timeout_is_positive(self):
        # A zero/absent busy_timeout is the bug — must be a real wait window.
        assert cb.CACHE_BUSY_TIMEOUT_MS > 0

    def test_backend_connect_applies_busy_timeout(self, tmp_path):
        # The backend's own connect() must carry the discipline end-to-end.
        be = cb.SqliteCacheBackend(repo_root=tmp_path)
        with be.connect("keeper-patterns") as conn:
            assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == cb.CACHE_BUSY_TIMEOUT_MS

    def test_idempotent(self, tmp_path):
        # Safe to call more than once on the same connection.
        conn = sqlite3.connect(str(tmp_path / "t.sqlite"))
        try:
            cb.apply_locking_pragmas(conn)
            cb.apply_locking_pragmas(conn)
            assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == cb.CACHE_BUSY_TIMEOUT_MS
        finally:
            conn.close()
