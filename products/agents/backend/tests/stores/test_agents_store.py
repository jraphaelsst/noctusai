"""FakeAgentStore behaviour — contract §E.1 `agents` rules."""
from __future__ import annotations

from uuid import uuid4

import pytest

from app.stores.agents import FakeAgentStore
from app.stores.errors import NotFound


@pytest.fixture
def store() -> FakeAgentStore:
    return FakeAgentStore()


def test_ensure_default_agents_seeds_one_chat_only(store):
    """Renata cutover: the code-defined chat agent is no longer seeded -- its key is free for a new agent."""
    org_id = uuid4()
    store.ensure_default_agents(org_id)

    rows = {r.key: r for r in store.list(org_id)}
    assert set(rows) == {"one-chat"}

    one_chat = rows["one-chat"]
    assert one_chat.runtime == "external"
    assert one_chat.owner_product == "social-wiring"
    assert one_chat.external_ref is None
    assert one_chat.ativo is False


def test_ensure_default_agents_is_idempotent(store):
    org_id = uuid4()
    store.ensure_default_agents(org_id)
    # A caller may have already toggled `ativo` — a second ensure call must
    # never clobber that back to the default.
    store.set_active(org_id, "one-chat", True)

    store.ensure_default_agents(org_id)

    rows = store.list(org_id)
    assert len(rows) == 1, "ensure_default_agents must not duplicate rows"
    assert store.get_by_key(org_id, "one-chat").ativo is True, "a second ensure call clobbered an existing toggle"


def test_ensure_default_agents_is_per_org(store):
    org_a, org_b = uuid4(), uuid4()
    store.ensure_default_agents(org_a)
    store.ensure_default_agents(org_b)

    assert len(store.list(org_a)) == 1
    assert len(store.list(org_b)) == 1
    # Different rows entirely — not shared/aliased across orgs.
    assert store.get_by_key(org_a, "one-chat").id != store.get_by_key(org_b, "one-chat").id


def test_get_by_key_raises_not_found_for_unknown_key(store):
    org_id = uuid4()
    store.ensure_default_agents(org_id)
    with pytest.raises(NotFound):
        store.get_by_key(org_id, "does-not-exist")


def test_get_by_key_raises_not_found_for_another_org(store):
    org_a, org_b = uuid4(), uuid4()
    store.ensure_default_agents(org_a)
    with pytest.raises(NotFound):
        store.get_by_key(org_b, "one-chat")


def test_set_active_toggles_and_raises_on_unknown(store):
    org_id = uuid4()
    store.ensure_default_agents(org_id)

    updated = store.set_active(org_id, "one-chat", True)
    assert updated.ativo is True
    assert store.get_by_key(org_id, "one-chat").ativo is True

    with pytest.raises(NotFound):
        store.set_active(org_id, "nope", True)


def test_set_external_ref_sets_and_clears(store):
    org_id = uuid4()
    store.ensure_default_agents(org_id)

    ref = {"connection_id": str(uuid4())}
    updated = store.set_external_ref(org_id, "one-chat", ref)
    assert updated.external_ref == ref

    cleared = store.set_external_ref(org_id, "one-chat", None)
    assert cleared.external_ref is None


def test_seed_legacy_chat_agent_is_a_fake_fixture_of_the_pre_cutover_row(store):
    org_id = uuid4()
    row = store.seed_legacy_chat_agent(org_id)
    assert (row.key, row.runtime, row.definition_mode, row.chat_legado) == ("bia", "claude_sdk", "legacy", True)
