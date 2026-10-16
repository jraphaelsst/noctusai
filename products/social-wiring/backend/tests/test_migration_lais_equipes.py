"""Structural tests for migration 276 `lais_equipes` (lais-build-contract 13). The guards' BEHAVIOUR is proven by the
`verify_db_guards` probes (replayed on PGlite in mcp/noctusai/tests/test_sw_lais_equipes_probes_on_replay.py)."""
from __future__ import annotations

from pathlib import Path

import pytest
from noctusai_lib.testing.migrations import migration_path

MIGRATION = migration_path(Path(__file__).resolve().parents[1], "lais_equipes")
TABELAS = ("lais_equipes", "lais_equipe_membros", "lais_distribuicao_cursor", "lais_atribuicoes")


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
def test_rls_select_own_org_and_service_role(flat, t):
    assert f"ALTER TABLE social_wiring.{t} ENABLE ROW LEVEL SECURITY" in flat
    assert f'CREATE POLICY "{t}_select_own_org" ON social_wiring.{t} FOR SELECT TO authenticated ' \
           "USING (org_id = (SELECT public.current_org_id_for('social_wiring')))" in flat
    assert f'CREATE POLICY "{t}_service_role" ON social_wiring.{t} FOR ALL TO service_role USING (true) WITH CHECK (true)' in flat


def test_columns_and_guards(flat):
    assert "modo text NOT NULL DEFAULT 'funil'" in flat
    assert "CONSTRAINT lais_equipes_modo_valido CHECK (modo IN ('funil', 'julia'))" in flat
    assert "PRIMARY KEY (equipe_id, user_id)" in flat
    assert "ultimo_user_id uuid" in flat


def test_no_security_definer(flat):
    assert "SECURITY DEFINER" not in flat


def test_status_pagina_row_copies_whatsapp_chat(flat):
    assert "'lais_equipes'" in flat and "origem.nome_pagina = 'whatsapp_chat'" in flat
