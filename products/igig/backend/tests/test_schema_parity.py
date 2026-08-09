"""Postgres ↔ SQLite schema parity.

IgIg carries TWO SETS of schema files: `migrations/00N_igig_*.sql` (canonical,
Postgres + RLS) and `migrations/sqlite/*.sql` (the development mirrors). Two
hand-maintained schemas drift — that is a near-certainty, not a risk — and the
drift surfaces as a column that exists in dev but not in production, or vice
versa, long after the change that caused it.

These tests make the drift loud. They compare TABLES and COLUMN NAMES only:
types deliberately differ (UUID→TEXT, JSONB→TEXT, TIMESTAMPTZ→TEXT), and
asserting on them would just encode the translation table twice. They also
assert the two sets stay the same SIZE, so a new domain migration cannot ship
without its mirror.

The SQLite files are also EXECUTED here, so a syntax error or a bad constraint
fails at test time rather than at app boot.
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pytest

MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"
SQLITE_DIR = MIGRATIONS / "sqlite"

#: Postgres files that declare DOMAIN tables. Framework migrations (001-005)
#: are seed-owned and have no SQLite mirror by design.
PG_FILES = sorted(MIGRATIONS.glob("00[6-9]_igig_*.sql")) + sorted(
    MIGRATIONS.glob("0[1-9][0-9]_igig_*.sql")
)

DOMAIN_TABLES = {
    "cliente", "marca", "contrato", "pauta", "tarefa", "apontamento", "aprovacao",
    # 008 — custo/hora model, Cofre de Acessos, visual assets
    "funcao", "profissional", "acesso", "peca",
}


def _read_all(paths) -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in paths)


def _sqlite_files():
    return sorted(SQLITE_DIR.glob("*.sql"))


def _parse_tables(sql: str) -> dict[str, set[str]]:
    """Map table name → column names from CREATE TABLE blocks.

    Intentionally a small parser rather than a SQL library: it only has to
    understand the subset these two files use, and a dependency here would
    be a heavier commitment than the ~20 lines it replaces.
    """
    tables: dict[str, set[str]] = {}
    pattern = re.compile(
        r"CREATE TABLE(?:\s+IF NOT EXISTS)?\s+(?:igig\.)?(\w+)\s*\((.*?)\n\);",
        re.DOTALL | re.IGNORECASE,
    )
    for name, body in pattern.findall(sql):
        # Strip `--` comments FIRST. A comma inside a comment would otherwise
        # split the column list mid-sentence and register the next word as a
        # column name (caught 2026-08-09: "…inadimplente, which gates…" was
        # parsed as a column called `which`).
        body = "\n".join(
            line.split("--", 1)[0] for line in body.splitlines()
        )
        columns: set[str] = set()
        depth = 0
        current = ""
        for char in body:
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
            if char == "," and depth == 0:
                columns.add(current)
                current = ""
                continue
            current += char
        columns.add(current)

        parsed: set[str] = set()
        for raw in columns:
            line = raw.strip()
            if not line:
                continue
            # Skip comment-only fragments and table-level constraints.
            line = "\n".join(
                l for l in line.splitlines() if not l.strip().startswith("--")
            ).strip()
            if not line:
                continue
            first = line.split()[0]
            if first.upper() in {
                "PRIMARY", "FOREIGN", "UNIQUE", "CHECK", "CONSTRAINT", "REFERENCES",
            }:
                continue
            parsed.add(first.strip('"'))
        tables[name] = parsed
    return tables


@pytest.fixture(scope="module")
def pg_tables() -> dict[str, set[str]]:
    return _parse_tables(_read_all(PG_FILES))


@pytest.fixture(scope="module")
def sqlite_tables() -> dict[str, set[str]]:
    return _parse_tables(_read_all(_sqlite_files()))


def test_both_schema_file_sets_exist():
    assert PG_FILES, f"no canonical Postgres domain migrations under {MIGRATIONS}"
    assert _sqlite_files(), f"no SQLite mirrors under {SQLITE_DIR}"


def test_every_pg_domain_migration_has_a_sqlite_counterpart():
    """A new domain migration without a mirror would silently skip dev."""
    assert len(_sqlite_files()) == len(PG_FILES), (
        f"{len(PG_FILES)} Postgres domain migration(s) "
        f"{[p.name for p in PG_FILES]} but {len(_sqlite_files())} SQLite mirror(s) "
        f"{[p.name for p in _sqlite_files()]} — every domain migration needs both."
    )


def test_postgres_declares_every_domain_table(pg_tables):
    assert DOMAIN_TABLES <= set(pg_tables), (
        f"Postgres schema is missing {DOMAIN_TABLES - set(pg_tables)}"
    )


def test_table_sets_match(pg_tables, sqlite_tables):
    pg_domain = set(pg_tables) & DOMAIN_TABLES
    sqlite_domain = set(sqlite_tables) & DOMAIN_TABLES
    assert pg_domain == sqlite_domain, (
        f"table drift — only in Postgres: {pg_domain - sqlite_domain}; "
        f"only in SQLite: {sqlite_domain - pg_domain}"
    )


@pytest.mark.parametrize("table", sorted(DOMAIN_TABLES))
def test_columns_match_per_table(table, pg_tables, sqlite_tables):
    pg_cols = pg_tables[table]
    sqlite_cols = sqlite_tables[table]
    assert pg_cols == sqlite_cols, (
        f"column drift in {table!r} — only in Postgres: {sorted(pg_cols - sqlite_cols)}; "
        f"only in SQLite: {sorted(sqlite_cols - pg_cols)}. "
        "Update BOTH the Postgres migration and its migrations/sqlite/ mirror."
    )


def test_every_domain_table_carries_org_id(pg_tables):
    """org_id is the tenant boundary — a table without it cannot be scoped."""
    for table in DOMAIN_TABLES:
        assert "org_id" in pg_tables[table], f"{table} has no org_id column"


def test_postgres_enables_rls_on_every_domain_table():
    """The Postgres path must ship real policies even though dev runs SQLite."""
    sql = _read_all(PG_FILES)
    assert "ENABLE ROW LEVEL SECURITY" in sql
    assert "public.current_org_id()" in sql, (
        "RLS must resolve org through the trusted resolver, never user_metadata"
    )
    for table in DOMAIN_TABLES:
        assert table in sql


def test_sqlite_schema_actually_executes():
    """Run the mirror — a syntax error must fail here, not at app boot."""
    conn = sqlite3.connect(":memory:")
    try:
        conn.executescript(_read_all(_sqlite_files()))
        found = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert DOMAIN_TABLES <= found, f"missing after execute: {DOMAIN_TABLES - found}"
    finally:
        conn.close()


def test_sqlite_enforces_one_open_timesheet_segment_per_user():
    """The play/pause invariant from Módulo 4, enforced by a partial index."""
    conn = sqlite3.connect(":memory:")
    try:
        conn.executescript(_read_all(_sqlite_files()))
        conn.execute(
            "INSERT INTO cliente (id, org_id, nome, created_at) VALUES ('c1','o1','X','t')"
        )
        conn.execute(
            "INSERT INTO pauta (id, org_id, cliente_id, titulo, created_at)"
            " VALUES ('p1','o1','c1','T','t')"
        )
        conn.execute(
            "INSERT INTO tarefa (id, org_id, pauta_id, titulo, created_at)"
            " VALUES ('t1','o1','p1','T','t')"
        )
        conn.execute(
            "INSERT INTO apontamento (id, org_id, tarefa_id, usuario_id, iniciado_em, created_at)"
            " VALUES ('a1','o1','t1','u1','t','t')"
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO apontamento (id, org_id, tarefa_id, usuario_id, iniciado_em, created_at)"
                " VALUES ('a2','o1','t1','u1','t','t')"
            )
    finally:
        conn.close()


def test_sqlite_rejects_an_invalid_kanban_etapa():
    """The 8-step esteira is a closed set on both backends."""
    conn = sqlite3.connect(":memory:")
    try:
        conn.executescript(_read_all(_sqlite_files()))
        conn.execute(
            "INSERT INTO cliente (id, org_id, nome, created_at) VALUES ('c1','o1','X','t')"
        )
        conn.execute(
            "INSERT INTO pauta (id, org_id, cliente_id, titulo, created_at)"
            " VALUES ('p1','o1','c1','T','t')"
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO tarefa (id, org_id, pauta_id, titulo, etapa, created_at)"
                " VALUES ('t1','o1','p1','T','etapa_inventada','t')"
            )
    finally:
        conn.close()
