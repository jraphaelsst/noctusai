"""FakeAgentStore behaviour — contract §E.1 `agents` rules."""
from __future__ import annotations

from uuid import uuid4

import pytest

from app.stores.agents import FakeAgentStore
from app.stores.errors import NotFound


@pytest.fixture
def store() -> FakeAgentStore:
    return FakeAgentStore()


def test_get_by_key_raises_not_found_for_unknown_key(store):
    org_id = uuid4()
    store.seed_legacy_chat_agent(org_id)
    with pytest.raises(NotFound):
        store.get_by_key(org_id, "does-not-exist")


def test_get_by_key_raises_not_found_for_another_org(store):
    org_a, org_b = uuid4(), uuid4()
    store.seed_legacy_chat_agent(org_a)
    with pytest.raises(NotFound):
        store.get_by_key(org_b, "bia")


def test_set_active_toggles_and_raises_on_unknown(store):
    org_id = uuid4()
    store.seed_legacy_chat_agent(org_id)

    updated = store.set_active(org_id, "bia", True)
    assert updated.ativo is True
    assert store.get_by_key(org_id, "bia").ativo is True

    with pytest.raises(NotFound):
        store.set_active(org_id, "nope", True)


def test_set_external_ref_sets_and_clears(store):
    org_id = uuid4()
    store.seed_legacy_chat_agent(org_id)

    ref = {"connection_id": str(uuid4())}
    updated = store.set_external_ref(org_id, "bia", ref)
    assert updated.external_ref == ref

    cleared = store.set_external_ref(org_id, "bia", None)
    assert cleared.external_ref is None


def test_seed_legacy_chat_agent_is_a_fake_fixture_of_the_pre_cutover_row(store):
    org_id = uuid4()
    row = store.seed_legacy_chat_agent(org_id)
    assert (row.key, row.runtime, row.definition_mode, row.chat_legado) == ("bia", "claude_sdk", "legacy", True)
