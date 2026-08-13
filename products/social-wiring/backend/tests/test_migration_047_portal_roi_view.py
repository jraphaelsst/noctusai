"""Structural tests for `047_portal_roi_view_null_investimento.sql`.

The migration is a FILE, not an applied change — production consent is
required to run it. These assert its *structure* by parsing it, which is
the only honest verification available before it is applied. Mirrors
`test_migration_040_imoveis.py`'s shape.

The interesting assertions are the per-column ones: `cpl`'s numerator lost
its `COALESCE`, `roi` did NOT change, and the view still carries every
invariant `043` established (RLS is a TABLE concern untouched by this
migration — `vw_portal_roi` is a plain view with no RLS of its own,
inheriting the underlying tables' policies — so this file has no RLS
assertions of its own, unlike `040`'s).
"""
from __future__ import annotations

from pathlib import Path

import pytest

MIGRATION = (
    Path(__file__).resolve().parent
    / ".."
    / "migrations"
    / "047_portal_roi_view_null_investimento.sql"
).resolve()


@pytest.fixture(scope="module")
def sql() -> str:
    return MIGRATION.read_text()


@pytest.fixture(scope="module")
def code(sql: str) -> str:
    """SQL with comment lines stripped — prose in the header must never
    satisfy (or trip) a check about actual SQL."""
    return "\n".join(l for l in sql.splitlines() if not l.strip().startswith("--"))


@pytest.fixture(scope="module")
def flat(code: str) -> str:
    """`code` with runs of whitespace collapsed — substring checks must
    not depend on the DDL's column alignment."""
    return " ".join(code.split())


def test_migration_file_exists():
    assert MIGRATION.exists(), MIGRATION


def test_migration_parses(sql: str):
    pglast = pytest.importorskip("pglast", reason="pglast not installed in this env")
    statements = pglast.parse_sql(sql)
    assert len(statements) > 0


def test_is_create_or_replace_view_only(code: str):
    """Forward-only, idempotent — no ALTER, no new table, no data
    migration. Re-running this file any number of times must be a no-op
    beyond redefining the view."""
    assert "CREATE OR REPLACE VIEW" in code
    assert "ALTER TABLE" not in code
    assert "CREATE TABLE" not in code
    assert "INSERT INTO" not in code
    assert "UPDATE " not in code


def test_view_name_unchanged(flat: str):
    assert "CREATE OR REPLACE VIEW social_wiring.vw_portal_roi AS" in flat


def test_raw_investimento_column_has_no_coalesce(flat: str):
    """The central fix: `c.investimento AS investimento` — bare, not
    `COALESCE(c.investimento, 0)`. This is the column the service layer
    reads to decide `null` vs `0` in the JSON contract; masking it here
    makes the distinction unrecoverable one layer up."""
    assert "c.investimento AS investimento" in flat
    assert "COALESCE(c.investimento, 0) AS investimento" not in flat


def test_cpl_numerator_has_no_coalesce(flat: str):
    """`cpl`'s numerator must be bare `c.investimento`, not
    `COALESCE(c.investimento, 0)` and not `NULLIF(COALESCE(c.investimento,
    0), 0)` — the latter was considered and rejected (it would turn a
    genuine recorded R$ 0,00 into `null` too, see the migration header)."""
    assert "c.investimento / NULLIF(COALESCE(l.total_leads, 0), 0) AS cpl" in flat
    assert "COALESCE(c.investimento, 0) / NULLIF(COALESCE(l.total_leads, 0), 0) AS cpl" not in flat


def test_roi_is_untouched(flat: str):
    """✅ Already correct per the migration header's verdict — assert the
    EXACT original expression survives unchanged, character for
    character, so a future edit that "fixes" it the same way as `cpl`
    fails loudly instead of silently."""
    assert (
        "COALESCE(v.valor_vendas, 0) / NULLIF(COALESCE(c.investimento, 0), 0) AS roi"
        in flat
    )


def test_taxa_conversao_formula_is_untouched(flat: str):
    """Documented, accepted limitation (see header) — NOT mirrored from
    the `cpl` fix. Assert the exact original expression survives."""
    assert (
        "COALESCE(v.total_vendas, 0)::NUMERIC / NULLIF(COALESCE(l.total_leads, 0), 0) AS taxa_conversao"
        in flat
    )


def test_total_leads_total_vendas_valor_vendas_stay_coalesced(flat: str):
    """These are counts of things — zero really is zero (043's own
    verdict, restated and NOT revisited by this migration)."""
    assert "COALESCE(l.total_leads, 0) AS total_leads" in flat
    assert "COALESCE(v.total_vendas, 0) AS total_vendas" in flat
    assert "COALESCE(v.valor_vendas, 0) AS valor_vendas" in flat


def test_left_joins_preserved(flat: str):
    """Dropping to an INNER JOIN would silently hide exactly the portals
    worth investigating (spend with no leads, or leads with no spend)."""
    assert flat.count("LEFT JOIN") == 3
    assert "INNER JOIN" not in flat


def test_marks_itself_unapplied(sql: str):
    """No migration in this codebase is applied by the agent that writes
    it — this DB is production, there is no separate dev DB."""
    assert "MIGRATION FILE ONLY" in sql
    assert "NOT applied" in sql


def test_documents_the_collision_check(sql: str):
    """`043`'s header established the collision-check ritual for this
    product; every migration since should show it was actually run."""
    assert "collision" in sql.lower()
