"""Structural tests for migration 274 `lais_conversas_v2` (lais-build-contract 9). The guards' BEHAVIOUR is proven by the
`verify_db_guards` probes (`lais_conv.*`, run on the real chain on PGlite by
mcp/noctusai/tests/test_sw_lais_conv_probes_on_replay.py)."""
from __future__ import annotations

from pathlib import Path

import pytest
from noctusai_lib.testing.migrations import migration_path

MIGRATION = migration_path(Path(__file__).resolve().parents[1], "lais_conversas_v2")
TABLES = ("lais_etiquetas", "lais_contato_etiquetas", "lais_notas", "lais_feedback")


@pytest.fixture(scope="module")
def sql() -> str:
    return MIGRATION.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def flat(sql: str) -> str:
    return " ".join("\n".join(l for l in sql.splitlines() if not l.strip().startswith("--")).split())


def test_parses(sql):
    pglast = pytest.importorskip("pglast")
    assert pglast.parse_sql(sql)


@pytest.mark.parametrize("table", TABLES)
def test_rls_select_own_org_and_service_role(flat, table):
    block = flat.split(f"CREATE TABLE IF NOT EXISTS social_wiring.{table}")[1].split("CREATE TABLE")[0]
    assert "org_id uuid NOT NULL" in block
    assert f"ALTER TABLE social_wiring.{table} ENABLE ROW LEVEL SECURITY" in flat
    assert f'CREATE POLICY "{table}_select_own_org" ON social_wiring.{table} FOR SELECT TO authenticated ' \
           "USING (org_id = (SELECT public.current_org_id_for('social_wiring')))" in flat
    assert f'CREATE POLICY "{table}_service_role" ON social_wiring.{table} FOR ALL TO service_role USING (true) WITH CHECK (true)' in flat


def test_contatos_gain_the_two_flags_defaulting_false(flat):
    for col in ("arquivado", "bloqueado"):
        assert f"ALTER TABLE social_wiring.lais_contatos ADD COLUMN IF NOT EXISTS {col} boolean NOT NULL DEFAULT false" in flat


def test_notes_are_soft_deleted_and_bounded(flat):
    assert "deleted_at timestamptz" in flat.split("lais_notas")[1]
    assert "CHECK (char_length(btrim(texto)) BETWEEN 1 AND 4000)" in flat


def test_feedback_vocabulary(flat):
    assert "CHECK (nota IN ('like', 'dislike'))" in flat


def test_the_new_tables_are_idempotent(flat):
    assert flat.count("CREATE TABLE IF NOT EXISTS") == len(TABLES)
    assert "CREATE TABLE social_wiring" not in flat
