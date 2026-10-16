"""Structural tests for migration 280 `lais_avaliacoes_capi` (lais-build-contract 15/17). Guard BEHAVIOUR is proven by the
`lais_avaliacoes.*` verify_db_guards probes (mcp/noctusai/tests/test_sw_lais_avaliacoes_probes_on_replay.py)."""
from __future__ import annotations

from pathlib import Path

import pytest
from noctusai_lib.testing.migrations import migration_path

MIGRATION = migration_path(Path(__file__).resolve().parents[1], "lais_avaliacoes_capi")
TABELAS = ("lais_avaliacao_config", "lais_avaliacao_pedidos", "lais_avaliacoes_cache", "lais_capi_eventos")


@pytest.fixture(scope="module")
def sql() -> str:
    return MIGRATION.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def flat(sql: str) -> str:
    return " ".join("\n".join(l for l in sql.splitlines() if not l.strip().startswith("--")).split())


def test_parses(sql):
    pglast = pytest.importorskip("pglast")
    assert pglast.parse_sql(sql)


@pytest.mark.parametrize("t", TABELAS)
def test_rls_and_policies(flat, t):
    assert f"ALTER TABLE social_wiring.{t} ENABLE ROW LEVEL SECURITY" in flat
    assert f'CREATE POLICY "{t}_select_own_org" ON social_wiring.{t} FOR SELECT TO authenticated ' \
           "USING (org_id = (SELECT public.current_org_id_for('social_wiring')))" in flat
    assert f'CREATE POLICY "{t}_service_role" ON social_wiring.{t} FOR ALL TO service_role USING (true) WITH CHECK (true)' in flat


def test_vocabularies_and_status_pagina(flat):
    assert "evento IN ('lead_qualificado', 'visita_agendada', 'resposta_cliente')" in flat
    assert "status IN ('pendente', 'enviado', 'erro', 'nao_configurado')" in flat
    assert "status IN ('enviado', 'erro')" in flat
    assert "nota BETWEEN 1 AND 5" in flat
    assert "ON social_wiring.lais_capi_eventos (org_id, dedupe_key)" in flat
    assert "'lais_avaliacoes'" in flat and "origem.nome_pagina = 'whatsapp_chat'" in flat
    assert "SECURITY DEFINER" not in flat
