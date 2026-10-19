"""Structural tests for ``*_atendimento_blocos_supervisao.sql`` (maya-blocks S1; parse-based --
the migration is a FILE, not an applied change). Behaviour of every guard is proven separately on a
real Postgres chain by mcp/noctusai/tests/test_sw_maya_blocos_probes_on_replay.py."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from noctusai_lib.testing.migrations import migration_path

MIGRATION = migration_path(Path(__file__).resolve().parents[1], "atendimento_blocos_supervisao")
TABLES = ("atendimento_blocos", "atendimento_handoffs", "agente_scorecards", "supervisao_config")
BLOCOS = {"sdr", "atendimento", "negociacao", "juridico", "financeiro", "contador"}


@pytest.fixture(scope="module")
def sql():
    raw = MIGRATION.read_text(encoding="utf-8")
    code = "\n".join(l for l in raw.splitlines() if not l.strip().startswith("--"))
    code = re.sub(r"--[^\n]*", "", code)
    return " ".join(code.split())


def _lista(sql: str, after: str) -> set[str]:
    m = re.search(re.escape(after) + r" IN \(([^)]*)\)", sql)
    assert m, f"closed list after {after!r} missing"
    return {v.strip().strip("'") for v in m.group(1).split(",")}


def test_parses():
    pglast = pytest.importorskip("pglast", reason="pglast not installed in this env")
    assert len(pglast.parse_sql(MIGRATION.read_text(encoding="utf-8"))) > 0


def test_forward_only_and_idempotent(sql):
    upper = sql.upper()
    for forbidden in ("DROP TABLE", "DROP COLUMN", "TRUNCATE", "DELETE FROM", "ALTER COLUMN"):
        assert forbidden not in upper
    assert "SET search_path = social_wiring, public;" in sql
    for t in TABLES:
        assert f"CREATE TABLE IF NOT EXISTS social_wiring.{t} (" in sql
    assert sql.count("CREATE INDEX") == sql.count("CREATE INDEX IF NOT EXISTS")
    assert sql.count("CREATE POLICY") == sql.count("DROP POLICY IF EXISTS")
    assert sql.count("CREATE TRIGGER") == sql.count("DROP TRIGGER IF EXISTS")
    assert sql.count("ADD CONSTRAINT") == sql.count("DROP CONSTRAINT IF EXISTS")
    assert "ADD COLUMN IF NOT EXISTS primeira_resposta_at timestamptz" in sql
    assert "SECURITY DEFINER" not in upper


@pytest.mark.parametrize("table", TABLES)
def test_rls_org_scoped_like_siblings(sql, table):
    assert f"ALTER TABLE social_wiring.{table} ENABLE ROW LEVEL SECURITY" in sql
    assert (
        f'CREATE POLICY "{table}_select_own_org" ON social_wiring.{table} '
        "FOR SELECT TO authenticated "
        "USING (org_id = (SELECT public.current_org_id_for('social_wiring')));"
    ) in sql
    assert (
        f'CREATE POLICY "{table}_service_role" ON social_wiring.{table} '
        "FOR ALL TO service_role USING (true) WITH CHECK (true);"
    ) in sql
    # writes go through the backend only: no authenticated write policy
    assert not re.search(rf"ON social_wiring\.{table} FOR (INSERT|UPDATE|DELETE|ALL) TO authenticated", sql)


def test_the_closed_block_list_is_one_list(sql):
    assert _lista(sql, "CONSTRAINT atendimento_blocos_bloco_valido CHECK (bloco") == BLOCOS
    assert _lista(sql, "CONSTRAINT agente_scorecards_bloco_valido CHECK (bloco") == BLOCOS
    assert _lista(sql, "de_bloco") == BLOCOS
    assert _lista(sql, "AND para_bloco") == BLOCOS


def test_handoff_vocabularies(sql):
    assert _lista(sql, "CONSTRAINT atendimento_handoffs_gatilho_valido CHECK (gatilho") == {"novo_lead", "movimento_etapa"}
    assert _lista(sql, "CONSTRAINT atendimento_handoffs_status_valido CHECK (status") == {"emitido", "assumido", "expirado"}
    assert "CONSTRAINT atendimento_handoffs_uma_por_origem UNIQUE (org_id, gatilho, origem_evento)" in sql


def test_handoffs_hold_references_not_personal_data(sql):
    body = re.search(r"CREATE TABLE IF NOT EXISTS social_wiring\.atendimento_handoffs \((.*?)\);", sql).group(1)
    for pii in ("nome", "telefone", "email", "chat_id", "mensagem", "resumo", "slots"):
        assert not re.search(rf"\b{pii}\b", body), pii
    for ref in ("contato_id", "lead_id", "atendimento_id", "atribuicao_id", "entrega_id"):
        assert re.search(rf"\b{ref}\s+uuid\s+REFERENCES social_wiring\.\w+ \(id\) ON DELETE SET NULL", body), ref


def test_nothing_is_on_by_default(sql):
    assert "ativo boolean NOT NULL DEFAULT false" in sql
    assert "supervisao_ativa boolean NOT NULL DEFAULT false" in sql
    for t in ("atendimento_blocos", "atendimento_handoffs", "agente_scorecards", "supervisao_config"):
        assert f"INSERT INTO social_wiring.{t}" not in sql


def test_stages_owned_by_one_block(sql):
    for guard in ("atendimento_blocos_etapas_validas", "atendimento_blocos_etapas_disjuntas"):
        assert f"CONSTRAINT = '{guard}'" in sql
    assert "BEFORE INSERT OR UPDATE ON social_wiring.atendimento_blocos" in sql


def test_scorecard_one_row_per_day_including_human_blocks(sql):
    assert "UNIQUE NULLS NOT DISTINCT (org_id, bloco, agent_key, dia)" in sql


def test_pages_seeded_in_development(sql):
    assert "('atendimento_blocos', 'desenvolvimento'," in sql
    assert "('supervisao', 'desenvolvimento'," in sql
    assert "ON CONFLICT (nome_pagina) DO NOTHING" in sql
