"""Router tests for `/api/studio/agents/{key}/evals/*` (contract §D4)."""
from __future__ import annotations

from uuid import uuid4

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

    def test_run_in_progress_409s_once_scheduler_is_available(self, ke_client):
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
            assert second.status_code == 409
            assert second.json()["code"] == "run_in_progress"
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
