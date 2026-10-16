"""Structural tests for the `lais_envio` migration (lais-build-contract 5). The migration is a FILE; these pin the
DECLARED shape. The guards' BEHAVIOUR is proven by the `verify_db_guards` probes (`lais_envio.*`, executed on the
real chain on PGlite by mcp/noctusai/tests/test_sw_lais_envio_probes_on_replay.py)."""
from __future__ import annotations

from pathlib import Path

import pytest
from noctusai_lib.testing.migrations import migration_path

MIGRATION = migration_path(Path(__file__).resolve().parents[1], "lais_envio")
TABLES = ("lais_envio_regras", "lais_envio_politicas", "lais_envio_entregas")


@pytest.fixture(scope="module")
def sql() -> str:
    assert MIGRATION.is_file() and MIGRATION.name.endswith("_lais_envio.sql")
    return MIGRATION.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def flat(sql: str) -> str:
    return " ".join("\n".join(l for l in sql.splitlines() if not l.strip().startswith("--")).split())


def test_parses(sql):
    pglast = pytest.importorskip("pglast")
    assert pglast.parse_sql(sql)


@pytest.mark.parametrize("table", TABLES)
def test_every_table_is_org_scoped_with_rls_a_select_policy_and_a_service_role_policy(flat, table):
    block = flat.split(f"CREATE TABLE IF NOT EXISTS social_wiring.{table}")[1].split("CREATE TABLE")[0]
    assert "org_id uuid" in block and "created_at timestamptz NOT NULL DEFAULT now()" in block
    assert f"ALTER TABLE social_wiring.{table} ENABLE ROW LEVEL SECURITY" in flat
    assert f'CREATE POLICY "{table}_select_own_org" ON social_wiring.{table} FOR SELECT TO authenticated ' \
           "USING (org_id = (SELECT public.current_org_id_for('social_wiring')))" in flat
    assert f'CREATE POLICY "{table}_service_role" ON social_wiring.{table} FOR ALL TO service_role USING (true) WITH CHECK (true)' in flat


def test_one_rule_per_operation_and_the_closed_vocabularies(flat):
    assert "CREATE UNIQUE INDEX IF NOT EXISTS lais_envio_regras_operacao_uq ON social_wiring.lais_envio_regras (org_id, operacao)" in flat
    assert "operacao IN ('compra', 'aluguel', 'ambas')" in flat
    assert "gatilho IN ('qualificado', 'visita', 'frio', 'captacao', 'invalido', 'manual')" in flat
    assert "status IN ('ok', 'erro')" in flat and "CHECK (status = 'ok' OR erro IS NOT NULL)" in flat
    assert "captacoes IN ('enviar', 'notificar')" in flat


def test_status_pagina_rows_for_both_pages_and_no_security_definer(flat):
    assert "'lais_envio'" in flat and "'lais_leads'" in flat and "origem.nome_pagina = 'whatsapp_chat'" in flat
    assert "SECURITY DEFINER" not in flat
