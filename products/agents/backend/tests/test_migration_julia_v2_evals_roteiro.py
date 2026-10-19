"""Structural pins for migration 038 (Julia v2 A-EVAL). Behaviour is proven by the chain replay."""
from __future__ import annotations

import re
from pathlib import Path

from noctusai_lib.testing.migrations import migration_sql

ROOT = Path(__file__).resolve().parents[1]
M38 = migration_sql(ROOT, "julia_v2_evals_roteiro")


def test_eval_cases_gain_the_four_columns_and_their_checks():
    for col in ("suite", "k", "roteiro", "asserts"):
        assert re.search(rf"ADD COLUMN IF NOT EXISTS {col} ", M38), col
    assert "CHECK (suite IN ('mecanismo', 'comportamento'))" in M38
    assert "CHECK (k BETWEEN 1 AND 10)" in M38
    assert "eval_cases_criterios_ou_mecanismo" in M38 and "eval_cases_mecanismo_conteudo" in M38


def test_new_tables_are_service_role_only():
    for t in ("eval_mecanismo_runs", "eval_mecanismo_execucoes"):
        assert f"CREATE TABLE IF NOT EXISTS agents.{t}" in M38
        assert f"ALTER TABLE agents.{t} ENABLE ROW LEVEL SECURITY" in M38, t
        assert f"REVOKE ALL ON agents.{t} FROM anon, authenticated" in M38, t
        assert re.search(rf"ON agents\.{t}\s+FOR ALL TO service_role USING \(true\) WITH CHECK \(true\)", M38), t
    assert not re.search(r"GRANT\s+(ALL|INSERT|UPDATE|DELETE)[^;]*TO\s+authenticated", M38)


def test_scripted_content_is_not_readable_by_org_members():
    grant = M38[M38.index("GRANT SELECT ("):]
    grant = grant[: grant.index("TO authenticated")]
    assert "roteiro" not in grant and "asserts" not in grant and "suite" in grant


def test_only_a_finished_complete_under_budget_all_green_run_can_be_approved():
    block = M38[M38.index("eval_mecanismo_runs_aprovado_consistente"):]
    block = block[: block.index(");")]
    for needle in ("status = 'concluida'", "completa", "NOT orcamento_excedido", "casos_aprovados = total_casos"):
        assert needle in block, needle
    assert "driver IN ('live', 'fake')" in M38


def test_judge_run_creation_only_resolves_comportamento_cases_and_keeps_the_service_role_only_grant():
    fn = M38[M38.index("CREATE OR REPLACE FUNCTION agents.create_eval_run"):]
    assert fn.count("c.suite = 'comportamento'") == 2
    flat = " ".join(fn.split())
    assert "REVOKE ALL ON FUNCTION agents.create_eval_run(UUID, UUID, UUID, TEXT, NUMERIC, UUID[], UUID, TEXT, NUMERIC) FROM PUBLIC, anon, authenticated" in flat
    assert "TO service_role" in flat


def test_agent_flags_default_off_so_existing_agents_keep_the_old_gate():
    assert "exige_mecanismo BOOLEAN NOT NULL DEFAULT false" in M38
    assert "comportamento_bloqueia BOOLEAN NOT NULL DEFAULT false" in M38
