"""Tests for the PULL direction of cache_deploy_mirror (prod PG → local SQLite).

🔴 Why this file exists (2026-08-18). `cache_pull` had NO tests and exactly one
production caller (`cache_backend`'s auto-pull-on-empty, which only fires on a
fresh clone). Under that cover it had been broken since it was written: the
pull path carried its own hand-authored copy of all seven local schemas
(`_LOCAL_SCHEMA_INIT`) plus its own copy of every column list, and not one of
them matched the real DDL. The four chunk+embedding caches key their embedding
siblings on `<chunks>.rowid_alias`; the invented schema had no such column,
gave `*_embeddings_json` a `(path, symbol_name, chunk_idx)` composite key it
does not have, and never created the `*_vec` sibling that every vector read
goes through. The three non-vector caches named columns (`pattern_id`, `tier`,
`bundle_sha`) that exist on neither side.

It surfaced only because `code_chunks.kind` is NOT NULL and a real table
already existed to collide with — on a genuinely fresh clone the fake DDL
would have been CREATEd, the INSERT would have succeeded, and `cache_pull`
would have reported `ok: true` over a cache no reader can query. That is the
exact failure the Tier-2 mirror exists to prevent, so the tests below are the
gate: `TestSchemaParity` compares the shared spec against BOTH real schemas,
and `TestRoundTrip` mirrors then pulls and asserts the bytes come back.

`*_vec` here is a real vec0 virtual table (every DB is opened with
`_ec.connect_cache`, exactly as `pull_one_cache` does); the round-trip case is
skipped when sqlite-vec is unavailable — unlike the mirror tests, the pull WRITES to it, so a plain
stand-in table would not prove the insert shape.

KB § PATTERNS/devops/cache-deploy-mirror.md.
"""
import json
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from tools.noctus.dev import _embedding_corpus as _ec
from tools.noctus.dev.cache_deploy_mirror import (
    _EMBEDDING_CACHE_SPEC,
    _PG_INIT_DDL,
    _SIMPLE_CACHE_SPEC,
    _TABLE_MAP,
    _init_local_schema,
    _mirror_chunks_with_embedding,
    _pull_chunks_with_embedding,
    _pull_simple_table,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _columns_of(conn: sqlite3.Connection, table: str) -> set[str]:
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def _pg_columns_of(table: str) -> set[str]:
    """Parse `_PG_INIT_DDL` for one table's column names.

    Deliberately parses the DDL string rather than restating the columns: a
    restated list is a third copy of the schema, which is the bug this file
    exists to catch.
    """
    m = re.search(
        rf"CREATE TABLE IF NOT EXISTS noctus_cache\.{table} \((.*?)\n\);",
        _PG_INIT_DDL,
        re.S,
    )
    assert m, f"{table} not found in _PG_INIT_DDL"
    cols = set()
    for line in m.group(1).split("\n"):
        line = line.strip()
        if not line or line.startswith("--") or line.startswith("UNIQUE"):
            continue
        cols.add(line.split()[0])
    # Columns added later by an ALTER migration leg count too.
    for alter in re.finditer(
        rf"ALTER TABLE noctus_cache\.{table} ADD COLUMN IF NOT EXISTS (\w+)",
        _PG_INIT_DDL,
    ):
        cols.add(alter.group(1))
    return cols


DIM = 1536


def _vec(seed: float) -> list[float]:
    """A full-width 1536-D vector — vec0 rejects anything shorter."""
    return [seed] + [0.0] * (DIM - 1)


class _StubPgCursor:
    """Returns canned rows for the single SELECT the pull path issues."""

    def __init__(self, rows):
        self._rows = rows
        self.executed: list[str] = []

    def execute(self, sql, params=None):
        self.executed.append(sql)

    def fetchall(self):
        return self._rows

    def close(self):
        pass


class _StubPgConn:
    def __init__(self, rows):
        self.cursor_obj = _StubPgCursor(rows)

    def cursor(self):
        return self.cursor_obj


# ── Schema parity — the gate ──────────────────────────────────────────────────


class TestSchemaParity:
    """The shared spec must agree with BOTH real schemas, for every cache."""

    @pytest.mark.parametrize("cache_name", sorted(_EMBEDDING_CACHE_SPEC))
    def test_local_chunk_columns_exist_in_canonical_ddl(self, cache_name, tmp_path):
        spec = _EMBEDDING_CACHE_SPEC[cache_name]
        conn = _ec.connect_cache(tmp_path / f"{cache_name}.sqlite")
        _init_local_schema(conn, cache_name)
        cols = _columns_of(conn, spec["chunks_table"])
        missing = set(spec["chunk_columns_local"]) - cols
        assert not missing, (
            f"{cache_name}: spec names {missing} but "
            f"{spec['chunks_table']} has {sorted(cols)}"
        )
        # rowid_alias is the key both embedding siblings join on — its absence
        # was the structural half of the 2026-08-18 bug.
        assert "rowid_alias" in cols
        conn.close()

    @pytest.mark.parametrize("cache_name", sorted(_EMBEDDING_CACHE_SPEC))
    def test_json_sibling_is_rowid_keyed(self, cache_name, tmp_path):
        spec = _EMBEDDING_CACHE_SPEC[cache_name]
        conn = _ec.connect_cache(tmp_path / f"{cache_name}.sqlite")
        _init_local_schema(conn, cache_name)
        assert _columns_of(conn, spec["json_table"]) == {"chunk_rowid", "embedding"}
        conn.close()

    @pytest.mark.parametrize("cache_name", sorted(_EMBEDDING_CACHE_SPEC))
    def test_pg_columns_match_prod_ddl(self, cache_name):
        spec = _EMBEDDING_CACHE_SPEC[cache_name]
        pg_cols = _pg_columns_of(spec["pg_table"])
        missing = set(spec["pg_columns"]) - pg_cols
        assert not missing, f"{cache_name}: spec names {missing}, absent from _PG_INIT_DDL"

    @pytest.mark.parametrize("cache_name", sorted(_EMBEDDING_CACHE_SPEC))
    def test_embedding_index_is_consistent(self, cache_name):
        spec = _EMBEDDING_CACHE_SPEC[cache_name]
        assert spec["pg_columns"][spec["embedding_pg_col_idx"]] == "embedding"
        # pg_columns == chunk columns + the embedding slot, nothing else.
        assert len(spec["pg_columns"]) == len(spec["chunk_columns_local"]) + 1

    @pytest.mark.parametrize("cache_name", sorted(_SIMPLE_CACHE_SPEC))
    def test_simple_cache_columns_exist_on_both_sides(self, cache_name, tmp_path):
        spec = _SIMPLE_CACHE_SPEC[cache_name]
        conn = _ec.connect_cache(tmp_path / f"{cache_name}.sqlite")
        _init_local_schema(conn, cache_name)
        local_cols = _columns_of(conn, spec["sqlite_table"])
        conn.close()
        assert not set(spec["columns"]) - local_cols, (
            f"{cache_name}: spec names columns absent from the local DDL"
        )
        assert not set(spec["columns"]) - _pg_columns_of(spec["pg_table"]), (
            f"{cache_name}: spec names columns absent from _PG_INIT_DDL"
        )

    def test_every_mirrorable_cache_has_a_spec(self):
        """No cache may be added to _TABLE_MAP without a pull contract.

        `noc-graph` is deliberately absent from _TABLE_MAP entirely (it is
        rebuild-only — see the branch in `pull_one_cache`), so every entry
        that IS there must be pullable.
        """
        specced = set(_EMBEDDING_CACHE_SPEC) | set(_SIMPLE_CACHE_SPEC)
        assert set(_TABLE_MAP) - specced == set()


# ── Round trip — mirror out, pull back, compare ───────────────────────────────


HAS_VEC = getattr(_ec, "HAS_VEC", False)


class TestRoundTrip:
    def _seed_code_cache(self, path: Path) -> sqlite3.Connection:
        conn = _ec.connect_cache(path)
        _init_local_schema(conn, "code-embeddings")
        rows = [
            ("app/main.py", "handler", 0, "function", "def handler(): ...", "sha1", "t0"),
            ("app/main.py", "", 1, "file", "# module docstring", "sha1", "t0"),
            ("lib/util.py", "Helper", 0, "class", "class Helper: ...", "sha2", "t0"),
        ]
        for i, r in enumerate(rows):
            cur = conn.execute(
                "INSERT INTO code_chunks (path, symbol_name, chunk_idx, kind, "
                "chunk_text, source_sha, cached_at) VALUES (?,?,?,?,?,?,?)", r,
            )
            vec = _vec(float(i))
            if HAS_VEC:
                conn.execute(
                    "INSERT INTO code_vec(rowid, embedding) VALUES (?, ?)",
                    (cur.lastrowid, _ec.pack_vec(vec)),
                )
            else:
                conn.execute(
                    "INSERT INTO code_embeddings_json(chunk_rowid, embedding) "
                    "VALUES (?, ?)", (cur.lastrowid, json.dumps(vec)),
                )
        conn.commit()
        return conn

    @pytest.mark.skipif(
        not HAS_VEC, reason="pull writes a real vec0 table; needs sqlite-vec"
    )
    def test_mirror_then_pull_restores_every_chunk_and_vector(self, tmp_path):
        source = self._seed_code_cache(tmp_path / "src.sqlite")
        spec = _EMBEDDING_CACHE_SPEC["code-embeddings"]

        # Mirror out — capture what would have gone to prod.
        class _Cap:
            def __init__(self):
                self.rows = []

            def cursor(self):
                return self

            def execute(self, sql, params=None):
                pass

            def executemany(self, sql, rows):
                self.rows.extend(rows)

            def close(self):
                pass

        cap = _Cap()
        res = _mirror_chunks_with_embedding(
            source, cap,
            chunks_table=spec["chunks_table"], vec_table=spec["vec_table"],
            embeddings_json_table=spec["json_table"], pg_table=spec["pg_table"],
            chunk_columns_local=spec["chunk_columns_local"],
            pg_insert_cols=spec["pg_columns"],
            embedding_pg_col_idx=spec["embedding_pg_col_idx"],
        )
        assert res["rows_written"] == 3 and res["missing_embedding_count"] == 0
        source.close()

        # Pull back into a virgin cache.
        dest = _ec.connect_cache(tmp_path / "dst.sqlite")
        _init_local_schema(dest, "code-embeddings")
        detail = _pull_chunks_with_embedding(
            dest, _StubPgConn(cap.rows), spec=spec,
        )
        assert detail["rows_pulled"] == 3
        assert detail["vec_rows"] == 3
        assert detail["null_embedding_count"] == 0
        assert detail["legacy_null_backfilled"] == {}

        got = dest.execute(
            "SELECT path, symbol_name, chunk_idx, kind, chunk_text, source_sha, "
            "cached_at FROM code_chunks ORDER BY rowid_alias"
        ).fetchall()
        assert [tuple(r) for r in got] == [
            ("app/main.py", "handler", 0, "function", "def handler(): ...", "sha1", "t0"),
            ("app/main.py", "", 1, "file", "# module docstring", "sha1", "t0"),
            ("lib/util.py", "Helper", 0, "class", "class Helper: ...", "sha2", "t0"),
        ]
        # Every chunk's embedding is reachable through the rowid join the
        # readers actually use.
        joined = dest.execute(
            "SELECT c.path, j.embedding FROM code_chunks c "
            "JOIN code_embeddings_json j ON j.chunk_rowid = c.rowid_alias "
            "ORDER BY c.rowid_alias"
        ).fetchall()
        assert len(joined) == 3
        assert json.loads(joined[0][1]) == _vec(0.0)
        dest.close()

    def test_pull_writes_json_sibling_keyed_by_chunk_rowid(self, tmp_path):
        """The join the search path uses must resolve — without sqlite-vec too."""
        spec = _EMBEDDING_CACHE_SPEC["kb-embeddings"]
        dest = _ec.connect_cache(tmp_path / "kb.sqlite")
        _init_local_schema(dest, "kb-embeddings")
        rows = [
            ("KB/a.md", 0, "alpha", json.dumps(_vec(1.0)), "sha", "t0"),
            ("KB/b.md", 0, "beta", _vec(3.0), "sha", "t0"),  # sequence form
        ]
        detail = _pull_chunks_with_embedding(dest, _StubPgConn(rows), spec=spec)
        assert detail["rows_pulled"] == 2 and detail["json_rows"] == 2
        joined = dest.execute(
            "SELECT c.path, j.embedding FROM kb_chunks c "
            "JOIN kb_embeddings_json j ON j.chunk_rowid = c.rowid_alias "
            "ORDER BY c.rowid_alias"
        ).fetchall()
        assert [r[0] for r in joined] == ["KB/a.md", "KB/b.md"]
        assert json.loads(joined[0][1]) == _vec(1.0)
        assert json.loads(joined[1][1]) == _vec(3.0)
        dest.close()

    def test_pull_replaces_prior_content(self, tmp_path):
        spec = _EMBEDDING_CACHE_SPEC["kb-embeddings"]
        dest = _ec.connect_cache(tmp_path / "kb.sqlite")
        _init_local_schema(dest, "kb-embeddings")
        _pull_chunks_with_embedding(
            dest, _StubPgConn([("old.md", 0, "stale", _vec(1.0), "sha", "t0")]), spec=spec
        )
        _pull_chunks_with_embedding(
            dest, _StubPgConn([("new.md", 0, "fresh", _vec(2.0), "sha", "t1")]), spec=spec
        )
        assert [r[0] for r in dest.execute("SELECT path FROM kb_chunks")] == ["new.md"]
        assert dest.execute("SELECT COUNT(*) FROM kb_embeddings_json").fetchone()[0] == 1
        dest.close()

    def test_empty_prod_table_is_not_an_error(self, tmp_path):
        spec = _EMBEDDING_CACHE_SPEC["kb-embeddings"]
        dest = _ec.connect_cache(tmp_path / "kb.sqlite")
        _init_local_schema(dest, "kb-embeddings")
        detail = _pull_chunks_with_embedding(dest, _StubPgConn([]), spec=spec)
        assert detail["rows_pulled"] == 0
        dest.close()


# ── No-silent-error legs ──────────────────────────────────────────────────────


class TestNoSilentErrors:
    def test_legacy_null_kind_uses_declared_sentinel_and_is_reported(self, tmp_path):
        """A prod snapshot predating the `kind` column must not fail, nor lie."""
        spec = _EMBEDDING_CACHE_SPEC["code-embeddings"]
        dest = _ec.connect_cache(tmp_path / "code.sqlite")
        _init_local_schema(dest, "code-embeddings")
        rows = [("a.py", "f", 0, None, "def f(): ...", _vec(1.0), "sha", "t0")]
        detail = _pull_chunks_with_embedding(dest, _StubPgConn(rows), spec=spec)
        assert detail["rows_pulled"] == 1
        assert detail["legacy_null_backfilled"] == {"kind": 1}
        assert dest.execute("SELECT kind FROM code_chunks").fetchone()[0] == "unknown"
        dest.close()

    def test_null_embedding_is_counted_not_silently_dropped(self, tmp_path):
        spec = _EMBEDDING_CACHE_SPEC["kb-embeddings"]
        dest = _ec.connect_cache(tmp_path / "kb.sqlite")
        _init_local_schema(dest, "kb-embeddings")
        rows = [
            ("good.md", 0, "text", _vec(1.0), "sha", "t0"),
            ("bad.md", 0, "text", None, "sha", "t0"),
        ]
        detail = _pull_chunks_with_embedding(dest, _StubPgConn(rows), spec=spec)
        # The chunk is still restored — it is the EMBEDDING that is missing,
        # and the caller is told so rather than discovering a short corpus.
        assert detail["rows_pulled"] == 2
        assert detail["json_rows"] == 1
        assert detail["null_embedding_count"] == 1
        assert detail["null_embedding_sample"][0]["path"] == "bad.md"
        dest.close()

    def test_unexpected_null_in_not_null_column_raises(self, tmp_path):
        """Only DECLARED legacy gaps get a sentinel; anything else must be loud."""
        spec = _EMBEDDING_CACHE_SPEC["kb-embeddings"]
        dest = _ec.connect_cache(tmp_path / "kb.sqlite")
        _init_local_schema(dest, "kb-embeddings")
        rows = [("a.md", 0, None, _vec(1.0), "sha", "t0")]  # chunk_text NOT NULL
        with pytest.raises(sqlite3.IntegrityError):
            _pull_chunks_with_embedding(dest, _StubPgConn(rows), spec=spec)
        dest.close()


class TestPullSimpleTable:
    def test_round_trips_and_replaces(self, tmp_path):
        spec = _SIMPLE_CACHE_SPEC["agent-context"]
        dest = _ec.connect_cache(tmp_path / "ac.sqlite")
        _init_local_schema(dest, "agent-context")
        rows = [("architect", "owns_kb", "KB/x.md", "body", "sha", "t0")]
        assert _pull_simple_table(
            dest, _StubPgConn(rows), spec["sqlite_table"], spec["pg_table"],
            spec["columns"],
        ) == 1
        got = dest.execute(
            f"SELECT {', '.join(spec['columns'])} FROM agent_context"
        ).fetchone()
        assert tuple(got) == rows[0]
        dest.close()


class TestFailedPullIsAtomic:
    def test_failed_pull_leaves_prior_cache_intact(self, tmp_path):
        """A restore that blows up must not destroy what was already there.

        The pull DELETEs before it INSERTs, so without a rollback boundary a
        mid-transfer failure would leave the operator with an empty cache AND
        an error — strictly worse than not having tried.
        """
        spec = _EMBEDDING_CACHE_SPEC["kb-embeddings"]
        db = _ec.connect_cache(tmp_path / "kb.sqlite")
        _init_local_schema(db, "kb-embeddings")

        good = [("keep.md", 0, "precious", _vec(1.0), "sha", "t0")]
        assert _pull_chunks_with_embedding(
            db, _StubPgConn(good), spec=spec
        )["rows_pulled"] == 1

        # Second pull carries a NULL in a NOT NULL column — it must raise...
        bad = [("wipe.md", 0, None, _vec(2.0), "sha", "t1")]
        with pytest.raises(sqlite3.IntegrityError):
            _pull_chunks_with_embedding(db, _StubPgConn(bad), spec=spec)

        # ...and leave the previous contents, including the sibling row.
        assert [r[0] for r in db.execute("SELECT path FROM kb_chunks")] == ["keep.md"]
        joined = db.execute(
            "SELECT c.path FROM kb_chunks c "
            "JOIN kb_embeddings_json j ON j.chunk_rowid = c.rowid_alias"
        ).fetchall()
        assert [r[0] for r in joined] == ["keep.md"]
        db.close()


class TestRealDriverTypes:
    """Regression: the fixtures above are too kind to the pull path.

    `TestRoundTrip` feeds plain Python lists, so it passed while the REAL
    driver path failed twice in prod on 2026-08-18:

      1. pgvector returns numpy `float32` elements once its adapter is
         registered — `json.dumps` refuses them outright.
      2. `init_prod_cache_schema` splits `_PG_INIT_DDL` on the statement
         separator, so a semicolon or apostrophe inside a COMMENT truncates
         the statement mid-comment.

    Both are shape mismatches between the fixture and the driver, which is
    exactly the class this file exists to catch.
    """

    def test_numpy_float32_embeddings_serialize(self, tmp_path):
        np = pytest.importorskip("numpy")
        spec = _EMBEDDING_CACHE_SPEC["kb-embeddings"]
        dest = _ec.connect_cache(tmp_path / "kb.sqlite")
        _init_local_schema(dest, "kb-embeddings")
        vec = np.array(_vec(1.5), dtype=np.float32)
        detail = _pull_chunks_with_embedding(
            dest, _StubPgConn([("a.md", 0, "text", vec, "sha", "t0")]), spec=spec,
        )
        assert detail["rows_pulled"] == 1 and detail["json_rows"] == 1
        stored = json.loads(
            dest.execute("SELECT embedding FROM kb_embeddings_json").fetchone()[0]
        )
        assert stored[0] == pytest.approx(1.5)
        assert all(isinstance(x, float) for x in stored[:8])
        dest.close()

    def test_pg_ddl_comments_carry_no_statement_separator(self):
        """No semicolon inside a `--` comment in `_PG_INIT_DDL`.

        `init_prod_cache_schema` splits the script on the statement
        separator. Postgres ignores `--` comments, so an apostrophe in one is
        harmless ON ITS OWN — the failure needs two stages, and both fired in
        prod on 2026-08-18:

          1. a `;` inside a comment splits the script mid-comment, so the
             NEXT fragment begins in the middle of prose with no `--` prefix;
          2. an apostrophe in that orphaned prose is then parsed as a live
             quote, and the statement dies on "unterminated quoted string".

        Only step 1 is preventable by construction, so that is what this
        asserts — banning apostrophes outright would flag harmless comments
        like "mirrors SQLite's cache_meta" and train people to ignore it.
        """
        from tools.noctus.dev.cache_deploy_mirror import _PG_INIT_DDL
        offenders = [
            line.strip() for line in _PG_INIT_DDL.splitlines()
            if line.strip().startswith("--") and ";" in line
        ]
        assert not offenders, (
            "comment lines in _PG_INIT_DDL must not contain a semicolon — "
            f"the splitter truncates the statement there: {offenders}"
        )
