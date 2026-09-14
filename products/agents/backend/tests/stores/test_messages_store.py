"""FakeMessageStore behaviour — ordering + `before` pagination (contract §E.2)."""
from __future__ import annotations

from uuid import uuid4

import pytest

from app.stores.messages import FakeMessageStore


@pytest.fixture
def store() -> FakeMessageStore:
    return FakeMessageStore()


def test_add_and_list_round_trips_in_insertion_order(store):
    org_id, conv_id = uuid4(), uuid4()

    m1 = store.add(org_id, conv_id, "user", "oi")
    m2 = store.add(org_id, conv_id, "assistant", "olá")

    messages = store.list(org_id, conv_id)
    assert [m.id for m in messages] == [m1.id, m2.id], "newest must be LAST"


def test_list_respects_limite(store):
    org_id, conv_id = uuid4(), uuid4()
    ids = [store.add(org_id, conv_id, "user", f"msg-{i}").id for i in range(5)]

    page = store.list(org_id, conv_id, limite=2)

    assert [m.id for m in page] == ids[-2:]


def test_list_before_cursor_pages_backward_and_stays_oldest_first(store):
    org_id, conv_id = uuid4(), uuid4()
    ids = [store.add(org_id, conv_id, "user", f"msg-{i}").id for i in range(5)]

    # Page immediately preceding msg-3 (index 3), limite=2 -> msg-1, msg-2.
    page = store.list(org_id, conv_id, before=ids[3], limite=2)

    assert [m.id for m in page] == ids[1:3]


def test_list_is_scoped_to_the_conversation(store):
    org_id = uuid4()
    conv_a, conv_b = uuid4(), uuid4()

    store.add(org_id, conv_a, "user", "in A")
    store.add(org_id, conv_b, "user", "in B")

    assert len(store.list(org_id, conv_a)) == 1
    assert len(store.list(org_id, conv_b)) == 1


def test_add_rejects_an_unknown_role(store):
    with pytest.raises(ValueError):
        store.add(uuid4(), uuid4(), "narrator", "texto")


def test_blocks_and_token_usage_default_safely(store):
    org_id, conv_id = uuid4(), uuid4()

    msg = store.add(org_id, conv_id, "assistant", "ok")

    assert msg.blocks == []
    assert msg.token_usage is None
