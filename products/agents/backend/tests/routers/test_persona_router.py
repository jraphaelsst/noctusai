"""Tests for ``/api/agents/julia/persona`` (contract §E.2)."""
from __future__ import annotations

from tests.routers.conftest import DEFAULT_ORG_ID, seed_org_role


class TestAuthBoundary:
    def test_get_requires_auth(self, agents_client):
        resp = agents_client.raw().get("/api/agents/julia/persona")
        assert resp.status_code == 401

    def test_put_requires_auth(self, agents_client):
        resp = agents_client.raw().put(
            "/api/agents/julia/persona",
            json={"nome": "Julia", "papel": "assistente", "model": "claude-sonnet-5", "effort": "medium"},
        )
        assert resp.status_code == 401


class TestGetPersona:
    def test_no_active_persona_404(self, agents_client):
        seed_org_role(agents_client, role="member")
        resp = agents_client.get("/api/agents/julia/persona")
        assert resp.status_code == 404

    def test_returns_active_version(self, agents_client):
        seed_org_role(agents_client, role="member")
        agents_client.stores.agents.ensure_default_agents(DEFAULT_ORG_ID)
        resp = agents_client.put(
            "/api/agents/julia/persona",
            json={"nome": "Julia", "papel": "assistente", "model": "claude-sonnet-5", "effort": "medium"},
        )
        # PUT is admin-only; a member seeded above gets 403 here —
        # re-seed as owner to set up the fixture, then re-seed as member
        # to exercise the read path.
        assert resp.status_code == 403

        seed_org_role(agents_client, role="owner")
        put_resp = agents_client.put(
            "/api/agents/julia/persona",
            json={"nome": "Julia", "papel": "assistente", "model": "claude-sonnet-5", "effort": "medium"},
        )
        assert put_resp.status_code == 200, put_resp.text

        seed_org_role(agents_client, role="member")
        get_resp = agents_client.get("/api/agents/julia/persona")
        assert get_resp.status_code == 200, get_resp.text
        body = get_resp.json()
        assert body["nome"] == "Julia"
        assert body["versao"] == 1
        assert body["ativa"] is True


class TestUpdatePersona:
    def test_member_forbidden(self, agents_client):
        seed_org_role(agents_client, role="member")
        resp = agents_client.put(
            "/api/agents/julia/persona",
            json={"nome": "Julia", "papel": "assistente", "model": "claude-sonnet-5", "effort": "medium"},
        )
        assert resp.status_code == 403
        assert resp.json()["code"] == "role_missing"

    def test_model_outside_allowlist_422(self, agents_client):
        seed_org_role(agents_client, role="owner")
        resp = agents_client.put(
            "/api/agents/julia/persona",
            json={"nome": "Julia", "papel": "assistente", "model": "gpt-4o", "effort": "medium"},
        )
        assert resp.status_code == 422, resp.text

    def test_version_increments_on_second_edit(self, agents_client):
        seed_org_role(agents_client, role="owner")
        first = agents_client.put(
            "/api/agents/julia/persona",
            json={"nome": "Julia", "papel": "assistente", "model": "claude-sonnet-5", "effort": "medium"},
        )
        assert first.status_code == 200, first.text
        assert first.json()["versao"] == 1

        second = agents_client.put(
            "/api/agents/julia/persona",
            json={"nome": "Julia v2", "papel": "assistente", "model": "claude-opus-5", "effort": "high"},
        )
        assert second.status_code == 200, second.text
        body = second.json()
        assert body["versao"] == 2
        assert body["ativa"] is True
        assert body["nome"] == "Julia v2"

    def test_extra_field_rejected_422(self, agents_client):
        seed_org_role(agents_client, role="owner")
        resp = agents_client.put(
            "/api/agents/julia/persona",
            json={
                "nome": "Julia", "papel": "assistente", "model": "claude-sonnet-5",
                "effort": "medium", "unexpected": "x",
            },
        )
        assert resp.status_code == 422
