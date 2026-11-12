"""One eval run / eval loop per USER at a time (owner 2026-11-12, migration 087): Marina cannot start a second run while one is
in flight (any agent, either suite, single run or loop round) nor open a second loop; Cindy is never affected."""
from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

import pytest

from app.routers.studio_agents_router import get_mecanismo_store_dep
from app.routers.studio_evals_router import get_eval_scheduler_dep
from app.stores.studio_eval_mecanismo import FakeMecanismoStore
from app.stores.studio_eval_runs import FakeEvalRunWriter
from app.stores.studio_evals import EvalCaseInput
from app.studio.eval_um_por_usuario import checar_um_por_usuario
from fastapi import HTTPException
from noctusai_lib.testing.migrations import migration_sql
from tests.routers.conftest import DEFAULT_USER_ID, bind_user
from tests.studio.ke.conftest import DEFAULT_ORG_ID, seed_draft, seed_studio_agent

LOOPS = "/api/studio/agents/isaia/evals/loops"
RUNS = "/api/studio/agents/isaia/evals/runs"
CINDY = UUID("00000000-0000-0000-0000-00000000c1d1")
SQL = migration_sql(Path(__file__).resolve().parents[3], "eval_um_por_usuario")


def _admins(ke_client):
    rows = [{"id": str(u), "org_id": str(DEFAULT_ORG_ID), "org_role": "owner", "role": "admin"} for u in (DEFAULT_USER_ID, CINDY)]
    ke_client.mock_supabase.set_table_data("noctus_users", rows)


def _seed(ke_client, key="isaia"):
    agent = seed_studio_agent(ke_client, key=key)
    version_id = seed_draft(ke_client, agent).id
    ke_client.stores.evals.create_case(
        DEFAULT_ORG_ID, agent.id, EvalCaseInput(slug="c0", titulo="Caso", entrada="e", criterios={"deve": ["x"], "nao_deve": []}))
    return agent, version_id


def _run(ke_client, version_id, key="isaia", **extra):
    app = ke_client.raw().app
    app.dependency_overrides[get_eval_scheduler_dep] = lambda: (lambda run_id: None)
    try:
        return ke_client.post(f"/api/studio/agents/{key}/evals/runs", json={"version_id": str(version_id), **extra})
    finally:
        app.dependency_overrides.pop(get_eval_scheduler_dep, None)


def _finish(ke_client, agent, run_id):
    ev = ke_client.stores.evals
    w = FakeEvalRunWriter(ev)
    w.claim_run(DEFAULT_ORG_ID, UUID(run_id))
    w.finish_run(DEFAULT_ORG_ID, UUID(run_id), status="concluida", aprovados=0, score=0.0, custo_usd=0.0)


def test_a_second_single_run_while_one_is_in_flight_is_409_naming_it_and_cancel_frees_the_slot(ke_client):
    _admins(ke_client)
    agent, version_id = _seed(ke_client)
    first = _run(ke_client, version_id)
    assert first.status_code == 202, first.text
    second = _run(ke_client, version_id)
    assert second.status_code == 409, second.text
    body = second.json()
    assert body["code"] == "execucao_em_andamento"
    assert body["detail"].startswith("Você já tem uma avaliação em andamento (isaia · comportamento).")
    assert "Aguarde terminar ou cancele-a antes de iniciar outra." in body["detail"]
    assert body["em_andamento"] == {"run_id": first.json()["id"], "agent_key": "isaia", "suite": "comportamento",
                                    "status": "pendente", "loop_id": None, "rodada": None}
    # the refusal is recorded as an event
    (ev,) = ke_client.stores.loops.recusas
    assert ev["codigo"] == "execucao_em_andamento" and ev["started_by"] == DEFAULT_USER_ID and ev["em_andamento_run"][0] == UUID(first.json()["id"])
    # cancelling frees the slot at once
    assert ke_client.post(f"/api/studio/agents/isaia/evals/runs/{first.json()['id']}/cancel").status_code == 200
    assert _run(ke_client, version_id).status_code == 202


def test_a_finished_run_frees_the_slot(ke_client):
    _admins(ke_client)
    agent, version_id = _seed(ke_client)
    first = _run(ke_client, version_id)
    _finish(ke_client, agent, first.json()["id"])
    assert _run(ke_client, version_id).status_code == 202


def test_the_orphan_sweep_frees_a_run_whose_process_died(ke_client):
    from app.studio.evals import sweep_orphaned_runs
    from app.stores._util import utcnow
    from datetime import timedelta

    _admins(ke_client)
    agent, version_id = _seed(ke_client)
    assert _run(ke_client, version_id).status_code == 202
    assert _run(ke_client, version_id).status_code == 409
    assert sweep_orphaned_runs(FakeEvalRunWriter(ke_client.stores.evals), started_before=utcnow() + timedelta(seconds=1)) == 1
    assert _run(ke_client, version_id).status_code == 202


def test_another_user_is_never_affected(ke_client):
    _admins(ke_client)
    agent, version_id = _seed(ke_client)
    assert _run(ke_client, version_id).status_code == 202  # Marina
    bind_user(ke_client, user_id=CINDY)
    assert _run(ke_client, version_id).status_code == 202  # Cindy runs her own


def test_another_user_hits_the_per_agent_suite_slot_not_the_per_user_one(ke_client):
    _admins(ke_client)
    _seed(ke_client)
    assert ke_client.post(LOOPS, json={"suite": "comportamento"}).status_code == 201  # Marina
    bind_user(ke_client, user_id=CINDY)
    refused = ke_client.post(LOOPS, json={"suite": "comportamento"})
    assert refused.status_code == 409 and refused.json()["code"] == "loop_ativo_existente"
    assert ke_client.post(LOOPS, json={"suite": "mecanismo"}).status_code == 201  # Cindy opens her own loop on the other suite


def test_a_run_in_flight_on_another_agent_blocks_a_new_loop(ke_client):
    _admins(ke_client)
    _, version_id = _seed(ke_client, "outro")
    seed_studio_agent(ke_client, key="isaia")
    assert _run(ke_client, version_id, key="outro").status_code == 202
    refused = ke_client.post(LOOPS, json={"suite": "comportamento"})
    assert refused.status_code == 409 and refused.json()["code"] == "execucao_em_andamento"
    assert "outro · comportamento" in refused.json()["detail"]


def test_an_active_loop_allows_its_own_rounds_but_not_a_second_loop_nor_a_single_run(ke_client):
    _admins(ke_client)
    agent, version_id = _seed(ke_client)
    loop = ke_client.post(LOOPS, json={"suite": "comportamento", "rodadas_planejadas": 10})
    assert loop.status_code == 201, loop.text
    lid = loop.json()["id"]
    # a second loop (other suite) and a single run are refused, naming the open loop
    second = ke_client.post(LOOPS, json={"suite": "mecanismo", "rodadas_planejadas": 5})
    assert second.status_code == 409 and second.json()["code"] == "loop_ativo_do_usuario"
    assert "isaia · comportamento" in second.json()["detail"] and "Parar loop" in second.json()["detail"]
    assert second.json()["em_andamento"]["loop_id"] == lid
    single = _run(ke_client, version_id)
    assert single.status_code == 409 and single.json()["code"] == "loop_ativo_do_usuario"
    # its own round goes through; while in flight the next one names the round
    round1 = _run(ke_client, version_id, loop_id=lid)
    assert round1.status_code == 202, round1.text
    busy = _run(ke_client, version_id, loop_id=lid)
    assert busy.status_code == 409 and busy.json()["code"] == "execucao_em_andamento"
    assert "rodada 1 do loop" in busy.json()["detail"]
    assert busy.json()["em_andamento"]["loop_id"] == lid and busy.json()["em_andamento"]["rodada"] == 1
    # stopping the loop frees the user (after the round ends)
    _finish(ke_client, agent, round1.json()["id"])
    assert ke_client.post(f"{LOOPS}/{lid}/stop", json={}).status_code == 200
    assert _run(ke_client, version_id).status_code == 202


def test_cindy_runs_while_marina_has_a_loop_and_a_round_in_flight(ke_client):
    _admins(ke_client)
    agent, version_id = _seed(ke_client)
    lid = ke_client.post(LOOPS, json={"suite": "comportamento"}).json()["id"]
    assert _run(ke_client, version_id, loop_id=lid).status_code == 202  # Marina's round in flight
    bind_user(ke_client, user_id=CINDY)
    assert _run(ke_client, version_id).status_code == 202


class _Loops:
    def __init__(self, store):
        self._s = store

    def __getattr__(self, n):
        return getattr(self._s, n)


def test_a_mechanism_run_in_flight_blocks_every_start_of_the_same_user_and_only_that_user():
    from app.stores.studio_eval_loops import FakeLoopStore
    from app.stores.studio_evals import FakeEvalStore

    evals, loops = FakeEvalStore(), FakeLoopStore()
    mec = FakeMecanismoStore(evals)
    marina, cindy, agent_a, agent_b = uuid4(), uuid4(), uuid4(), uuid4()
    run = mec.start_run(DEFAULT_ORG_ID, agent_a, uuid4(), compiled_hash="h", driver="fake", limite_usd=1.0, started_by=marina, total_casos=1)
    kw = dict(org_id=DEFAULT_ORG_ID, suite="comportamento", loop_id=None, runs=evals, mecanismo=mec, loops=loops,
              chave_do_agente=lambda _id: "agente-base")
    with pytest.raises(HTTPException) as exc:
        checar_um_por_usuario(started_by=marina, agent_id=agent_b, **kw)
    assert exc.value.status_code == 409 and exc.value.detail["code"] == "execucao_em_andamento"
    assert exc.value.detail["detail"].startswith("Você já tem uma avaliação em andamento (agente-base · mecanismo).")
    assert exc.value.detail["em_andamento"]["run_id"] == str(run) and exc.value.detail["em_andamento"]["suite"] == "mecanismo"
    checar_um_por_usuario(started_by=cindy, agent_id=agent_b, **kw)  # never affected
    mec.fail_run(DEFAULT_ORG_ID, run, erro="x")  # ended: the slot is free
    checar_um_por_usuario(started_by=marina, agent_id=agent_b, **kw)


def test_the_run_stores_only_report_runs_in_flight():
    from app.stores.studio_evals import FakeEvalStore

    evals, mec = FakeEvalStore(), FakeMecanismoStore(FakeEvalStore())
    u = uuid4()
    rid = mec.start_run(DEFAULT_ORG_ID, uuid4(), uuid4(), compiled_hash="h", driver="fake", limite_usd=None, started_by=u, total_casos=1)
    assert [r.run_id for r in mec.em_andamento_do_usuario(u)] == [rid] and evals.em_andamento_do_usuario(u) == []
    mec.fail_run(DEFAULT_ORG_ID, rid, erro="x")
    assert mec.em_andamento_do_usuario(u) == []


# ── migration 087: the race-safe backstop ──────────────────────────────────────────────────────────────────────────────

def test_the_db_guard_serializes_per_user_and_reads_both_run_tables_and_the_loops():
    body = SQL[SQL.index("CREATE OR REPLACE FUNCTION agents.guard_eval_um_por_usuario"):SQL.index("-- 3 .")]
    assert "pg_advisory_xact_lock(hashtextextended('agents.eval_um_por_usuario:' || NEW.started_by::text, 0))" in body
    assert body.index("pg_advisory_xact_lock") < body.index("RAISE EXCEPTION 'execucao_em_andamento'")  # lock BEFORE the read
    assert "agents.eval_runs" in body and "status IN ('pendente', 'executando')" in body
    assert "agents.eval_mecanismo_runs" in body and "status = 'executando'" in body
    assert "RAISE EXCEPTION 'loop_ativo_do_usuario'" in body
    for tabela in ("eval_runs", "eval_mecanismo_runs", "eval_loops"):
        assert f"BEFORE INSERT ON agents.{tabela}" in SQL


def test_the_refusal_events_are_append_only_platform_tier_and_service_role_only():
    assert "CREATE TABLE IF NOT EXISTS agents.eval_recusas_eventos" in SQL
    assert "codigo IN ('execucao_em_andamento', 'loop_ativo_do_usuario')" in SQL
    assert "BEFORE UPDATE OR DELETE ON agents.eval_recusas_eventos" in SQL
    assert "COMMENT ON TABLE agents.eval_recusas_eventos IS 'tier:platform'" in SQL
    assert "REVOKE ALL ON agents.eval_recusas_eventos FROM anon, authenticated" in SQL
    assert "REVOKE ALL ON FUNCTION agents.guard_eval_um_por_usuario() FROM PUBLIC, anon, authenticated" in SQL
    assert "DROP TABLE" not in SQL and "DROP COLUMN" not in SQL


def test_the_db_codes_map_to_409_conflicts():
    from app.stores._db_errors import StudioConflict, map_db_error

    class _E(Exception):
        code = "P0001"
        message = "execucao_em_andamento"

    assert "execucao_em_andamento" in __import__("app.stores._db_errors", fromlist=["x"]).MENSAGENS_CONFLITO
    assert "loop_ativo_do_usuario" in __import__("app.stores._db_errors", fromlist=["x"]).MENSAGENS_CONFLITO
