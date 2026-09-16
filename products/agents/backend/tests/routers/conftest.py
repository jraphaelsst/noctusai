"""Shared fixtures for the G1b router test suite.

``agents_client`` overrides every ``get_*_store_dep`` / ``get_*_client_dep``
FastAPI dependency (``app/dependencies.py``) with a single SHARED Fake
instance per store — a real dependency-injection seam
(``app.dependency_overrides``), never a settings-attribute monkeypatch. The
default (no override) path constructs a brand-new, immediately-discarded
``Fake*Store()`` on EVERY call, which cannot carry state across two HTTP
requests inside one test.
"""
from __future__ import annotations

from uuid import UUID, uuid5, NAMESPACE_OID

import pytest

from app.clients.social_wiring import FakeSocialWiringClient
from app.dependencies import (
    get_agent_runtime_dep,
    get_agent_store_dep,
    get_approval_broker_dep,
    get_approval_store_dep,
    get_conversation_store_dep,
    get_message_store_dep,
    get_persona_store_dep,
    get_realtime_bus_dep,
    get_social_wiring_client_dep,
)
from app.runtime.broker import StoreApprovalBroker
from app.runtime.fake_runtime import FakeAgentRuntime
from app.stores.agents import FakeAgentStore
from app.stores.approvals import FakeApprovalStore
from app.stores.conversations import FakeConversationStore
from app.stores.messages import FakeMessageStore
from app.stores.personas import FakePersonaStore
from noctusai_lib.realtime import FakeRealtimeBus
from noctusai_lib.testing import MockUser, MockUserResponse
from noctusai_lib.testing.clients import TEST_USER_ID

#: The `client` fixture's default bearer is a JWT-shaped opaque token
#: (never `pk_*`), resolved through the legacy-JWT bridge. Its default
#: `MockUser(org_id="test-org-123")` org_id AND `TEST_USER_ID`
#: ("test-user-123") are both non-UUID opaque strings — the bridge's
#: `coerce_org_uuid` / `uuid5(NAMESPACE_OID, ...)` fallback deterministically
#: maps each to the SAME UUID every time, so every test that doesn't
#: re-bind `auth.get_user` shares these two UUIDs.
DEFAULT_ORG_ID: UUID = uuid5(NAMESPACE_OID, "test-org-123")
DEFAULT_USER_ID: UUID = uuid5(NAMESPACE_OID, TEST_USER_ID)


class _Stores:
    """Bag of the shared Fake store/client instances one test's stack of
    HTTP requests all resolve to, via ``app.dependency_overrides``."""

    def __init__(self) -> None:
        self.agents = FakeAgentStore()
        self.conversations = FakeConversationStore()
        self.messages = FakeMessageStore()
        self.personas = FakePersonaStore()
        self.approvals = FakeApprovalStore()
        self.social_wiring = FakeSocialWiringClient()
        self.bus = FakeRealtimeBus()


@pytest.fixture
def agents_client(client):
    """The shared ``client`` fixture, with every store/client dependency
    overridden onto a shared, stateful Fake set (``client.stores``).

    Also ENTERS the underlying ``starlette.testclient.TestClient`` as a
    context manager for the test's duration. The top-level ``client``
    fixture builds a bare (never-entered) ``TestClient(app)`` — Starlette
    then opens a BRAND-NEW ``anyio`` portal PER REQUEST
    (``_TestClientTransport.handle_request``'s ``with self.portal_factory()
    as portal:``) and tears it down (cancelling every task still running
    on it) the instant that ONE request's response finishes sending. A
    turn-loop background task that only completes SYNCHRONOUSLY before the
    response returns survives by coincidence; one that genuinely suspends
    — e.g. ``StoreApprovalBroker.request()`` awaiting an unresolved
    ``asyncio.Future`` across TWO separate HTTP calls (the escrita POST,
    then the decision POST) — gets a real ``asyncio.CancelledError`` the
    moment the FIRST request's throwaway portal exits (confirmed
    empirically, 2026-09-14: tracing showed ``request()``'s
    ``asyncio.wait_for`` raising ``CancelledError`` within the same
    request, before any decision could arrive). Entering the context
    manager here builds ONE portal that stays alive for every request this
    fixture's caller makes, matching production (uvicorn never tears down
    the event loop between requests). Scoped to THIS fixture only — the
    shared root ``tests/conftest.py::client`` fixture (used by every other
    test file in this product) is deliberately left untouched."""
    from app.main import app

    tc = client.raw()
    tc.__enter__()

    stores = _Stores()
    app.dependency_overrides[get_agent_store_dep] = lambda: stores.agents
    app.dependency_overrides[get_conversation_store_dep] = lambda: stores.conversations
    app.dependency_overrides[get_message_store_dep] = lambda: stores.messages
    app.dependency_overrides[get_persona_store_dep] = lambda: stores.personas
    app.dependency_overrides[get_approval_store_dep] = lambda: stores.approvals
    app.dependency_overrides[get_social_wiring_client_dep] = lambda: stores.social_wiring
    # A real `RedisRealtimeBus` is constructed whenever `settings.redis_url`
    # is truthy (the fleet-wide default), regardless of whether Redis is
    # actually reachable — a publish then attempts (and, in some
    # environments, takes several real seconds to fail) a genuine network
    # connection. Overriding this dependency keeps every test's publish
    # calls in-memory and instant, matching the other Fake-store overrides.
    app.dependency_overrides[get_realtime_bus_dep] = lambda: stores.bus
    # Default runtime/broker — every `POST .../messages` route declares
    # these as `Depends(...)` UNCONDITIONALLY (FastAPI resolves every
    # dependency before the route body runs, including for a request that
    # 404s/409s/422s before ever touching the turn loop), so a test that
    # doesn't care about turn behaviour still needs SOMETHING here. Both
    # are G2's REAL implementations (`app.runtime.fake_runtime.
    # FakeAgentRuntime` / `app.runtime.broker.StoreApprovalBroker`) —
    # never a G1b-local stand-in. `get_build_julia_spec_dep` is NOT
    # overridden: G2's real `build_julia_spec` reads two shipped files
    # (`JULIA.md` / `spec.yaml`) and a persona row — no test double needed.
    #
    # `get_approval_broker(settings)` (the un-overridden factory) is a
    # PROCESS-WIDE singleton bound to whatever `get_approval_store(settings)`
    # resolves to at its FIRST call in this process — never this test's own
    # `stores.approvals`. Every test therefore builds its OWN
    # `StoreApprovalBroker` over `stores.approvals` instead of calling the
    # factory, exactly like every other store override in this fixture.
    default_runtime = FakeAgentRuntime([])
    default_broker = StoreApprovalBroker(
        stores.approvals, timeout_seconds=5, instance_id="default-test-instance"
    )
    app.dependency_overrides[get_agent_runtime_dep] = lambda: default_runtime
    app.dependency_overrides[get_approval_broker_dep] = lambda: default_broker
    client.stores = stores
    try:
        yield client
    finally:
        for dep in (
            get_agent_store_dep,
            get_conversation_store_dep,
            get_message_store_dep,
            get_persona_store_dep,
            get_approval_store_dep,
            get_social_wiring_client_dep,
            get_realtime_bus_dep,
            # Defensively cleared too — individual test files that install
            # their own script/broker via these same dependency-override
            # keys must never leak into a later test that didn't ask for one.
            get_agent_runtime_dep,
            get_approval_broker_dep,
        ):
            app.dependency_overrides.pop(dep, None)
        tc.__exit__(None, None, None)


def seed_org_role(client, *, user_id: UUID = DEFAULT_USER_ID, org_id: UUID = DEFAULT_ORG_ID, role: str = "owner") -> None:
    """Seed the ``noctus_users`` row ``resolve_org_role`` looks up."""
    client.mock_supabase.set_table_data(
        "noctus_users",
        [{"id": str(user_id), "org_id": str(org_id), "org_role": role}],
    )


def bind_user(client, *, user_id: UUID = DEFAULT_USER_ID, org_id: UUID = DEFAULT_ORG_ID) -> None:
    """Re-bind ``auth.get_user`` to a specific (user_id, org_id) pair —
    for tests exercising a SECOND, non-owning caller."""
    from unittest.mock import MagicMock

    client.mock_supabase.auth.get_user = MagicMock(
        return_value=MockUserResponse(MockUser(id=str(user_id), org_id=str(org_id)))
    )


def seed_active_agent_and_persona(agents_client, *, ativo: bool = True):
    """Julia, active, with a published persona — the minimum fixture every
    turn-loop / persona test needs."""
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


def install_runtime(
    agents_client, script, *, timeout_seconds: float = 30.0, capacity: int | None = None
):
    """Override the runtime/broker dependency seams with G2's REAL
    implementations: a scripted ``FakeAgentRuntime`` (never a G1b stand-in)
    and a ``StoreApprovalBroker`` bound to THIS test's own approvals store.
    Returns ``(runtime, broker)`` — tests that need to drive a real
    ``broker.request()``/``resolve()`` round-trip use the returned broker
    only for introspection; the actual `resolve()` call happens through
    the HTTP endpoint, exactly like a real caller.

    ``capacity`` (contract §E.11) sizes the runtime's internal
    ``FakeSlotPool`` — ``None`` keeps ``FakeAgentRuntime``'s own default
    (``DEFAULT_SLOT_COUNT``, matching the real deploy's 3 slots). B4's
    capacity/429 tests pass a small explicit value so the pool exhausts
    with few requests."""
    from app.main import app

    runtime = (
        FakeAgentRuntime(script, capacity=capacity)
        if capacity is not None
        else FakeAgentRuntime(script)
    )
    broker = StoreApprovalBroker(
        agents_client.stores.approvals, timeout_seconds=timeout_seconds, instance_id="test-instance"
    )
    app.dependency_overrides[get_agent_runtime_dep] = lambda: runtime
    app.dependency_overrides[get_approval_broker_dep] = lambda: broker
    return runtime, broker


def wait_until(predicate, *, timeout_s: float = 10.0, interval_s: float = 0.01) -> bool:
    """Poll ``predicate()`` from the test's (main) thread. Starlette's
    ``TestClient`` runs the whole ASGI app on a background-thread event
    loop that stays alive for the client's lifetime — a
    ``asyncio.create_task(...)`` spawned inside a request handler (or a
    ``StoreApprovalBroker.request()`` future awaited inside one) keeps
    running/pending on that loop AFTER the response returns, exactly like
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


def wait_turn_released(conv_store, org_id, conversation_id) -> bool:
    """Block until the given conversation's turn lock is free — i.e. the
    background task's `finally: release_turn(...)` has run (contract
    §E.9 points 5/6). MUST be called by every test that lets a
    `POST .../messages` call reach the point of spawning a background
    task, even one whose assertions don't care about the turn's outcome
    — an un-joined task left running past the end of a test competes for
    the SAME shared TestClient portal thread the next test's requests
    also drive. Uses a synthetic probe instance id — never the real
    process ``INSTANCE_ID`` — so it can never accidentally satisfy (or
    corrupt) the real lock."""
    probe_instance = "test-poll-probe"
    acquired = wait_until(
        lambda: conv_store.try_acquire_turn(org_id, conversation_id, probe_instance, 1)
    )
    if acquired:
        conv_store.release_turn(org_id, conversation_id, probe_instance)
    return acquired


def wait_for_pending_approval(approval_store, org_id, *, timeout_s: float = 10.0):
    """Poll until at least one `pendente` approval exists for the org,
    then return it — used after posting a message whose script drives an
    escrita tool call, so the test can decide the LIVE approval
    `broker.request()` is blocked on (contract §E.9), the same way a real
    human would via the HTTP decision endpoint. Raises ``AssertionError``
    on timeout (never returns ``None`` — a caller that forgets to check
    would otherwise silently proceed with no approval)."""
    box: list = []

    def _check() -> bool:
        pending = approval_store.list_pending(org_id)
        if pending:
            box.append(pending[0])
            return True
        return False

    found = wait_until(_check, timeout_s=timeout_s)
    assert found, "no pending approval appeared within the timeout"
    return box[0]


__all__ = [
    "DEFAULT_ORG_ID",
    "DEFAULT_USER_ID",
    "agents_client",
    "bind_user",
    "install_runtime",
    "seed_active_agent_and_persona",
    "seed_org_role",
    "wait_for_pending_approval",
    "wait_turn_released",
    "wait_until",
]
