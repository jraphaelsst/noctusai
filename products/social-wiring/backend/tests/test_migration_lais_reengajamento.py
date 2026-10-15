"""Structural tests for the `lais_reengajamento` migration (lais-build-contract 6). The migration is a FILE; these
pin the DECLARED shape. The guards' BEHAVIOUR is proven by the `verify_db_guards` probes (`lais_reeng.*`, executed on
the real chain on PGlite by mcp/noctusai/tests/test_sw_lais_reeng_probes_on_replay.py)."""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from noctusai_lib.testing.migrations import migration_path

MIGRATION = migration_path(Path(__file__).resolve().parents[1], "lais_reengajamento")
TABLES = ("lais_reengajamento_config", "lais_reguas", "lais_regua_tentativas")


@pytest.fixture(scope="module")
def sql() -> str:
    assert MIGRATION.is_file() and MIGRATION.name.endswith("_lais_reengajamento.sql")
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


def test_config_is_one_row_per_org_with_the_two_grids(flat):
    assert "org_id uuid PRIMARY KEY" in flat.split("lais_reengajamento_config")[1]
    assert "CHECK (minutos_intervalo BETWEEN 5 AND 60 AND minutos_intervalo % 5 = 0)" in flat
    assert "CHECK (horas_intervalo BETWEEN 1 AND 11)" in flat


def test_three_attempts_is_structural(flat):
    assert "CHECK (ordem BETWEEN 1 AND 3)" in flat
    assert "CREATE UNIQUE INDEX IF NOT EXISTS lais_regua_tentativas_ordem_uq ON social_wiring.lais_regua_tentativas (regua_id, ordem)" in flat
    assert "espera_unidade text NOT NULL DEFAULT 'dias'" in flat and "IN ('minutos', 'horas', 'dias')" in flat
    assert "num_nonnulls(texto, template_id) = 1" in flat and "BETWEEN 1 AND 1024" in flat


def test_the_active_regua_guard_is_two_triggers_without_security_definer(flat):
    assert "BEFORE INSERT OR UPDATE OF ativa ON social_wiring.lais_reguas" in flat
    assert "BEFORE UPDATE OF ativa, regua_id OR DELETE ON social_wiring.lais_regua_tentativas" in flat
    assert "SECURITY DEFINER" not in flat
    assert flat.count("SET search_path = social_wiring, public AS") == 2


def test_status_pagina_copies_whatsapp_chat(flat):
    assert "('lais_reengajamento', 'Lais — Reengajamento')" in flat and "origem.nome_pagina = 'whatsapp_chat'" in flat


def test_forward_only_and_idempotent(flat):
    assert not re.search(r"\bDROP TABLE\b|\bDROP COLUMN\b|\bTRUNCATE\b", flat)
    assert "CREATE TABLE social_wiring" not in flat
    assert flat.count("DROP POLICY IF EXISTS") == flat.count("CREATE POLICY") == 6
    assert flat.count("DROP TRIGGER IF EXISTS") == flat.count("CREATE TRIGGER") == 2
