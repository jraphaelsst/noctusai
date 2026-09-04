"""Structural tests for `093_imoveis_campos_vista_completos.sql`.

The migration is a FILE, not an applied change — it needs tech-lead consent
to run against any database. So these assert its *structure* by parsing it,
which is the only honest verification available before it is applied. Same
shape as `test_migration_040_imoveis.py`, which this migration extends.

The interesting assertions are the same two classes as 040's:

1. Idempotency (`ADD COLUMN IF NOT EXISTS`) and the asymmetric CHECK
   constraints — money/measure columns reject a stored 0, count columns
   accept it. Do NOT harmonize the two conventions; that is the point.
2. The `matricula_vista` (not `matricula`) namespacing — the exact
   `origem`-style collision the contract calls out.
"""

from __future__ import annotations

from pathlib import Path

import pytest

MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "093_imoveis_campos_vista_completos.sql"
)


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
    """`code` with runs of whitespace collapsed — the DDL aligns its column
    definitions, so a substring check must not depend on that alignment."""
    return " ".join(code.split())


def test_migration_parses(sql: str):
    pglast = pytest.importorskip("pglast", reason="pglast not installed in this env")
    statements = pglast.parse_sql(sql)
    assert len(statements) > 0


def test_is_idempotent(code: str):
    assert "ADD COLUMN IF NOT EXISTS" in code
    assert "DROP CONSTRAINT IF EXISTS" in code


def test_targets_the_imoveis_table(code: str):
    assert "ALTER TABLE social_wiring.imoveis" in code


ALL_29_COLUMNS = [
    "descricao_web", "observacoes", "valor_condominio", "valor_iptu",
    "ano_construcao", "situacao", "ocupacao", "pavimentos", "posicao",
    "elevador", "portaria", "exclusivo", "aceita_permuta",
    "aceita_financiamento", "destaque_web", "super_destaque_web",
    "exibir_no_site", "chave", "zona", "regiao", "area_terreno",
    "closet", "frente", "fundos", "referencia",
    "matricula_vista", "inscricao_municipal", "video_destaque", "tour_360",
]

# CORRECTION 2026-09-04: Vista shadows these three whenever `Caracteristicas`
# rides in the same request (our sync always includes it) — they must NEVER
# become columns. Pinned negatively so a future edit re-adding one of them
# fails loudly instead of silently reintroducing a permanently-NULL column.
SHADOWED_BY_CARACTERISTICAS = ["lavabo", "copa", "escritorio"]


def test_all_29_contract_columns_are_added(code: str):
    assert len(ALL_29_COLUMNS) == 29
    for column in ALL_29_COLUMNS:
        assert f"ADD COLUMN IF NOT EXISTS {column} " in code, f"missing column: {column}"


def test_no_more_no_fewer_than_29_columns_added(code: str):
    """Pins the count itself — a copy/paste that duplicates or drops one
    column would still pass a per-name loop if it added an unlisted 30th."""
    assert code.count("ADD COLUMN IF NOT EXISTS") == 29


@pytest.mark.parametrize("column", SHADOWED_BY_CARACTERISTICAS)
def test_shadowed_fields_are_never_added_as_columns(code: str, column: str):
    """`lavabo`/`copa`/`escritorio` are `Sim`/`Nao` values Vista shadows
    (returns `null`) at the top level whenever `Caracteristicas` rides in
    the same request — which our sync always does. A column here would be
    permanently NULL while the true value sits in `caracteristicas`/
    `caracteristicas_raw`. See the 2026-09-04 CORRECTION in the header."""
    assert f"ADD COLUMN IF NOT EXISTS {column} " not in code


def test_matricula_column_is_namespaced_vista_not_bare(code: str):
    """🔴 The column is `matricula_vista`, never bare `matricula` —
    `social_wiring.imovel_dados` (migration 075) already owns a
    cartório-authored `matricula`. A bare `matricula` here would collide."""
    assert "matricula_vista" in code
    assert "ADD COLUMN IF NOT EXISTS matricula " not in code


def test_matricula_vista_has_a_provenance_comment(sql: str):
    assert "COMMENT ON COLUMN social_wiring.imoveis.matricula_vista" in sql
    assert "imovel_dados" in sql


@pytest.mark.parametrize(
    "column",
    ["valor_condominio", "valor_iptu", "ano_construcao", "area_terreno", "frente", "fundos"],
)
def test_money_and_measure_columns_reject_zero(sql: str, flat: str, column: str):
    """`"0"` on the wire means "not applicable" for these — matches the
    `valor_venda > 0` convention 040 already established."""
    assert f"imoveis_{column}_not_zero" in sql
    assert f"{column} IS NULL OR {column} > 0" in flat


@pytest.mark.parametrize("column", ["pavimentos", "closet"])
def test_count_columns_accept_zero(sql: str, flat: str, column: str):
    """The deliberate asymmetry — a real zero (e.g. zero pavimentos on a
    térreo) is data, not absence. Do NOT harmonize with the block above."""
    assert f"imoveis_{column}_non_negative" in sql
    assert f"{column} IS NULL OR {column} >= 0" in flat
    assert f"{column} IS NULL OR {column} > 0" not in flat


@pytest.mark.parametrize(
    "column",
    [
        "elevador", "portaria", "exclusivo", "aceita_permuta",
        "aceita_financiamento", "destaque_web", "super_destaque_web",
        "exibir_no_site",
    ],
)
def test_bool_columns_are_boolean_not_text(flat: str, column: str):
    assert f"{column} BOOLEAN" in flat


def test_no_rls_policy_changes(code: str):
    """CONTRACT: plain columns on an existing table need no new RLS —
    Postgres RLS is table-scoped, and the 040 policies already cover any
    column added later. This migration must not touch policies at all."""
    assert "CREATE POLICY" not in code
    assert "DROP POLICY" not in code
    assert "ENABLE ROW LEVEL SECURITY" not in code


def test_header_states_rls_was_considered(sql: str):
    """The header must say so explicitly — a silent absence of RLS changes
    reads as an oversight, not a decision."""
    assert "NO RLS CHANGES" in sql


def test_is_migration_file_only(sql: str):
    assert "MIGRATION FILE ONLY" in sql


def test_cites_the_contract(sql: str):
    assert "imoveis-vista-field-surface-CONTRACT.md" in sql
