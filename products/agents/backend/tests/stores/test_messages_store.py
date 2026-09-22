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


def test_custo_usd_and_tokens_default_to_none(store):
    org_id, conv_id = uuid4(), uuid4()
    msg = store.add(org_id, conv_id, "assistant", "ok")
    assert (msg.custo_usd, msg.tokens_entrada, msg.tokens_saida) == (None, None, None)


def test_set_turn_cost_stamps_the_message_contract_l(store):
    """Contract §L: the turn loop stamps cost/tokens on the assistant
    message it persisted, off the SDK ResultMessage."""
    org_id, conv_id = uuid4(), uuid4()
    msg = store.add(org_id, conv_id, "assistant", "ok")

    updated = store.set_turn_cost(
        org_id, conv_id, msg.id, custo_usd=0.0456, tokens_entrada=200, tokens_saida=80,
    )

    assert (updated.custo_usd, updated.tokens_entrada, updated.tokens_saida) == (0.0456, 200, 80)
    # Round-trips through list() too — not just the returned record.
    reread = store.list(org_id, conv_id)[0]
    assert reread.custo_usd == 0.0456


def test_set_turn_cost_unknown_message_raises_not_found(store):
    from app.stores.errors import NotFound

    org_id, conv_id = uuid4(), uuid4()
    with pytest.raises(NotFound):
        store.set_turn_cost(org_id, conv_id, uuid4(), custo_usd=1.0, tokens_entrada=1, tokens_saida=1)
