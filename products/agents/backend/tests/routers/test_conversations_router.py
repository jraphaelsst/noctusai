"""Tests for ``/api/conversations`` — CRUD, the turn loop, SSE auth
(contract §E.2, §E.3, §E.9, §E.11).

The turn-loop tests drive G2's REAL runtime/broker
(``app.runtime.fake_runtime.FakeAgentRuntime`` /
``app.runtime.broker.StoreApprovalBroker``) via ``install_runtime`` —
never a G1b-local stand-in. An escrita script entry blocks on a real
``asyncio.Future`` inside the broker until the test decides it through
the ACTUAL ``POST /api/approvals/{id}/decision`` endpoint, exactly as a
human approver would.
"""
from __future__ import annotations

from uuid import uuid4

from app.dependencies import get_agent_runtime_dep, get_approval_broker_dep
from app.realtime import conversation_scope
from app.runtime.broker import StoreApprovalBroker
from tests.routers.conftest import (
    DEFAULT_ORG_ID,
    DEFAULT_USER_ID,
    install_runtime,
    seed_active_agent_and_persona,
    seed_org_role,
    wait_for_pending_approval,
    wait_turn_released,
    wait_until,
)


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

    def test_rename_requires_auth(self, agents_client):
        resp = agents_client.raw().patch(
            f"/api/conversations/{uuid4()}", json={"titulo": "Nova"}
        )
        assert resp.status_code == 401


class TestCreateAndList:
    def test_create_and_get(self, agents_client):
        seed_org_role(agents_client, role="member")
        seed_active_agent_and_persona(agents_client)
        resp = agents_client.post("/api/conversations", json={"titulo": "Primeira"})
        assert resp.status_code == 201, resp.text
        conv_id = resp.json()["id"]

        get_resp = agents_client.get(f"/api/conversations/{conv_id}")
        assert get_resp.status_code == 200, get_resp.text
        assert get_resp.json()["titulo"] == "Primeira"

    def test_list_only_own(self, agents_client):
        seed_org_role(agents_client, role="member")
        seed_active_agent_and_persona(agents_client)
        agents_client.post("/api/conversations", json={})
        resp = agents_client.get("/api/conversations")
        assert resp.status_code == 200, resp.text
        assert resp.json()["total"] == 1


class TestConversationOwnershipBoundary:
    def test_get_another_users_conversation_404(self, agents_client):
        seed_org_role(agents_client, role="member")
        seed_active_agent_and_persona(agents_client)
        other_user = uuid4()
        agent = agents_client.stores.agents.get_by_key(DEFAULT_ORG_ID, "julia")
        other_conv = agents_client.stores.conversations.create(DEFAULT_ORG_ID, agent.id, other_user)

        resp = agents_client.get(f"/api/conversations/{other_conv.id}")
        assert resp.status_code == 404

    def test_admin_can_read_another_users_conversation(self, agents_client):
        seed_org_role(agents_client, role="owner")
        seed_active_agent_and_persona(agents_client)
        other_user = uuid4()
        agent = agents_client.stores.agents.get_by_key(DEFAULT_ORG_ID, "julia")
        other_conv = agents_client.stores.conversations.create(DEFAULT_ORG_ID, agent.id, other_user)

        resp = agents_client.get(f"/api/conversations/{other_conv.id}")
        assert resp.status_code == 200, resp.text

    def test_post_message_to_another_users_conversation_404(self, agents_client):
        seed_org_role(agents_client, role="owner")  # even admins may not POST
        seed_active_agent_and_persona(agents_client)
        other_user = uuid4()
        agent = agents_client.stores.agents.get_by_key(DEFAULT_ORG_ID, "julia")
        other_conv = agents_client.stores.conversations.create(DEFAULT_ORG_ID, agent.id, other_user)

        resp = agents_client.post(
            f"/api/conversations/{other_conv.id}/messages", json={"texto": "oi"}
        )
        assert resp.status_code == 404

    def test_messages_get_another_users_conversation_404(self, agents_client):
        seed_org_role(agents_client, role="member")
        seed_active_agent_and_persona(agents_client)
        other_user = uuid4()
        agent = agents_client.stores.agents.get_by_key(DEFAULT_ORG_ID, "julia")
        other_conv = agents_client.stores.conversations.create(DEFAULT_ORG_ID, agent.id, other_user)

        resp = agents_client.get(f"/api/conversations/{other_conv.id}/messages")
        assert resp.status_code == 404

    def test_rename_another_users_conversation_404(self, agents_client):
        seed_org_role(agents_client, role="owner")  # even admins may not rename
        seed_active_agent_and_persona(agents_client)
        other_user = uuid4()
        agent = agents_client.stores.agents.get_by_key(DEFAULT_ORG_ID, "julia")
        other_conv = agents_client.stores.conversations.create(DEFAULT_ORG_ID, agent.id, other_user)

        resp = agents_client.patch(
            f"/api/conversations/{other_conv.id}", json={"titulo": "Sequestrada"}
        )
        assert resp.status_code == 404


class TestRenameConversation:
    def test_rename_happy_path(self, agents_client):
        seed_org_role(agents_client, role="member")
        seed_active_agent_and_persona(agents_client)
        create_resp = agents_client.post("/api/conversations", json={"titulo": "Original"})
        conv_id = create_resp.json()["id"]

        resp = agents_client.patch(
            f"/api/conversations/{conv_id}", json={"titulo": "  Renomeada  "}
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["titulo"] == "Renomeada"
        assert body["id"] == conv_id

        get_resp = agents_client.get(f"/api/conversations/{conv_id}")
        assert get_resp.json()["titulo"] == "Renomeada"

    def test_rename_unknown_conversation_404(self, agents_client):
        seed_org_role(agents_client, role="member")
        seed_active_agent_and_persona(agents_client)
        resp = agents_client.patch(
            f"/api/conversations/{uuid4()}", json={"titulo": "Nova"}
        )
        assert resp.status_code == 404

    def test_rename_blank_after_trim_422(self, agents_client):
        seed_org_role(agents_client, role="member")
        seed_active_agent_and_persona(agents_client)
        create_resp = agents_client.post("/api/conversations", json={"titulo": "Original"})
        conv_id = create_resp.json()["id"]

        resp = agents_client.patch(f"/api/conversations/{conv_id}", json={"titulo": "   "})
        assert resp.status_code == 422

    def test_rename_too_long_422(self, agents_client):
        seed_org_role(agents_client, role="member")
        seed_active_agent_and_persona(agents_client)
        create_resp = agents_client.post("/api/conversations", json={"titulo": "Original"})
        conv_id = create_resp.json()["id"]

        resp = agents_client.patch(
            f"/api/conversations/{conv_id}", json={"titulo": "x" * 121}
        )
        assert resp.status_code == 422

    def test_rename_missing_titulo_422(self, agents_client):
        seed_org_role(agents_client, role="member")
        seed_active_agent_and_persona(agents_client)
        create_resp = agents_client.post("/api/conversations", json={"titulo": "Original"})
        conv_id = create_resp.json()["id"]

        resp = agents_client.patch(f"/api/conversations/{conv_id}", json={})
        assert resp.status_code == 422

    def test_rename_unknown_field_422(self, agents_client):
        """``StrictHttpModel`` — ``extra="forbid"`` (contract §0 "Strictness")."""
        seed_org_role(agents_client, role="member")
        seed_active_agent_and_persona(agents_client)
        create_resp = agents_client.post("/api/conversations", json={"titulo": "Original"})
        conv_id = create_resp.json()["id"]

        resp = agents_client.patch(
            f"/api/conversations/{conv_id}", json={"titulo": "Nova", "status": "arquivada"}
        )
        assert resp.status_code == 422


class TestPostMessage:
    def test_agent_off_409(self, agents_client):
        seed_org_role(agents_client, role="member")
        seed_active_agent_and_persona(agents_client, ativo=False)
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
        agent = seed_active_agent_and_persona(agents_client)
        conv = agents_client.stores.conversations.create(DEFAULT_ORG_ID, agent.id, DEFAULT_USER_ID)
        install_runtime(agents_client, [])

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
        agent = seed_active_agent_and_persona(agents_client)
        conv = agents_client.stores.conversations.create(DEFAULT_ORG_ID, agent.id, DEFAULT_USER_ID)
        resp = agents_client.post(f"/api/conversations/{conv.id}/messages", json={"texto": ""})
        assert resp.status_code == 422

    def test_rate_limited_after_threshold(self, agents_client, monkeypatch):
        seed_org_role(agents_client, role="member")
        agent = seed_active_agent_and_persona(agents_client)
        conv = agents_client.stores.conversations.create(DEFAULT_ORG_ID, agent.id, DEFAULT_USER_ID)
        monkeypatch.setattr(
            "app.routers.conversations_router.settings.messages_rate_limit", "2/minute"
        )
        install_runtime(agents_client, [])
        statuses = []
        for _ in range(4):
            resp = agents_client.post(
                f"/api/conversations/{conv.id}/messages", json={"texto": "oi"}
            )
            statuses.append(resp.status_code)
            if resp.status_code == 202:
                # Wait for THIS iteration's background task to release the
                # turn lock before the next iteration — a 409 from lock
                # contention (rather than the rate limit itself) would
                # mask the boundary this test exists to check, and an
                # un-joined task must never be left running into the next
                # test (see `wait_turn_released`'s docstring).
                wait_turn_released(agents_client.stores.conversations, DEFAULT_ORG_ID, conv.id)
        assert 429 in statuses, statuses


class TestFullScriptedTurn:
    def test_full_turn_persists_and_publishes_in_order(self, agents_client):
        seed_org_role(agents_client, role="member")
        agent = seed_active_agent_and_persona(agents_client)
        conv = agents_client.stores.conversations.create(DEFAULT_ORG_ID, agent.id, DEFAULT_USER_ID)

        script = [
            {"event": "message.new", "payload": {"texto": "Vou verificar a KB."}},
            ("escrita", "mcp__academia__kb_escrever", {"slug": "x", "corpo_md": "y"}),
        ]
        install_runtime(agents_client, script)

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

        # The escrita entry blocks the background task inside a REAL
        # `broker.request()` future — decide it through the actual HTTP
        # endpoint, exactly like a human approver would.
        approval = wait_for_pending_approval(agents_client.stores.approvals, DEFAULT_ORG_ID)
        decide_resp = agents_client.post(
            f"/api/approvals/{approval.id}/decision", json={"aprovada": True}
        )
        assert decide_resp.status_code == 200, decide_resp.text

        # The turn is done once the lock is released (contract §E.9 point
        # 5/6 — `release_turn` is the LAST thing either the success or the
        # failure branch does). G2's `FakeAgentRuntime` always appends a
        # final `session.status` with a generated `sdk_session_id` once
        # the script is exhausted.
        turn_finished = wait_turn_released(conv_store, DEFAULT_ORG_ID, conv.id)
        assert turn_finished, "turn never released the lock within the timeout"

        messages = msg_store.list(DEFAULT_ORG_ID, conv.id, limite=50)
        roles = [m.role for m in messages]
        # user (posted by the route) -> assistant (message.new) -> the
        # SAME assistant message carries the tool block from the escrita
        # entry (no new row for tool.*/approval.*, contract §E.9: appended
        # into the CURRENT assistant message's blocks).
        assert roles == ["user", "assistant"], messages

        assistant_message = messages[1]
        assert assistant_message.texto == "Vou verificar a KB."
        tool_blocks = [b for b in assistant_message.blocks if b["kind"] == "tool"]
        approval_blocks = [b for b in assistant_message.blocks if b["kind"] == "approval"]
        assert len(tool_blocks) == 1, assistant_message.blocks
        assert tool_blocks[0]["status"] == "ok"
        assert len(approval_blocks) == 1
        assert approval_blocks[0]["decision"] == "aprovada"
        assert approval_blocks[0]["approvalId"] == str(approval.id)

        conversation = conv_store.get_owned(DEFAULT_ORG_ID, conv.id, DEFAULT_USER_ID)
        assert conversation.sdk_session_id, "session.status must carry a sdk_session_id"

    def test_exception_turn_yields_generic_system_message(self, agents_client):
        seed_org_role(agents_client, role="member")
        agent = seed_active_agent_and_persona(agents_client)
        conv = agents_client.stores.conversations.create(DEFAULT_ORG_ID, agent.id, DEFAULT_USER_ID)

        class _ExplodingSlot:
            """Minimal stand-in for `app.runtime.slots.TurnSlot` — B4's
            route/turn-loop now always reserves + releases a slot, so
            even a hand-rolled runtime double needs one."""

            async def release(self) -> None:
                return None

        class _ExplodingRuntime:
            def try_reserve(self):
                return _ExplodingSlot()

            async def run_turn(self, spec, ctx, prompt, broker, slot=None):
                raise RuntimeError("segredo-interno-nao-deve-vazar")
                yield  # pragma: no cover — makes this an async generator

        from app.main import app

        app.dependency_overrides[get_agent_runtime_dep] = lambda: _ExplodingRuntime()
        app.dependency_overrides[get_approval_broker_dep] = lambda: StoreApprovalBroker(
            agents_client.stores.approvals, timeout_seconds=5, instance_id="test-instance"
        )

        resp = agents_client.post(
            f"/api/conversations/{conv.id}/messages", json={"texto": "vai falhar"}
        )
        assert resp.status_code == 202, resp.text

        conv_store = agents_client.stores.conversations
        turn_finished = wait_turn_released(conv_store, DEFAULT_ORG_ID, conv.id)
        assert turn_finished

        messages = agents_client.stores.messages.list(DEFAULT_ORG_ID, conv.id, limite=50)
        system_messages = [m for m in messages if m.role == "system"]
        assert len(system_messages) == 1
        assert system_messages[0].texto == "O turno falhou."
        assert "segredo-interno-nao-deve-vazar" not in system_messages[0].texto


def _session_status_payloads(agents_client, conversation_id) -> list[dict]:
    """The ``session.status`` payloads a conversation's stream published,
    in publish order — same internal-introspection idiom as the
    canonical-fixture test's ``_published_events`` (no public "dump"
    method exists on ``FakeRealtimeBus``)."""
    scope = conversation_scope(conversation_id)
    stream = agents_client.stores.bus._streams.get(scope, [])
    return [e.payload for e in stream if e.event == "session.status"]


class TestSlotCapacityAndReleaseEveryPath:
    """Contract §E.11 "Route order" + "Slot pool" — every exit path
    releases the reserved slot (and, once acquired, the turn lock)
    exactly once. Asserted on the pool's own ``try_reserve()`` /
    ``health()`` — never a mock of our own code."""

    def test_429_at_capacity_flat_body_retry_after_no_persist_no_lock(
        self, agents_client
    ):
        seed_org_role(agents_client, role="member")
        agent = seed_active_agent_and_persona(agents_client)
        conv = agents_client.stores.conversations.create(DEFAULT_ORG_ID, agent.id, DEFAULT_USER_ID)
        runtime, _broker = install_runtime(agents_client, [], capacity=1)

        # Exhaust the single slot directly — isolates the 429 branch from
        # any timing dependency on a first HTTP request.
        held = runtime.try_reserve()
        assert held is not None

        resp = agents_client.post(
            f"/api/conversations/{conv.id}/messages", json={"texto": "oi"}
        )
        assert resp.status_code == 429, resp.text
        assert resp.json() == {
            "detail": (
                "A Julia está atendendo o número máximo de conversas agora. "
                "Tente novamente em instantes."
            ),
            "code": "julia_capacidade",
        }
        assert resp.headers["retry-after"] == "10"

        # No user message persisted.
        messages = agents_client.stores.messages.list(DEFAULT_ORG_ID, conv.id, limite=50)
        assert messages == []

        # No lock taken — a probe acquires it immediately.
        conv_store = agents_client.stores.conversations
        probe_acquired = conv_store.try_acquire_turn(DEFAULT_ORG_ID, conv.id, "probe-429", 1)
        assert probe_acquired
        conv_store.release_turn(DEFAULT_ORG_ID, conv.id, "probe-429")

    def test_409_turn_in_progress_releases_the_reserved_slot_no_persist(
        self, agents_client
    ):
        seed_org_role(agents_client, role="member")
        agent = seed_active_agent_and_persona(agents_client)
        conv = agents_client.stores.conversations.create(DEFAULT_ORG_ID, agent.id, DEFAULT_USER_ID)
        runtime, _broker = install_runtime(agents_client, [], capacity=1)

        # Simulate an already in-flight turn (another instance holds the lock).
        agents_client.stores.conversations.try_acquire_turn(
            DEFAULT_ORG_ID, conv.id, "some-other-instance", 600
        )

        resp = agents_client.post(
            f"/api/conversations/{conv.id}/messages", json={"texto": "oi"}
        )
        assert resp.status_code == 409, resp.text
        assert resp.json()["code"] == "turn_in_progress"

        messages = agents_client.stores.messages.list(DEFAULT_ORG_ID, conv.id, limite=50)
        assert messages == [], "the orphan-message bug: no message may persist on a 409"

        # Capacity is 1 — a second reservation succeeding proves the
        # first one (consumed by the 429... here, the 409 branch) was
        # released back to the pool.
        assert runtime.try_reserve() is not None

    def test_normal_completion_releases_the_slot(self, agents_client):
        seed_org_role(agents_client, role="member")
        agent = seed_active_agent_and_persona(agents_client)
        conv = agents_client.stores.conversations.create(DEFAULT_ORG_ID, agent.id, DEFAULT_USER_ID)
        runtime, _broker = install_runtime(agents_client, [], capacity=1)

        resp = agents_client.post(
            f"/api/conversations/{conv.id}/messages", json={"texto": "oi"}
        )
        assert resp.status_code == 202, resp.text

        conv_store = agents_client.stores.conversations
        assert wait_turn_released(conv_store, DEFAULT_ORG_ID, conv.id)
        assert wait_until(lambda: runtime.try_reserve() is not None), (
            "slot never returned to the pool after a normal turn"
        )

    def test_runtime_exception_releases_the_slot(self, agents_client):
        """Same shape as ``TestFullScriptedTurn::
        test_exception_turn_yields_generic_system_message``, but asserts
        the SLOT side of release (contract §E.11) via a hand-rolled
        double that owns its own real ``FakeSlotPool`` — never the
        default-capacity shared runtime, so ``try_reserve()`` after
        release is a genuine capacity-exhaustion proof."""
        from app.runtime.slots import FakeSlotPool

        seed_org_role(agents_client, role="member")
        agent = seed_active_agent_and_persona(agents_client)
        conv = agents_client.stores.conversations.create(DEFAULT_ORG_ID, agent.id, DEFAULT_USER_ID)

        class _ExplodingRuntime:
            def __init__(self) -> None:
                self.pool = FakeSlotPool(1)

            def try_reserve(self):
                return self.pool.try_reserve()

            async def run_turn(self, spec, ctx, prompt, broker, slot=None):
                raise RuntimeError("segredo-interno-nao-deve-vazar")
                yield  # pragma: no cover — makes this an async generator

        runtime = _ExplodingRuntime()
        from app.main import app

        app.dependency_overrides[get_agent_runtime_dep] = lambda: runtime
        app.dependency_overrides[get_approval_broker_dep] = lambda: StoreApprovalBroker(
            agents_client.stores.approvals, timeout_seconds=5, instance_id="test-instance"
        )

        resp = agents_client.post(
            f"/api/conversations/{conv.id}/messages", json={"texto": "vai falhar"}
        )
        assert resp.status_code == 202, resp.text

        conv_store = agents_client.stores.conversations
        assert wait_turn_released(conv_store, DEFAULT_ORG_ID, conv.id)
        assert wait_until(lambda: runtime.pool.health()["free"] == 1), runtime.pool.health()

    def test_turn_deadline_persists_generic_message_erro_status_and_releases_slot(
        self, agents_client, monkeypatch
    ):
        seed_org_role(agents_client, role="member")
        agent = seed_active_agent_and_persona(agents_client)
        conv = agents_client.stores.conversations.create(DEFAULT_ORG_ID, agent.id, DEFAULT_USER_ID)

        # An escrita entry blocks on a REAL, un-resolved broker future — a
        # broker timeout generous enough (5s) that the OUTER turn deadline
        # below (0.05s) fires first.
        script = [("escrita", "mcp__academia__kb_escrever", {"slug": "exemplo", "corpo_md": "x"})]
        runtime, _broker = install_runtime(agents_client, script, timeout_seconds=5, capacity=1)
        monkeypatch.setattr(
            "app.routers.conversations_router.settings.turn_timeout_seconds", 0.05
        )

        resp = agents_client.post(
            f"/api/conversations/{conv.id}/messages", json={"texto": "oi"}
        )
        assert resp.status_code == 202, resp.text

        conv_store = agents_client.stores.conversations
        assert wait_turn_released(conv_store, DEFAULT_ORG_ID, conv.id)

        messages = agents_client.stores.messages.list(DEFAULT_ORG_ID, conv.id, limite=50)
        system_messages = [m for m in messages if m.role == "system"]
        assert len(system_messages) == 1
        assert system_messages[0].texto == "O turno excedeu o tempo limite."

        statuses = _session_status_payloads(agents_client, conv.id)
        assert statuses[-1] == {"status": "erro"}

        assert wait_until(lambda: runtime.try_reserve() is not None), (
            "slot never returned to the pool after the turn deadline"
        )

    def test_task_cancellation_releases_lock_and_slot(self, agents_client):
        seed_org_role(agents_client, role="member")
        agent = seed_active_agent_and_persona(agents_client)
        conv = agents_client.stores.conversations.create(DEFAULT_ORG_ID, agent.id, DEFAULT_USER_ID)

        # Same blocking shape as the deadline test, but nobody shortens
        # `turn_timeout_seconds` here — the task is cancelled from OUTSIDE
        # while genuinely suspended inside `broker.request()`, distinct
        # from the deadline firing on its own.
        script = [("escrita", "mcp__academia__kb_escrever", {"slug": "exemplo", "corpo_md": "x"})]
        runtime, _broker = install_runtime(agents_client, script, timeout_seconds=30, capacity=1)

        resp = agents_client.post(
            f"/api/conversations/{conv.id}/messages", json={"texto": "oi"}
        )
        assert resp.status_code == 202, resp.text

        # Proves the task is genuinely suspended (not merely unscheduled)
        # before cancelling it.
        wait_for_pending_approval(agents_client.stores.approvals, DEFAULT_ORG_ID)

        from app.main import app

        tasks = list(getattr(app.state, "agents_background_tasks", ()))
        assert len(tasks) == 1
        tasks[0].get_loop().call_soon_threadsafe(tasks[0].cancel)

        conv_store = agents_client.stores.conversations
        assert wait_turn_released(conv_store, DEFAULT_ORG_ID, conv.id)
        assert wait_until(lambda: runtime.try_reserve() is not None), (
            "slot never returned to the pool after task cancellation"
        )


class TestCostControl:
    """Contract §L: the turn loop stamps the SDK's cost/token counts (off
    ``run_turn``'s final ``session.status`` event) on the assistant message
    that turn persisted."""

    def test_turn_cost_lands_on_the_assistant_message(self, agents_client):
        from app.runtime.fake_runtime import FakeAgentRuntime
        from app.runtime.broker import StoreApprovalBroker
        from app.main import app

        seed_org_role(agents_client, role="member")
        agent = seed_active_agent_and_persona(agents_client)
        conv = agents_client.stores.conversations.create(DEFAULT_ORG_ID, agent.id, DEFAULT_USER_ID)

        script = [{"event": "message.new", "payload": {"texto": "Olá!"}}]
        runtime = FakeAgentRuntime(
            script, custo_usd=0.0042, tokens_entrada=300, tokens_saida=90, tokens_cache_leitura=15,
        )
        broker = StoreApprovalBroker(agents_client.stores.approvals, instance_id="test-instance")
        app.dependency_overrides[get_agent_runtime_dep] = lambda: runtime
        app.dependency_overrides[get_approval_broker_dep] = lambda: broker

        resp = agents_client.post(
            f"/api/conversations/{conv.id}/messages", json={"texto": "Oi"}
        )
        assert resp.status_code == 202, resp.text

        conv_store = agents_client.stores.conversations
        assert wait_turn_released(conv_store, DEFAULT_ORG_ID, conv.id)

        messages = agents_client.stores.messages.list(DEFAULT_ORG_ID, conv.id, limite=50)
        assistant_message = next(m for m in messages if m.role == "assistant")
        assert assistant_message.custo_usd == 0.0042
        assert assistant_message.tokens_entrada == 300
        assert assistant_message.tokens_saida == 90

        # And the GET response surfaces it (§L: "make cost visible").
        listed = agents_client.get(f"/api/conversations/{conv.id}/messages")
        assert listed.status_code == 200, listed.text
        out = next(m for m in listed.json()["items"] if m["role"] == "assistant")
        assert out["custo_usd"] == 0.0042
        assert out["tokens_entrada"] == 300
        assert out["tokens_saida"] == 90

    def test_no_cost_reported_stays_null(self, agents_client):
        """No `ResultMessage` (or no cost fields on it) -> null, never 0."""
        seed_org_role(agents_client, role="member")
        agent = seed_active_agent_and_persona(agents_client)
        conv = agents_client.stores.conversations.create(DEFAULT_ORG_ID, agent.id, DEFAULT_USER_ID)

        script = [{"event": "message.new", "payload": {"texto": "Olá!"}}]
        install_runtime(agents_client, script)  # default FakeAgentRuntime — no cost scripted

        resp = agents_client.post(
            f"/api/conversations/{conv.id}/messages", json={"texto": "Oi"}
        )
        assert resp.status_code == 202, resp.text
        conv_store = agents_client.stores.conversations
        assert wait_turn_released(conv_store, DEFAULT_ORG_ID, conv.id)

        messages = agents_client.stores.messages.list(DEFAULT_ORG_ID, conv.id, limite=50)
        assistant_message = next(m for m in messages if m.role == "assistant")
        assert assistant_message.custo_usd is None
        assert assistant_message.tokens_entrada is None


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
        agent = seed_active_agent_and_persona(agents_client)
        other_user = uuid4()
        other_conv = agents_client.stores.conversations.create(DEFAULT_ORG_ID, agent.id, other_user)
        resp = agents_client.raw().get(
            f"/api/conversations/{other_conv.id}/stream",
            headers={"Authorization": "Bearer test-token-valid"},
        )
        assert resp.status_code == 404
