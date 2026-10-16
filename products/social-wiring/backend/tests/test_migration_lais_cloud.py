"""Structural tests for migration `lais_cloud` (lais-build-contract 14 / 17). The guards' BEHAVIOUR is
proven by the `verify_db_guards` probes registered for each named CHECK/UNIQUE here (and run against the
real chain on PGlite by mcp/noctusai/tests/test_sw_lais_cloud_probes_on_replay.py)."""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from noctusai_lib.testing.migrations import migration_path

MIGRATION = migration_path(Path(__file__).resolve().parents[1], "lais_cloud")
TABLES = ["lais_modelos", "lais_disparos", "lais_disparo_alvos", "lais_proprietarios_contatos"]


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
def test_every_table_is_org_scoped_with_rls_a_select_policy_and_a_service_role_policy(flat, table):
    block = flat.split(f"CREATE TABLE IF NOT EXISTS social_wiring.{table}")[1].split("CREATE TABLE")[0]
    assert "org_id uuid NOT NULL" in block and "created_at timestamptz NOT NULL DEFAULT now()" in block
    assert f"ALTER TABLE social_wiring.{table} ENABLE ROW LEVEL SECURITY" in flat
    assert f'CREATE POLICY "{table}_select_own_org" ON social_wiring.{table} FOR SELECT TO authenticated ' \
           "USING (org_id = (SELECT public.current_org_id_for('social_wiring')))" in flat
    assert f'CREATE POLICY "{table}_service_role" ON social_wiring.{table} FOR ALL TO service_role USING (true) WITH CHECK (true)' in flat


def test_transport_column_defaults_to_waha_and_is_checked(flat):
    assert "ADD COLUMN IF NOT EXISTS transporte text NOT NULL DEFAULT 'waha'" in flat
    assert "CHECK (transporte IN ('waha', 'cloud'))" in flat


def test_modelos_guards(flat):
    assert "'administrativo', 'campanha', 'cobranca', 'documentacao', 'primeiro_contato', 'reativacao', 'visita', 'outros'" in flat
    assert "CHECK (length(btrim(corpo)) BETWEEN 1 AND 1024)" in flat
    assert "status IN ('rascunho', 'enviado_meta', 'aprovado', 'rejeitado')" in flat


def test_disparos_guards(flat):
    assert "tipo IN ('remarketing', 'atualizacao_anuncios')" in flat
    assert "(tipo = 'atualizacao_anuncios') = (segmento = 'proprietarios')" in flat
    assert "status <> 'agendado' OR agendado_para IS NOT NULL" in flat


def test_alvos_status_flow_and_owner_opt_out(flat):
    assert "status IN ('pendente', 'enviado', 'respondido', 'enviado_sw', 'erro')" in flat
    assert "CHECK (opt_out = (opt_out_at IS NOT NULL))" in flat


def test_status_pagina_rows_copy_whatsapp_chat(flat):
    for page in ("lais_modelos", "lais_disparos", "lais_proprietarios"):
        assert f"('{page}'," in flat
    assert "origem.nome_pagina = 'whatsapp_chat'" in flat


def test_no_security_definer_forward_only_and_idempotent(flat):
    assert "SECURITY DEFINER" not in flat
    assert not re.search(r"\bDROP TABLE\b|\bDROP COLUMN\b|\bTRUNCATE\b", flat)
    assert "CREATE TABLE social_wiring" not in flat
    assert flat.count("DROP POLICY IF EXISTS") == flat.count("CREATE POLICY") == 8
