"""Router tests for `/api/studio/agents/{key}/evals/*` (contract §D4)."""
from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.routers.studio_evals_router import (
    EvalSchedulerUnavailable,
    get_eval_scheduler_dep,
)
from app.stores.studio_evals import EvalCaseInput
from tests.studio.ke.conftest import DEFAULT_ORG_ID, seed_draft, seed_org_role, seed_studio_agent

CASE_PAYLOAD = {
    "slug": "roteiro-basico",
    "titulo": "Roteiro básico",
    "entrada": "Escreva um roteiro de reels sobre reciclagem",
    "criterios": {"deve": ["menciona reciclagem"], "nao_deve": ["usa gírias"]},
}


class TestAuthBoundary:
    def test_list_cases_requires_auth(self, ke_client):
        resp = ke_client.raw().get("/api/studio/agents/isaia/evals/cases")
        assert resp.status_code == 401

    def test_create_run_requires_auth(self, ke_client):
        resp = ke_client.raw().post(
            "/api/studio/agents/isaia/evals/runs", json={"version_id": str(uuid4())},
        )
        assert resp.status_code == 401

    def test_member_forbidden_from_creating_a_case(self, ke_client):
        seed_org_role(ke_client, role="member")
        seed_studio_agent(ke_client)
        resp = ke_client.post("/api/studio/agents/isaia/evals/cases", json=CASE_PAYLOAD)
        assert resp.status_code == 403


class TestCasesCrud:
    def test_create_list_update_delete(self, ke_client):
        seed_org_role(ke_client, role="owner")
        seed_studio_agent(ke_client)
        created = ke_client.post("/api/studio/agents/isaia/evals/cases", json=CASE_PAYLOAD)
        assert created.status_code == 201, created.text
        case_id = created.json()["id"]

        listed = ke_client.get("/api/studio/agents/isaia/evals/cases")
        assert listed.status_code == 200
        assert len(listed.json()["items"]) == 1

        updated = ke_client.patch(
            f"/api/studio/agents/isaia/evals/cases/{case_id}", json={"titulo": "Roteiro revisado"},
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["titulo"] == "Roteiro revisado"

        deleted = ke_client.delete(f"/api/studio/agents/isaia/evals/cases/{case_id}")
        assert deleted.status_code == 204
        assert ke_client.get("/api/studio/agents/isaia/evals/cases").json()["items"] == []

    def test_empty_criterios_422s(self, ke_client):
        seed_org_role(ke_client, role="owner")
        seed_studio_agent(ke_client)
        payload = dict(CASE_PAYLOAD, criterios={"deve": [], "nao_deve": []})
        resp = ke_client.post("/api/studio/agents/isaia/evals/cases", json=payload)
        assert resp.status_code == 422

    def test_unknown_field_rejected_422(self, ke_client):
        seed_org_role(ke_client, role="owner")
        seed_studio_agent(ke_client)
        payload = dict(CASE_PAYLOAD, campo_desconhecido=True)
        resp = ke_client.post("/api/studio/agents/isaia/evals/cases", json=payload)
        assert resp.status_code == 422

    def test_update_unknown_case_404s(self, ke_client):
        seed_org_role(ke_client, role="owner")
        seed_studio_agent(ke_client)
        resp = ke_client.patch(
            f"/api/studio/agents/isaia/evals/cases/{uuid4()}", json={"titulo": "x"},
        )
        assert resp.status_code == 404
        assert resp.json()["code"] == "eval_case_not_found"


class TestCreateRun:
    def _seed_agent_case_version(self, ke_client):
        agent = seed_studio_agent(ke_client)
        version_id = seed_draft(ke_client, agent).id
        ke_client.stores.evals.create_case(
            DEFAULT_ORG_ID, agent.id,
            EvalCaseInput(
                slug="case-1", titulo="Caso 1", entrada="entrada",
                criterios={"deve": ["x"], "nao_deve": []},
            ),
        )
        return agent, version_id

    def test_unavailable_scheduler_marks_run_failed_and_503s(self, ke_client):
        seed_org_role(ke_client, role="owner")
        agent, version_id = self._seed_agent_case_version(ke_client)

        resp = ke_client.post(
            "/api/studio/agents/isaia/evals/runs", json={"version_id": str(version_id)},
        )
        assert resp.status_code == 503, resp.text
        assert resp.json()["code"] == "eval_runner_unavailable"

        runs = ke_client.get("/api/studio/agents/isaia/evals/runs").json()["items"]
        assert len(runs) == 1
        assert runs[0]["status"] == "falhou"
        assert runs[0]["erro"] == "eval_runner_unavailable"

    def test_run_is_stamped_with_the_hash_compiled_now_not_the_stored_one(self, ke_client):
        """Compliance review #3: the stored ``compiled_hash`` can be stale
        (knowledge doc counts live in the compiled text); the run carries
        what ``get_current_hash_dep`` computes at creation."""
        seed_org_role(ke_client, role="owner")
        agent, version_id = self._seed_agent_case_version(ke_client)
        ke_client.stores.defs.set_compiled_hash(DEFAULT_ORG_ID, version_id, "sha256:" + "a" * 64)  # stale
        ke_client.stores.hashes[version_id] = "sha256:" + "b" * 64  # what compiles now
        app = ke_client.raw().app
        app.dependency_overrides[get_eval_scheduler_dep] = lambda: (lambda run_id: None)
        try:
            resp = ke_client.post("/api/studio/agents/isaia/evals/runs", json={"version_id": str(version_id)})
        finally:
            app.dependency_overrides.pop(get_eval_scheduler_dep, None)
        assert resp.status_code == 202, resp.text
        assert resp.json()["compiled_hash"] == "sha256:" + "b" * 64

    def test_unknown_version_404s(self, ke_client):
        seed_org_role(ke_client, role="owner")
        seed_studio_agent(ke_client)
        resp = ke_client.post(
            "/api/studio/agents/isaia/evals/runs", json={"version_id": str(uuid4())},
        )
        assert resp.status_code == 404
        assert resp.json()["code"] == "version_not_found"

    def test_a_second_run_by_the_same_user_is_refused_one_run_per_user(self, ke_client):
        seed_org_role(ke_client, role="owner")
        agent, version_id = self._seed_agent_case_version(ke_client)

        app = ke_client.raw().app
        app.dependency_overrides[get_eval_scheduler_dep] = lambda: (lambda run_id: None)
        try:
            first = ke_client.post(
                "/api/studio/agents/isaia/evals/runs", json={"version_id": str(version_id)},
            )
            assert first.status_code == 202, first.text

            second = ke_client.post(
                "/api/studio/agents/isaia/evals/runs", json={"version_id": str(version_id)},
            )
            # 087: one run per user at a time (parallel runs of one version stay possible across users).
            assert second.status_code == 409, second.text
            assert second.json()["code"] == "execucao_em_andamento"
            assert second.json()["em_andamento"]["run_id"] == first.json()["id"]
        finally:
            app.dependency_overrides.pop(get_eval_scheduler_dep, None)


class TestGetAndCancelRun:
    def _create_run_with_available_scheduler(self, ke_client):
        agent = seed_studio_agent(ke_client)
        version_id = seed_draft(ke_client, agent).id
        ke_client.stores.evals.create_case(
            DEFAULT_ORG_ID, agent.id,
            EvalCaseInput(slug="case-1", titulo="Caso 1", entrada="entrada", criterios={"deve": ["x"], "nao_deve": []}),
        )
        app = ke_client.raw().app
        app.dependency_overrides[get_eval_scheduler_dep] = lambda: (lambda run_id: None)
        try:
            resp = ke_client.post(
                "/api/studio/agents/isaia/evals/runs", json={"version_id": str(version_id)},
            )
            assert resp.status_code == 202, resp.text
            return resp.json()["id"]
        finally:
            app.dependency_overrides.pop(get_eval_scheduler_dep, None)

    def test_get_run_detail_includes_pending_results(self, ke_client):
        seed_org_role(ke_client, role="owner")
        run_id = self._create_run_with_available_scheduler(ke_client)
        resp = ke_client.get(f"/api/studio/agents/isaia/evals/runs/{run_id}")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total"] == 1
        assert len(body["resultados"]) == 1
        assert body["resultados"][0]["case_slug"] == "case-1"
        assert body["resultados"][0]["status"] == "pendente"

    def test_unknown_run_404s(self, ke_client):
        seed_org_role(ke_client, role="owner")
        seed_studio_agent(ke_client)
        resp = ke_client.get(f"/api/studio/agents/isaia/evals/runs/{uuid4()}")
        assert resp.status_code == 404
        assert resp.json()["code"] == "eval_run_not_found"

    def test_cancel_then_cancel_again_conflicts(self, ke_client):
        seed_org_role(ke_client, role="owner")
        run_id = self._create_run_with_available_scheduler(ke_client)

        cancelled = ke_client.post(f"/api/studio/agents/isaia/evals/runs/{run_id}/cancel")
        assert cancelled.status_code == 200, cancelled.text
        assert cancelled.json()["status"] == "cancelada"

        again = ke_client.post(f"/api/studio/agents/isaia/evals/runs/{run_id}/cancel")
        assert again.status_code == 409
        assert again.json()["code"] == "run_not_cancellable"

    def test_cancel_requires_admin(self, ke_client):
        seed_org_role(ke_client, role="owner")
        run_id = self._create_run_with_available_scheduler(ke_client)
        seed_org_role(ke_client, role="member")
        resp = ke_client.post(f"/api/studio/agents/isaia/evals/runs/{run_id}/cancel")
        assert resp.status_code == 403


def test_default_scheduler_dependency_is_fail_closed():
    scheduler = get_eval_scheduler_dep()
    with pytest.raises(EvalSchedulerUnavailable):
        scheduler(uuid4())


class TestCostControl:
    """Contract §L — `modelo_geracao` / `limite_usd` / `repetir_falhas_de`."""

    def _seed_agent_case_version(self, ke_client):
        agent = seed_studio_agent(ke_client)
        version_id = seed_draft(ke_client, agent).id
        ke_client.stores.evals.create_case(
            DEFAULT_ORG_ID, agent.id,
            EvalCaseInput(
                slug="case-1", titulo="Caso 1", entrada="entrada",
                criterios={"deve": ["x"], "nao_deve": []},
            ),
        )
        return agent, version_id

    def _with_available_scheduler(self, ke_client, body):
        app = ke_client.raw().app
        app.dependency_overrides[get_eval_scheduler_dep] = lambda: (lambda run_id: None)
        try:
            return ke_client.post("/api/studio/agents/isaia/evals/runs", json=body)
        finally:
            app.dependency_overrides.pop(get_eval_scheduler_dep, None)

    def test_modelo_geracao_outside_allowlist_422s(self, ke_client):
        seed_org_role(ke_client, role="owner")
        _agent, version_id = self._seed_agent_case_version(ke_client)
        resp = ke_client.post(
            "/api/studio/agents/isaia/evals/runs",
            json={"version_id": str(version_id), "modelo_geracao": "claude-opus-5"},
        )
        assert resp.status_code == 422, resp.text

    def test_modelo_geracao_is_stamped_and_returned(self, ke_client):
        seed_org_role(ke_client, role="owner")
        _agent, version_id = self._seed_agent_case_version(ke_client)
        resp = self._with_available_scheduler(
            ke_client, {"version_id": str(version_id), "modelo_geracao": "claude-haiku-4-5"},
        )
        assert resp.status_code == 202, resp.text
        assert resp.json()["modelo_geracao"] == "claude-haiku-4-5"

    def test_limite_usd_defaults_from_settings_when_omitted(self, ke_client):
        from app.config import settings

        seed_org_role(ke_client, role="owner")
        _agent, version_id = self._seed_agent_case_version(ke_client)
        resp = self._with_available_scheduler(ke_client, {"version_id": str(version_id)})
        assert resp.status_code == 202, resp.text
        assert resp.json()["limite_usd"] == settings.studio_eval_run_budget_usd

    def test_limite_usd_explicit_value_round_trips(self, ke_client):
        seed_org_role(ke_client, role="owner")
        _agent, version_id = self._seed_agent_case_version(ke_client)
        resp = self._with_available_scheduler(
            ke_client, {"version_id": str(version_id), "limite_usd": 5.0},
        )
        assert resp.status_code == 202, resp.text
        assert resp.json()["limite_usd"] == 5.0

    def test_limite_usd_above_cap_422s(self, ke_client):
        seed_org_role(ke_client, role="owner")
        _agent, version_id = self._seed_agent_case_version(ke_client)
        resp = ke_client.post(
            "/api/studio/agents/isaia/evals/runs",
            json={"version_id": str(version_id), "limite_usd": 50.01},
        )
        assert resp.status_code == 422, resp.text

    def test_case_ids_and_repetir_falhas_de_are_mutually_exclusive(self, ke_client):
        seed_org_role(ke_client, role="owner")
        _agent, version_id = self._seed_agent_case_version(ke_client)
        resp = ke_client.post(
            "/api/studio/agents/isaia/evals/runs",
            json={
                "version_id": str(version_id), "case_ids": [str(uuid4())],
                "repetir_falhas_de": str(uuid4()),
            },
        )
        assert resp.status_code == 422, resp.text

    def test_repetir_falhas_de_unknown_run_404s(self, ke_client):
        seed_org_role(ke_client, role="owner")
        _agent, version_id = self._seed_agent_case_version(ke_client)
        resp = ke_client.post(
            "/api/studio/agents/isaia/evals/runs",
            json={"version_id": str(version_id), "repetir_falhas_de": str(uuid4())},
        )
        assert resp.status_code == 404, resp.text
        assert resp.json()["code"] == "eval_run_not_found"

    def test_repetir_falhas_de_reruns_only_non_aprovado_cases(self, ke_client):
        seed_org_role(ke_client, role="owner")
        agent, version_id = self._seed_agent_case_version(ke_client)
        # A second, passing case on the same agent/version.
        passing_case = ke_client.stores.evals.create_case(
            DEFAULT_ORG_ID, agent.id,
            EvalCaseInput(slug="case-2", titulo="Caso 2", entrada="entrada", criterios={"deve": ["x"], "nao_deve": []}),
        )
        prior = self._with_available_scheduler(ke_client, {"version_id": str(version_id)})
        assert prior.status_code == 202, prior.text
        prior_run_id = UUID(prior.json()["id"])

        # Mark case-1's result reprovado, case-2's aprovado — direct store
        # introspection (no public "set result" surface on this slice's own
        # store; the runner's writer is BE-RT's `FakeEvalRunWriter`, mirrors
        # the internal-introspection idiom this suite already uses).
        for row in ke_client.stores.evals._results[prior_run_id]:
            row["status"] = "aprovado" if row["case_id"] == passing_case.id else "reprovado"
        # Free the version's one-active-run slot (013 partial unique index)
        # — the HTTP-created run never got claimed by a real runner here.
        ke_client.stores.evals._runs[prior_run_id]["status"] = "concluida"

        rerun = self._with_available_scheduler(
            ke_client, {"version_id": str(version_id), "repetir_falhas_de": str(prior_run_id)},
        )
        assert rerun.status_code == 202, rerun.text
        rerun_id = UUID(rerun.json()["id"])
        results = ke_client.stores.evals._results[rerun_id]
        assert len(results) == 1
        assert results[0]["case_id"] != passing_case.id
        # A rerun over a SUBSET is never `completa` (H1) regardless of it
        # having been derived from a full prior run.
        assert rerun.json()["completa"] is False


class TestConsolidacaoRuns:
    """Owner rule 2026-11-09: a default run executes only cases that are not consolidated-and-unaffected."""

    P0 = {"secao:a": "1", "secao:b": "1", "modelo": "m", "config": "c", "estrutura": "e"}

    def _seed(self, ke_client, n=3):
        agent = seed_studio_agent(ke_client)
        version_id = seed_draft(ke_client, agent).id
        ids = []
        for i in range(n):
            c = ke_client.stores.evals.create_case(
                DEFAULT_ORG_ID, agent.id,
                EvalCaseInput(slug=f"c{i}", titulo=f"Caso {i}", entrada="e", criterios={"deve": ["x"], "nao_deve": []}))
            ke_client.stores.consol.set_caso(DEFAULT_ORG_ID, agent.id, c.id, depende_de=["secao:a"], depende_de_origem="declarada")
            ids.append(c.id)
        ke_client.stores.partes[version_id] = dict(self.P0)
        return agent, version_id, ids

    def _consolidar(self, ke_client, agent, ids, h="sha256:" + "0" * 56 + "0"):
        from app.studio.consolidacao_service import registrar_resultados

        for _ in range(5):
            registrar_resultados(ke_client.stores.consol, org_id=DEFAULT_ORG_ID, agent_id=agent.id, suite="comportamento", run_id=uuid4(),
                                 run_tipo="comportamento", hash_atual=h, partes=dict(self.P0), resultados=[(i, ["aprovado"]) for i in ids])

    def _post_run(self, ke_client, version_id, **extra):
        app = ke_client.raw().app
        app.dependency_overrides[get_eval_scheduler_dep] = lambda: (lambda run_id: None)
        try:
            return ke_client.post("/api/studio/agents/isaia/evals/runs", json={"version_id": str(version_id), **extra})
        finally:
            app.dependency_overrides.pop(get_eval_scheduler_dep, None)

    def test_default_run_skips_consolidated_cases_and_the_run_says_why(self, ke_client):
        seed_org_role(ke_client, role="owner")
        agent, version_id, ids = self._seed(ke_client)
        self._consolidar(ke_client, agent, ids[:2])
        resp = self._post_run(ke_client, version_id)
        assert resp.status_code == 202, resp.text
        assert resp.json()["total"] == 1 and resp.json()["completa"] is True  # covered: executed + consolidated-unaffected = every active case
        detail = ke_client.get(f"/api/studio/agents/isaia/evals/runs/{resp.json()['id']}").json()
        assert [r["case_slug"] for r in detail["resultados"]] == ["c2"]
        assert {p["case_slug"] for p in detail["casos_pulados"]} == {"c0", "c1"}
        assert all(p["motivo"] == "consolidado_nao_afetado" and p["estado"] == "consolidado" for p in detail["casos_pulados"])

    def test_rodar_tudo_runs_every_case_and_stays_complete(self, ke_client):
        seed_org_role(ke_client, role="owner")
        agent, version_id, ids = self._seed(ke_client)
        self._consolidar(ke_client, agent, ids[:2])
        resp = self._post_run(ke_client, version_id, rodar_tudo=True)
        assert resp.status_code == 202, resp.text
        assert resp.json()["total"] == 3 and resp.json()["completa"] is True
        assert ke_client.get(f"/api/studio/agents/isaia/evals/runs/{resp.json()['id']}").json()["casos_pulados"] == []

    def test_a_change_to_a_dependency_brings_the_case_back_as_revalidar(self, ke_client):
        seed_org_role(ke_client, role="owner")
        agent, version_id, ids = self._seed(ke_client)
        self._consolidar(ke_client, agent, ids)
        ke_client.stores.partes[version_id] = {**self.P0, "secao:a": "2"}
        resp = self._post_run(ke_client, version_id)
        assert resp.status_code == 202 and resp.json()["total"] == 3
        assert {e.estado for e in ke_client.stores.consol.get_estados(DEFAULT_ORG_ID, agent.id).values()} == {"revalidar"}

    def test_everything_consolidated_and_unaffected_is_a_409_not_an_empty_run(self, ke_client):
        seed_org_role(ke_client, role="owner")
        agent, version_id, ids = self._seed(ke_client)
        self._consolidar(ke_client, agent, ids)
        resp = self._post_run(ke_client, version_id)
        assert resp.status_code == 409 and resp.json()["code"] == "todos_consolidados"
        assert ke_client.get("/api/studio/agents/isaia/evals/runs").json()["items"] == []

    def test_without_part_hashes_nothing_is_skipped(self, ke_client):
        seed_org_role(ke_client, role="owner")
        agent, version_id, ids = self._seed(ke_client)
        self._consolidar(ke_client, agent, ids)
        ke_client.stores.partes.clear()  # compile of parts unavailable -> fail-safe
        resp = self._post_run(ke_client, version_id)
        assert resp.status_code == 202 and resp.json()["total"] == 3

    def test_explicit_case_ids_are_never_filtered(self, ke_client):
        seed_org_role(ke_client, role="owner")
        agent, version_id, ids = self._seed(ke_client)
        self._consolidar(ke_client, agent, ids)
        resp = self._post_run(ke_client, version_id, case_ids=[str(ids[0])])
        assert resp.status_code == 202 and resp.json()["total"] == 1


class TestConsolidacaoApi:
    def test_state_listing_set_criticality_deps_transitions_and_backfill_dry_run(self, ke_client):
        seed_org_role(ke_client, role="owner")
        agent = seed_studio_agent(ke_client)
        seed_draft(ke_client, agent)
        c = ke_client.stores.evals.create_case(
            DEFAULT_ORG_ID, agent.id,
            EvalCaseInput(slug="adv", titulo="Adv", entrada="e", criterios={"deve": ["x"], "nao_deve": []}, tags=("adversarial",)))
        listed = ke_client.get("/api/studio/agents/isaia/evals/consolidacao").json()
        assert listed["config"]["consolidar_critico"] == 10 and listed["contagem"]["em_validacao"] == 1
        assert listed["items"][0]["estado"] == "em_validacao" and listed["items"][0]["limite"] == 5

        put = ke_client.put(f"/api/studio/agents/isaia/evals/cases/{c.id}/consolidacao",
                            json={"criticidade": "critico", "depende_de": ["secao:a", "skill:*"]})
        assert put.status_code == 200, put.text
        body = put.json()
        assert (body["criticidade"], body["criticidade_origem"], body["depende_de"], body["depende_de_origem"], body["limite"]) == (
            "critico", "definida", ["secao:a", "skill:*"], "declarada", 10)
        case_out = ke_client.get("/api/studio/agents/isaia/evals/cases").json()["items"][0]
        assert case_out["criticidade"] == "critico" and case_out["depende_de"] == ["secao:a", "skill:*"]

        assert ke_client.get("/api/studio/agents/isaia/evals/consolidacao/transicoes").json() == {"items": []}
        dry = ke_client.post("/api/studio/agents/isaia/evals/consolidacao/backfill", json={})
        assert dry.status_code == 200, dry.text
        assert dry.json()["aplicado"] is False and dry.json()["politica_sem_partes"] == "dono"

    def test_put_rejects_an_invalid_criticality_and_unknown_case(self, ke_client):
        seed_org_role(ke_client, role="owner")
        agent = seed_studio_agent(ke_client)
        assert ke_client.put(f"/api/studio/agents/isaia/evals/cases/{uuid4()}/consolidacao", json={"criticidade": "x"}).status_code == 422
        r = ke_client.put(f"/api/studio/agents/isaia/evals/cases/{uuid4()}/consolidacao", json={"criticidade": "normal"})
        assert r.status_code == 404 and r.json()["code"] == "eval_case_not_found"

    def test_member_cannot_read_or_write_consolidation(self, ke_client):
        seed_org_role(ke_client, role="member")
        seed_studio_agent(ke_client)
        assert ke_client.get("/api/studio/agents/isaia/evals/consolidacao").status_code == 403
        assert ke_client.post("/api/studio/agents/isaia/evals/consolidacao/backfill", json={}).status_code == 403

    def test_consolidation_requires_auth(self, ke_client):
        assert ke_client.raw().get("/api/studio/agents/isaia/evals/consolidacao").status_code == 401
