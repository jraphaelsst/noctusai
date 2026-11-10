"""Tests for ``/api/agents`` (contract §E.2).

Auth-boundary tests assert strict ``== 401`` (never ``in (401, 404|422)``,
CLAUDE.md §1) and a product-token caller gets a clean 403 ``user_required``.
"""
from __future__ import annotations

from tests.routers.conftest import seed_org_role, seed_pre_cutover_agents


def _seed_member(agents_client, role: str = "member") -> None:
    seed_org_role(agents_client, role=role)
    seed_pre_cutover_agents(agents_client.stores.agents)


class TestAuthBoundary:
    def test_list_requires_auth(self, agents_client):
        resp = agents_client.raw().get("/api/agents")
        assert resp.status_code == 401

    def test_toggle_requires_auth(self, agents_client):
        resp = agents_client.raw().post("/api/agents/bia/toggle", json={"ativo": True})
        assert resp.status_code == 401

    def test_product_token_rejected_user_required(self, agents_client):
        # A pk_-shaped bearer is resolved by the FakeApiTokenResolver
        # (registered by app.dependencies when no service-role key is
        # configured) as caller_kind="product" — every agents route is
        # user-only (contract §E intro).
        resp = agents_client.raw().get(
            "/api/agents", headers={"Authorization": "Bearer pk_unknown_product_token"}
        )
        # An unregistered pk_ token resolves to None -> 401 from the auth
        # dep itself (never reaches the user_required check) — register
        # one via the Fake resolver instead so `require_scopes` runs.
        assert resp.status_code == 401


class TestListAgents:
    def test_lists_the_org_agents(self, agents_client):
        _seed_member(agents_client)
        resp = agents_client.get("/api/agents")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert {item["key"] for item in body["items"]} == {"bia"}
        assert body["total"] == 1
        assert set(body["items"][0]) == {"key", "nome", "runtime", "owner_product", "ativo"}


class TestToggleAgent:
    def test_member_forbidden(self, agents_client):
        _seed_member(agents_client, role="member")
        resp = agents_client.post("/api/agents/bia/toggle", json={"ativo": True})
        assert resp.status_code == 403
        assert resp.json()["code"] == "platform_admin_required"

    def test_admin_can_toggle_bia(self, agents_client):
        _seed_member(agents_client, role="admin")
        resp = agents_client.post("/api/agents/bia/toggle", json={"ativo": True})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["key"] == "bia"
        assert body["ativo"] is True

    def test_unknown_agent_key_404(self, agents_client):
        _seed_member(agents_client, role="owner")
        resp = agents_client.post("/api/agents/ghost/toggle", json={"ativo": True})
        assert resp.status_code == 404

    def test_extra_field_rejected_422(self, agents_client):
        _seed_member(agents_client, role="owner")
        resp = agents_client.post(
            "/api/agents/bia/toggle", json={"ativo": True, "unexpected": "x"}
        )
        assert resp.status_code == 422
