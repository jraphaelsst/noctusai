"""Structural tests for `054_negociacoes_venda_collapse.sql`.

Same rationale as `test_migration_048_clientes_person_layer.py`: the
migration is a FILE, not an applied change (contract §7 — no dev database,
no live apply until the tech-lead + user give an explicit go-ahead), so
these assert its *structure* by parsing it — the only honest pre-apply
verification available.

Unlike `048`, this file is NOT DDL-only — its `DO $$` block collapses
existing duplicate rows — so the load-bearing assertions here are about
THAT block's shape:

1. Idempotency: only `substituida_por IS NULL` rows are candidates, so a
   row already collapsed drops out of the grouping on re-run.
2. The four-way survivor ORDER BY, in the exact order the migration
   header argues for (open beats closed FIRST, to avoid the "open deal
   hidden behind a closed one" failure mode).
3. Nothing is ever deleted — a collapse is a marker, reversible by
   nulling the two new columns.
"""
from __future__ import annotations

from pathlib import Path

import pytest

MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "migrations" / "054_negociacoes_venda_collapse.sql"
)


@pytest.fixture(scope="module")
def sql() -> str:
    return MIGRATION.read_text()


@pytest.fixture(scope="module")
def code(sql: str) -> str:
    """SQL with full-line `--` comments stripped. This file also carries a
    few trailing `-- rule N: ...` comments on the same line as SQL — those
    are real SQL comments, valid to a real parser, and deliberately left in
    place here so ordering assertions below read the real ORDER BY clause
    with its own annotations rather than a hand-trimmed copy."""
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
    """Same parser `MockSupabaseClient` uses to validate every product's
    tests (`noctusai_lib.testing.migration_parser`) — a real bug here
    would silently degrade schema validation for `negociacoes_venda`
    fleet-wide (048's delivery note documents exactly that failure mode
    for a different file)."""
    from noctusai_lib.testing.migration_parser import parse_sql

    parsed = parse_sql(sql, source_label=str(MIGRATION))
    assert "social_wiring.negociacoes_venda" in parsed
    assert {"substituida_por", "colapsada_em"} <= parsed["social_wiring.negociacoes_venda"]


# ─── the collapse columns ───────────────────────────────────────────────


def test_substituida_por_is_a_nullable_self_fk(flat: str):
    assert "ADD COLUMN IF NOT EXISTS substituida_por UUID" in flat
    assert "REFERENCES social_wiring.negociacoes_venda(id) ON DELETE SET NULL" in flat


def test_colapsada_em_exists_nullable(flat: str):
    assert "ADD COLUMN IF NOT EXISTS colapsada_em TIMESTAMPTZ" in flat
    # No NOT NULL / DEFAULT on this column — a still-visible card must have
    # neither set.
    assert "colapsada_em TIMESTAMPTZ NOT NULL" not in flat
    assert "colapsada_em TIMESTAMPTZ DEFAULT" not in flat


def test_no_column_is_ever_dropped(code: str):
    """A collapse marks, never deletes — the migration header's D3
    reversibility bar."""
    assert "DROP COLUMN" not in code.upper()


def test_no_row_is_ever_deleted_or_truncated(code: str):
    upper = code.upper()
    assert "DELETE FROM" not in upper
    assert "TRUNCATE" not in upper


# ─── the two indexes ────────────────────────────────────────────────────


def test_board_filter_index_excludes_collapsed_rows(flat: str):
    assert "idx_sw_negociacoes_venda_cliente_ativa" in flat
    assert (
        "ON social_wiring.negociacoes_venda (org_id, cliente_id) "
        "WHERE substituida_por IS NULL" in flat
    )


def test_siblings_lookup_index_is_partial_on_not_null(flat: str):
    assert "idx_sw_negociacoes_venda_substituida" in flat
    assert (
        "ON social_wiring.negociacoes_venda (substituida_por) "
        "WHERE substituida_por IS NOT NULL" in flat
    )


# ─── the collapse DO $$ block ───────────────────────────────────────────


def test_is_wrapped_in_a_do_block(code: str):
    assert "DO $$" in code
    assert "END" in code


def test_only_still_active_rows_are_candidates(code: str):
    """The idempotency guarantee: a row already collapsed on a prior run
    (`substituida_por IS NOT NULL`) drops out of the grouping here, so a
    second run against unchanged data is a no-op."""
    assert "nv.substituida_por IS NULL" in code


def test_only_rows_with_a_cliente_id_are_candidates(code: str):
    assert "nv.cliente_id IS NOT NULL" in code


def test_survivor_order_is_open_then_stage_then_oldest_then_id(flat: str):
    """The exact four-way tiebreak the migration header argues for, IN
    ORDER: open-beats-closed must come FIRST, or a closed negociação that
    reached a later stage could outrank a currently-open one and vanish it
    from the board (`obter_funil` only shows `status = 'aberta'`)."""
    idx = flat.index("ORDER BY", flat.index("ranqueadas"))
    window = flat[idx : idx + 260]
    i_status = window.index("(status = 'aberta') DESC")
    i_posicao = window.index("posicao DESC")
    i_created = window.index("created_at ASC")
    i_id = window.index("id ASC")
    assert i_status < i_posicao < i_created < i_id


def test_posicao_is_resolved_from_this_orgs_own_stage_rows(code: str):
    """Never a hardcoded stage-slug list — stages are user-editable rows
    (migration `034`'s whole point)."""
    assert "pipeline_stages" in code
    assert "ps.posicao" in code
    assert "COALESCE(ps.posicao, -1)" in code


def test_no_hardcoded_stage_slug_appears_in_the_ranking_logic(code: str):
    for slug in ("'novo'", "'contato'", "'qualificado'", "'proposta'", "'negociacao'", "'fechado'"):
        assert slug not in code


def test_update_only_writes_the_two_collapse_columns(flat: str):
    assert "SET substituida_por = a.sobrevivente_id" in flat
    assert "colapsada_em = now()" in flat


def test_update_touches_only_rows_ranked_below_the_survivor(code: str):
    """`rn = 1` is the survivor (never written); `rn > 1` are the losers —
    and only within a group that actually has more than one member
    (`grupo_tamanho > 1`), so a lone negociação for a cliente is never
    touched."""
    assert "WHERE rn = 1" in code
    assert "r.rn > 1 AND r.grupo_tamanho > 1" in code


def test_notify_pgrst_reload_schema(sql: str):
    assert "NOTIFY pgrst, 'reload schema';" in sql


def test_is_idempotent_by_construction_no_destructive_statements(code: str):
    """Forward-only, matching every migration in this product: every DDL
    statement is `IF NOT EXISTS` / `IF EXISTS`-guarded."""
    assert "ADD COLUMN IF NOT EXISTS substituida_por" in code
    assert "ADD COLUMN IF NOT EXISTS colapsada_em" in code
    assert "CREATE INDEX IF NOT EXISTS idx_sw_negociacoes_venda_cliente_ativa" in code
    assert "CREATE INDEX IF NOT EXISTS idx_sw_negociacoes_venda_substituida" in code
