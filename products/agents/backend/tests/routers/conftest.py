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
    get_build_julia_spec_dep,
    get_conversation_store_dep,
    get_message_store_dep,
    get_persona_store_dep,
    get_social_wiring_client_dep,
)
from app.stores.agents import FakeAgentStore
from app.stores.approvals import FakeApprovalStore
from app.stores.conversations import FakeConversationStore
from app.stores.messages import FakeMessageStore
from app.stores.personas import FakePersonaStore
from noctusai_lib.testing import MockUser, MockUserResponse
from noctusai_lib.testing.clients import TEST_USER_ID
from tests._runtime_standin import (
    FakeAgentRuntime,
    InProcessApprovalBroker,
    fake_build_julia_spec,
)

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


@pytest.fixture
def agents_client(client):
    """The shared ``client`` fixture, with every store/client dependency
    overridden onto a shared, stateful Fake set (``client.stores``)."""
    from app.main import app

    stores = _Stores()
    app.dependency_overrides[get_agent_store_dep] = lambda: stores.agents
    app.dependency_overrides[get_conversation_store_dep] = lambda: stores.conversations
    app.dependency_overrides[get_message_store_dep] = lambda: stores.messages
    app.dependency_overrides[get_persona_store_dep] = lambda: stores.personas
    app.dependency_overrides[get_approval_store_dep] = lambda: stores.approvals
    app.dependency_overrides[get_social_wiring_client_dep] = lambda: stores.social_wiring
    # Default runtime/broker/spec-builder — every `POST .../messages` route
    # declares these as `Depends(...)` UNCONDITIONALLY (FastAPI resolves
    # every dependency before the route body runs, including for a request
    # that 404s/409s/422s before ever touching the turn loop), so a test
    # that doesn't care about turn behaviour still needs SOMETHING here.
    # Tests exercising the turn loop itself override these again with
    # their own script via `_install_runtime` in the test module.
    default_runtime = FakeAgentRuntime(
        [{"event": "session.status", "payload": {"status": "ociosa"}}]
    )
    default_broker = InProcessApprovalBroker(
        stores.approvals, stores.conversations, instance_id="default-test-instance"
    )
    app.dependency_overrides[get_agent_runtime_dep] = lambda: default_runtime
    app.dependency_overrides[get_approval_broker_dep] = lambda: default_broker
    app.dependency_overrides[get_build_julia_spec_dep] = lambda: fake_build_julia_spec
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
            # Defensively cleared too — individual test files that install
            # a runtime/broker/spec-builder stand-in (tests/_runtime_standin.py)
            # via these same dependency-override keys must never leak into
            # a later test that didn't ask for one.
            get_agent_runtime_dep,
            get_approval_broker_dep,
            get_build_julia_spec_dep,
        ):
            app.dependency_overrides.pop(dep, None)


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


__all__ = [
    "DEFAULT_ORG_ID",
    "DEFAULT_USER_ID",
    "agents_client",
    "bind_user",
    "seed_org_role",
]
