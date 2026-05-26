"""Tests for cache_deploy_mirror.py — focus on `_mirror_chunks_with_json_embedding`.

The helper does the load-bearing work of mirroring local SQLite vector caches
(`kb_chunks` + `kb_embeddings_json` sibling pair, similarly for code) into the
prod pgvector tables. End-to-end smoke against a real prod cache is the
strongest validation, but unit tests here catch schema-shape drift (JOIN
column rename, embedding splice position, JSON parse failure handling) before
they touch prod.

Mock the psycopg2 connection — no live Postgres required.
"""
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from tools.noctus.dev.cache_deploy_mirror import (
    _mirror_chunks_with_json_embedding,
    _mirror_keeper_patterns,
    _mirror_simple_table,
)


# ── Minimal psycopg2 connection stub ──────────────────────────────────────────


class _MockCursor:
    def __init__(self):
        self.executed: list[tuple[str, object]] = []
        self.executemany_calls: list[tuple[str, list]] = []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def executemany(self, sql, rows):
        # Materialize rows so iterators don't lose their content for assertions.
        self.executemany_calls.append((sql, list(rows)))

    def close(self):
        pass


class _MockConnection:
    def __init__(self):
        self.cursor_obj = _MockCursor()

    def cursor(self):
        return self.cursor_obj


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def kb_local_db():
    """In-memory SQLite seeded with the kb_chunks + kb_embeddings_json shape
    that lives in the real local `.claude/cache/kb-embeddings.sqlite`."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE kb_chunks (
            rowid_alias INTEGER PRIMARY KEY,
            kb_path TEXT NOT NULL,
            chunk_text TEXT NOT NULL,
            cached_at TEXT NOT NULL
        );
        CREATE TABLE kb_embeddings_json (
            chunk_rowid INTEGER PRIMARY KEY,
            embedding TEXT NOT NULL
        );
        """
    )
    return conn


@pytest.fixture
def code_local_db():
    """In-memory SQLite for code_chunks — same shape as kb but with an extra
    symbol_name column to exercise the column_renames branch (the real code
    cache renames `symbol_name` → `symbol` on the way to pgvector)."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE code_chunks (
            rowid_alias INTEGER PRIMARY KEY,
            file_path TEXT NOT NULL,
            symbol_name TEXT NOT NULL,
            chunk_text TEXT NOT NULL,
            cached_at TEXT NOT NULL
        );
        CREATE TABLE code_embeddings_json (
            chunk_rowid INTEGER PRIMARY KEY,
            embedding TEXT NOT NULL
        );
        """
    )
    return conn


# ── _mirror_chunks_with_json_embedding ────────────────────────────────────────


class TestMirrorChunksWithJsonEmbedding:
    def test_truncates_target_pg_table(self, kb_local_db):
        pg = _MockConnection()
        _mirror_chunks_with_json_embedding(
            kb_local_db,
            pg,
            chunks_table="kb_chunks",
            embeddings_json_table="kb_embeddings_json",
            pg_table="cache_kb_embeddings",
            chunk_columns_local=["kb_path", "chunk_text", "cached_at"],
            pg_insert_cols=["kb_path", "chunk_text", "embedding", "cached_at"],
            embedding_pg_col_idx=2,
        )
        # Empty source → executemany never called, but TRUNCATE always runs.
        truncate_sqls = [sql for sql, _ in pg.cursor_obj.executed if "TRUNCATE" in sql]
        assert len(truncate_sqls) == 1
        assert "cache_kb_embeddings" in truncate_sqls[0]

    def test_returns_zero_when_source_empty(self, kb_local_db):
        pg = _MockConnection()
        rows_written = _mirror_chunks_with_json_embedding(
            kb_local_db,
            pg,
            chunks_table="kb_chunks",
            embeddings_json_table="kb_embeddings_json",
            pg_table="cache_kb_embeddings",
            chunk_columns_local=["kb_path", "chunk_text", "cached_at"],
            pg_insert_cols=["kb_path", "chunk_text", "embedding", "cached_at"],
            embedding_pg_col_idx=2,
        )
        assert rows_written == 0
        assert pg.cursor_obj.executemany_calls == []

    def test_join_links_chunks_to_embeddings(self, kb_local_db):
        kb_local_db.execute(
            "INSERT INTO kb_chunks (rowid_alias, kb_path, chunk_text, cached_at) "
            "VALUES (1, 'KB/X.md', 'hello', '2026-01-01T00:00:00+00:00')"
        )
        kb_local_db.execute(
            "INSERT INTO kb_embeddings_json (chunk_rowid, embedding) "
            "VALUES (1, ?)",
            (json.dumps([0.1, 0.2, 0.3]),),
        )
        pg = _MockConnection()
        rows_written = _mirror_chunks_with_json_embedding(
            kb_local_db,
            pg,
            chunks_table="kb_chunks",
            embeddings_json_table="kb_embeddings_json",
            pg_table="cache_kb_embeddings",
            chunk_columns_local=["kb_path", "chunk_text", "cached_at"],
            pg_insert_cols=["kb_path", "chunk_text", "embedding", "cached_at"],
            embedding_pg_col_idx=2,
        )
        assert rows_written == 1
        assert len(pg.cursor_obj.executemany_calls) == 1
        sql, rows = pg.cursor_obj.executemany_calls[0]
        assert "INSERT INTO noctus_cache.cache_kb_embeddings" in sql
        # Column order must match pg_insert_cols exactly.
        assert "(kb_path, chunk_text, embedding, cached_at)" in sql
        # The single row's embedding was spliced at index 2.
        (kb_path, chunk_text, embedding, cached_at) = rows[0]
        assert kb_path == "KB/X.md"
        assert chunk_text == "hello"
        assert embedding == [0.1, 0.2, 0.3]
        assert cached_at == "2026-01-01T00:00:00+00:00"

    def test_chunk_without_embedding_is_skipped(self, kb_local_db):
        # Chunk row exists but its sibling embeddings row does NOT — JOIN
        # filters it out (INNER JOIN semantics).
        kb_local_db.execute(
            "INSERT INTO kb_chunks (rowid_alias, kb_path, chunk_text, cached_at) "
            "VALUES (1, 'KB/orphan.md', 'no-embed', '2026-01-01T00:00:00+00:00')"
        )
        pg = _MockConnection()
        rows_written = _mirror_chunks_with_json_embedding(
            kb_local_db,
            pg,
            chunks_table="kb_chunks",
            embeddings_json_table="kb_embeddings_json",
            pg_table="cache_kb_embeddings",
            chunk_columns_local=["kb_path", "chunk_text", "cached_at"],
            pg_insert_cols=["kb_path", "chunk_text", "embedding", "cached_at"],
            embedding_pg_col_idx=2,
        )
        assert rows_written == 0
        assert pg.cursor_obj.executemany_calls == []

    def test_malformed_json_embedding_becomes_none(self, kb_local_db):
        kb_local_db.execute(
            "INSERT INTO kb_chunks (rowid_alias, kb_path, chunk_text, cached_at) "
            "VALUES (1, 'KB/bad.md', 'corrupted', '2026-01-01T00:00:00+00:00')"
        )
        kb_local_db.execute(
            "INSERT INTO kb_embeddings_json (chunk_rowid, embedding) "
            "VALUES (1, 'not-valid-json')"
        )
        pg = _MockConnection()
        rows_written = _mirror_chunks_with_json_embedding(
            kb_local_db,
            pg,
            chunks_table="kb_chunks",
            embeddings_json_table="kb_embeddings_json",
            pg_table="cache_kb_embeddings",
            chunk_columns_local=["kb_path", "chunk_text", "cached_at"],
            pg_insert_cols=["kb_path", "chunk_text", "embedding", "cached_at"],
            embedding_pg_col_idx=2,
        )
        assert rows_written == 1
        (_sql, rows) = pg.cursor_obj.executemany_calls[0]
        (_kb_path, _chunk_text, embedding, _cached_at) = rows[0]
        # Malformed JSON → embedding = None (lets PG decide what NULL means;
        # the JOIN already filtered missing-sibling rows).
        assert embedding is None

    def test_empty_string_embedding_becomes_none(self, kb_local_db):
        # `if embedding_json` short-circuits on empty string — exercise that
        # branch explicitly (it's the silent-error shape we want NULL on).
        kb_local_db.execute(
            "INSERT INTO kb_chunks (rowid_alias, kb_path, chunk_text, cached_at) "
            "VALUES (1, 'KB/empty.md', 'no-embed', '2026-01-01T00:00:00+00:00')"
        )
        kb_local_db.execute(
            "INSERT INTO kb_embeddings_json (chunk_rowid, embedding) VALUES (1, '')"
        )
        pg = _MockConnection()
        rows_written = _mirror_chunks_with_json_embedding(
            kb_local_db,
            pg,
            chunks_table="kb_chunks",
            embeddings_json_table="kb_embeddings_json",
            pg_table="cache_kb_embeddings",
            chunk_columns_local=["kb_path", "chunk_text", "cached_at"],
            pg_insert_cols=["kb_path", "chunk_text", "embedding", "cached_at"],
            embedding_pg_col_idx=2,
        )
        assert rows_written == 1
        (_sql, rows) = pg.cursor_obj.executemany_calls[0]
        assert rows[0][2] is None

    def test_column_renames_honored(self, code_local_db):
        # The real code-embeddings mirror renames `symbol_name` → `symbol` —
        # SELECT emits `c.symbol_name AS symbol`, the insert column list uses
        # `symbol`. Without column_renames, the row_dict lookup would KeyError.
        code_local_db.execute(
            "INSERT INTO code_chunks "
            "(rowid_alias, file_path, symbol_name, chunk_text, cached_at) "
            "VALUES (1, 'app/main.py', 'main', 'def main():', '2026-01-01T00:00:00+00:00')"
        )
        code_local_db.execute(
            "INSERT INTO code_embeddings_json (chunk_rowid, embedding) VALUES (1, ?)",
            (json.dumps([1.0, 2.0]),),
        )
        pg = _MockConnection()
        rows_written = _mirror_chunks_with_json_embedding(
            code_local_db,
            pg,
            chunks_table="code_chunks",
            embeddings_json_table="code_embeddings_json",
            pg_table="cache_code_embeddings",
            chunk_columns_local=["file_path", "symbol_name", "chunk_text", "cached_at"],
            pg_insert_cols=["file_path", "symbol", "chunk_text", "embedding", "cached_at"],
            embedding_pg_col_idx=3,
            column_renames={"symbol_name": "symbol"},
        )
        assert rows_written == 1
        (sql, rows) = pg.cursor_obj.executemany_calls[0]
        # The INSERT spells the PG column name `symbol`, not `symbol_name`.
        assert "symbol" in sql and "symbol_name" not in sql
        (file_path, symbol, chunk_text, embedding, cached_at) = rows[0]
        assert file_path == "app/main.py"
        assert symbol == "main"
        assert chunk_text == "def main():"
        assert embedding == [1.0, 2.0]
        assert cached_at == "2026-01-01T00:00:00+00:00"

    def test_embedding_spliced_at_correct_index(self, kb_local_db):
        # Move the embedding column to the front of pg_insert_cols and verify
        # the splice still lands it at index 0 (not at a hard-coded position).
        kb_local_db.execute(
            "INSERT INTO kb_chunks (rowid_alias, kb_path, chunk_text, cached_at) "
            "VALUES (1, 'KB/front.md', 'lead-with-embed', '2026-01-01T00:00:00+00:00')"
        )
        kb_local_db.execute(
            "INSERT INTO kb_embeddings_json (chunk_rowid, embedding) VALUES (1, ?)",
            (json.dumps([9.9, 8.8]),),
        )
        pg = _MockConnection()
        _mirror_chunks_with_json_embedding(
            kb_local_db,
            pg,
            chunks_table="kb_chunks",
            embeddings_json_table="kb_embeddings_json",
            pg_table="cache_kb_embeddings",
            chunk_columns_local=["kb_path", "chunk_text", "cached_at"],
            pg_insert_cols=["embedding", "kb_path", "chunk_text", "cached_at"],
            embedding_pg_col_idx=0,
        )
        (_sql, rows) = pg.cursor_obj.executemany_calls[0]
        (embedding, kb_path, chunk_text, cached_at) = rows[0]
        assert embedding == [9.9, 8.8]
        assert kb_path == "KB/front.md"

    def test_multiple_rows_preserve_join_order(self, kb_local_db):
        for i in range(1, 4):
            kb_local_db.execute(
                "INSERT INTO kb_chunks (rowid_alias, kb_path, chunk_text, cached_at) "
                "VALUES (?, ?, ?, '2026-01-01T00:00:00+00:00')",
                (i, f"KB/{i}.md", f"text-{i}"),
            )
            kb_local_db.execute(
                "INSERT INTO kb_embeddings_json (chunk_rowid, embedding) VALUES (?, ?)",
                (i, json.dumps([float(i)] * 4)),
            )
        pg = _MockConnection()
        rows_written = _mirror_chunks_with_json_embedding(
            kb_local_db,
            pg,
            chunks_table="kb_chunks",
            embeddings_json_table="kb_embeddings_json",
            pg_table="cache_kb_embeddings",
            chunk_columns_local=["kb_path", "chunk_text", "cached_at"],
            pg_insert_cols=["kb_path", "chunk_text", "embedding", "cached_at"],
            embedding_pg_col_idx=2,
        )
        assert rows_written == 3
        (_sql, rows) = pg.cursor_obj.executemany_calls[0]
        assert [r[0] for r in rows] == ["KB/1.md", "KB/2.md", "KB/3.md"]
        assert [r[2] for r in rows] == [[1.0]*4, [2.0]*4, [3.0]*4]


# ── Sanity tests for the simpler siblings (lock down their contract too) ─────


class TestMirrorKeeperPatterns:
    def test_empty_source_returns_zero(self):
        local = sqlite3.connect(":memory:")
        local.executescript(
            """
            CREATE TABLE keeper_patterns (
                keeper_name TEXT, pattern_kind TEXT, pattern_value TEXT,
                severity TEXT, remediation TEXT, source_file TEXT,
                source_line INTEGER, fixture_example TEXT, scope TEXT,
                cached_at TEXT
            );
            """
        )
        pg = _MockConnection()
        assert _mirror_keeper_patterns(local, pg) == 0

    def test_truncates_then_inserts(self):
        local = sqlite3.connect(":memory:")
        local.executescript(
            """
            CREATE TABLE keeper_patterns (
                keeper_name TEXT, pattern_kind TEXT, pattern_value TEXT,
                severity TEXT, remediation TEXT, source_file TEXT,
                source_line INTEGER, fixture_example TEXT, scope TEXT,
                cached_at TEXT
            );
            INSERT INTO keeper_patterns VALUES (
                'check_x', 'symbol', 'foo', 'high', 'fix it',
                'compliance.py', 42, 'example()', 'noctusai', '2026-01-01'
            );
            """
        )
        pg = _MockConnection()
        rows_written = _mirror_keeper_patterns(local, pg)
        assert rows_written == 1
        truncates = [sql for sql, _ in pg.cursor_obj.executed if "TRUNCATE" in sql]
        assert len(truncates) == 1


class TestMirrorSimpleTable:
    def test_empty_source_returns_zero(self):
        local = sqlite3.connect(":memory:")
        local.executescript("CREATE TABLE t (a TEXT, b TEXT);")
        pg = _MockConnection()
        assert _mirror_simple_table(local, pg, "t", "cache_t", ["a", "b"]) == 0

    def test_round_trips_rows(self):
        local = sqlite3.connect(":memory:")
        local.executescript(
            """
            CREATE TABLE t (a TEXT, b TEXT);
            INSERT INTO t VALUES ('x', 'y');
            INSERT INTO t VALUES ('p', 'q');
            """
        )
        pg = _MockConnection()
        rows_written = _mirror_simple_table(local, pg, "t", "cache_t", ["a", "b"])
        assert rows_written == 2
        (sql, rows) = pg.cursor_obj.executemany_calls[0]
        assert "cache_t" in sql and "a, b" in sql
        assert sorted(rows) == [("p", "q"), ("x", "y")]
