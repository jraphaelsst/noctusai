"""Agents 038: the DB publish path enforces the mechanism gate (Julia v2 A-EVAL), on the REAL chain on PGlite.

A direct `agents.publish_agent_version` call must refuse (`mecanismo_required`) unless the newest LIVE run of the
version, for the exact hash, finished complete, under budget and fully green -- so the router is not the only gate.
Also: the judge-run creation never resolves a mecanismo case, and a mecanismo case needs roteiro + asserts.
"""
from __future__ import annotations

from pathlib import Path

from settings import REPO_ROOT
from tools.noctus.dev import migration_replay as mr

_A = "a0000000-0000-4000-8000-0000000000bb"  # not the 033 fixture org
_AG = "a7000000-0000-4000-8000-000000000001"
_AG_PLAIN = "a8000000-0000-4000-8000-000000000002"
_V = "b1000000-0000-4000-8000-000000000001"
_V_PLAIN = "b2000000-0000-4000-8000-000000000002"
_U = "c0000000-0000-4000-8000-00000000000c"
_C = "d1000000-0000-4000-8000-000000000001"
_TARGET = "products/agents/backend/migrations/038_julia_v2_evals_roteiro.sql"


def _step(name: str, sql: str) -> dict:
    return {"product": "agents", "file": f"step:{name}", "sql": sql, "mode": "file", "twice": False}


def _publish(version: str, override: str = "NULL") -> str:
    return (f"PERFORM agents.publish_agent_version('{_A}', '{version}', '{_U}', NULL, {override}, 'sha256:1111111111111111111111111111111111111111111111111111111111111111', 'texto', '{{}}'::jsonb);")


def _refused_with(code: str, body: str) -> str:
    return f"""
DO $t$ BEGIN
  BEGIN
    {body}
    RAISE EXCEPTION 'ASSERT not refused';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM <> '{code}' THEN RAISE EXCEPTION 'ASSERT wrong refusal: %', SQLERRM; END IF;
  END;
END $t$;"""


_OVERRIDE = "'override com motivo suficientemente longo'"
def _run(hash_: str, driver: str, total: int, ok: int, completa: str, aprovado: str, finished: str) -> str:
    return (
        "INSERT INTO agents.eval_mecanismo_runs (org_id, agent_id, version_id, compiled_hash, driver, status, total_casos, "
        "casos_aprovados, completa, aprovado, orcamento_excedido, started_by, finished_at) VALUES "
        f"('{_A}', '{_AG}', '{_V}', '{hash_}', '{driver}', 'concluida', {total}, {ok}, {completa}, {aprovado}, false, '{_U}', {finished});"
    )


ASSERTIONS = [
    _step("seed", f"""
INSERT INTO agents.agents (id, org_id, key, nome, runtime, ativo) VALUES
  ('{_AG}', '{_A}', 'julia', 'Julia', 'claude_sdk', false), ('{_AG_PLAIN}', '{_A}', 'plain', 'Plain', 'claude_sdk', false);
INSERT INTO agents.agent_versions (id, org_id, agent_id, versao, status, model, effort, created_by, compiled_hash) VALUES
  ('{_V}', '{_A}', '{_AG}', 1, 'rascunho', 'claude-sonnet-5', 'medium', '{_U}', 'sha256:1111111111111111111111111111111111111111111111111111111111111111'),
  ('{_V_PLAIN}', '{_A}', '{_AG_PLAIN}', 1, 'rascunho', 'claude-sonnet-5', 'medium', '{_U}', 'sha256:1111111111111111111111111111111111111111111111111111111111111111');
UPDATE agents.agent_versions SET compiled_hash = 'sha256:1111111111111111111111111111111111111111111111111111111111111111' WHERE id IN ('{_V}', '{_V_PLAIN}');
INSERT INTO agents.eval_cases (id, org_id, agent_id, slug, titulo, entrada, criterios, suite, k, roteiro, asserts) VALUES
  ('{_C}', '{_A}', '{_AG}', 'm1', 't', 'e', '{{}}'::jsonb, 'mecanismo', 3, '{{"turnos":[{{"lead":"oi"}}]}}'::jsonb, '{{"sem_violacoes": true}}'::jsonb);
"""),
    _step("a_mecanismo_case_needs_roteiro_and_asserts", _refused_with(
        'new row for relation "eval_cases" violates check constraint "eval_cases_mecanismo_conteudo"',
        f"INSERT INTO agents.eval_cases (org_id, agent_id, slug, titulo, entrada, criterios, suite) VALUES ('{_A}', '{_AG}', 'm2', 't', 'e', '{{}}'::jsonb, 'mecanismo');")),
    _step("a_comportamento_case_still_needs_criteria", _refused_with(
        'new row for relation "eval_cases" violates check constraint "eval_cases_criterios_ou_mecanismo"',
        f"INSERT INTO agents.eval_cases (org_id, agent_id, slug, titulo, entrada, criterios) VALUES ('{_A}', '{_AG}', 'c1', 't', 'e', '{{}}'::jsonb);")),
    _step("judge_run_never_resolves_a_mecanismo_case", _refused_with(
        "no_eval_cases", f"PERFORM agents.create_eval_run('{_A}', '{_AG}', '{_V}', 'sha256:1111111111111111111111111111111111111111111111111111111111111111', 0.8, NULL, '{_U}');")),
    _step("no_run_means_refused_even_with_an_override", _refused_with("mecanismo_required", _publish(_V, _OVERRIDE))),
    _step("a_fake_driver_run_does_not_open_it", f"""
{_run('sha256:1111111111111111111111111111111111111111111111111111111111111111', 'fake', 1, 1, 'true', 'true', "now()")}
""" + _refused_with("mecanismo_required", _publish(_V, _OVERRIDE))),
    _step("a_run_of_another_hash_does_not_open_it", f"""
{_run('sha256:0000000000000000000000000000000000000000000000000000000000000000', 'live', 1, 1, 'true', 'true', "now()")}
""" + _refused_with("mecanismo_required", _publish(_V, _OVERRIDE))),
    _step("a_red_newest_live_run_blocks_even_after_an_older_green_one", f"""
{_run('sha256:1111111111111111111111111111111111111111111111111111111111111111', 'live', 1, 1, 'true', 'true', "now() - interval '1 hour'")}
{_run('sha256:1111111111111111111111111111111111111111111111111111111111111111', 'live', 1, 0, 'true', 'false', "now()")}
""" + _refused_with("mecanismo_required", _publish(_V, _OVERRIDE))),
    _step("a_case_added_after_the_run_is_not_covered", f"""
DELETE FROM agents.eval_mecanismo_runs WHERE version_id = '{_V}';
{_run('sha256:1111111111111111111111111111111111111111111111111111111111111111', 'live', 1, 1, 'true', 'true', "now()")}
INSERT INTO agents.eval_cases (org_id, agent_id, slug, titulo, entrada, criterios, suite, roteiro, asserts) VALUES
  ('{_A}', '{_AG}', 'm3', 't', 'e', '{{}}'::jsonb, 'mecanismo', '{{"turnos":[{{"lead":"oi"}}]}}'::jsonb, '{{"sem_violacoes": true}}'::jsonb);
""" + _refused_with("mecanismo_required", _publish(_V, _OVERRIDE)) + "\nUPDATE agents.eval_cases SET ativo = false WHERE slug = 'm3';"),
    _step("a_green_complete_live_run_for_the_hash_opens_it", f"""
DO $t$ BEGIN
  {_publish(_V, _OVERRIDE)}
  IF (SELECT status FROM agents.agent_versions WHERE id = '{_V}') <> 'ativa' THEN RAISE EXCEPTION 'ASSERT must be published'; END IF;
END $t$;"""),
    _step("the_exige_flag_blocks_an_agent_with_no_cases", f"""
UPDATE agents.agents SET exige_mecanismo = true WHERE id = '{_AG_PLAIN}';
""" + _refused_with("mecanismo_required", _publish(_V_PLAIN, _OVERRIDE)) + f"""
UPDATE agents.agents SET exige_mecanismo = false WHERE id = '{_AG_PLAIN}';"""),
    _step("an_agent_without_the_requirement_is_unaffected", f"""
DO $t$ BEGIN
  {_publish(_V_PLAIN, _OVERRIDE)}
  IF (SELECT status FROM agents.agent_versions WHERE id = '{_V_PLAIN}') <> 'ativa' THEN RAISE EXCEPTION 'ASSERT plain agent must publish'; END IF;
END $t$;"""),
    _step("an_approved_run_cannot_be_inconsistent", _refused_with(
        'new row for relation "eval_mecanismo_runs" violates check constraint "eval_mecanismo_runs_aprovado_consistente"',
        f"INSERT INTO agents.eval_mecanismo_runs (org_id, agent_id, version_id, compiled_hash, driver, status, total_casos, casos_aprovados, completa, aprovado, started_by) "
        f"VALUES ('{_A}', '{_AG}', '{_V}', 'sha256:1111111111111111111111111111111111111111111111111111111111111111', 'live', 'concluida', 2, 1, true, true, '{_U}');")),
]


def test_db_publish_enforces_the_mechanism_gate_on_the_real_chain(pglite):
    root = Path(REPO_ROOT)
    steps = mr._steps_for(root, "agents", {_TARGET}, "worktree", {})
    steps.extend(ASSERTIONS)
    res = mr._run_harness(steps, 900, None)
    assert res.get("ok"), res
    by_file = {(s["product"], s["file"]): s for s in res["steps"]}
    assert not by_file[("agents", "038_julia_v2_evals_roteiro.sql")]["failures"]
    failed = {n: s["failures"][0]["error"] for (p, n), s in by_file.items() if p == "agents" and n.startswith("step:") and s["failures"]}
    assert not failed, "\n".join(f"{k}: {v}" for k, v in failed.items())
    assert len([n for (p, n) in by_file if p == "agents" and n.startswith("step:")]) == len(ASSERTIONS)
