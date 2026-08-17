"""Tests for the 2026-08-14 cache-mirror-join-drift fix in `_embedding_corpus`:

  - `delete_embedding_rows`: cleans BOTH sibling tables unconditionally
    (json always; vec when HAS_VEC), not just the current process's engine.
  - `init_schema`: always creates the json fallback table, regardless of
    HAS_VEC, so a later delete under a different environment has somewhere
    to clean up.
  - `backfill_cross_engine_embeddings`: the lossless (zero re-embed) repair
    that copies json-only embeddings into vec and prunes true orphans.

Root cause (measured empirically against the live local caches on
2026-08-14): `sqlite-vec` is an opportunistically pip-installed, UNPINNED
dependency present in `mcp/noctusai/.venv` but absent from every
requirements.txt. A cache refreshed across environments with different
`HAS_VEC` over its lifetime split its corpus across BOTH sibling tables —
verified: union(vec, json) == chunks_total, intersection == 0, for all 4
local caches. See KB § PATTERNS/devops/cache-deploy-mirror.md.
"""
from __future__ import annotations

import json
import sqlite3
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from tools.noctus.dev import _embedding_corpus as ec


def _pack(vec: list[float]) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


def _make_conn_no_vec(monkeypatch):
    """A connection under a NO-sqlite-vec process (HAS_VEC=False) — the
    plain-table `json_table` is the only reachable sibling."""
    monkeypatch.setattr(ec, "HAS_VEC", False)
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE chunks (rowid_alias INTEGER PRIMARY KEY, path TEXT);
        CREATE TABLE js (chunk_rowid INTEGER PRIMARY KEY, embedding TEXT);
        """
    )
    return conn


def _make_conn_with_vec(monkeypatch):
    """A connection under a sqlite-vec-CAPABLE process (HAS_VEC=True). The
    `vec_table` here is a PLAIN table shaped like vec0's queryable surface
    (rowid, embedding BLOB) — sufficient for `delete_embedding_rows`, which
    never issues a vec0-specific statement (no MATCH / no virtual-table
    DDL), only a plain DELETE/SELECT."""
    monkeypatch.setattr(ec, "HAS_VEC", True)
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE chunks (rowid_alias INTEGER PRIMARY KEY, path TEXT);
        CREATE TABLE vc (rowid INTEGER PRIMARY KEY, embedding BLOB);
        CREATE TABLE js (chunk_rowid INTEGER PRIMARY KEY, embedding TEXT);
        """
    )
    return conn


class TestDeleteEmbeddingRows:
    def test_noop_on_empty_rowids(self, monkeypatch):
        conn = _make_conn_no_vec(monkeypatch)
        # Must not raise even with a nonexistent vec_table reference, since
        # rowids=[] short-circuits before any SQL touches vec_table.
        ec.delete_embedding_rows(conn, vec_table="nonexistent_vec", json_table="js", rowids=[])

    def test_deletes_from_json_regardless_of_has_vec(self, monkeypatch):
        conn = _make_conn_no_vec(monkeypatch)
        conn.execute("INSERT INTO js (chunk_rowid, embedding) VALUES (1, '[]')")
        ec.delete_embedding_rows(conn, vec_table="nonexistent_vec", json_table="js", rowids=[1])
        assert conn.execute("SELECT count(*) FROM js").fetchone()[0] == 0

    def test_deletes_from_vec_when_has_vec_true(self, monkeypatch):
        conn = _make_conn_with_vec(monkeypatch)
        conn.execute("INSERT INTO vc (rowid, embedding) VALUES (1, ?)", (_pack([1.0]),))
        conn.execute("INSERT INTO js (chunk_rowid, embedding) VALUES (1, '[]')")
        ec.delete_embedding_rows(conn, vec_table="vc", json_table="js", rowids=[1])
        assert conn.execute("SELECT count(*) FROM vc").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM js").fetchone()[0] == 0

    def test_the_regression_shape_cross_engine_cleanup(self, monkeypatch):
        """THE bug this fix closes: a row written under engine A (json) must
        be cleaned up by a delete running under engine B (vec-capable) —
        this is exactly what stranded orphans pre-fix (the old code only
        cleaned the CURRENT process's engine table)."""
        conn = _make_conn_with_vec(monkeypatch)  # THIS delete runs under HAS_VEC=True
        # Row was written by a PRIOR refresh under HAS_VEC=False (json only).
        conn.execute("INSERT INTO js (chunk_rowid, embedding) VALUES (1, '[]')")
        ec.delete_embedding_rows(conn, vec_table="vc", json_table="js", rowids=[1])
        # Cleaned even though this process's "native" engine (vec) never
        # held the row — json is always attempted regardless of HAS_VEC.
        assert conn.execute("SELECT count(*) FROM js").fetchone()[0] == 0


class TestInitSchemaAlwaysCreatesJson:
    def test_json_table_created_even_when_has_vec_true(self, monkeypatch, tmp_path):
        monkeypatch.setattr(ec, "HAS_VEC", False)  # avoid needing the real extension
        conn = sqlite3.connect(":memory:")
        ec.init_schema(conn, "chunks", "vc", "js")
        tables = {
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "js" in tables  # the plain fallback table always exists
        assert "chunks" in tables

    def test_vec_table_only_created_when_has_vec(self, monkeypatch):
        monkeypatch.setattr(ec, "HAS_VEC", False)
        conn = sqlite3.connect(":memory:")
        ec.init_schema(conn, "chunks", "vc", "js")
        tables = {
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        # No sqlite-vec extension loaded in this test process/connection —
        # a real `CREATE VIRTUAL TABLE ... USING vec0` would error, so
        # init_schema correctly skips it when HAS_VEC is False.
        assert "vc" not in tables


class TestBackfillCrossEngineEmbeddings:
    def _conn_with_vec_module_absent_gracefully(self, monkeypatch):
        # backfill requires HAS_VEC=True (the copy TARGET is vec) — simulate
        # via a plain table standing in for vec0's queryable surface.
        monkeypatch.setattr(ec, "HAS_VEC", True)
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript(
            """
            CREATE TABLE chunks (rowid_alias INTEGER PRIMARY KEY, path TEXT);
            CREATE TABLE vc (rowid INTEGER PRIMARY KEY, embedding BLOB);
            CREATE TABLE js (chunk_rowid INTEGER PRIMARY KEY, embedding TEXT);
            """
        )
        return conn

    def test_skips_when_no_vec(self, monkeypatch):
        monkeypatch.setattr(ec, "HAS_VEC", False)
        conn = sqlite3.connect(":memory:")
        result = ec.backfill_cross_engine_embeddings(
            conn, chunks_table="chunks", vec_table="vc", json_table="js"
        )
        assert result == {
            "ok": True, "status": "skipped-no-vec",
            "copied_json_to_vec": 0, "deleted_orphan_json": 0,
            "deleted_orphan_vec": 0, "chunks_total": 0,
        }

    def test_copies_json_only_embedding_into_vec_losslessly(self, monkeypatch):
        conn = self._conn_with_vec_module_absent_gracefully(monkeypatch)
        conn.execute("INSERT INTO chunks (rowid_alias, path) VALUES (1, 'KB/a.md')")
        conn.execute(
            "INSERT INTO js (chunk_rowid, embedding) VALUES (1, ?)",
            (json.dumps([1.5, 2.5, 3.5]),),
        )
        result = ec.backfill_cross_engine_embeddings(
            conn, chunks_table="chunks", vec_table="vc", json_table="js"
        )
        assert result["status"] == "repaired"
        assert result["copied_json_to_vec"] == 1
        assert result["chunks_total"] == 1
        blob = conn.execute("SELECT embedding FROM vc WHERE rowid=1").fetchone()[0]
        n = len(blob) // 4
        recovered = list(struct.unpack(f"<{n}f", blob))
        assert recovered == pytest.approx([1.5, 2.5, 3.5], abs=1e-5)

    def test_does_not_overwrite_existing_vec_row(self, monkeypatch):
        conn = self._conn_with_vec_module_absent_gracefully(monkeypatch)
        conn.execute("INSERT INTO chunks (rowid_alias, path) VALUES (1, 'KB/a.md')")
        conn.execute("INSERT INTO vc (rowid, embedding) VALUES (1, ?)", (_pack([9.0, 9.0]),))
        conn.execute(
            "INSERT INTO js (chunk_rowid, embedding) VALUES (1, ?)",
            (json.dumps([1.0, 1.0]),),
        )
        result = ec.backfill_cross_engine_embeddings(
            conn, chunks_table="chunks", vec_table="vc", json_table="js"
        )
        assert result["copied_json_to_vec"] == 0  # already present — skipped
        blob = conn.execute("SELECT embedding FROM vc WHERE rowid=1").fetchone()[0]
        n = len(blob) // 4
        assert list(struct.unpack(f"<{n}f", blob)) == pytest.approx([9.0, 9.0])

    def test_prunes_true_orphans_on_both_sides(self, monkeypatch):
        conn = self._conn_with_vec_module_absent_gracefully(monkeypatch)
        # Only chunk 1 is live. Rows 2 (json) and 3 (vec) are garbage from a
        # superseded doc generation — their chunk no longer exists.
        conn.execute("INSERT INTO chunks (rowid_alias, path) VALUES (1, 'KB/a.md')")
        conn.execute(
            "INSERT INTO js (chunk_rowid, embedding) VALUES (1, ?)",
            (json.dumps([1.0]),),
        )
        conn.execute("INSERT INTO js (chunk_rowid, embedding) VALUES (2, '[9.0]')")
        conn.execute("INSERT INTO vc (rowid, embedding) VALUES (3, ?)", (_pack([9.0]),))
        result = ec.backfill_cross_engine_embeddings(
            conn, chunks_table="chunks", vec_table="vc", json_table="js"
        )
        assert result["deleted_orphan_json"] == 1
        assert result["deleted_orphan_vec"] == 1
        assert conn.execute("SELECT count(*) FROM js").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM vc").fetchone()[0] == 1

    def test_idempotent_second_run_is_a_noop(self, monkeypatch):
        conn = self._conn_with_vec_module_absent_gracefully(monkeypatch)
        conn.execute("INSERT INTO chunks (rowid_alias, path) VALUES (1, 'KB/a.md')")
        conn.execute(
            "INSERT INTO js (chunk_rowid, embedding) VALUES (1, ?)",
            (json.dumps([1.0, 2.0]),),
        )
        first = ec.backfill_cross_engine_embeddings(
            conn, chunks_table="chunks", vec_table="vc", json_table="js"
        )
        second = ec.backfill_cross_engine_embeddings(
            conn, chunks_table="chunks", vec_table="vc", json_table="js"
        )
        assert first["copied_json_to_vec"] == 1
        assert second["copied_json_to_vec"] == 0
        assert second["deleted_orphan_json"] == 0
        assert second["deleted_orphan_vec"] == 0

    def test_realistic_split_corpus_fully_repaired(self, monkeypatch):
        """The measured real-world shape: chunk 1 lives ONLY in vec, chunk 2
        ONLY in json, chunk 3 was superseded (orphan on both sides). After
        repair: chunks 1+2 are joinable via vec (the canonical engine going
        forward); the orphan garbage is gone; NO re-embed happened."""
        conn = self._conn_with_vec_module_absent_gracefully(monkeypatch)
        conn.execute("INSERT INTO chunks (rowid_alias, path) VALUES (1, 'KB/vec-only.md')")
        conn.execute("INSERT INTO chunks (rowid_alias, path) VALUES (2, 'KB/json-only.md')")
        conn.execute("INSERT INTO vc (rowid, embedding) VALUES (1, ?)", (_pack([1.0, 1.0]),))
        conn.execute(
            "INSERT INTO js (chunk_rowid, embedding) VALUES (2, ?)",
            (json.dumps([2.0, 2.0]),),
        )
        conn.execute("INSERT INTO js (chunk_rowid, embedding) VALUES (99, '[0.0]')")  # orphan

        result = ec.backfill_cross_engine_embeddings(
            conn, chunks_table="chunks", vec_table="vc", json_table="js"
        )
        assert result["chunks_total"] == 2
        assert result["copied_json_to_vec"] == 1  # chunk 2's embedding copied in
        assert result["deleted_orphan_json"] == 1  # rowid 99 pruned

        vec_rowids = {r[0] for r in conn.execute("SELECT rowid FROM vc").fetchall()}
        assert vec_rowids == {1, 2}  # BOTH chunks now joinable via vec
