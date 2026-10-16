"""Structural tests for migration 278 `lais_captacoes` (lais-build-contract 10). Guard BEHAVIOUR is proven by the
`lais_captacao.*` verify_db_guards probes (mcp/noctusai/tests/test_sw_lais_captacao_probes_on_replay.py)."""
from __future__ import annotations

from pathlib import Path

import pytest
from noctusai_lib.testing.migrations import migration_path

MIGRATION = migration_path(Path(__file__).resolve().parents[1], "lais_captacoes")


@pytest.fixture(scope="module")
def sql() -> str:
    return MIGRATION.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def flat(sql: str) -> str:
    return " ".join("\n".join(l for l in sql.splitlines() if not l.strip().startswith("--")).split())


def test_parses(sql):
    pglast = pytest.importorskip("pglast")
    assert pglast.parse_sql(sql)


def test_rls_and_policies(flat):
    t = "lais_captacoes"
    assert f"ALTER TABLE social_wiring.{t} ENABLE ROW LEVEL SECURITY" in flat
    assert f'CREATE POLICY "{t}_select_own_org" ON social_wiring.{t} FOR SELECT TO authenticated ' \
           "USING (org_id = (SELECT public.current_org_id_for('social_wiring')))" in flat
    assert f'CREATE POLICY "{t}_service_role" ON social_wiring.{t} FOR ALL TO service_role USING (true) WITH CHECK (true)' in flat


def test_vocabularies_columns_and_status_pagina(flat):
    assert "status IN ('nova', 'registrada', 'descartada')" in flat
    assert "operacao IS NULL OR operacao IN ('venda', 'aluguel')" in flat
    assert "status <> 'registrada' OR imovel_id IS NOT NULL" in flat
    assert "imovel_codigo text" in flat and "'lais_captacao'" in flat and "origem.nome_pagina = 'whatsapp_chat'" in flat
    assert "SECURITY DEFINER" not in flat
