"""FakeApprovalStore behaviour — decision lifecycle + instance-scoped expiry
(contract §E.1/§E.2, security finding 5)."""
from __future__ import annotations

from uuid import uuid4

import pytest

from app.stores.approvals import FakeApprovalStore
from app.stores.errors import AlreadyDecided, NotFound


@pytest.fixture
def store() -> FakeApprovalStore:
    return FakeApprovalStore()


def _create(store, *, org_id=None, conversation_id=None, instance_id="inst-1", requested_by=None):
    return store.create_pending(
        org_id or uuid4(),
        conversation_id or uuid4(),
        "mcp__academia__kb_escrever",
        {"slug": "dominio-regulatorio-pnrs"},
        "Atualizar entrada da KB",
        instance_id,
        requested_by or uuid4(),
    )


def test_create_pending_defaults_to_pendente_and_escrita(store):
    approval = _create(store)
    assert approval.decision == "pendente"
    assert approval.classe == "escrita"
    assert approval.consumed_at is None


def test_create_pending_rejects_an_unknown_classe(store):
    with pytest.raises(ValueError):
        store.create_pending(
            uuid4(), uuid4(), "tool", {}, "resumo", "inst-1", uuid4(),
            classe="leitura",
        )


def test_decide_approves_and_records_who(store):
    org_id = uuid4()
    approval = _create(store, org_id=org_id)
    decider = uuid4()

    decided = store.decide(org_id, approval.id, True, decider)

    assert decided.decision == "aprovada"
    assert decided.decided_by == decider
    assert decided.decided_at is not None


def test_decide_denies(store):
    org_id = uuid4()
    approval = _create(store, org_id=org_id)

    decided = store.decide(org_id, approval.id, False, uuid4())

    assert decided.decision == "negada"


def test_deciding_twice_raises_already_decided(store):
    org_id = uuid4()
    approval = _create(store, org_id=org_id)

    store.decide(org_id, approval.id, True, uuid4())

    with pytest.raises(AlreadyDecided):
        store.decide(org_id, approval.id, True, uuid4())


def test_decide_raises_not_found_for_unknown_or_other_org(store):
    org_id = uuid4()
    approval = _create(store, org_id=org_id)

    with pytest.raises(NotFound):
        store.decide(uuid4(), approval.id, True, uuid4())

    with pytest.raises(NotFound):
        store.decide(org_id, uuid4(), True, uuid4())


def test_expire_for_instance_only_touches_that_instances_pending_rows(store):
    a = _create(store, instance_id="inst-A")
    b = _create(store, instance_id="inst-B")
    c = _create(store, instance_id="inst-A")

    count = store.expire_for_instance("inst-A")

    assert count == 2
    assert store._rows[a.id]["decision"] == "expirada"
    assert store._rows[c.id]["decision"] == "expirada"
    assert store._rows[b.id]["decision"] == "pendente", (
        "another instance's pending row must never be touched"
    )


def test_expire_for_instance_never_re_expires_an_already_decided_row(store):
    org_id = uuid4()
    approval = _create(store, org_id=org_id, instance_id="inst-A")
    store.decide(org_id, approval.id, True, uuid4())

    store.expire_for_instance("inst-A")

    assert store._rows[approval.id]["decision"] == "aprovada", (
        "a landed decision must never be overwritten by the startup sweep"
    )


def test_expire_one_only_flips_a_pendente_row(store):
    org_id = uuid4()
    pending = _create(store, org_id=org_id)
    decided = _create(store, org_id=org_id)
    store.decide(org_id, decided.id, True, uuid4())

    store.expire_one(pending.id)
    store.expire_one(decided.id)  # must be a silent no-op

    assert store._rows[pending.id]["decision"] == "expirada"
    assert store._rows[decided.id]["decision"] == "aprovada"


def test_consume_returns_the_record_only_on_the_first_call(store):
    """§E.10: ``consume`` replaces ``mark_consumed`` — atomic, single-use,
    returns the record once and ``None`` on every replay."""
    org_id = uuid4()
    approval = _create(store, org_id=org_id)
    store.decide(org_id, approval.id, True, uuid4())

    first = store.consume(org_id, approval.id)
    assert first is not None
    assert first.consumed_at is not None
    first_consumed_at = first.consumed_at

    second = store.consume(org_id, approval.id)  # replay — must not move the timestamp
    assert second is None
    assert store._rows[approval.id]["consumed_at"] == first_consumed_at


def test_consume_returns_none_for_an_unapproved_row(store):
    org_id = uuid4()
    approval = _create(store, org_id=org_id)  # still pendente — never decided

    assert store.consume(org_id, approval.id) is None


def test_consume_returns_none_for_wrong_org_or_unknown_id(store):
    org_id = uuid4()
    approval = _create(store, org_id=org_id)
    store.decide(org_id, approval.id, True, uuid4())

    assert store.consume(uuid4(), approval.id) is None
    assert store.consume(org_id, uuid4()) is None


def test_two_concurrent_consume_calls_yield_exactly_one_record(store):
    """§E.10 required test: "two concurrent consume calls yielding exactly
    one record"."""
    org_id = uuid4()
    approval = _create(store, org_id=org_id)
    store.decide(org_id, approval.id, True, uuid4())

    results = [store.consume(org_id, approval.id) for _ in range(2)]
    non_none = [r for r in results if r is not None]
    assert len(non_none) == 1


def test_list_pending_filters_by_owner(store):
    org_id = uuid4()
    owner_a, owner_b = uuid4(), uuid4()
    a = _create(store, org_id=org_id, requested_by=owner_a)
    _create(store, org_id=org_id, requested_by=owner_b)

    only_a = store.list_pending(org_id, owner_user_id=owner_a)
    everyone = store.list_pending(org_id)

    assert [r.id for r in only_a] == [a.id]
    assert len(everyone) == 2


def test_list_pending_excludes_decided_rows(store):
    org_id = uuid4()
    approval = _create(store, org_id=org_id)
    store.decide(org_id, approval.id, True, uuid4())

    assert store.list_pending(org_id) == []
