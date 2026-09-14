"""Tests for ``/api/approvals`` (contract §E.2)."""
from __future__ import annotations

from uuid import uuid4

from app.dependencies import get_approval_broker_dep
from tests._runtime_standin import InProcessApprovalBroker
from tests.routers.conftest import DEFAULT_ORG_ID, DEFAULT_USER_ID, bind_user, seed_org_role


def _seed_conversation(agents_client, *, owner_user_id=DEFAULT_USER_ID):
    agents_client.stores.agents.ensure_default_agents(DEFAULT_ORG_ID)
    agent = agents_client.stores.agents.get_by_key(DEFAULT_ORG_ID, "julia")
    return agents_client.stores.conversations.create(DEFAULT_ORG_ID, agent.id, owner_user_id)


def _install_broker(agents_client, *, auto_decide=None):
    from app.main import app

    broker = InProcessApprovalBroker(
        agents_client.stores.approvals,
        agents_client.stores.conversations,
        instance_id="test-instance",
        auto_decide=auto_decide,
    )
    app.dependency_overrides[get_approval_broker_dep] = lambda: broker
    return broker


class TestAuthBoundary:
    def test_list_requires_auth(self, agents_client):
        resp = agents_client.raw().get("/api/approvals")
        assert resp.status_code == 401

    def test_decision_requires_auth(self, agents_client):
        resp = agents_client.raw().post(
            f"/api/approvals/{uuid4()}/decision", json={"aprovada": True}
        )
        assert resp.status_code == 401


class TestListApprovals:
    def test_member_sees_only_own(self, agents_client):
        seed_org_role(agents_client, role="member")
        conversation = _seed_conversation(agents_client)
        agents_client.stores.approvals.create_pending(
            DEFAULT_ORG_ID, conversation.id, "mcp__academia__kb_escrever", {"slug": "x"},
            "Escrever x", "instance-a", DEFAULT_USER_ID,
        )
        # Another user's approval — must NOT show up for the member.
        other_user = uuid4()
        other_conv = agents_client.stores.conversations.create(
            DEFAULT_ORG_ID, agents_client.stores.agents.get_by_key(DEFAULT_ORG_ID, "julia").id,
            other_user,
        )
        agents_client.stores.approvals.create_pending(
            DEFAULT_ORG_ID, other_conv.id, "mcp__academia__kb_escrever", {"slug": "y"},
            "Escrever y", "instance-a", other_user,
        )
        resp = agents_client.get("/api/approvals")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["requested_by"] == str(DEFAULT_USER_ID)

    def test_admin_sees_all(self, agents_client):
        seed_org_role(agents_client, role="owner")
        conversation = _seed_conversation(agents_client)
        agents_client.stores.approvals.create_pending(
            DEFAULT_ORG_ID, conversation.id, "mcp__academia__kb_escrever", {"slug": "x"},
            "Escrever x", "instance-a", DEFAULT_USER_ID,
        )
        other_user = uuid4()
        other_conv = agents_client.stores.conversations.create(
            DEFAULT_ORG_ID, agents_client.stores.agents.get_by_key(DEFAULT_ORG_ID, "julia").id,
            other_user,
        )
        agents_client.stores.approvals.create_pending(
            DEFAULT_ORG_ID, other_conv.id, "mcp__academia__kb_escrever", {"slug": "y"},
            "Escrever y", "instance-a", other_user,
        )
        resp = agents_client.get("/api/approvals")
        assert resp.status_code == 200, resp.text
        assert resp.json()["total"] == 2

    def test_invalid_estado_422(self, agents_client):
        seed_org_role(agents_client, role="member")
        resp = agents_client.get("/api/approvals?estado=respondida")
        assert resp.status_code == 422


class TestDecideApproval:
    def test_requester_can_decide(self, agents_client):
        seed_org_role(agents_client, role="member")
        broker = _install_broker(agents_client)
        conversation = _seed_conversation(agents_client)
        approval = agents_client.stores.approvals.create_pending(
            DEFAULT_ORG_ID, conversation.id, "mcp__academia__kb_escrever", {"slug": "x"},
            "Escrever x", "instance-a", DEFAULT_USER_ID,
        )
        resp = agents_client.post(
            f"/api/approvals/{approval.id}/decision", json={"aprovada": True}
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["decision"] == "aprovada"

    def test_other_member_forbidden(self, agents_client):
        seed_org_role(agents_client, role="member")
        _install_broker(agents_client)
        owner_user = uuid4()
        conversation = _seed_conversation(agents_client, owner_user_id=owner_user)
        approval = agents_client.stores.approvals.create_pending(
            DEFAULT_ORG_ID, conversation.id, "mcp__academia__kb_escrever", {"slug": "x"},
            "Escrever x", "instance-a", owner_user,
        )
        resp = agents_client.post(
            f"/api/approvals/{approval.id}/decision", json={"aprovada": True}
        )
        assert resp.status_code == 403, resp.text
        assert resp.json()["code"] == "not_allowed"

    def test_admin_can_decide_someone_elses(self, agents_client):
        seed_org_role(agents_client, role="owner")
        _install_broker(agents_client)
        owner_user = uuid4()
        conversation = _seed_conversation(agents_client, owner_user_id=owner_user)
        approval = agents_client.stores.approvals.create_pending(
            DEFAULT_ORG_ID, conversation.id, "mcp__academia__kb_escrever", {"slug": "x"},
            "Escrever x", "instance-a", owner_user,
        )
        resp = agents_client.post(
            f"/api/approvals/{approval.id}/decision", json={"aprovada": False}
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["decision"] == "negada"

    def test_deciding_twice_conflicts(self, agents_client):
        seed_org_role(agents_client, role="member")
        _install_broker(agents_client)
        conversation = _seed_conversation(agents_client)
        approval = agents_client.stores.approvals.create_pending(
            DEFAULT_ORG_ID, conversation.id, "mcp__academia__kb_escrever", {"slug": "x"},
            "Escrever x", "instance-a", DEFAULT_USER_ID,
        )
        first = agents_client.post(
            f"/api/approvals/{approval.id}/decision", json={"aprovada": True}
        )
        assert first.status_code == 200, first.text
        second = agents_client.post(
            f"/api/approvals/{approval.id}/decision", json={"aprovada": True}
        )
        assert second.status_code == 409, second.text
        assert second.json()["code"] == "already_decided"

    def test_unknown_approval_404(self, agents_client):
        seed_org_role(agents_client, role="member")
        _install_broker(agents_client)
        resp = agents_client.post(
            f"/api/approvals/{uuid4()}/decision", json={"aprovada": True}
        )
        assert resp.status_code == 404
