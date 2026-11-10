"""Router tests for the eval-loop gate (migration 076, G1-G7): ``/api/studio/agents/{key}/evals/loops`` and the loop-aware
run start ``POST .../evals/runs`` (``loop_id``)."""
from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.routers.studio_evals_router import get_eval_scheduler_dep
from app.stores.studio_eval_runs import FakeEvalRunWriter
from app.stores.studio_evals import EvalCaseInput
from app.studio.eval_loop_service import KIND_PARADA
from tests.studio.ke.conftest import DEFAULT_ORG_ID, seed_draft, seed_org_role, seed_studio_agent

LOOPS = "/api/studio/agents/isaia/evals/loops"
RUNS = "/api/studio/agents/isaia/evals/runs"


class TestAuthBoundary:
    @pytest.mark.parametrize("method,path", [
        ("get", LOOPS), ("post", LOOPS), ("get", f"{LOOPS}/{uuid4()}"), ("post", f"{LOOPS}/{uuid4()}/stop"),
    ])
    def test_every_loop_route_requires_auth(self, ke_client, method, path):
        resp = getattr(ke_client.raw(), method)(path, **({"json": {}} if method == "post" else {}))
        assert resp.status_code == 401

    def test_member_is_forbidden(self, ke_client):
        seed_org_role(ke_client, role="member")
        seed_studio_agent(ke_client)
        assert ke_client.post(LOOPS, json={"suite": "comportamento", "rodadas_planejadas": 5}).status_code == 403
        assert ke_client.get(LOOPS).status_code == 403


class TestStartAndRead:
    def _start(self, ke_client, **kw):
        return ke_client.post(LOOPS, json={"suite": "comportamento", "rodadas_planejadas": 30, **kw})

    def test_g1_g2_g7_a_loop_carries_target_floor_rounds_and_the_default_budget(self, ke_client):
        seed_org_role(ke_client, role="owner")
        seed_studio_agent(ke_client, publicacao_limiar=0.8)
        resp = self._start(ke_client)
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert (body["alvo"], body["piso"], body["rodadas_planejadas"], body["orcamento_usd"], body["status"]) == (1.0, 0.8, 30, 20.0, "ativo")
        assert [c["rodada"] for c in body["checkpoints"]] == [5, 10, 15] and body["serie"] == [] and body["gasto_usd"] == 0
        assert ke_client.get(f"{LOOPS}/{body['id']}").json()["id"] == body["id"]
        assert [i["id"] for i in ke_client.get(LOOPS).json()["items"]] == [body["id"]]
        assert ke_client.get(f"{LOOPS}?status=parado").json()["items"] == []

    def test_one_active_loop_per_suite_is_a_409(self, ke_client):
        seed_org_role(ke_client, role="owner")
        seed_studio_agent(ke_client)
        assert self._start(ke_client).status_code == 201
        dup = self._start(ke_client)
        assert dup.status_code == 409 and dup.json()["code"] == "loop_ativo_existente"
        assert ke_client.post(LOOPS, json={"suite": "mecanismo", "rodadas_planejadas": 5}).status_code == 201

    @pytest.mark.parametrize("payload", [
        {"suite": "outra", "rodadas_planejadas": 5}, {"suite": "comportamento", "rodadas_planejadas": 0},
        {"suite": "comportamento", "rodadas_planejadas": 101}, {"suite": "comportamento", "rodadas_planejadas": 5, "orcamento_usd": 0},
        {"suite": "comportamento", "rodadas_planejadas": 5, "campo_desconhecido": 1},
    ])
    def test_invalid_payloads_are_422(self, ke_client, payload):
        seed_org_role(ke_client, role="owner")
        seed_studio_agent(ke_client)
        assert ke_client.post(LOOPS, json=payload).status_code == 422

    def test_unknown_loop_is_404_and_a_manual_stop_is_recorded(self, ke_client):
        seed_org_role(ke_client, role="owner")
        seed_studio_agent(ke_client)
        assert ke_client.get(f"{LOOPS}/{uuid4()}").status_code == 404
        lid = self._start(ke_client).json()["id"]
        stopped = ke_client.post(f"{LOOPS}/{lid}/stop", json={"motivo": "vou rever"})
        assert stopped.status_code == 200 and stopped.json()["status"] == "parado" and stopped.json()["motivo_parada"] == "parado_manualmente"
        again = ke_client.post(f"{LOOPS}/{lid}/stop", json={})
        assert again.status_code == 409 and again.json()["code"] == "loop_ja_encerrado"


class TestLoopRuns:
    P = {"secao:a": "1"}

    def _seed(self, ke_client, *, n=2, **loop_kw):
        agent = seed_studio_agent(ke_client)
        version_id = seed_draft(ke_client, agent).id
        ids = [ke_client.stores.evals.create_case(
            DEFAULT_ORG_ID, agent.id, EvalCaseInput(slug=f"c{i}", titulo=f"Caso {i}", entrada="e", criterios={"deve": ["x"], "nao_deve": []})).id
            for i in range(n)]
        loop = ke_client.post(LOOPS, json={"suite": "comportamento", "rodadas_planejadas": 30, **loop_kw}).json()
        return agent, version_id, ids, loop

    def _post_run(self, ke_client, version_id, **extra):
        app = ke_client.raw().app
        app.dependency_overrides[get_eval_scheduler_dep] = lambda: (lambda run_id: None)
        try:
            return ke_client.post(RUNS, json={"version_id": str(version_id), **extra})
        finally:
            app.dependency_overrides.pop(get_eval_scheduler_dep, None)

    def _terminar(self, ke_client, agent, run_id, *, aprovados, falhando=(), custo=1.0):
        """Finish a run through the run writer (as the runner does), then close its round the way the runner's hook does."""
        ev = ke_client.stores.evals
        w = FakeEvalRunWriter(ev)
        w.claim_run(DEFAULT_ORG_ID, UUID(str(run_id)))
        total = len(ev._results[UUID(str(run_id))])
        for r in ev.list_results_with_cases(DEFAULT_ORG_ID, agent.id, UUID(str(run_id))):
            w.set_result(DEFAULT_ORG_ID, UUID(str(run_id)), r.result.case_id, status="reprovado" if r.case_slug in falhando else "aprovado",
                         saida="s", score=0.0 if r.case_slug in falhando else 1.0, veredito=[], notas_juiz="n", duracao_ms=1)
        w.finish_run(DEFAULT_ORG_ID, UUID(str(run_id)), status="concluida", aprovados=aprovados, score=round(aprovados / total, 3), custo_usd=custo)
        from app.studio.eval_loop_service import resumo_comportamento

        ke_client.stores.loop_service.fechar_sem_falhar(
            DEFAULT_ORG_ID, lambda: resumo_comportamento(ev, DEFAULT_ORG_ID, agent.id, UUID(str(run_id))), run_id=UUID(str(run_id)),
            run_tipo="comportamento")

    def test_a_looped_run_opens_a_round_and_blocks_the_next_while_in_flight(self, ke_client):
        seed_org_role(ke_client, role="owner")
        agent, version_id, ids, loop = self._seed(ke_client)
        resp = self._post_run(ke_client, version_id, loop_id=loop["id"])
        assert resp.status_code == 202, resp.text
        state = ke_client.get(f"{LOOPS}/{loop['id']}").json()
        assert [(s["rodada"], s["status"]) for s in state["serie"]] == [(1, "executando")]
        second = self._post_run(ke_client, version_id, loop_id=loop["id"])
        assert second.status_code == 409 and second.json()["code"] == "rodada_em_andamento"

    def test_g6_an_unchanged_hash_after_failures_is_refused_with_the_failing_cases(self, ke_client):
        seed_org_role(ke_client, role="owner")
        agent, version_id, ids, loop = self._seed(ke_client)
        run = self._post_run(ke_client, version_id, loop_id=loop["id"]).json()
        self._terminar(ke_client, agent, run["id"], aprovados=1, falhando=("c1",))
        state = ke_client.get(f"{LOOPS}/{loop['id']}").json()
        assert state["serie"][0]["score"] == 0.5 and state["serie"][0]["falhas"] == ["c1"]
        refused = self._post_run(ke_client, version_id, loop_id=loop["id"])
        assert refused.status_code == 409 and refused.json()["code"] == "hash_inalterado" and "c1" in refused.json()["detail"]
        ke_client.stores.hashes[version_id] = "sha256:" + "a" * 64  # the content was fixed: a new hash
        assert self._post_run(ke_client, version_id, loop_id=loop["id"]).status_code == 202

    def test_g4_through_the_api_two_flat_rounds_stop_the_loop_and_the_notice_carries_the_reason(self, ke_client):
        seed_org_role(ke_client, role="owner")
        agent, version_id, ids, loop = self._seed(ke_client)
        for i, h in enumerate(["a", "b", "c"]):
            ke_client.stores.hashes[version_id] = "sha256:" + h * 64
            run = self._post_run(ke_client, version_id, loop_id=loop["id"])
            assert run.status_code == 202, run.text
            self._terminar(ke_client, agent, run.json()["id"], aprovados=1, falhando=("c1",))
        state = ke_client.get(f"{LOOPS}/{loop['id']}").json()
        assert state["status"] == "parado" and state["motivo_parada"] == "sem_melhora"
        assert [s["overcall"] for s in state["serie"]] == [False, True, True] and len(state["overcalls"]) == 2
        assert state["custo_overcalls_usd"] == 2.0
        [n] = ke_client.stores.sink.sent
        assert n["kind"] == KIND_PARADA and n["metadata"]["casos_falhando"] == ["c1"] and n["metadata"]["serie"] == [0.5, 0.5, 0.5]
        stopped = self._post_run(ke_client, version_id, loop_id=loop["id"])
        assert stopped.status_code == 409 and stopped.json()["code"] == "loop_encerrado"

    def test_g7_budget_clamps_the_run_cap_then_stops_the_loop(self, ke_client):
        seed_org_role(ke_client, role="owner")
        agent, version_id, ids, loop = self._seed(ke_client, orcamento_usd=3.0)
        first = self._post_run(ke_client, version_id, loop_id=loop["id"], limite_usd=2.0)
        assert first.json()["limite_usd"] == 2.0
        self._terminar(ke_client, agent, first.json()["id"], aprovados=1, falhando=("c1",), custo=2.0)
        ke_client.stores.hashes[version_id] = "sha256:" + "b" * 64
        second = self._post_run(ke_client, version_id, loop_id=loop["id"], limite_usd=2.0)
        assert second.json()["limite_usd"] == 1.0  # what the loop has left, visible on the run
        self._terminar(ke_client, agent, second.json()["id"], aprovados=2, custo=1.0)  # 100%: target wins; spend is 3.0 too
        state = ke_client.get(f"{LOOPS}/{loop['id']}").json()
        assert state["gasto_usd"] == 3.0 and state["status"] == "concluido"

    def test_g7_budget_reached_below_target_stops_for_an_owner_decision(self, ke_client):
        seed_org_role(ke_client, role="owner")
        agent, version_id, ids, loop = self._seed(ke_client, orcamento_usd=2.0)
        run = self._post_run(ke_client, version_id, loop_id=loop["id"]).json()
        self._terminar(ke_client, agent, run["id"], aprovados=1, falhando=("c1",), custo=2.0)
        state = ke_client.get(f"{LOOPS}/{loop['id']}").json()
        assert state["status"] == "parado" and state["motivo_parada"] == "orcamento_atingido" and state["restante_usd"] == 0

    def test_partial_and_other_model_runs_are_refused_inside_a_loop(self, ke_client):
        seed_org_role(ke_client, role="owner")
        agent, version_id, ids, loop = self._seed(ke_client)
        partial = self._post_run(ke_client, version_id, loop_id=loop["id"], case_ids=[str(ids[0])])
        assert partial.status_code == 422 and partial.json()["code"] == "loop_run_parcial"
        other = self._post_run(ke_client, version_id, loop_id=loop["id"], modelo_geracao="claude-haiku-4-5")
        assert other.status_code == 422 and other.json()["code"] == "loop_modelo_geracao_nao_permitido"
        assert ke_client.get(f"{LOOPS}/{loop['id']}").json()["serie"] == []

    def test_a_loop_of_the_other_suite_and_an_unknown_loop(self, ke_client):
        seed_org_role(ke_client, role="owner")
        agent, version_id, ids, _ = self._seed(ke_client)
        mec = ke_client.post(LOOPS, json={"suite": "mecanismo", "rodadas_planejadas": 5}).json()
        wrong = self._post_run(ke_client, version_id, loop_id=mec["id"])
        assert wrong.status_code == 422 and wrong.json()["code"] == "loop_suite_invalida"
        assert self._post_run(ke_client, version_id, loop_id=str(uuid4())).status_code == 404

    def test_cancelling_a_looped_run_closes_its_round_as_neutral(self, ke_client):
        seed_org_role(ke_client, role="owner")
        agent, version_id, ids, loop = self._seed(ke_client)
        run = self._post_run(ke_client, version_id, loop_id=loop["id"]).json()
        assert ke_client.post(f"{RUNS}/{run['id']}/cancel").status_code == 200
        s = ke_client.get(f"{LOOPS}/{loop['id']}").json()
        assert s["status"] == "ativo" and s["serie"][0]["status"] == "cancelada" and s["serie"][0]["score"] is None
        assert self._post_run(ke_client, version_id, loop_id=loop["id"]).status_code == 202  # the slot is free again

    def test_runs_without_a_loop_are_unchanged(self, ke_client):
        seed_org_role(ke_client, role="owner")
        agent, version_id, ids, loop = self._seed(ke_client)
        assert self._post_run(ke_client, version_id).status_code == 202
        assert ke_client.get(f"{LOOPS}/{loop['id']}").json()["serie"] == []
