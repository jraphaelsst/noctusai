"""Agents 072: the DB publish gate accepts CONSOLIDATED COVERAGE (owner decision 2026-11-09), on the REAL chain on PGlite.

A version is publishable when every active case is either (a) executed and passed in the run the publish names / the newest live
mechanism run, or (b) `consolidado` and recorded as skipped (`eval_casos_pulados`) by that run. A `revalidar` / `em_validacao` case, a
critical case below its 10-pass threshold, or an uncovered case never counts. Direct DB publish must enforce this, not only the router.
"""
from __future__ import annotations

from pathlib import Path

from settings import REPO_ROOT
from tools.noctus.dev import migration_replay as mr

_A = "a0000000-0000-4000-8000-0000000000cc"
_U = "c0000000-0000-4000-8000-00000000000c"
_H = "sha256:" + "1" * 64
_TARGET = "products/agents/backend/migrations/072_eval_consolidacao.sql"


def _id(kind: int, n: int, i: int = 1) -> str:
    return f"{kind:01d}0000{n:03d}-0000-4000-8000-{i:012d}"


def _step(name: str, sql: str) -> dict:
    return {"product": "agents", "file": f"step:{name}", "sql": sql, "mode": "file", "twice": False}


def _publish(n: int, run: str | None) -> str:
    r = f"'{run}'" if run else "NULL"
    return (f"PERFORM agents.publish_agent_version('{_A}', '{_id(2, n)}', '{_U}', {r}, NULL, '{_H}', 'texto', '{{}}'::jsonb, NULL);")


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


def _published(n: int, run: str | None) -> str:
    return f"""
DO $t$ BEGIN
  {_publish(n, run)}
  IF (SELECT status FROM agents.agent_versions WHERE id = '{_id(2, n)}') <> 'ativa' THEN RAISE EXCEPTION 'ASSERT must be published'; END IF;
END $t$;"""


def _agent(n: int, *, mecanismo: bool = False) -> str:
    return f"""
INSERT INTO agents.agents (id, org_id, key, nome, runtime, ativo, publicacao_limiar) VALUES
  ('{_id(1, n)}', '{_A}', 'sc{n}', 'Sc{n}', 'claude_sdk', false, 0.8);
INSERT INTO agents.agent_versions (id, org_id, agent_id, versao, status, model, effort, created_by, compiled_hash) VALUES
  ('{_id(2, n)}', '{_A}', '{_id(1, n)}', 1, 'rascunho', 'claude-sonnet-5', 'medium', '{_U}', '{_H}');
UPDATE agents.agent_versions SET compiled_hash = '{_H}' WHERE id = '{_id(2, n)}';
"""


def _judge_case(n: int, i: int, crit: str = "normal") -> str:
    return (f"INSERT INTO agents.eval_cases (id, org_id, agent_id, slug, titulo, entrada, criterios, criticidade) VALUES "
            f"('{_id(3, n, i)}', '{_A}', '{_id(1, n)}', 'c{i}', 't', 'e', '{{\"deve\":[\"x\"]}}'::jsonb, '{crit}');")


def _mec_case(n: int, i: int) -> str:
    return (f"INSERT INTO agents.eval_cases (id, org_id, agent_id, slug, titulo, entrada, criterios, suite, k, roteiro, asserts) VALUES "
            f"('{_id(3, n, i)}', '{_A}', '{_id(1, n)}', 'm{i}', 't', 'e', '{{}}'::jsonb, 'mecanismo', 2, "
            "'{\"turnos\":[{\"lead\":\"oi\"}]}'::jsonb, '{\"sem_violacoes\": true}'::jsonb);")


def _estado(n: int, i: int, estado: str, seq: int, limite: int, suite: str = "comportamento") -> str:
    return (f"INSERT INTO agents.eval_case_estado (case_id, org_id, agent_id, suite, estado, sequencia, limite) VALUES "
            f"('{_id(3, n, i)}', '{_A}', '{_id(1, n)}', '{suite}', '{estado}', {seq}, {limite});")


def _skip(n: int, i: int, run: str, tipo: str, estado: str, seq: int, limite: int) -> str:
    return (f"INSERT INTO agents.eval_casos_pulados (org_id, agent_id, run_id, run_tipo, case_id, estado, motivo, sequencia, limite) VALUES "
            f"('{_A}', '{_id(1, n)}', '{run}', '{tipo}', '{_id(3, n, i)}', '{estado}', 'consolidado_nao_afetado', {seq}, {limite});")


def _judge_run(n: int) -> str:
    """A concluida run over case 1 only (score 1.0), flagged completa as the app does for a covered, filtered run."""
    r = _id(4, n)
    return (f"INSERT INTO agents.eval_runs (id, org_id, agent_id, version_id, compiled_hash, status, total, aprovados, score, limiar, completa, started_by, finished_at) VALUES "
            f"('{r}', '{_A}', '{_id(1, n)}', '{_id(2, n)}', '{_H}', 'concluida', 1, 1, 1.0, 0.8, true, '{_U}', now());\n"
            f"INSERT INTO agents.eval_results (org_id, run_id, case_id, status, score) VALUES ('{_A}', '{r}', '{_id(3, n, 1)}', 'aprovado', 1.0);")


def _mec_run(n: int, total: int, ok: int) -> str:
    r = _id(5, n)
    return (f"INSERT INTO agents.eval_mecanismo_runs (id, org_id, agent_id, version_id, compiled_hash, driver, status, total_casos, casos_aprovados, completa, aprovado, started_by, finished_at) VALUES "
            f"('{r}', '{_A}', '{_id(1, n)}', '{_id(2, n)}', '{_H}', 'live', 'concluida', {total}, {ok}, true, true, '{_U}', now());")


def _judge(n: int, *, estado: str, seq: int, limite: int, crit: str = "normal", skip: bool = True) -> str:
    sql = _agent(n) + _judge_case(n, 1) + "\n" + _judge_case(n, 2, crit) + "\n" + _estado(n, 2, estado, seq, limite) + "\n" + _judge_run(n)
    if skip:
        sql += "\n" + _skip(n, 2, _id(4, n), "comportamento", estado, seq, limite)
    return sql


ASSERTIONS = [
    # ── judge suite ─────────────────────────────────────────────────────────────
    _step("judge_consolidado_case_is_covered", _judge(1, estado="consolidado", seq=5, limite=5) + _published(1, _id(4, 1))),
    _step("judge_critical_case_covered_only_after_its_10", _judge(2, estado="consolidado", seq=10, limite=10, crit="critico") + _published(2, _id(4, 2))),
    _step("judge_critical_case_below_10_is_not_covered", _judge(3, estado="consolidado", seq=9, limite=10, crit="critico")
          + _refused_with("eval_required", _publish(3, _id(4, 3)))),
    _step("judge_em_validacao_case_is_never_covered", _judge(4, estado="em_validacao", seq=4, limite=5)
          + _refused_with("eval_required", _publish(4, _id(4, 4)))),
    _step("judge_revalidar_case_is_never_covered", _judge(5, estado="revalidar", seq=2, limite=3)
          + _refused_with("eval_required", _publish(5, _id(4, 5)))),
    _step("judge_case_regressed_after_the_run_is_not_covered", _judge(6, estado="consolidado", seq=5, limite=5)
          + f"\nUPDATE agents.eval_case_estado SET estado = 'em_validacao', sequencia = 0 WHERE case_id = '{_id(3, 6, 2)}';"
          + _refused_with("eval_required", _publish(6, _id(4, 6)))),
    _step("judge_case_added_after_the_run_is_not_covered", _judge(7, estado="consolidado", seq=5, limite=5) + "\n" + _judge_case(7, 3)
          + _refused_with("eval_required", _publish(7, _id(4, 7)))),
    # ── mechanism suite ─────────────────────────────────────────────────────────
    _step("mec_consolidado_case_is_covered", _agent(8) + _mec_case(8, 1) + "\n" + _mec_case(8, 2) + "\n" + _estado(8, 2, "consolidado", 6, 5, "mecanismo")
          + "\n" + _mec_run(8, 1, 1) + "\n" + _skip(8, 2, _id(5, 8), "mecanismo", "consolidado", 6, 5)
          + f"\nINSERT INTO agents.eval_mecanismo_execucoes (org_id, run_id, case_id, indice, status) VALUES ('{_A}', '{_id(5, 8)}', '{_id(3, 8, 1)}', 1, 'aprovado');"
          + _published(8, None).replace("NULL, NULL", "NULL, 'override com motivo suficientemente longo'")),
    _step("mec_uncovered_case_blocks", _agent(9) + _mec_case(9, 1) + "\n" + _mec_case(9, 2) + "\n" + _mec_run(9, 1, 1)
          + _refused_with("mecanismo_required", _publish(9, None).replace("NULL, NULL", "NULL, 'override com motivo suficientemente longo'"))),
    _step("mec_revalidar_case_is_never_covered", _agent(10) + _mec_case(10, 1) + "\n" + _mec_case(10, 2) + "\n" + _estado(10, 2, "revalidar", 1, 3, "mecanismo")
          + "\n" + _mec_run(10, 1, 1) + "\n" + _skip(10, 2, _id(5, 10), "mecanismo", "revalidar", 1, 3)
          + _refused_with("mecanismo_required", _publish(10, None).replace("NULL, NULL", "NULL, 'override com motivo suficientemente longo'"))),
]


def test_db_publish_accepts_consolidated_coverage_only_when_valid_on_the_real_chain(pglite):
    steps = mr._steps_for(Path(REPO_ROOT), "agents", {_TARGET}, "worktree", {})
    steps.extend(ASSERTIONS)
    res = mr._run_harness(steps, 900, None)
    assert res.get("ok"), res
    by_file = {(s["product"], s["file"]): s for s in res["steps"]}
    assert not by_file[("agents", "072_eval_consolidacao.sql")]["failures"]
    failed = {n: s["failures"][0]["error"] for (p, n), s in by_file.items() if p == "agents" and n.startswith("step:") and s["failures"]}
    assert not failed, "\n".join(f"{k}: {v}" for k, v in failed.items())
    assert len([n for (p, n) in by_file if p == "agents" and n.startswith("step:")]) == len(ASSERTIONS)
