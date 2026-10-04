"""``studio:publish`` (2026-10-03) — the noc pre-push publish leg's token scope.

Accepted ONLY on: import, eval-run start + status/results, draft publish; and
only for a ``dev-advisor`` agent. A runtime agent (Julia, IsaIA) stays
user-only (403 ``user_required``); a token can never use the gate override
(403 ``override_requires_user``); the eval gate still decides; the audit actor
is the token id. Auth seams are `dependency_overrides` — never a patched guard.
"""
from __future__ import annotations

from uuid import UUID

import pytest

from app.dependencies import PACKAGE_TOKEN_SCOPES
from app.routers.studio_agents_router import get_eval_gate_dep, get_knowledge_catalog_dep
from app.routers.studio_evals_router import get_current_hash_dep, get_eval_scheduler_dep
from app.studio.catalog import StoreKnowledgeCatalog
from app.studio.models import FakeEvalGate, GateRun
from tests.studio.pkg.conftest import make_bundle

SCOPE = "studio:publish"
TOKEN_ID = UUID(int=7)
OTHERS = tuple(sorted(PACKAGE_TOKEN_SCOPES - {SCOPE}))
BASE = "/api/studio/agents"


@pytest.fixture
def seams(pkg):
    """Gate/catalog/scheduler/hash seams bound onto the shared Fakes."""
    from app.main import app

    gate = FakeEvalGate()
    scheduled: list[UUID] = []
    bindings = {
        get_eval_gate_dep: lambda: gate,
        get_knowledge_catalog_dep: lambda: StoreKnowledgeCatalog(pkg.rt.knowledge),
        get_eval_scheduler_dep: lambda: scheduled.append,
        get_current_hash_dep: lambda: (lambda org, agent, version: "h" * 64),
    }
    saved = {k: app.dependency_overrides.get(k) for k in bindings}
    app.dependency_overrides.update(bindings)
    try:
        yield gate, scheduled
    finally:
        for k, v in saved.items():
            if v is None:
                app.dependency_overrides.pop(k, None)
            else:
                app.dependency_overrides[k] = v


def _runtime(pkg, key="julia2"):
    agent, _ = pkg.rt.make_agent(key, publish=True)
    return agent


def _advisor_draft(pkg, key="mobile-dev"):
    assert pkg.import_bundle(make_bundle()).status_code == 200
    agent = pkg.rt.studio.get_agent(pkg.rt.org_id, key)
    return agent, pkg.rt.studio.get_draft(pkg.rt.org_id, agent.id)


def _pass_gate(pkg, gate, agent, draft):
    """Stamp the draft hash via an admin write, then make a run that passes."""
    # the publish route re-stamps the hash itself; read what it will compute
    compiled = pkg.get(f"{BASE}/{agent.key}/versions/{draft.id}/compiled").json()["hash"]
    run = GateRun(id=UUID(int=99), score=0.95, limiar=0.8, compiled_hash=compiled,
                  status="concluida", completa=True, total=1)
    gate.set_run(pkg.rt.org_id, draft.id, run)
    pkg.rt.studio.register_eval_run(
        pkg.rt.org_id, draft.id, run_id=run.id, score=0.95, compiled_hash=compiled, completa=True, total=1,
    )
    return run


class TestImport:
    def test_token_with_scope_imports_a_new_dev_advisor(self, pkg):
        with pkg.as_token(SCOPE):
            resp = pkg.rt.client.raw().post(f"{BASE}/mobile-dev/import", json=make_bundle())
        assert resp.status_code == 200, resp.text
        assert resp.json()["pacote"]["kind"] == "dev-advisor"

    def test_token_without_scope_is_scope_missing(self, pkg):
        with pkg.as_token(*OTHERS):
            resp = pkg.rt.client.raw().post(f"{BASE}/mobile-dev/import", json=make_bundle())
        assert resp.status_code == 403
        assert resp.json()["code"] == "scope_missing"

    def test_token_cannot_create_a_runtime_agent(self, pkg):
        body = make_bundle(agente__kind="runtime")
        for k in ("versao_semver", "package_sha"):
            body["versao"].pop(k)
        body.pop("claude")
        with pkg.as_token(SCOPE):
            resp = pkg.rt.client.raw().post(f"{BASE}/mobile-dev/import", json=body)
        assert resp.status_code == 403
        assert resp.json()["code"] == "user_required"
        assert pkg.rt.studio.list_agents(pkg.rt.org_id) == [] or all(
            a.key != "mobile-dev" for a in pkg.rt.studio.list_agents(pkg.rt.org_id))

    def test_token_cannot_import_over_an_existing_runtime_agent(self, pkg):
        _runtime(pkg)
        with pkg.as_token(SCOPE):
            resp = pkg.rt.client.raw().post(f"{BASE}/julia2/import", json=make_bundle(agente__key="julia2"))
        assert resp.status_code == 403
        assert resp.json()["code"] == "user_required"

    def test_token_reimports_an_existing_dev_advisor(self, pkg):
        pkg.advisor(publish=False)
        with pkg.as_token(SCOPE):
            resp = pkg.rt.client.raw().post(f"{BASE}/mobile-dev/import", json=make_bundle())
        assert resp.status_code == 200, resp.text

    def test_the_draft_is_attributed_to_the_token_id(self, pkg):
        with pkg.as_token(SCOPE):
            assert pkg.rt.client.raw().post(f"{BASE}/mobile-dev/import", json=make_bundle()).status_code == 200
        agent = pkg.rt.studio.get_agent(pkg.rt.org_id, "mobile-dev")
        assert pkg.rt.studio.get_draft(pkg.rt.org_id, agent.id).created_by == TOKEN_ID


class TestEvalRuns:
    def test_token_starts_and_reads_a_run_on_a_dev_advisor(self, pkg, seams):
        agent, draft = _advisor_draft(pkg)
        with pkg.as_token(SCOPE):
            raw = pkg.rt.client.raw()
            created = raw.post(f"{BASE}/mobile-dev/evals/runs", json={"version_id": str(draft.id)})
            assert created.status_code == 202, created.text
            run_id = created.json()["id"]
            assert raw.get(f"{BASE}/mobile-dev/evals/runs").status_code == 200
            detail = raw.get(f"{BASE}/mobile-dev/evals/runs/{run_id}")
            assert detail.status_code == 200, detail.text

    def test_without_scope_every_run_route_is_scope_missing(self, pkg, seams):
        agent, draft = _advisor_draft(pkg)
        with pkg.as_token(*OTHERS):
            raw = pkg.rt.client.raw()
            calls = [
                raw.post(f"{BASE}/mobile-dev/evals/runs", json={"version_id": str(draft.id)}),
                raw.get(f"{BASE}/mobile-dev/evals/runs"),
                raw.get(f"{BASE}/mobile-dev/evals/runs/{UUID(int=1)}"),
            ]
        for resp in calls:
            assert resp.status_code == 403
            assert resp.json()["code"] == "scope_missing"

    def test_runtime_agent_run_routes_stay_user_only(self, pkg, seams):
        agent = _runtime(pkg)
        draft = pkg.rt.studio.get_draft(pkg.rt.org_id, agent.id) or pkg.rt.studio.get_active_version(pkg.rt.org_id, agent.id)
        vid = str(draft.id) if draft else str(UUID(int=2))
        with pkg.as_token(SCOPE):
            raw = pkg.rt.client.raw()
            calls = [
                raw.post(f"{BASE}/julia2/evals/runs", json={"version_id": vid}),
                raw.get(f"{BASE}/julia2/evals/runs"),
                raw.get(f"{BASE}/julia2/evals/runs/{UUID(int=1)}"),
            ]
        for resp in calls:
            assert resp.status_code == 403
            assert resp.json()["code"] == "user_required"

    def test_the_run_is_attributed_to_the_token_id(self, pkg, seams):
        agent, draft = _advisor_draft(pkg)
        with pkg.as_token(SCOPE):
            created = pkg.rt.client.raw().post(f"{BASE}/mobile-dev/evals/runs", json={"version_id": str(draft.id)})
        assert created.status_code == 202, created.text
        run = pkg.rt.evals.get_run(pkg.rt.org_id, agent.id, UUID(created.json()["id"]))
        assert run.started_by == TOKEN_ID


class TestPublish:
    def test_token_publishes_a_dev_advisor_through_the_gate_and_audit_names_the_token(self, pkg, seams):
        gate, _ = seams
        agent, draft = _advisor_draft(pkg)
        run = _pass_gate(pkg, gate, agent, draft)
        with pkg.as_token(SCOPE):
            resp = pkg.rt.client.raw().post(f"{BASE}/mobile-dev/draft/publish", json={})
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "ativa"
        audit = pkg.rt.studio.list_audit_log(pkg.rt.org_id, agent.id)
        published = [a for a in audit if a.acao == "publicado"]
        assert len(published) == 1
        assert published[0].actor == TOKEN_ID
        assert published[0].depois["eval_run_id"] == str(run.id)

    def test_the_gate_is_still_enforced_for_a_token(self, pkg, seams):
        _advisor_draft(pkg)
        with pkg.as_token(SCOPE):
            resp = pkg.rt.client.raw().post(f"{BASE}/mobile-dev/draft/publish", json={})
        assert resp.status_code == 409
        assert resp.json()["code"] == "eval_required"

    def test_override_is_refused_for_a_token_even_with_a_valid_reason(self, pkg, seams):
        agent, _ = _advisor_draft(pkg)
        with pkg.as_token(SCOPE):
            resp = pkg.rt.client.raw().post(
                f"{BASE}/mobile-dev/draft/publish", json={"override_reason": "x" * 40})
        assert resp.status_code == 403
        assert resp.json()["code"] == "override_requires_user"
        assert pkg.rt.studio.get_active_version(pkg.rt.org_id, agent.id) is None

    def test_a_human_can_still_override(self, pkg, seams):
        agent, _ = _advisor_draft(pkg)
        resp = pkg.post(f"{BASE}/mobile-dev/draft/publish", json={"override_reason": "x" * 40})
        assert resp.status_code == 200, resp.text

    def test_without_scope_publish_is_scope_missing(self, pkg, seams):
        _advisor_draft(pkg)
        with pkg.as_token(*OTHERS):
            resp = pkg.rt.client.raw().post(f"{BASE}/mobile-dev/draft/publish", json={})
        assert resp.status_code == 403
        assert resp.json()["code"] == "scope_missing"

    def test_runtime_agent_publish_stays_user_only(self, pkg, seams):
        _runtime(pkg)
        with pkg.as_token(SCOPE):
            resp = pkg.rt.client.raw().post(f"{BASE}/julia2/draft/publish", json={})
        assert resp.status_code == 403
        assert resp.json()["code"] == "user_required"


class TestScopeIsMintable:
    def test_the_scope_is_in_the_documented_mintable_set(self):
        assert SCOPE in PACKAGE_TOKEN_SCOPES

    def test_an_owner_mints_a_token_carrying_the_scope(self, pkg):
        from datetime import datetime, timedelta, timezone

        resp = pkg.post("/api/settings/api-tokens", json={
            "label": "noc-prepush-publish", "scopes": [SCOPE],
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
        })
        assert resp.status_code == 201, resp.text
        assert resp.json()["scopes"] == [SCOPE]


class TestEvalRunThroughProductionWiring:
    """Regression (2026-10-04): the PRODUCTION scheduler binding
    (``app.studio.wiring.studio_eval_scheduler``) carried its own user-only
    ``require_admin``, so a ``studio:publish`` token got 403 ``user_required``
    in prod while every test above passed — they fake the scheduler seam.
    This test leaves the scheduler on its real binding (no ``seams`` fixture)."""

    def test_token_run_is_scheduled_and_concluded_by_the_real_runner(self, pkg):
        from tests.routers.conftest import install_runtime, wait_until

        install_runtime(pkg.rt.client, [])
        agent, draft = _advisor_draft(pkg)
        with pkg.as_token(SCOPE):
            created = pkg.rt.client.raw().post(f"{BASE}/mobile-dev/evals/runs", json={"version_id": str(draft.id)})
        assert created.status_code == 202, created.text
        run_id = UUID(created.json()["id"])
        assert wait_until(lambda: pkg.rt.evals.get_run(pkg.rt.org_id, agent.id, run_id).status == "concluida")
