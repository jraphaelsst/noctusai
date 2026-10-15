"""Structural tests for migration 267 `lais_fundacao` (lais-build-contract 2.2). The migration is a FILE;
these pin the DECLARED shape. The guards' BEHAVIOUR is proven by the `verify_db_guards` probes (registered in mcp/noctusai for every named CHECK/UNIQUE here) and the whole chain is replayed on PGlite by the pre-commit gate."""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from noctusai_lib.testing.migrations import migration_path

MIGRATION = migration_path(Path(__file__).resolve().parents[1], "lais_fundacao")
TABLES = ("lais_contatos", "lais_interacoes", "lais_acoes_aplicadas", "lais_eventos")


@pytest.fixture(scope="module")
def sql() -> str:
    assert MIGRATION.is_file() and MIGRATION.name.endswith("_lais_fundacao.sql")
    return MIGRATION.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def flat(sql: str) -> str:
    return " ".join("\n".join(l for l in sql.splitlines() if not l.strip().startswith("--")).split())


def test_parses(sql):
    pglast = pytest.importorskip("pglast")
    assert pglast.parse_sql(sql)


@pytest.mark.parametrize("table", TABLES)
def test_every_table_is_org_scoped_with_rls_a_select_policy_and_a_service_role_policy(flat, table):
    assert f"CREATE TABLE IF NOT EXISTS social_wiring.{table}" in flat
    block = flat.split(f"CREATE TABLE IF NOT EXISTS social_wiring.{table}")[1].split("CREATE TABLE")[0]
    assert "org_id uuid NOT NULL" in block and "created_at timestamptz NOT NULL DEFAULT now()" in block
    assert f"ALTER TABLE social_wiring.{table} ENABLE ROW LEVEL SECURITY" in flat
    assert f'CREATE POLICY "{table}_select_own_org" ON social_wiring.{table} FOR SELECT TO authenticated ' \
           "USING (org_id = (SELECT public.current_org_id_for('social_wiring')))" in flat
    assert f'CREATE POLICY "{table}_service_role" ON social_wiring.{table} FOR ALL TO service_role USING (true) WITH CHECK (true)' in flat


def test_contatos_columns_defaults_and_status_check(flat):
    for frag in ("slots jsonb NOT NULL DEFAULT '{}'::jsonb", "gen integer NOT NULL DEFAULT 0",
                 "status_envio text NOT NULL DEFAULT 'nao_pronto'", "canal text NOT NULL DEFAULT 'whatsapp'",
                 "lead_id uuid REFERENCES social_wiring.leads (id) ON DELETE SET NULL",
                 "connection_id uuid NOT NULL", "chat_id text NOT NULL"):
        assert frag in flat
    assert "CONSTRAINT lais_contatos_status_envio_valido CHECK (status_envio IN ('nao_pronto', 'enviado', 'erro', 'enviado_auto'))" in flat
    assert "CREATE UNIQUE INDEX IF NOT EXISTS lais_contatos_org_conexao_chat_uq ON social_wiring.lais_contatos (org_id, connection_id, chat_id)" in flat


def test_one_open_episode_per_contato_is_a_partial_unique_index(flat):
    assert ("CREATE UNIQUE INDEX IF NOT EXISTS lais_interacoes_uma_aberta_uq ON social_wiring.lais_interacoes "
            "(contato_id) WHERE encerrada_at IS NULL") in flat
    assert "contato_id uuid NOT NULL REFERENCES social_wiring.lais_contatos (id) ON DELETE CASCADE" in flat


def test_the_action_ledger_is_unique_per_org_lote_seq(flat):
    assert ("CREATE UNIQUE INDEX IF NOT EXISTS lais_acoes_aplicadas_lote_seq_uq ON social_wiring.lais_acoes_aplicadas "
            "(org_id, lote_hash, seq)") in flat


def test_eventos_guard_the_type_token_shape_and_default_lido_por(flat):
    assert "CONSTRAINT lais_eventos_tipo_valido CHECK (tipo ~ '^[a-z][a-z0-9_]{2,39}$')" in flat
    assert "lido_por uuid[] NOT NULL DEFAULT '{}'" in flat


def test_forward_only_and_idempotent(flat):
    assert not re.search(r"\bDROP TABLE\b|\bDROP COLUMN\b|\bTRUNCATE\b", flat)
    assert "CREATE TABLE social_wiring" not in flat  # every create is IF NOT EXISTS
    assert flat.count("DROP POLICY IF EXISTS") == flat.count("CREATE POLICY") == 8
