"""Structural tests for migration 281 `lais_credito` (lais-build-contract 15/17). Guard BEHAVIOUR is proven by the
`lais_credito.*` verify_db_guards probes (mcp/noctusai/tests/test_sw_lais_credito_probes_on_replay.py)."""
from __future__ import annotations

from pathlib import Path

import pytest
from noctusai_lib.testing.migrations import migration_path

MIGRATION = migration_path(Path(__file__).resolve().parents[1], "lais_credito")
TABELAS = ("lais_credito_config", "lais_credito_consentimentos", "lais_credito_analises")


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


def test_columns_guards_and_status_pagina(flat):
    for needle in (
        "apenas_aluguel boolean NOT NULL DEFAULT true", "NOT ativo OR provider IS NOT NULL",
        "status IN ('pendente', 'aprovado', 'reprovado', 'erro')", "texto_versao text NOT NULL",
        "CHECK (consentimento_aceito)", "REFERENCES social_wiring.lais_credito_consentimentos (id, contato_id, aceito)",
        "'lais_credito'", "origem.nome_pagina = 'whatsapp_chat'",
    ):
        assert needle in flat, needle
    assert "SECURITY DEFINER" not in flat
