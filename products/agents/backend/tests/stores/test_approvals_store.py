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


def test_mark_consumed_is_idempotent(store):
    org_id = uuid4()
    approval = _create(store, org_id=org_id)
    store.decide(org_id, approval.id, True, uuid4())

    store.mark_consumed(approval.id)
    first_consumed_at = store._rows[approval.id]["consumed_at"]

    store.mark_consumed(approval.id)  # second call must not move the timestamp
    assert store._rows[approval.id]["consumed_at"] == first_consumed_at


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
