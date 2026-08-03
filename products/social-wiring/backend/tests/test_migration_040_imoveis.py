"""Structural tests for `040_imoveis.sql`.

The migration is a FILE, not an applied change — it needs tech-lead consent
to run against any database. So these assert its *structure* by parsing it,
which is the only honest verification available before it is applied.

Two classes of assertion, and the second is the interesting one:

1. The invariants every social_wiring table must hold (RLS on,
   `current_org_id()` not `auth.jwt()`, service_role write policy).
2. The **asymmetric** CHECK constraints. Money and area reject 0 while room
   counts accept it, because Vista's ``"0"`` means "not applicable" in the
   first case and a literal zero in the second. That asymmetry looks like an
   inconsistency and is the single most likely thing for a future editor to
   "clean up" — which would either resurrect "R$ 0" listings or erase the
   difference between a Terreno and an unknown. Pinning it here makes the
   cleanup fail loudly instead of silently.
"""

from __future__ import annotations

from pathlib import Path

import pytest

MIGRATION = (
    Path(__file__).resolve().parents[1] / "migrations" / "040_imoveis.sql"
)


@pytest.fixture(scope="module")
def sql() -> str:
    return MIGRATION.read_text()


@pytest.fixture(scope="module")
def code(sql: str) -> str:
    """SQL with comment lines stripped — so prose about `auth.jwt()` in the
    rationale never satisfies (or trips) a check about actual SQL."""
    return "\n".join(l for l in sql.splitlines() if not l.strip().startswith("--"))


@pytest.fixture(scope="module")
def flat(code: str) -> str:
    """`code` with runs of whitespace collapsed.

    The DDL aligns its column definitions, so `suites      >= 0` is what is
    actually written. Substring checks must not depend on that alignment —
    a reformat would otherwise "break" tests that still hold.
    """
    return " ".join(code.split())


def test_migration_parses(sql: str):
    pglast = pytest.importorskip("pglast", reason="pglast not installed in this env")
    statements = pglast.parse_sql(sql)
    assert len(statements) > 0


def test_rls_is_enabled_with_org_scoped_read(code: str):
    assert "ENABLE ROW LEVEL SECURITY" in code
    assert "current_org_id()" in code
    assert "FOR SELECT TO authenticated" in code


def test_rls_never_keys_off_jwt_or_user_metadata(code: str):
    """`auth.jwt()` top-level is always-null and `user_metadata` is
    user-editable — either makes the policy a no-op or a privilege escalation."""
    assert "auth.jwt()" not in code
    assert "user_metadata" not in code


def test_service_role_can_write(code: str):
    assert "TO service_role" in code


def test_primary_key_is_org_scoped(code: str):
    """`codigo` has 0 duplicates within a tenant but is not globally unique."""
    assert "PRIMARY KEY (org_id, codigo)" in code


def test_is_idempotent(code: str):
    assert "CREATE TABLE IF NOT EXISTS" in code
    assert "DROP POLICY IF EXISTS" in code
    assert "ON CONFLICT" in code


def test_nav_item_has_a_status_pagina_row(code: str):
    """Without this the sidebar link is invisible with no error anywhere."""
    assert "status_pagina" in code
    assert "'imoveis'" in code


@pytest.mark.parametrize("column", ["valor_venda", "valor_locacao"])
def test_money_columns_reject_zero(flat: str, column: str, sql: str):
    """`"0"` on the wire means "not for sale/rent", so a stored 0 is a bug."""
    assert f"imoveis_{column}_not_zero" in sql
    assert f"{column} IS NULL OR {column} > 0" in flat


@pytest.mark.parametrize(
    "column", ["area_total", "area_privativa", "area_construida"]
)
def test_area_columns_reject_zero(sql: str, column: str):
    assert f"imoveis_{column}_not_zero" in sql


@pytest.mark.parametrize("column", ["dormitorios", "suites", "vagas"])
def test_room_counts_ACCEPT_zero(sql: str, flat: str, column: str):
    """The deliberate asymmetry — do NOT harmonize these with the money CHECKs.

    A Terreno has 0 dormitórios as a fact. `>= 0`, never `> 0`.
    """
    assert f"imoveis_{column}_non_negative" in sql
    assert f"{column} IS NULL OR {column} >= 0" in flat
    assert f"{column} IS NULL OR {column} > 0" not in flat


def test_banheiro_social_is_boolean_not_a_count(flat: str):
    """It is a "Sim"/"Nao" flag; parsing it as an int is what made it
    NULL on 100% of rows."""
    assert "banheiro_social BOOLEAN" in flat
    assert "banheiro_social INTEGER" not in flat


def test_corretores_is_a_collection(flat: str):
    """13.1% of imóveis have 2-3 corretores — a scalar column loses them."""
    assert "corretores JSONB" in flat


def test_caracteristicas_is_a_set_not_boolean_columns(flat: str):
    """76 tenant-defined keys that drift — columns would need a migration
    per new amenity."""
    assert "caracteristicas TEXT[]" in flat
    assert "USING gin (caracteristicas)" in flat


def test_there_is_no_origem_column(code: str):
    """`origem` is the marketing-portal dimension on LEADS.

    Vista is the source of truth for imóveis, so there is no provenance to
    discriminate here — and reusing the word would put two different
    `origem`s in one schema.
    """
    assert "origem" not in code


def test_raw_payload_is_preserved_for_re_derivation(code: str):
    assert "vista_raw" in code
