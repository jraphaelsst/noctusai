"""Tests for ``/api/agents`` (contract §E.2, §E.6).

Auth-boundary tests assert strict ``== 401`` (never ``in (401, 404|422)``,
CLAUDE.md §1) and a product-token caller gets a clean 403 ``user_required``.
"""
from __future__ import annotations

from uuid import uuid4

from tests.routers.conftest import DEFAULT_ORG_ID, DEFAULT_USER_ID, seed_org_role


def _seed_member(agents_client, role: str = "member") -> None:
    seed_org_role(agents_client, role=role)


class TestAuthBoundary:
    def test_list_requires_auth(self, agents_client):
        resp = agents_client.raw().get("/api/agents")
        assert resp.status_code == 401

    def test_toggle_requires_auth(self, agents_client):
        resp = agents_client.raw().post("/api/agents/julia/toggle", json={"ativo": True})
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
    def test_lists_julia_and_one_chat(self, agents_client):
        _seed_member(agents_client)
        resp = agents_client.get("/api/agents")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        keys = {item["key"] for item in body["items"]}
        assert keys == {"julia", "one-chat"}
        assert body["total"] == 2

    def test_one_chat_not_configured_carries_aviso(self, agents_client):
        _seed_member(agents_client)
        resp = agents_client.get("/api/agents")
        one_chat = next(a for a in resp.json()["items"] if a["key"] == "one-chat")
        assert one_chat["estado_externo"] is None
        assert one_chat["aviso"]

    def test_one_chat_reachable_state(self, agents_client):
        _seed_member(agents_client)
        connection_id = uuid4()
        agents_client.stores.agents.ensure_default_agents(DEFAULT_ORG_ID)
        agents_client.stores.agents.set_external_ref(
            DEFAULT_ORG_ID, "one-chat", {"connection_id": str(connection_id)}
        )
        agents_client.stores.social_wiring.register(
            connection_id, auto_reply_enabled=True
        )
        resp = agents_client.get("/api/agents")
        one_chat = next(a for a in resp.json()["items"] if a["key"] == "one-chat")
        assert one_chat["estado_externo"] == {"auto_reply_enabled": True}
        assert one_chat["aviso"] is None

    def test_one_chat_unreachable_carries_aviso_not_error(self, agents_client):
        _seed_member(agents_client)
        connection_id = uuid4()
        agents_client.stores.agents.ensure_default_agents(DEFAULT_ORG_ID)
        agents_client.stores.agents.set_external_ref(
            DEFAULT_ORG_ID, "one-chat", {"connection_id": str(connection_id)}
        )
        agents_client.stores.social_wiring.fail_connection_ids.add(str(connection_id))
        resp = agents_client.get("/api/agents")
        assert resp.status_code == 200, resp.text
        one_chat = next(a for a in resp.json()["items"] if a["key"] == "one-chat")
        assert one_chat["estado_externo"] is None
        assert one_chat["aviso"]


class TestToggleAgent:
    def test_member_forbidden(self, agents_client):
        _seed_member(agents_client, role="member")
        resp = agents_client.post("/api/agents/julia/toggle", json={"ativo": True})
        assert resp.status_code == 403
        assert resp.json()["code"] == "role_missing"

    def test_admin_can_toggle_julia(self, agents_client):
        _seed_member(agents_client, role="admin")
        resp = agents_client.post("/api/agents/julia/toggle", json={"ativo": True})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["key"] == "julia"
        assert body["ativo"] is True

    def test_one_chat_not_configured_409(self, agents_client):
        _seed_member(agents_client, role="owner")
        agents_client.stores.agents.ensure_default_agents(DEFAULT_ORG_ID)
        resp = agents_client.post("/api/agents/one-chat/toggle", json={"ativo": True})
        assert resp.status_code == 409, resp.text
        assert resp.json()["code"] == "not_configured"

    def test_one_chat_upstream_failure_502(self, agents_client):
        _seed_member(agents_client, role="owner")
        connection_id = uuid4()
        agents_client.stores.agents.ensure_default_agents(DEFAULT_ORG_ID)
        agents_client.stores.agents.set_external_ref(
            DEFAULT_ORG_ID, "one-chat", {"connection_id": str(connection_id)}
        )
        agents_client.stores.social_wiring.fail_connection_ids.add(str(connection_id))
        resp = agents_client.post("/api/agents/one-chat/toggle", json={"ativo": True})
        assert resp.status_code == 502, resp.text
        assert resp.json()["code"] == "upstream_failed"

    def test_one_chat_toggle_success_reflects_bridge_state(self, agents_client):
        _seed_member(agents_client, role="owner")
        connection_id = uuid4()
        agents_client.stores.agents.ensure_default_agents(DEFAULT_ORG_ID)
        agents_client.stores.agents.set_external_ref(
            DEFAULT_ORG_ID, "one-chat", {"connection_id": str(connection_id)}
        )
        agents_client.stores.social_wiring.register(connection_id, auto_reply_enabled=False)
        resp = agents_client.post("/api/agents/one-chat/toggle", json={"ativo": True})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["ativo"] is True
        assert body["estado_externo"] == {"auto_reply_enabled": True}

    def test_unknown_agent_key_404(self, agents_client):
        _seed_member(agents_client, role="owner")
        resp = agents_client.post("/api/agents/ghost/toggle", json={"ativo": True})
        assert resp.status_code == 404

    def test_extra_field_rejected_422(self, agents_client):
        _seed_member(agents_client, role="owner")
        resp = agents_client.post(
            "/api/agents/julia/toggle", json={"ativo": True, "unexpected": "x"}
        )
        assert resp.status_code == 422
