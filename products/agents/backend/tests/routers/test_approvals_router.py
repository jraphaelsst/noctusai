"""Tests for ``/api/approvals`` (contract §E.2, §E.9).

``TestDecideApproval`` drives G2's REAL ``StoreApprovalBroker`` — a
successful decision needs a LIVE ``broker.request()`` future, which only
exists once a real turn (via ``install_runtime`` + ``POST .../messages``)
has actually reached the escrita branch and is blocked awaiting it. A row
created directly on the store (bypassing ``broker.request()``) has no such
future — deciding it is the ``orphaned`` case, not a stand-in limitation.
"""
from __future__ import annotations

from uuid import uuid4

from tests.routers.conftest import (
    DEFAULT_ORG_ID,
    DEFAULT_USER_ID,
    bind_user,
    install_runtime,
    seed_active_agent_and_persona,
    seed_org_role,
    wait_for_pending_approval,
    wait_turn_released,
)


def _seed_conversation(agents_client, *, owner_user_id=DEFAULT_USER_ID):
    agents_client.stores.agents.ensure_default_agents(DEFAULT_ORG_ID)
    agent = agents_client.stores.agents.get_by_key(DEFAULT_ORG_ID, "julia")
    return agents_client.stores.conversations.create(DEFAULT_ORG_ID, agent.id, owner_user_id)


def _seed_live_pending_approval(agents_client, *, owner_user_id=DEFAULT_USER_ID):
    """Drive a REAL turn through the escrita branch so G2's
    ``StoreApprovalBroker`` has a live ``request()`` future waiting —
    the only way ``resolve()`` succeeds rather than raising ``Orphaned``.

    Contract §E.2: ``POST .../messages`` is owner-only (never an admin
    bypass) — the caller identity MUST be re-bound to ``owner_user_id``
    for the POST itself when a caller wants to decide as a DIFFERENT
    (e.g. admin) identity afterward."""
    agent = seed_active_agent_and_persona(agents_client)
    conv = agents_client.stores.conversations.create(DEFAULT_ORG_ID, agent.id, owner_user_id)
    if owner_user_id != DEFAULT_USER_ID:
        bind_user(agents_client, user_id=owner_user_id)
        agents_client.mock_supabase.set_table_data(
            "noctus_users",
            [{"id": str(owner_user_id), "org_id": str(DEFAULT_ORG_ID), "org_role": "member"}],
        )
    install_runtime(
        agents_client, [("escrita", "mcp__academia__kb_escrever", {"slug": "x"})]
    )
    resp = agents_client.post(
        f"/api/conversations/{conv.id}/messages", json={"texto": "registre isso"}
    )
    assert resp.status_code == 202, resp.text
    approval = wait_for_pending_approval(agents_client.stores.approvals, DEFAULT_ORG_ID)
    return conv, approval


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
        conversation, approval = _seed_live_pending_approval(agents_client)
        resp = agents_client.post(
            f"/api/approvals/{approval.id}/decision", json={"aprovada": True}
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["decision"] == "aprovada"
        wait_turn_released(agents_client.stores.conversations, DEFAULT_ORG_ID, conversation.id)

    def test_other_member_forbidden(self, agents_client):
        # The requester-or-admin check runs BEFORE `broker.resolve` —
        # a store-direct pending row (no live future) is sufficient here.
        seed_org_role(agents_client, role="member")
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
        owner_user = uuid4()
        conversation, approval = _seed_live_pending_approval(agents_client, owner_user_id=owner_user)
        # Switch back to the admin identity for the decision — the POST
        # above ran AS `owner_user` (contract §E.2: POST .../messages is
        # owner-only, never an admin bypass).
        bind_user(agents_client, user_id=DEFAULT_USER_ID)
        seed_org_role(agents_client, user_id=DEFAULT_USER_ID, role="owner")
        resp = agents_client.post(
            f"/api/approvals/{approval.id}/decision", json={"aprovada": False}
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["decision"] == "negada"
        wait_turn_released(agents_client.stores.conversations, DEFAULT_ORG_ID, conversation.id)

    def test_deciding_twice_conflicts(self, agents_client):
        seed_org_role(agents_client, role="member")
        conversation, approval = _seed_live_pending_approval(agents_client)
        first = agents_client.post(
            f"/api/approvals/{approval.id}/decision", json={"aprovada": True}
        )
        assert first.status_code == 200, first.text
        second = agents_client.post(
            f"/api/approvals/{approval.id}/decision", json={"aprovada": True}
        )
        assert second.status_code == 409, second.text
        assert second.json()["code"] == "already_decided"
        wait_turn_released(agents_client.stores.conversations, DEFAULT_ORG_ID, conversation.id)

    def test_unknown_approval_404(self, agents_client):
        seed_org_role(agents_client, role="member")
        resp = agents_client.post(
            f"/api/approvals/{uuid4()}/decision", json={"aprovada": True}
        )
        assert resp.status_code == 404

    def test_orphaned_approval_returns_409_not_500(self, agents_client):
        """A `pendente` row with NO live `broker.request()` future waiting
        on it (the process that created it restarted, or — as here — it
        was never requested through the broker at all) is `orphaned`
        (contract §E.9), through G2's REAL `StoreApprovalBroker`."""
        seed_org_role(agents_client, role="member")
        conversation = _seed_conversation(agents_client)
        approval = agents_client.stores.approvals.create_pending(
            DEFAULT_ORG_ID, conversation.id, "mcp__academia__kb_escrever", {"slug": "x"},
            "Escrever x", "instance-a", DEFAULT_USER_ID,
        )
        resp = agents_client.post(
            f"/api/approvals/{approval.id}/decision", json={"aprovada": True}
        )
        assert resp.status_code == 409, resp.text
        assert resp.json()["code"] == "orphaned"
