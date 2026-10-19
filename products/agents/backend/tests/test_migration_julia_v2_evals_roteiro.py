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


def test_no_grant_or_policy_to_browser_roles_anywhere_in_038():
    """Eval content is platform-admin-only via the API (IP): only REVOKEs and service_role policies."""
    assert not re.search(r"\bGRANT\b(?![^;]*\bTO\s+service_role)[^;]*\bTO\b[^;]*(anon|authenticated|public)", M38, re.I)
    for pol in re.findall(r"CREATE POLICY[^;]*;", M38):
        assert "TO service_role" in pol and not re.search(r"anon|authenticated|public", pol)


def test_the_db_publish_path_enforces_the_mechanism_gate():
    fn = M38[M38.index("CREATE OR REPLACE FUNCTION agents.publish_agent_version"):]
    assert "RAISE EXCEPTION 'mecanismo_required'" in fn
    for needle in ("r.driver = 'live'", "r.status = 'concluida'", "v_mec.compiled_hash IS DISTINCT FROM p_expected_hash",
                   "NOT v_mec.aprovado", "NOT v_mec.completa", "v_mec.orcamento_excedido", "exige_mecanismo"):
        assert needle in fn, needle
    flat = " ".join(fn.split())
    assert "REVOKE ALL ON FUNCTION agents.publish_agent_version(UUID, UUID, UUID, UUID, TEXT, TEXT, TEXT, JSONB) FROM PUBLIC, anon, authenticated" in flat
    assert "TO service_role" in flat


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
