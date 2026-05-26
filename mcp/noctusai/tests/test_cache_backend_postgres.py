"""Tests for PostgresCacheBackend (cache_backend_postgres.py).

All tests mock psycopg2 — no live Postgres required.

Design mirrors test_cache_backend.py structure: catalog-access tests
are already covered there; this file targets the Postgres-specific
Protocol surface, DSN resolution, vector-registration gating, and the
get_backend() factory extension.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from tools.noctus.dev import cache_backend as cb
from tools.noctus.dev.cache_backend_postgres import PostgresCacheBackend


# ── Minimal DB-API-2.0 stub ───────────────────────────────────────────────────

class _MockCursor:
    def __init__(self):
        self.executed: list[str] = []

    def execute(self, sql, params=None):
        self.executed.append(sql)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class _MockConnection:
    """Minimal psycopg2 connection stub."""

    def __init__(self):
        self.closed = False
        self.autocommit = False
        self._cursor = _MockCursor()
        self._vector_registered = False

    def cursor(self):
        return self._cursor

    def execute(self, sql, params=None):
        self._cursor.execute(sql, params)

    def commit(self):
        pass

    def close(self):
        self.closed = True

    def execute_after_close(self):
        """Simulate psycopg2 raising ProgrammingError on closed conn."""
        if self.closed:
            import psycopg2
            raise psycopg2.ProgrammingError("connection already closed")


_last_connection: _MockConnection | None = None


def _make_mock_connect():
    """Return a fresh factory that tracks the last created connection."""
    def _connect(dsn):
        global _last_connection
        _last_connection = _MockConnection()
        return _last_connection
    return _connect


# ── kind / location ───────────────────────────────────────────────────────────

class TestKindAndLocation:
    def test_kind_is_postgres(self):
        be = PostgresCacheBackend()
        assert be.kind() == "postgres"

    def test_location_is_url_shaped(self, monkeypatch):
        monkeypatch.setenv("NOCTUS_CACHE_POSTGRES_HOST", "db.example.com")
        monkeypatch.setenv("NOCTUS_CACHE_POSTGRES_PORT", "5432")
        monkeypatch.setenv("NOCTUS_CACHE_POSTGRES_DB", "noctusai")
        be = PostgresCacheBackend()
        loc = be.location("keeper-patterns")
        assert loc.startswith("postgresql://")
        assert "db.example.com" in loc
        assert "keeper_patterns" in loc

    def test_location_no_password_leak(self, monkeypatch):
        """Password MUST NOT appear in the location string."""
        monkeypatch.setenv("NOCTUS_CACHE_POSTGRES_PASSWORD", "super_secret_pw")
        be = PostgresCacheBackend()
        loc = be.location("keeper-patterns")
        assert "super_secret_pw" not in loc

    def test_location_table_name_mapping(self, monkeypatch):
        """Dashes in cache names become underscores in table names."""
        be = PostgresCacheBackend()
        assert "cache_keeper_patterns" in be.location("keeper-patterns")
        assert "cache_code_embeddings" in be.location("code-embeddings")


# ── connect context manager ───────────────────────────────────────────────────

class TestConnect:
    def test_connect_yields_connection(self, monkeypatch):
        monkeypatch.setattr("psycopg2.connect", _make_mock_connect())
        be = PostgresCacheBackend(dsn="fake-dsn")
        with be.connect("keeper-patterns") as conn:
            assert conn is not None

    def test_connect_autocommit_off(self, monkeypatch):
        monkeypatch.setattr("psycopg2.connect", _make_mock_connect())
        be = PostgresCacheBackend(dsn="fake-dsn")
        with be.connect("keeper-patterns") as conn:
            assert conn.autocommit is False

    def test_connect_closes_on_exit(self, monkeypatch):
        monkeypatch.setattr("psycopg2.connect", _make_mock_connect())
        be = PostgresCacheBackend(dsn="fake-dsn")
        with be.connect("agent-context") as conn:
            pass
        # After exit the underlying mock connection should be closed.
        assert conn.closed is True

    def test_connect_closes_on_exception(self, monkeypatch):
        """Connection is closed even when the body raises."""
        monkeypatch.setattr("psycopg2.connect", _make_mock_connect())
        be = PostgresCacheBackend(dsn="fake-dsn")
        with pytest.raises(RuntimeError):
            with be.connect("agent-context") as conn:
                raise RuntimeError("body error")
        assert conn.closed is True


# ── DSN resolution ────────────────────────────────────────────────────────────

class TestDsnResolution:
    def test_explicit_dsn_kwarg(self, monkeypatch):
        """Explicit dsn kwarg takes highest priority."""
        captured: list[str] = []

        def mock_connect(dsn):
            captured.append(dsn)
            return _MockConnection()

        monkeypatch.delenv("NOCTUS_CACHE_POSTGRES_DSN", raising=False)
        monkeypatch.setattr("psycopg2.connect", mock_connect)
        be = PostgresCacheBackend(dsn="postgresql://explicit-kwarg/db")
        with be.connect("keeper-patterns"):
            pass
        assert captured[0] == "postgresql://explicit-kwarg/db"

    def test_dsn_env_var(self, monkeypatch):
        """NOCTUS_CACHE_POSTGRES_DSN env var is used when no explicit kwarg."""
        captured: list[str] = []

        def mock_connect(dsn):
            captured.append(dsn)
            return _MockConnection()

        monkeypatch.setenv("NOCTUS_CACHE_POSTGRES_DSN", "postgresql://from-env/db")
        monkeypatch.setattr("psycopg2.connect", mock_connect)
        be = PostgresCacheBackend()  # no explicit dsn
        with be.connect("keeper-patterns"):
            pass
        assert captured[0] == "postgresql://from-env/db"

    def test_individual_env_vars(self, monkeypatch):
        """Individual *_HOST/_PORT/_DB/_USER/_PASSWORD vars build a DSN."""
        captured: list[str] = []

        def mock_connect(dsn):
            captured.append(dsn)
            return _MockConnection()

        monkeypatch.delenv("NOCTUS_CACHE_POSTGRES_DSN", raising=False)
        monkeypatch.setenv("NOCTUS_CACHE_POSTGRES_HOST", "myhost")
        monkeypatch.setenv("NOCTUS_CACHE_POSTGRES_PORT", "5433")
        monkeypatch.setenv("NOCTUS_CACHE_POSTGRES_DB", "mydb")
        monkeypatch.setenv("NOCTUS_CACHE_POSTGRES_USER", "myuser")
        monkeypatch.setenv("NOCTUS_CACHE_POSTGRES_PASSWORD", "mypw")
        monkeypatch.setattr("psycopg2.connect", mock_connect)
        be = PostgresCacheBackend()
        with be.connect("keeper-patterns"):
            pass
        dsn = captured[0]
        assert "myhost" in dsn
        assert "5433" in dsn
        assert "mydb" in dsn
        assert "myuser" in dsn
        assert "mypw" in dsn

    def test_explicit_dsn_beats_env_var(self, monkeypatch):
        """Explicit dsn kwarg takes priority over NOCTUS_CACHE_POSTGRES_DSN."""
        captured: list[str] = []

        def mock_connect(dsn):
            captured.append(dsn)
            return _MockConnection()

        monkeypatch.setenv("NOCTUS_CACHE_POSTGRES_DSN", "postgresql://env-dsn/db")
        monkeypatch.setattr("psycopg2.connect", mock_connect)
        be = PostgresCacheBackend(dsn="postgresql://kwarg-wins/db")
        with be.connect("keeper-patterns"):
            pass
        assert captured[0] == "postgresql://kwarg-wins/db"


# ── Table-name isolation ──────────────────────────────────────────────────────

class TestTableNameIsolation:
    def test_keeper_patterns_table(self):
        be = PostgresCacheBackend()
        assert be._table_name("keeper-patterns") == "noctus_cache.cache_keeper_patterns"

    def test_code_embeddings_table(self):
        be = PostgresCacheBackend()
        assert be._table_name("code-embeddings") == "noctus_cache.cache_code_embeddings"

    def test_different_caches_different_tables(self):
        be = PostgresCacheBackend()
        assert be._table_name("keeper-patterns") != be._table_name("code-embeddings")

    def test_custom_schema(self):
        be = PostgresCacheBackend(schema="custom_schema")
        assert be._table_name("agent-context") == "custom_schema.cache_agent_context"


# ── Protocol conformance ──────────────────────────────────────────────────────

class TestProtocol:
    def test_isinstance_cache_backend_protocol(self):
        """runtime_checkable Protocol check — PostgresCacheBackend satisfies."""
        be = PostgresCacheBackend()
        assert isinstance(be, cb.CacheBackend)


# ── _ensure_schema DDL ────────────────────────────────────────────────────────

class TestEnsureSchema:
    def test_ensure_schema_issues_create_schema(self, monkeypatch):
        """_ensure_schema() executes CREATE SCHEMA + CREATE EXTENSION."""
        mock_conn = _MockConnection()
        monkeypatch.setattr("psycopg2.connect", lambda dsn: mock_conn)
        be = PostgresCacheBackend(dsn="fake-dsn")
        be._ensure_schema()
        executed_sql = " ".join(mock_conn._cursor.executed)
        assert "CREATE SCHEMA" in executed_sql
        assert "vector" in executed_sql


# ── Vector-registration gating ────────────────────────────────────────────────

class TestVectorRegistration:
    def test_vector_not_registered_for_row_cache(self, monkeypatch):
        """register_vector is NOT called for methodology caches."""
        registered: list[str] = []

        class _FakePgvectorModule:
            class psycopg2:
                @staticmethod
                def register_vector(conn):
                    registered.append("registered")

        monkeypatch.setattr("psycopg2.connect", _make_mock_connect())
        monkeypatch.setitem(sys.modules, "pgvector", _FakePgvectorModule())
        monkeypatch.setitem(sys.modules, "pgvector.psycopg2", _FakePgvectorModule.psycopg2)
        be = PostgresCacheBackend(dsn="fake-dsn")
        with be.connect("keeper-patterns"):
            pass
        assert registered == [], "register_vector should NOT fire for keeper-patterns"

    def test_vector_registered_for_embedding_cache(self, monkeypatch):
        """register_vector IS called for kb-embeddings and code-embeddings."""
        registered: list[str] = []

        class _FakePgvectorPsycopg2:
            @staticmethod
            def register_vector(conn):
                registered.append("registered")

        class _FakePgvectorModule:
            psycopg2 = _FakePgvectorPsycopg2

        monkeypatch.setattr("psycopg2.connect", _make_mock_connect())
        monkeypatch.setitem(sys.modules, "pgvector", _FakePgvectorModule())
        monkeypatch.setitem(sys.modules, "pgvector.psycopg2", _FakePgvectorPsycopg2())
        be = PostgresCacheBackend(dsn="fake-dsn")
        with be.connect("kb-embeddings"):
            pass
        assert "registered" in registered, "register_vector should fire for kb-embeddings"


# ── Factory extension ─────────────────────────────────────────────────────────

class TestFactory:
    def test_get_backend_postgres_env(self, monkeypatch):
        """NOCTUS_CACHE_BACKEND=postgres returns a PostgresCacheBackend."""
        monkeypatch.setenv(cb._ENV_VAR, "postgres")
        be = cb.get_backend()
        assert isinstance(be, PostgresCacheBackend)
        assert be.kind() == "postgres"

    def test_get_backend_postgres_case_insensitive(self, monkeypatch):
        monkeypatch.setenv(cb._ENV_VAR, "POSTGRES")
        be = cb.get_backend()
        assert isinstance(be, PostgresCacheBackend)
