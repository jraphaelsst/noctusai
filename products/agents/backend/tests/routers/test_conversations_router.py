"""Tests for ``/api/conversations`` — CRUD, the turn loop, SSE auth
(contract §E.2, §E.3, §E.9)."""
from __future__ import annotations

from uuid import uuid4

from app.dependencies import (
    get_agent_runtime_dep,
    get_approval_broker_dep,
    get_build_julia_spec_dep,
)
from tests._runtime_standin import (
    FakeAgentRuntime,
    InProcessApprovalBroker,
    fake_build_julia_spec,
)
from tests.routers.conftest import DEFAULT_ORG_ID, DEFAULT_USER_ID, bind_user, seed_org_role


def _install_runtime(agents_client, script, *, auto_decide=True):
    from app.main import app

    runtime = FakeAgentRuntime(script)
    broker = InProcessApprovalBroker(
        agents_client.stores.approvals,
        agents_client.stores.conversations,
        instance_id="test-instance",
        auto_decide=auto_decide,
    )
    app.dependency_overrides[get_agent_runtime_dep] = lambda: runtime
    app.dependency_overrides[get_approval_broker_dep] = lambda: broker
    app.dependency_overrides[get_build_julia_spec_dep] = lambda: fake_build_julia_spec
    return runtime, broker


def _seed_active_agent_and_persona(agents_client, *, ativo: bool = True):
    agents_client.stores.agents.ensure_default_agents(DEFAULT_ORG_ID)
    agent = agents_client.stores.agents.set_active(DEFAULT_ORG_ID, "julia", ativo)
    from app.stores.personas import PersonaInput

    agents_client.stores.personas.create_version(
        DEFAULT_ORG_ID,
        agent.id,
        PersonaInput(nome="Julia", papel="assistente", model="claude-sonnet-5", effort="medium"),
        created_by=DEFAULT_USER_ID,
    )
    return agent


class TestAuthBoundary:
    def test_list_requires_auth(self, agents_client):
        resp = agents_client.raw().get("/api/conversations")
        assert resp.status_code == 401

    def test_create_requires_auth(self, agents_client):
        resp = agents_client.raw().post("/api/conversations", json={})
        assert resp.status_code == 401

    def test_get_requires_auth(self, agents_client):
        resp = agents_client.raw().get(f"/api/conversations/{uuid4()}")
        assert resp.status_code == 401

    def test_messages_get_requires_auth(self, agents_client):
        resp = agents_client.raw().get(f"/api/conversations/{uuid4()}/messages")
        assert resp.status_code == 401

    def test_messages_post_requires_auth(self, agents_client):
        resp = agents_client.raw().post(
            f"/api/conversations/{uuid4()}/messages", json={"texto": "oi"}
        )
        assert resp.status_code == 401

    def test_stream_requires_auth(self, agents_client):
        resp = agents_client.raw().get(f"/api/conversations/{uuid4()}/stream")
        assert resp.status_code == 401


class TestCreateAndList:
    def test_create_and_get(self, agents_client):
        seed_org_role(agents_client, role="member")
        _seed_active_agent_and_persona(agents_client)
        resp = agents_client.post("/api/conversations", json={"titulo": "Primeira"})
        assert resp.status_code == 201, resp.text
        conv_id = resp.json()["id"]

        get_resp = agents_client.get(f"/api/conversations/{conv_id}")
        assert get_resp.status_code == 200, get_resp.text
        assert get_resp.json()["titulo"] == "Primeira"

    def test_list_only_own(self, agents_client):
        seed_org_role(agents_client, role="member")
        _seed_active_agent_and_persona(agents_client)
        agents_client.post("/api/conversations", json={})
        resp = agents_client.get("/api/conversations")
        assert resp.status_code == 200, resp.text
        assert resp.json()["total"] == 1


class TestConversationOwnershipBoundary:
    def test_get_another_users_conversation_404(self, agents_client):
        seed_org_role(agents_client, role="member")
        _seed_active_agent_and_persona(agents_client)
        other_user = uuid4()
        agent = agents_client.stores.agents.get_by_key(DEFAULT_ORG_ID, "julia")
        other_conv = agents_client.stores.conversations.create(DEFAULT_ORG_ID, agent.id, other_user)

        resp = agents_client.get(f"/api/conversations/{other_conv.id}")
        assert resp.status_code == 404

    def test_admin_can_read_another_users_conversation(self, agents_client):
        seed_org_role(agents_client, role="owner")
        _seed_active_agent_and_persona(agents_client)
        other_user = uuid4()
        agent = agents_client.stores.agents.get_by_key(DEFAULT_ORG_ID, "julia")
        other_conv = agents_client.stores.conversations.create(DEFAULT_ORG_ID, agent.id, other_user)

        resp = agents_client.get(f"/api/conversations/{other_conv.id}")
        assert resp.status_code == 200, resp.text

    def test_post_message_to_another_users_conversation_404(self, agents_client):
        seed_org_role(agents_client, role="owner")  # even admins may not POST
        _seed_active_agent_and_persona(agents_client)
        other_user = uuid4()
        agent = agents_client.stores.agents.get_by_key(DEFAULT_ORG_ID, "julia")
        other_conv = agents_client.stores.conversations.create(DEFAULT_ORG_ID, agent.id, other_user)

        resp = agents_client.post(
            f"/api/conversations/{other_conv.id}/messages", json={"texto": "oi"}
        )
        assert resp.status_code == 404

    def test_messages_get_another_users_conversation_404(self, agents_client):
        seed_org_role(agents_client, role="member")
        _seed_active_agent_and_persona(agents_client)
        other_user = uuid4()
        agent = agents_client.stores.agents.get_by_key(DEFAULT_ORG_ID, "julia")
        other_conv = agents_client.stores.conversations.create(DEFAULT_ORG_ID, agent.id, other_user)

        resp = agents_client.get(f"/api/conversations/{other_conv.id}/messages")
        assert resp.status_code == 404


class TestPostMessage:
    def test_agent_off_409(self, agents_client):
        seed_org_role(agents_client, role="member")
        _seed_active_agent_and_persona(agents_client, ativo=False)
        conv = agents_client.stores.conversations.create(
            DEFAULT_ORG_ID,
            agents_client.stores.agents.get_by_key(DEFAULT_ORG_ID, "julia").id,
            DEFAULT_USER_ID,
        )
        resp = agents_client.post(
            f"/api/conversations/{conv.id}/messages", json={"texto": "oi"}
        )
        assert resp.status_code == 409, resp.text
        assert resp.json()["code"] == "agent_off"

    def test_turn_in_progress_409(self, agents_client):
        seed_org_role(agents_client, role="member")
        agent = _seed_active_agent_and_persona(agents_client)
        conv = agents_client.stores.conversations.create(DEFAULT_ORG_ID, agent.id, DEFAULT_USER_ID)
        _install_runtime(agents_client, [{"event": "session.status", "payload": {"status": "ociosa"}}])

        # Simulate an already-held lock (another in-flight turn).
        agents_client.stores.conversations.try_acquire_turn(
            DEFAULT_ORG_ID, conv.id, "some-other-instance", 600
        )
        resp = agents_client.post(
            f"/api/conversations/{conv.id}/messages", json={"texto": "oi"}
        )
        assert resp.status_code == 409, resp.text
        assert resp.json()["code"] == "turn_in_progress"

    def test_empty_texto_rejected_422(self, agents_client):
        seed_org_role(agents_client, role="member")
        agent = _seed_active_agent_and_persona(agents_client)
        conv = agents_client.stores.conversations.create(DEFAULT_ORG_ID, agent.id, DEFAULT_USER_ID)
        resp = agents_client.post(f"/api/conversations/{conv.id}/messages", json={"texto": ""})
        assert resp.status_code == 422

    def test_rate_limited_after_threshold(self, agents_client, monkeypatch):
        seed_org_role(agents_client, role="member")
        agent = _seed_active_agent_and_persona(agents_client)
        conv = agents_client.stores.conversations.create(DEFAULT_ORG_ID, agent.id, DEFAULT_USER_ID)
        monkeypatch.setattr(
            "app.routers.conversations_router.settings.messages_rate_limit", "2/minute"
        )
        _install_runtime(
            agents_client, [{"event": "session.status", "payload": {"status": "ociosa"}}]
        )
        statuses = []
        for _ in range(4):
            resp = agents_client.post(
                f"/api/conversations/{conv.id}/messages", json={"texto": "oi"}
            )
            statuses.append(resp.status_code)
            # Release the lock between requests so a 409 never masks the
            # rate-limit boundary being tested.
            agents_client.stores.conversations.release_turn(
                DEFAULT_ORG_ID, conv.id,
                agents_client.stores.conversations.get(DEFAULT_ORG_ID, conv.id).sdk_session_id
                or "",
            )
        assert 429 in statuses, statuses


def _wait_until(predicate, *, timeout_s: float = 10.0, interval_s: float = 0.01) -> bool:
    """Poll ``predicate()`` from the test's (main) thread. Starlette's
    ``TestClient`` runs the whole ASGI app on a background-thread event
    loop that stays alive for the client's lifetime — a
    ``asyncio.create_task(...)`` spawned inside a request handler keeps
    running on that loop AFTER the response returns, exactly like
    production. There is no cross-thread ``await``, so polling (not
    ``asyncio.sleep``, which would run on the WRONG loop) is the correct
    synchronization primitive here."""
    import time

    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval_s)
    return predicate()


class TestFullScriptedTurn:
    def test_full_turn_persists_and_publishes_in_order(self, agents_client):
        seed_org_role(agents_client, role="member")
        agent = _seed_active_agent_and_persona(agents_client)
        conv = agents_client.stores.conversations.create(DEFAULT_ORG_ID, agent.id, DEFAULT_USER_ID)

        script = [
            {"event": "message.new", "payload": {"texto": "Vou verificar a KB."}},
            ("escrita", "mcp__academia__kb_escrever", {"slug": "x", "corpo_md": "y"}),
            {
                "event": "session.status",
                "payload": {"status": "ociosa", "sdk_session_id": "sdk-session-1"},
            },
        ]
        _install_runtime(agents_client, script, auto_decide=True)

        resp = agents_client.post(
            f"/api/conversations/{conv.id}/messages", json={"texto": "Registre uma decisão"}
        )
        assert resp.status_code == 202, resp.text
        body = resp.json()
        assert body["status"] == "processando"
        assert body["mensagem"]["role"] == "user"
        assert body["mensagem"]["texto"] == "Registre uma decisão"

        msg_store = agents_client.stores.messages
        conv_store = agents_client.stores.conversations

        # The turn is done once the lock is released (contract §E.9 point
        # 5/6 — `release_turn` is the LAST thing either the success or the
        # failure branch does).
        turn_finished = _wait_until(
            lambda: conv_store.try_acquire_turn(DEFAULT_ORG_ID, conv.id, "poll-probe", 1)
        )
        assert turn_finished, "turn never released the lock within the timeout"
        conv_store.release_turn(DEFAULT_ORG_ID, conv.id, "poll-probe")

        messages = msg_store.list(DEFAULT_ORG_ID, conv.id, limite=50)
        roles = [m.role for m in messages]
        # user (posted by the route) -> assistant (message.new) -> the
        # SAME assistant message carries the tool block from the escrita
        # entry (no new row for tool.*/approval.*, contract §E.9: appended
        # into the CURRENT assistant message's blocks).
        assert roles == ["user", "assistant"]

        assistant_message = messages[1]
        assert assistant_message.texto == "Vou verificar a KB."
        tool_blocks = [b for b in assistant_message.blocks if b["kind"] == "tool"]
        approval_blocks = [b for b in assistant_message.blocks if b["kind"] == "approval"]
        assert len(tool_blocks) == 1
        assert tool_blocks[0]["status"] == "ok"
        assert len(approval_blocks) == 1
        assert approval_blocks[0]["decision"] == "aprovada"

        conversation = conv_store.get_owned(DEFAULT_ORG_ID, conv.id, DEFAULT_USER_ID)
        assert conversation.sdk_session_id == "sdk-session-1"

    def test_exception_turn_yields_generic_system_message(self, agents_client):
        seed_org_role(agents_client, role="member")
        agent = _seed_active_agent_and_persona(agents_client)
        conv = agents_client.stores.conversations.create(DEFAULT_ORG_ID, agent.id, DEFAULT_USER_ID)

        class _ExplodingRuntime:
            async def run_turn(self, spec, ctx, prompt, broker):
                raise RuntimeError("segredo-interno-nao-deve-vazar")
                yield  # pragma: no cover — makes this an async generator

        from app.main import app

        app.dependency_overrides[get_agent_runtime_dep] = lambda: _ExplodingRuntime()
        app.dependency_overrides[get_approval_broker_dep] = lambda: InProcessApprovalBroker(
            agents_client.stores.approvals, agents_client.stores.conversations,
            instance_id="test-instance",
        )
        app.dependency_overrides[get_build_julia_spec_dep] = lambda: fake_build_julia_spec

        resp = agents_client.post(
            f"/api/conversations/{conv.id}/messages", json={"texto": "vai falhar"}
        )
        assert resp.status_code == 202, resp.text

        conv_store = agents_client.stores.conversations
        turn_finished = _wait_until(
            lambda: conv_store.try_acquire_turn(DEFAULT_ORG_ID, conv.id, "poll-probe", 1)
        )
        assert turn_finished
        conv_store.release_turn(DEFAULT_ORG_ID, conv.id, "poll-probe")

        messages = agents_client.stores.messages.list(DEFAULT_ORG_ID, conv.id, limite=50)
        system_messages = [m for m in messages if m.role == "system"]
        assert len(system_messages) == 1
        assert system_messages[0].texto == "O turno falhou."
        assert "segredo-interno-nao-deve-vazar" not in system_messages[0].texto


class TestSSEStreamAuth:
    """Only the boundary (401 / 404) is exercised here — the 200 success
    path establishes a genuine ``StreamingResponse`` whose body never
    terminates (an SSE heartbeat loop), and Starlette's ``TestClient``
    runs the whole ASGI call to completion synchronously (``portal.call``)
    rather than truly streaming, so a successful connection cannot be
    asserted-and-closed without either hanging or racing the 20s
    heartbeat. Contract §G.4 covers the live-stream content assertion as
    an e2e check against a running server, not this unit suite."""

    def test_non_owner_gets_404(self, agents_client):
        seed_org_role(agents_client, role="member")
        agent = _seed_active_agent_and_persona(agents_client)
        other_user = uuid4()
        other_conv = agents_client.stores.conversations.create(DEFAULT_ORG_ID, agent.id, other_user)
        resp = agents_client.raw().get(
            f"/api/conversations/{other_conv.id}/stream",
            headers={"Authorization": "Bearer test-token-valid"},
        )
        assert resp.status_code == 404
