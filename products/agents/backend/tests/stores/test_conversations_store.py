"""FakeConversationStore behaviour — ownership + the turn lock (contract §E.2)."""
from __future__ import annotations

from uuid import uuid4

import pytest

from app.stores.conversations import FakeConversationStore
from app.stores.errors import NotFound


@pytest.fixture
def store() -> FakeConversationStore:
    return FakeConversationStore()


def test_create_and_get_owned_round_trips(store):
    org_id, agent_id, user_id = uuid4(), uuid4(), uuid4()

    created = store.create(org_id, agent_id, user_id, titulo="Sessão 1")
    fetched = store.get_owned(org_id, created.id, user_id)

    assert fetched.id == created.id
    assert fetched.titulo == "Sessão 1"
    assert fetched.status == "ativa"


def test_get_owned_raises_not_found_for_a_non_owner(store):
    org_id, agent_id = uuid4(), uuid4()
    owner, someone_else = uuid4(), uuid4()

    conv = store.create(org_id, agent_id, owner)

    with pytest.raises(NotFound):
        store.get_owned(org_id, conv.id, someone_else)


def test_get_owned_raises_not_found_for_another_org(store):
    org_a, org_b = uuid4(), uuid4()
    agent_id, user_id = uuid4(), uuid4()

    conv = store.create(org_a, agent_id, user_id)

    with pytest.raises(NotFound):
        store.get_owned(org_b, conv.id, user_id)


def test_list_owned_only_returns_the_users_own_conversations(store):
    org_id, agent_id = uuid4(), uuid4()
    owner, someone_else = uuid4(), uuid4()

    mine = store.create(org_id, agent_id, owner)
    store.create(org_id, agent_id, someone_else)

    owned = store.list_owned(org_id, owner)
    assert [c.id for c in owned] == [mine.id]


def test_try_acquire_turn_raises_not_found_for_unknown_conversation(store):
    with pytest.raises(NotFound):
        store.try_acquire_turn(uuid4(), uuid4(), "instance-1", ttl_seconds=30)


def test_second_acquire_while_held_fails(store):
    org_id, agent_id, user_id = uuid4(), uuid4(), uuid4()
    conv = store.create(org_id, agent_id, user_id)

    first = store.try_acquire_turn(org_id, conv.id, "instance-1", ttl_seconds=30)
    second = store.try_acquire_turn(org_id, conv.id, "instance-2", ttl_seconds=30)

    assert first is True
    assert second is False, "one in-flight turn per conversation must be enforced"


def test_release_by_a_non_holding_instance_is_a_noop(store):
    org_id, agent_id, user_id = uuid4(), uuid4(), uuid4()
    conv = store.create(org_id, agent_id, user_id)

    assert store.try_acquire_turn(org_id, conv.id, "instance-1", ttl_seconds=30)

    # A stale/foreign instance must never be able to clear a lock it
    # doesn't hold.
    store.release_turn(org_id, conv.id, "instance-2")

    still_held = store.try_acquire_turn(org_id, conv.id, "instance-3", ttl_seconds=30)
    assert still_held is False


def test_release_by_the_holder_then_reacquire_succeeds(store):
    org_id, agent_id, user_id = uuid4(), uuid4(), uuid4()
    conv = store.create(org_id, agent_id, user_id)

    assert store.try_acquire_turn(org_id, conv.id, "instance-1", ttl_seconds=30)
    store.release_turn(org_id, conv.id, "instance-1")

    reacquired = store.try_acquire_turn(org_id, conv.id, "instance-2", ttl_seconds=30)
    assert reacquired is True


def test_acquire_after_ttl_expiry_succeeds_for_a_new_instance(store):
    org_id, agent_id, user_id = uuid4(), uuid4(), uuid4()
    conv = store.create(org_id, agent_id, user_id)

    # ttl_seconds=0 means the lock is already "in the past" by the time a
    # second call checks it — an unexpired lock is the only thing that
    # should block acquisition.
    assert store.try_acquire_turn(org_id, conv.id, "instance-1", ttl_seconds=0)

    reacquired = store.try_acquire_turn(org_id, conv.id, "instance-2", ttl_seconds=30)
    assert reacquired is True
