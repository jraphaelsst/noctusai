"""Eval consolidation migration (072): service-role only, thresholds as rows, append-only history, fail-safe dependency column."""
from __future__ import annotations

from pathlib import Path

from noctusai_lib.testing.migrations import migration_sql

from app.studio.consolidacao import CHAVES_CONFIG, DEFAULT_CONFIG, TAGS_CRITICAS

SQL = migration_sql(Path(__file__).resolve().parents[1], "eval_consolidacao")
TABELAS = ("eval_consolidacao_config", "eval_case_estado", "eval_case_transicoes", "eval_casos_pulados")


def test_every_new_table_is_service_role_only():
    for t in TABELAS:
        assert f"CREATE TABLE IF NOT EXISTS agents.{t}" in SQL
    for t in TABELAS:  # explicit statements per table (no dynamic policy DDL in a DO block)
        assert f"ALTER TABLE agents.{t} ENABLE ROW LEVEL SECURITY" in SQL
        assert f"REVOKE ALL ON agents.{t} FROM anon, authenticated" in SQL
        assert f'CREATE POLICY "service_role_bypass" ON agents.{t} FOR ALL TO service_role USING (true) WITH CHECK (true)' in SQL
    assert all(t.startswith("eval_") for t in TABELAS)  # `agents.eval_*` is declared Platform-IP by the access-tier registry


def test_thresholds_are_seeded_as_config_rows_matching_the_code_defaults():
    for chave in CHAVES_CONFIG:
        assert f"'{chave}', {DEFAULT_CONFIG[chave]}," in SQL
    assert DEFAULT_CONFIG == {"consolidar_normal": 5, "consolidar_critico": 10, "revalidar_normal": 3, "revalidar_critico": 6}


def test_dependencies_are_nullable_failsafe_and_criticality_is_constrained():
    assert "ADD COLUMN IF NOT EXISTS depende_de JSONB NULL" in SQL
    assert "criticidade IN ('normal', 'critico')" in SQL
    assert "depende_de IS NULL OR jsonb_typeof(depende_de) = 'array'" in SQL


def test_history_refuses_updates_and_the_criticality_proposal_matches_the_code_tag_list():
    assert "BEFORE UPDATE ON agents.eval_case_transicoes" in SQL and "is append-only" in SQL
    body = SQL[SQL.index("tags && ARRAY["):SQL.index("]::text[]")]
    assert {t for t in TAGS_CRITICAS} == {t.strip().strip("'") for t in body.replace("tags && ARRAY[", "").replace("\n", "").split(",")}


def test_proposal_never_overwrites_a_human_decision():
    assert "WHERE criticidade_origem = 'padrao'" in SQL and "criticidade_origem = 'sugerida'" in SQL


def test_runs_carry_the_per_part_hashes_for_both_suites():
    assert SQL.count("ADD COLUMN IF NOT EXISTS partes JSONB NULL") == 2
    assert "ALTER TABLE agents.eval_mecanismo_runs" in SQL and "ALTER TABLE agents.eval_runs" in SQL
