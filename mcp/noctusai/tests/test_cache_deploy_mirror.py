"""Tests for cache_deploy_mirror.py — focus on `_mirror_chunks_with_embedding`
and the no-silent-shortfall gate in `mirror_one_cache`.

2026-08-14 cache-mirror-join-drift fix: a chunk's embedding lives in EXACTLY
ONE of two sibling tables (`*_vec` sqlite-vec / `*_embeddings_json` fallback)
depending on which environment last wrote it. The prior implementation read
ONLY the json sibling via an INNER JOIN, silently dropping every chunk whose
embedding lived in `*_vec` while still reporting `ok: true`. These tests lock
down: (a) both sibling tables are read, (b) a chunk missing from BOTH is
reported — never silently dropped, never shipped as NULL — and (c)
`mirror_one_cache` REFUSES (rolls back, `ok=False`) rather than reporting
success on any rows_written != source_total shortfall.

`*_vec` tables here are PLAIN tables shaped `(rowid, embedding BLOB)` — not a
real vec0 virtual table. `_mirror_chunks_with_embedding` never uses a vec0-
specific SQL feature (no `MATCH`, no `k = ?`) against this table, only a
vanilla `SELECT rowid, embedding`, so a plain table is a faithful stand-in
and keeps these tests independent of whether `sqlite-vec` is installed.

Mock the psycopg2 connection — no live Postgres required.
"""
import json
import sqlite3
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from tools.noctus.dev.cache_deploy_mirror import (
    _mirror_chunks_with_embedding,
    _mirror_keeper_patterns,
    _mirror_simple_table,
    mirror_one_cache,
)


def _pack(vec: list[float]) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


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
        self.committed = False
        self.rolled_back = False

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def kb_local_db():
    """In-memory SQLite seeded with the kb_chunks + BOTH sibling embedding
    tables — the real shape of the local `kb-embeddings.sqlite`."""
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
        CREATE TABLE kb_vec (
            rowid INTEGER PRIMARY KEY,
            embedding BLOB
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
    symbol_name column (renamed to `symbol` on the way to pgvector)."""
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
        CREATE TABLE code_vec (
            rowid INTEGER PRIMARY KEY,
            embedding BLOB
        );
        CREATE TABLE code_embeddings_json (
            chunk_rowid INTEGER PRIMARY KEY,
            embedding TEXT NOT NULL
        );
        """
    )
    return conn


def _mirror_kb(db, **overrides):
    kwargs = dict(
        chunks_table="kb_chunks",
        vec_table="kb_vec",
        embeddings_json_table="kb_embeddings_json",
        pg_table="cache_kb_embeddings",
        chunk_columns_local=["kb_path", "chunk_text", "cached_at"],
        pg_insert_cols=["kb_path", "chunk_text", "embedding", "cached_at"],
        embedding_pg_col_idx=2,
    )
    kwargs.update(overrides)
    pg = _MockConnection()
    result = _mirror_chunks_with_embedding(db, pg, **kwargs)
    return result, pg


# ── _mirror_chunks_with_embedding ──────────────────────────────────────────────


class TestMirrorChunksWithEmbedding:
    def test_truncates_target_pg_table(self, kb_local_db):
        _, pg = _mirror_kb(kb_local_db)
        truncate_sqls = [sql for sql, _ in pg.cursor_obj.executed if "TRUNCATE" in sql]
        assert len(truncate_sqls) == 1
        assert "cache_kb_embeddings" in truncate_sqls[0]

    def test_returns_zero_when_source_empty(self, kb_local_db):
        result, pg = _mirror_kb(kb_local_db)
        assert result == {
            "rows_written": 0, "chunks_total": 0,
            "missing_embedding_count": 0, "missing_embedding_sample": [],
        }
        assert pg.cursor_obj.executemany_calls == []

    def test_reads_embedding_from_vec_table(self, kb_local_db):
        kb_local_db.execute(
            "INSERT INTO kb_chunks (rowid_alias, kb_path, chunk_text, cached_at) "
            "VALUES (1, 'KB/X.md', 'hello', '2026-01-01T00:00:00+00:00')"
        )
        kb_local_db.execute(
            "INSERT INTO kb_vec (rowid, embedding) VALUES (1, ?)",
            (_pack([0.1, 0.2, 0.3]),),
        )
        result, pg = _mirror_kb(kb_local_db)
        assert result["rows_written"] == 1
        assert result["missing_embedding_count"] == 0
        (_sql, rows) = pg.cursor_obj.executemany_calls[0]
        (kb_path, chunk_text, embedding, cached_at) = rows[0]
        assert kb_path == "KB/X.md"
        assert embedding == pytest.approx([0.1, 0.2, 0.3], abs=1e-6)

    def test_reads_embedding_from_json_table(self, kb_local_db):
        kb_local_db.execute(
            "INSERT INTO kb_chunks (rowid_alias, kb_path, chunk_text, cached_at) "
            "VALUES (1, 'KB/X.md', 'hello', '2026-01-01T00:00:00+00:00')"
        )
        kb_local_db.execute(
            "INSERT INTO kb_embeddings_json (chunk_rowid, embedding) VALUES (1, ?)",
            (json.dumps([0.4, 0.5, 0.6]),),
        )
        result, pg = _mirror_kb(kb_local_db)
        assert result["rows_written"] == 1
        (_sql, rows) = pg.cursor_obj.executemany_calls[0]
        assert rows[0][2] == [0.4, 0.5, 0.6]

    def test_split_corpus_both_tables_contribute(self, kb_local_db):
        # The real-world drift shape: chunk 1's embedding lives ONLY in
        # kb_vec, chunk 2's ONLY in kb_embeddings_json. The pre-fix
        # INNER-JOIN-on-json-only implementation would have shipped ONLY
        # chunk 2 while reporting success — this proves BOTH are shipped.
        kb_local_db.executemany(
            "INSERT INTO kb_chunks (rowid_alias, kb_path, chunk_text, cached_at) VALUES (?,?,?,?)",
            [
                (1, "KB/vec-only.md", "vec-body", "2026-01-01T00:00:00+00:00"),
                (2, "KB/json-only.md", "json-body", "2026-01-01T00:00:00+00:00"),
            ],
        )
        kb_local_db.execute(
            "INSERT INTO kb_vec (rowid, embedding) VALUES (1, ?)", (_pack([9.0] * 4),)
        )
        kb_local_db.execute(
            "INSERT INTO kb_embeddings_json (chunk_rowid, embedding) VALUES (2, ?)",
            (json.dumps([8.0] * 4),),
        )
        result, pg = _mirror_kb(kb_local_db)
        assert result["rows_written"] == 2
        assert result["chunks_total"] == 2
        assert result["missing_embedding_count"] == 0
        (_sql, rows) = pg.cursor_obj.executemany_calls[0]
        paths_shipped = {r[0] for r in rows}
        assert paths_shipped == {"KB/vec-only.md", "KB/json-only.md"}

    def test_chunk_missing_from_both_tables_is_reported_not_dropped(self):
        # THE regression case: a chunk with NO embedding in EITHER sibling
        # table (orphan on both sides — the measured 2026-08-14 shape).
        # Must be counted in `missing_embedding_count` / `missing_embedding_sample`,
        # never silently absent from the return value. Uses the literal
        # `path` column name (the real cache's convention — the
        # `missing_embedding_sample`'s `path` field is only populated when
        # `chunk_columns_local` contains a column literally named `path`;
        # the `kb_local_db` fixture uses `kb_path` to independently prove
        # column-naming genericity elsewhere in this class).
        db = sqlite3.connect(":memory:")
        db.row_factory = sqlite3.Row
        db.executescript(
            """
            CREATE TABLE kb_chunks (
                rowid_alias INTEGER PRIMARY KEY, path TEXT NOT NULL,
                chunk_text TEXT NOT NULL, cached_at TEXT NOT NULL
            );
            CREATE TABLE kb_vec (rowid INTEGER PRIMARY KEY, embedding BLOB);
            CREATE TABLE kb_embeddings_json (
                chunk_rowid INTEGER PRIMARY KEY, embedding TEXT NOT NULL
            );
            """
        )
        db.execute(
            "INSERT INTO kb_chunks (rowid_alias, path, chunk_text, cached_at) "
            "VALUES (1, 'KB/orphan.md', 'no-embed-anywhere', '2026-01-01T00:00:00+00:00')"
        )
        pg = _MockConnection()
        result = _mirror_chunks_with_embedding(
            db, pg,
            chunks_table="kb_chunks",
            vec_table="kb_vec",
            embeddings_json_table="kb_embeddings_json",
            pg_table="cache_kb_embeddings",
            chunk_columns_local=["path", "chunk_text", "cached_at"],
            pg_insert_cols=["path", "chunk_text", "embedding", "cached_at"],
            embedding_pg_col_idx=2,
        )
        assert result["rows_written"] == 0
        assert result["chunks_total"] == 1
        assert result["missing_embedding_count"] == 1
        assert result["missing_embedding_sample"] == [
            {"rowid_alias": 1, "path": "KB/orphan.md"}
        ]
        assert pg.cursor_obj.executemany_calls == []

    def test_vec_preferred_over_json_when_both_present(self, kb_local_db):
        kb_local_db.execute(
            "INSERT INTO kb_chunks (rowid_alias, kb_path, chunk_text, cached_at) "
            "VALUES (1, 'KB/both.md', 'dual', '2026-01-01T00:00:00+00:00')"
        )
        kb_local_db.execute(
            "INSERT INTO kb_vec (rowid, embedding) VALUES (1, ?)", (_pack([1.0] * 4),)
        )
        kb_local_db.execute(
            "INSERT INTO kb_embeddings_json (chunk_rowid, embedding) VALUES (1, ?)",
            (json.dumps([2.0] * 4),),
        )
        result, pg = _mirror_kb(kb_local_db)
        (_sql, rows) = pg.cursor_obj.executemany_calls[0]
        assert rows[0][2] == pytest.approx([1.0] * 4, abs=1e-6)

    def test_missing_json_table_degrades_gracefully(self, kb_local_db):
        # A cache that has ONLY ever been refreshed under sqlite-vec never
        # gets a json_table created pre-fix — the read must not crash.
        kb_local_db.execute("DROP TABLE kb_embeddings_json")
        kb_local_db.execute(
            "INSERT INTO kb_chunks (rowid_alias, kb_path, chunk_text, cached_at) "
            "VALUES (1, 'KB/vec-only.md', 'body', '2026-01-01T00:00:00+00:00')"
        )
        kb_local_db.execute(
            "INSERT INTO kb_vec (rowid, embedding) VALUES (1, ?)", (_pack([1.0] * 2),)
        )
        result, pg = _mirror_kb(kb_local_db)
        assert result["rows_written"] == 1
        assert result["missing_embedding_count"] == 0

    def test_column_position_honored_with_rename_target(self, code_local_db):
        # The real code-embeddings mirror renames `symbol_name` -> `symbol`
        # in pg_insert_cols only — the local SELECT always uses the real
        # local column name; positional order does the rest (no SQL `AS`).
        code_local_db.execute(
            "INSERT INTO code_chunks "
            "(rowid_alias, file_path, symbol_name, chunk_text, cached_at) "
            "VALUES (1, 'app/main.py', 'main', 'def main():', '2026-01-01T00:00:00+00:00')"
        )
        code_local_db.execute(
            "INSERT INTO code_vec (rowid, embedding) VALUES (1, ?)", (_pack([1.0, 2.0]),)
        )
        pg = _MockConnection()
        result = _mirror_chunks_with_embedding(
            code_local_db, pg,
            chunks_table="code_chunks",
            vec_table="code_vec",
            embeddings_json_table="code_embeddings_json",
            pg_table="cache_code_embeddings",
            chunk_columns_local=["file_path", "symbol_name", "chunk_text", "cached_at"],
            pg_insert_cols=["file_path", "symbol", "chunk_text", "embedding", "cached_at"],
            embedding_pg_col_idx=3,
        )
        assert result["rows_written"] == 1
        (sql, rows) = pg.cursor_obj.executemany_calls[0]
        assert "symbol" in sql and "symbol_name" not in sql
        (file_path, symbol, chunk_text, embedding, cached_at) = rows[0]
        assert file_path == "app/main.py"
        assert symbol == "main"
        assert embedding == pytest.approx([1.0, 2.0], abs=1e-6)

    def test_multiple_rows_preserve_order(self, kb_local_db):
        for i in range(1, 4):
            kb_local_db.execute(
                "INSERT INTO kb_chunks (rowid_alias, kb_path, chunk_text, cached_at) "
                "VALUES (?, ?, ?, '2026-01-01T00:00:00+00:00')",
                (i, f"KB/{i}.md", f"text-{i}"),
            )
            kb_local_db.execute(
                "INSERT INTO kb_vec (rowid, embedding) VALUES (?, ?)",
                (i, _pack([float(i)] * 4)),
            )
        result, pg = _mirror_kb(kb_local_db)
        assert result["rows_written"] == 3
        (_sql, rows) = pg.cursor_obj.executemany_calls[0]
        assert [r[0] for r in rows] == ["KB/1.md", "KB/2.md", "KB/3.md"]


# ── mirror_one_cache — the no-silent-shortfall gate ────────────────────────────


class TestMirrorOneCacheRefusesShortfall:
    """This is THE regression proof the brief asked for: construct a
    chunks/embeddings pair with a deliberate key mismatch (one chunk has NO
    embedding in either sibling table) and assert `mirror_one_cache` reports
    the shortfall (`ok=False`, rolled back) rather than `ok: True`.

    Against the PRE-FIX code this assertion FAILS — the old
    `_mirror_chunks_with_json_embedding` INNER JOIN just silently drops the
    orphan chunk row and `mirror_one_cache` returns `ok: True` unconditionally
    whenever no exception was raised. See PR description for the before/after
    proof (`git stash` the fix, re-run this test, restore).
    """

    def _seed_kb_cache_with_orphan(self, db_path: Path) -> None:
        conn = sqlite3.connect(str(db_path))
        conn.executescript(
            """
            CREATE TABLE kb_chunks (
                rowid_alias INTEGER PRIMARY KEY, path TEXT NOT NULL,
                chunk_idx INTEGER NOT NULL, chunk_text TEXT NOT NULL,
                source_sha TEXT NOT NULL, cached_at TEXT NOT NULL
            );
            CREATE TABLE kb_vec (rowid INTEGER PRIMARY KEY, embedding BLOB);
            CREATE TABLE kb_embeddings_json (
                chunk_rowid INTEGER PRIMARY KEY, embedding TEXT NOT NULL
            );
            """
        )
        conn.execute(
            "INSERT INTO kb_chunks VALUES (1, 'KB/has-embed.md', 0, 'a', 'sha-a', '2026-01-01')"
        )
        conn.execute(
            "INSERT INTO kb_chunks VALUES (2, 'KB/orphan.md', 0, 'b', 'sha-b', '2026-01-01')"
        )
        # Only chunk 1 has an embedding. Chunk 2 is the join-drift orphan —
        # its embedding was stranded in a sibling table generation that no
        # longer matches this rowid (or was never written).
        conn.execute(
            "INSERT INTO kb_embeddings_json VALUES (1, ?)", (json.dumps([0.1] * 4),)
        )
        conn.commit()
        conn.close()

    def test_shortfall_refused_not_reported_as_success(self, tmp_path, monkeypatch):
        db_path = tmp_path / "kb-embeddings.sqlite"
        self._seed_kb_cache_with_orphan(db_path)

        pg_conn = _MockConnection()

        class _FakeConnCtx:
            def __enter__(self):
                return pg_conn

            def __exit__(self, *a):
                return False

        class _FakeBackend:
            def __init__(self, *a, **kw):
                pass

            def connect(self, cache_name):
                return _FakeConnCtx()

            def location(self, cache_name):
                return f"fake://{cache_name}"

        monkeypatch.setattr(
            "tools.noctus.dev.cache_backend_postgres.PostgresCacheBackend",
            _FakeBackend,
        )
        monkeypatch.setattr(
            "tools.noctus.dev.cache_deploy_mirror.cache_path",
            lambda name, repo_root=None: db_path,
        )

        result = mirror_one_cache("kb-embeddings")

        # THE assertion: never ok=True on a shortfall.
        assert result["ok"] is False
        assert "mirror-row-count-mismatch" in result["error"]
        assert result["rows_written"] == 1
        assert result["source_total"] == 2
        # Atomic-per-cache contract: refused, not partially committed.
        assert pg_conn.rolled_back is True
        assert pg_conn.committed is False

    def test_full_coverage_across_both_engines_still_ships(self, tmp_path, monkeypatch):
        """Sibling positive case: every chunk HAS an embedding (split across
        vec/json), so rows_written == source_total and the mirror ships."""
        db_path = tmp_path / "kb-embeddings.sqlite"
        conn = sqlite3.connect(str(db_path))
        conn.executescript(
            """
            CREATE TABLE kb_chunks (
                rowid_alias INTEGER PRIMARY KEY, path TEXT NOT NULL,
                chunk_idx INTEGER NOT NULL, chunk_text TEXT NOT NULL,
                source_sha TEXT NOT NULL, cached_at TEXT NOT NULL
            );
            CREATE TABLE kb_vec (rowid INTEGER PRIMARY KEY, embedding BLOB);
            CREATE TABLE kb_embeddings_json (
                chunk_rowid INTEGER PRIMARY KEY, embedding TEXT NOT NULL
            );
            """
        )
        conn.execute(
            "INSERT INTO kb_chunks VALUES (1, 'KB/a.md', 0, 'a', 'sha-a', '2026-01-01')"
        )
        conn.execute(
            "INSERT INTO kb_chunks VALUES (2, 'KB/b.md', 0, 'b', 'sha-b', '2026-01-01')"
        )
        conn.execute("INSERT INTO kb_vec VALUES (1, ?)", (_pack([1.0] * 4),))
        conn.execute(
            "INSERT INTO kb_embeddings_json VALUES (2, ?)", (json.dumps([2.0] * 4),)
        )
        conn.commit()
        conn.close()

        pg_conn = _MockConnection()

        class _FakeConnCtx:
            def __enter__(self):
                return pg_conn

            def __exit__(self, *a):
                return False

        class _FakeBackend:
            def __init__(self, *a, **kw):
                pass

            def connect(self, cache_name):
                return _FakeConnCtx()

            def location(self, cache_name):
                return f"fake://{cache_name}"

        monkeypatch.setattr(
            "tools.noctus.dev.cache_backend_postgres.PostgresCacheBackend",
            _FakeBackend,
        )
        monkeypatch.setattr(
            "tools.noctus.dev.cache_deploy_mirror.cache_path",
            lambda name, repo_root=None: db_path,
        )

        result = mirror_one_cache("kb-embeddings")

        assert result["ok"] is True
        assert result["rows_written"] == 2
        assert result["source_total"] == 2
        assert pg_conn.committed is True
        assert pg_conn.rolled_back is False


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
        assert _mirror_keeper_patterns(local, pg) == {"rows_written": 0, "source_total": 0}

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
        result = _mirror_keeper_patterns(local, pg)
        assert result == {"rows_written": 1, "source_total": 1}
        truncates = [sql for sql, _ in pg.cursor_obj.executed if "TRUNCATE" in sql]
        assert len(truncates) == 1


class TestMirrorSimpleTable:
    def test_empty_source_returns_zero(self):
        local = sqlite3.connect(":memory:")
        local.executescript("CREATE TABLE t (a TEXT, b TEXT);")
        pg = _MockConnection()
        assert _mirror_simple_table(local, pg, "t", "cache_t", ["a", "b"]) == {
            "rows_written": 0, "source_total": 0,
        }

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
        result = _mirror_simple_table(local, pg, "t", "cache_t", ["a", "b"])
        assert result == {"rows_written": 2, "source_total": 2}
        (sql, rows) = pg.cursor_obj.executemany_calls[0]
        assert "cache_t" in sql and "a, b" in sql
        assert sorted(rows) == [("p", "q"), ("x", "y")]
