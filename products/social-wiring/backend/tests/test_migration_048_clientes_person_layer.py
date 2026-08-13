"""Structural tests for `048_clientes_person_layer.sql`.

Same rationale as `test_migration_040_imoveis.py`: the migration is a FILE,
not an applied change (contract §7 — no dev database, no live apply until
the tech-lead gets an explicit go-ahead), so these assert its *structure*
by parsing it — the only honest pre-apply verification available. Three
classes of assertion, and the last two are the load-bearing ones for this
particular file:

1. The invariants every social_wiring table must hold (RLS on,
   `current_org_id()` not `auth.jwt()`, service_role write policy).
2. The 🔴 PARTIAL unique index on `clientes` — a plain UNIQUE would be
   satisfied by all 399 keyless nulls (contract §2) and silently permit a
   real duplicate key later.
3. That `negociacoes_venda`'s repoint is decoupled from data population:
   `cliente_id` is added and `exactly_one_origin` is dropped
   unconditionally (no dependency on a backfill having run), while
   `lead_id`/`meta_ads_lead_id` are kept.
"""
from __future__ import annotations

from pathlib import Path

import pytest

MIGRATION = (
    Path(__file__).resolve().parents[1] / "migrations" / "048_clientes_person_layer.sql"
)


@pytest.fixture(scope="module")
def sql() -> str:
    return MIGRATION.read_text()


@pytest.fixture(scope="module")
def code(sql: str) -> str:
    """SQL with `--` comment lines stripped — prose about `auth.jwt()` in
    the rationale must never satisfy (or trip) a check about actual SQL."""
    return "\n".join(l for l in sql.splitlines() if not l.strip().startswith("--"))


@pytest.fixture(scope="module")
def flat(code: str) -> str:
    """`code` with runs of whitespace collapsed — DDL alignment must not
    affect substring checks."""
    return " ".join(code.split())


def test_migration_parses(sql: str):
    pglast = pytest.importorskip("pglast", reason="pglast not installed in this env")
    statements = pglast.parse_sql(sql)
    assert len(statements) > 0


def test_migration_parses_via_the_mock_schema_cache_parser(sql: str):
    """The SAME regex-based parser `MockSupabaseClient` uses to validate
    every product's tests (`noctusai_lib.testing._schema_cache`) must
    resolve this file's new/altered tables — otherwise every OTHER
    product's test suite silently loses schema validation for whatever
    this file touches, per that module's graceful-degradation contract.
    A real bug in this exact file (a `--` inside a `COMMENT ON COLUMN`
    string literal corrupting the shared line-comment stripper) was caught
    this way during Slice A — see the delivery note."""
    from noctusai_lib.testing.migration_parser import parse_sql

    parsed = parse_sql(sql, source_label=str(MIGRATION))
    assert "social_wiring.clientes" in parsed
    assert "social_wiring.cliente_touches" in parsed
    assert "social_wiring.cliente_merges" in parsed
    assert {"id", "org_id", "chave_canonica", "chave_tipo", "identidade_incerta"} <= parsed[
        "social_wiring.clientes"
    ]
    assert {"origem_tabela", "origem_id", "cliente_id"} <= parsed["social_wiring.cliente_touches"]
    assert {"cliente_id_sobrevivente", "cliente_id_absorvido", "touches_movidos"} <= parsed[
        "social_wiring.cliente_merges"
    ]


@pytest.mark.parametrize(
    "table", ["clientes", "cliente_touches", "cliente_merges"]
)
def test_rls_is_enabled_with_org_scoped_read(code: str, table: str):
    assert f"ALTER TABLE social_wiring.{table} ENABLE ROW LEVEL SECURITY" in code
    assert f'"{table}_select_own_org" ON social_wiring.{table}' in code
    assert f'"{table}_service_role" ON social_wiring.{table}' in code


def test_rls_never_keys_off_jwt_or_user_metadata(code: str):
    assert "auth.jwt()" not in code
    assert "user_metadata" not in code


def test_reads_use_current_org_id(code: str):
    assert code.count("current_org_id()") >= 3  # one per new table's SELECT policy


def test_service_role_can_write(code: str):
    assert code.count("TO service_role") >= 3


def test_is_idempotent(code: str):
    assert "CREATE TABLE IF NOT EXISTS" in code
    assert "DROP POLICY IF EXISTS" in code
    assert "ADD COLUMN IF NOT EXISTS" in code
    assert "DROP CONSTRAINT IF EXISTS" in code


# ─── clientes -- the partial unique + the 399-keyless / review-groups shape ──


def test_clientes_chave_canonica_is_nullable(flat: str):
    """No `NOT NULL` on the column itself — the 399 keyless leads (§2) and
    every unresolved review-group cliente need a real NULL here."""
    assert "chave_canonica TEXT," in flat
    assert "chave_canonica TEXT NOT NULL" not in flat


def test_clientes_unique_key_is_a_partial_index_not_a_plain_unique(sql: str, flat: str):
    """🔴 The load-bearing assertion. A plain `UNIQUE (org_id,
    chave_canonica)` table constraint is satisfied by any number of NULLs
    and would silently let a second real duplicate key in later."""
    assert "CREATE UNIQUE INDEX IF NOT EXISTS uq_sw_clientes_org_chave" in sql
    assert (
        "ON social_wiring.clientes (org_id, chave_canonica) WHERE chave_canonica IS NOT NULL"
        in flat
    )
    # And NOT a plain table-level UNIQUE constraint on the same columns —
    # that shape is exactly the defect this migration exists to prevent.
    assert "UNIQUE (org_id, chave_canonica)," not in flat
    assert "CONSTRAINT clientes_chave_unique UNIQUE" not in flat


def test_identidade_incerta_cannot_coexist_with_a_real_key(flat: str):
    assert "CONSTRAINT clientes_incerta_implies_no_key" in flat
    assert "CHECK (NOT identidade_incerta OR chave_canonica IS NULL)" in flat


def test_chave_tipo_matches_chave_canonica_nullness(flat: str):
    assert "CONSTRAINT clientes_chave_tipo_matches_chave" in flat
    assert "CHECK ((chave_canonica IS NULL) = (chave_tipo IS NULL))" in flat


def test_chave_tipo_is_constrained_to_telefone_or_email(flat: str):
    assert "chave_tipo TEXT CHECK (chave_tipo IN ('telefone', 'email'))" in flat


# ─── cliente_touches -- losslessness substrate ───────────────────────────


def test_cliente_touches_origem_is_a_polymorphic_pair_not_two_fks(flat: str):
    """Mirrors `pipeline_movimentos.entidade_id`'s established rationale in
    this SAME file's product (034): one column cannot reference two
    tables whose PK types differ (leads.id is UUID, meta_ads_leads.id is
    TEXT)."""
    assert "origem_tabela TEXT NOT NULL CHECK (origem_tabela IN ('leads', 'meta_ads_leads'))" in flat
    assert "origem_id TEXT NOT NULL" in flat


def test_cliente_touches_origem_is_idempotency_key(sql: str, flat: str):
    assert "CREATE UNIQUE INDEX IF NOT EXISTS uq_sw_cliente_touches_origem" in sql
    assert "ON social_wiring.cliente_touches (origem_tabela, origem_id)" in flat


def test_cliente_touches_carries_denormalized_chave_for_review_recovery(flat: str):
    """This is what lets a null-keyed review-candidate cliente still be
    found by the real key it shares with its siblings, with no join back
    to leads/meta_ads_leads."""
    assert "idx_sw_cliente_touches_org_chave" in flat
    assert "ON social_wiring.cliente_touches (org_id, chave_canonica)" in flat


def test_cliente_touches_deletes_cascade_from_clientes(flat: str):
    assert "REFERENCES social_wiring.clientes(id) ON DELETE CASCADE" in flat


# ─── cliente_merges -- D3 reversibility ──────────────────────────────────


def test_cliente_merges_motivo_is_c1_through_c6(flat: str):
    assert (
        "CHECK (motivo IN ('C1', 'C2', 'C3', 'C4', 'C5', 'C6'))" in flat
    )


def test_cliente_merges_absorbed_id_is_not_a_foreign_key(sql: str):
    """It must survive the absorbed row's own deletion -- see the
    COMMENT ON COLUMN this migration attaches to it."""
    assert "cliente_id_absorvido          UUID NOT NULL," in sql
    assert "cliente_id_absorvido UUID NOT NULL REFERENCES" not in sql.replace("\n", " ")


def test_cliente_merges_snapshot_columns_exist_for_undo(flat: str):
    for col in (
        "nome_absorvido",
        "chave_canonica_absorvido",
        "chave_tipo_absorvido",
        "identidade_incerta_absorvido",
        "touches_movidos",
    ):
        assert col in flat


def test_touches_movidos_is_jsonb_not_a_fixed_column_set(flat: str):
    assert "touches_movidos JSONB NOT NULL DEFAULT '[]'::jsonb" in flat


def test_desfeito_em_exists_for_the_undo_marker(flat: str):
    assert "desfeito_em TIMESTAMPTZ," in flat


# ─── negociacoes_venda -- the repoint, decoupled from data population ────


def test_cliente_id_added_nullable(flat: str):
    assert "ADD COLUMN IF NOT EXISTS cliente_id UUID" in flat
    assert "REFERENCES social_wiring.clientes(id) ON DELETE SET NULL" in flat


def test_exactly_one_origin_check_is_dropped(sql: str):
    assert (
        "DROP CONSTRAINT IF EXISTS negociacoes_venda_exactly_one_origin" in sql
    )


def test_origin_columns_are_kept_not_dropped(code: str):
    """§4: dropping them is lossy and nothing in Phase 1 needs it."""
    assert "DROP COLUMN" not in code.upper().replace("ADD COLUMN", "")


def test_cliente_id_repoint_has_no_ordering_dependency_on_a_backfill(sql: str):
    """Both statements are unconditional DDL -- no `IF EXISTS (SELECT ...
    FROM clientes)` guard, no dependency on any row existing yet. Adding
    the column and dropping the CHECK are both safe the moment this file
    applies, well before any backfill runs (see the migration header)."""
    idx_add = sql.index("ADD COLUMN IF NOT EXISTS cliente_id")
    idx_drop = sql.index("DROP CONSTRAINT IF EXISTS negociacoes_venda_exactly_one_origin")
    between = sql[idx_add:idx_drop]
    assert "SELECT" not in between.upper()
    assert "WHERE EXISTS" not in between.upper()


def test_no_data_is_written_by_this_file(code: str):
    """DDL only -- the resolution algorithm's population step is Python
    (`clientes_service.run_backfill`), never SQL in this file. See the
    migration header for why."""
    upper = code.upper()
    assert "INSERT INTO" not in upper
    assert "UPDATE SOCIAL_WIRING." not in upper
