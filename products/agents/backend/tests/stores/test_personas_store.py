"""FakePersonaStore behaviour — the versioning flip (contract §E.1)."""
from __future__ import annotations

from uuid import uuid4

import pytest

from app.stores.errors import NotFound
from app.stores.personas import FakePersonaStore, PersonaInput


@pytest.fixture
def store() -> FakePersonaStore:
    return FakePersonaStore()


def _input(**overrides) -> PersonaInput:
    base = dict(
        nome="Julia",
        papel="assistente de pesquisa",
        model="claude-sonnet-5",
        effort="medium",
    )
    base.update(overrides)
    return PersonaInput(**base)


def test_get_active_raises_not_found_before_any_version(store):
    with pytest.raises(NotFound):
        store.get_active(uuid4(), uuid4())


def test_create_version_starts_at_one_and_is_active(store):
    org_id, agent_id, created_by = uuid4(), uuid4(), uuid4()

    persona = store.create_version(org_id, agent_id, _input(), created_by)

    assert persona.versao == 1
    assert persona.ativa is True
    assert store.get_active(org_id, agent_id).id == persona.id


def test_create_version_increments_and_flips_previous_inactive(store):
    org_id, agent_id, created_by = uuid4(), uuid4(), uuid4()

    v1 = store.create_version(org_id, agent_id, _input(nome="v1"), created_by)
    v2 = store.create_version(org_id, agent_id, _input(nome="v2"), created_by)

    assert v1.versao == 1
    assert v2.versao == 2
    assert v2.ativa is True

    active = store.get_active(org_id, agent_id)
    assert active.id == v2.id
    assert active.versao == 2

    # The OLD row itself must report inactive too — the flip is a real
    # state change, not just "get_active happens to return the newest".
    v1_after = next(
        r for r in store._rows[(org_id, agent_id)] if r["id"] == v1.id
    )
    assert v1_after["ativa"] is False


def test_versioning_is_scoped_per_agent(store):
    org_id, created_by = uuid4(), uuid4()
    agent_a, agent_b = uuid4(), uuid4()

    store.create_version(org_id, agent_a, _input(), created_by)
    persona_b = store.create_version(org_id, agent_b, _input(), created_by)

    assert persona_b.versao == 1, "a sibling agent's versions must not interleave"


def test_create_version_rejects_bad_model_and_effort(store):
    org_id, agent_id, created_by = uuid4(), uuid4(), uuid4()

    with pytest.raises(ValueError):
        store.create_version(org_id, agent_id, _input(model="gpt-5"), created_by)

    with pytest.raises(ValueError):
        store.create_version(org_id, agent_id, _input(effort="ultra"), created_by)
