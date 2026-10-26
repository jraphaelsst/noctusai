"""Org-config isolation (050): org/app configuration reaches an org ONLY through an explicit grant. Store (Fake mirrors
the DB guard + CHECK), `ensure_instancias`, and the grant routes."""
from __future__ import annotations

from uuid import uuid4

import pytest

from app.stores._db_errors import StudioConflict
from app.stores.studio_definitions import FakeStudioDefinitionStore
from app.studio.plataforma import ensure_definicao, ensure_instancia, ensure_instancias

PLAT = uuid4()
ORG_A, ORG_B = uuid4(), uuid4()


class _PublishedStore(FakeStudioDefinitionStore):
    """A store where every definition counts as published -- the grant logic is under test, not the publish flow."""

    def get_active_version(self, org_id, agent_id):
        return object()


def _world(*, key="julia", owner="social-wiring", instanciavel=False):
    st = _PublishedStore()
    st.mark_platform_org(PLAT)
    d = ensure_definicao(PLAT, key, studio_store=st, nome=key, owner_product=owner, instanciavel=instanciavel)
    return st, d


def test_store_defaults_are_closed():
    st = FakeStudioDefinitionStore()
    st.mark_platform_org(PLAT)
    d = st.create_studio_agent(PLAT, "x", "X", None, definition_scope="plataforma")
    assert d.instanciavel is False


def test_product_owned_definition_cannot_be_opened_to_every_org():
    st = FakeStudioDefinitionStore()
    st.mark_platform_org(PLAT)
    with pytest.raises(ValueError, match="product-owned"):
        st.create_studio_agent(PLAT, "x", "X", None, definition_scope="plataforma", owner_product="monica", instanciavel=True)
    st, d = _world()
    with pytest.raises(ValueError, match="product-owned"):
        st.update_definicao(PLAT, d.key, {"instanciavel": True})


def test_open_definition_without_owner_is_still_allowed():
    st, d = _world(key="geral", owner=None)
    assert st.update_definicao(PLAT, d.key, {"instanciavel": True}).instanciavel is True


def test_instance_of_closed_definition_requires_a_grant():
    st, d = _world()
    with pytest.raises(StudioConflict) as exc:
        st.create_studio_agent(ORG_A, "julia", "J", None, definition_scope="instancia", definition_agent_id=d.id)
    assert exc.value.code == "definition_not_granted"
    assert st.grant_definition_org(d.id, ORG_A) is True
    assert st.grant_definition_org(d.id, ORG_A) is False  # idempotent
    st.create_studio_agent(ORG_A, "julia", "J", None, definition_scope="instancia", definition_agent_id=d.id)


def test_ensure_instancias_reaches_only_granted_orgs():
    st, d = _world()
    st.grant_definition_org(d.id, ORG_A)
    assert [a.key for a in ensure_instancias(ORG_A, studio_store=st)] == ["julia"]
    assert ensure_instancias(ORG_B, studio_store=st) == []  # the leak: this used to give ORG_B a julia
    assert ensure_instancia(ORG_B, "julia", studio_store=st) is None


def test_open_definition_still_reaches_every_org():
    st, d = _world(key="geral", owner=None, instanciavel=True)
    assert [a.key for a in ensure_instancias(ORG_B, studio_store=st)] == ["geral"]
