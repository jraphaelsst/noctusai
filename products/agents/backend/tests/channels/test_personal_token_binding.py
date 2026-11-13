"""A channel token is PERSONAL: one per (agent, product, org) grant, and it never reaches another agent or org.

Owner 2026-11-05: "the token must not grant access to other agents, only to the agent set to that token". Three layers,
each tested here against the LIVE route table (never a hand list):

* the central gate (``_require_channel`` -> ``assert_channel_grant_live``): the token's GRANT must be ``ativo`` and not
  expired, and must name this very (org, agent) -- a revoked / expired / missing grant refuses EVERY channel route at once;
* the per-route binding: a route that addresses an agent (``{agent_key}``, a thread, a hand-off) requires
  ``principal_agent_id == that agent's instance`` (403 ``agent_not_allowed``);
* the org is the token's, never the request's.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

from app.dependencies import SCOPE_CHANNEL_SPECS, SCOPE_CHANNEL_STATUS, SCOPE_CHANNEL_TURN
from tests.channels.conftest import OTHER_ORG
from tests.channels.test_scope_isolation import CHANNEL_PREFIX, _code, _fill, _routes

ROUTES = _routes((CHANNEL_PREFIX,))
TOKEN_ID = UUID(int=9)
ALL = (SCOPE_CHANNEL_TURN, SCOPE_CHANNEL_STATUS, SCOPE_CHANNEL_SPECS)  # a grant mints all three; the gate under test is the grant's


def _call(chan, method, path, **token):
    with chan.as_token(*ALL, **token):
        return chan.request(method, _fill(path), json={})


@pytest.mark.parametrize("method,path", ROUTES)
def test_a_revoked_grant_refuses_every_channel_route(chan, method, path):
    chan.seed_agent()
    resp = _call(chan, method, path, grant="revogado")
    assert resp.status_code == 403 and _code(resp) == "grant_inativo", f"{method} {path} -> {resp.status_code}"


@pytest.mark.parametrize("method,path", ROUTES)
def test_an_expired_grant_refuses_every_channel_route(chan, method, path):
    chan.seed_agent()
    resp = _call(chan, method, path, grant_expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
    assert resp.status_code == 403 and _code(resp) == "grant_inativo", f"{method} {path} -> {resp.status_code}"


@pytest.mark.parametrize("method,path", ROUTES)
def test_a_token_with_no_grant_row_refuses_every_channel_route(chan, method, path):
    chan.seed_agent()
    for status in (None, "pendente", "falhou"):
        resp = _call(chan, method, path, grant=status)
        assert resp.status_code == 403 and _code(resp) == "grant_inativo", f"{method} {path} {status}"


@pytest.mark.parametrize("method,path", ROUTES)
def test_a_grant_naming_another_agent_or_org_refuses_every_channel_route(chan, method, path):
    chan.seed_agent()
    with chan.as_token(*ALL):  # the token's principal is Julia's instance ...
        chan.seed_grant(token_id=TOKEN_ID, org_id=chan.org_id, agent_id=uuid4(), status="ativo")  # ... its grant names another agent
        wrong_agent = chan.request(method, _fill(path), json={})
        chan.seed_grant(token_id=TOKEN_ID, org_id=OTHER_ORG, agent_id=chan.agent.id, status="ativo")
        wrong_org = chan.request(method, _fill(path), json={})
    for resp in (wrong_agent, wrong_org):
        assert resp.status_code == 403 and _code(resp) == "agent_not_allowed", f"{method} {path}"


@pytest.mark.parametrize("method,path", ROUTES)
def test_a_token_without_a_principal_refuses_every_channel_route(chan, method, path):
    chan.seed_agent()
    resp = _call(chan, method, path, principal=None)
    assert resp.status_code == 403 and _code(resp) == "agent_not_allowed", f"{method} {path}"


def test_a_live_grant_opens_the_agents_own_routes(chan):
    chan.seed_agent()
    with chan.as_token(*ALL):
        assert chan.request("GET", "/api/channels/agents/julia/status").status_code == 200


def test_julias_token_addressing_a_bia_instance_in_the_same_org_is_403_agent_not_allowed(chan):
    chan.seed_agent()
    chan.rt.studio.create_studio_agent(chan.org_id, "bia", "Bia", None, runtime="llm", owner_product="social-wiring")
    with chan.as_token(*ALL):  # Julia's personal token (principal = Julia's instance)
        status = chan.request("GET", "/api/channels/agents/bia/status")
        specs = chan.request("GET", "/api/channels/agents/bia/specs")
        controle = chan.request("GET", "/api/channels/agents/bia/controle")
        decisao = chan.request("POST", "/api/channels/agents/bia/decisoes/x", json={"opcoes": ["a"], "contexto": "x"})
    for resp in (status, specs, controle):
        assert resp.status_code == 403 and _code(resp) == "agent_not_allowed"
    assert decisao.status_code in (403, 422)  # body validation may answer first; never a 200
    assert chan.rt.studio.list_org_specs(chan.org_id, "bia") == []


def test_julias_token_of_one_org_never_addresses_another_orgs_instance(chan):
    chan.seed_agent()
    other = chan.rt.studio.create_studio_agent(OTHER_ORG, "julia", "Julia", None, runtime="llm", owner_product="social-wiring")
    # the token's org is A; its principal is B's Julia instance: refused (the grant must name org A's agent)
    with chan.as_token(*ALL, principal=other.id):
        chan.seed_grant(token_id=TOKEN_ID, org_id=chan.org_id, agent_id=chan.agent.id, status="ativo")
        resp = chan.request("GET", "/api/channels/agents/julia/status")
    assert resp.status_code == 403 and _code(resp) == "agent_not_allowed"
    # and org B's instance is not even addressable from org A's token (the org is the token's)
    with chan.as_token(*ALL, org_id=OTHER_ORG, principal=chan.agent.id):
        resp = chan.request("GET", "/api/channels/agents/julia/status")
    assert resp.status_code == 403 and _code(resp) == "agent_not_allowed"


def test_the_stored_tools_secret_is_cleared_only_by_the_agent_it_belongs_to(chan):
    from app.main import app
    from app.routers.channel_tools_token_router import get_julia_tools_token_store_dep
    from noctusai_lib.security import FakeCredentialStore

    store = FakeCredentialStore()
    app.dependency_overrides[get_julia_tools_token_store_dep] = lambda: store
    try:
        _tools_secret_body(chan)
    finally:
        app.dependency_overrides.pop(get_julia_tools_token_store_dep, None)


def _tools_secret_body(chan):
    chan.seed_agent()
    chan.rt.studio.create_studio_agent(chan.org_id, "bia", "Bia", None, runtime="llm", owner_product="social-wiring")
    bia = chan.rt.studio.get_agent(chan.org_id, "bia")
    with chan.as_token(*ALL, principal=bia.id):
        resp = chan.request("DELETE", "/api/channels/ferramentas-token")
    assert resp.status_code == 403 and _code(resp) == "agent_not_allowed"
    with chan.as_token(*ALL):
        assert chan.request("DELETE", "/api/channels/ferramentas-token").status_code == 204


def test_the_grant_registry_binds_one_agent_per_tools_token():
    """The SW tools token (scope + stored secret) is Julia's alone: a second agent needs its own registry entry."""
    from app.grants.registry import GRANT_PRODUCTS, GrantProduct

    scopes = [p.tools_scope for p in GRANT_PRODUCTS.values() if p.has_tools]
    secrets = [p.tools_secret_name for p in GRANT_PRODUCTS.values() if p.has_tools]
    assert len(set(scopes)) == len(scopes) and len(set(secrets)) == len(secrets)
    assert all(len(p.agent_keys) == 1 for p in GRANT_PRODUCTS.values())
    with pytest.raises(ValueError):
        GrantProduct(
            slug="x", label="X", schema="x", channel_issuer="x", tools_scope="x:t", tools_label="t",
            tools_secret_name="s", agent_keys=("julia", "bia"),
        )


def test_tools_fields_of_a_grant_product_are_all_or_none():
    from app.grants.registry import GrantProduct

    ok = GrantProduct(slug="x", label="X", schema="x", channel_issuer="x", agent_keys=("a",))
    assert not ok.has_tools
    with pytest.raises(ValueError):
        GrantProduct(slug="x", label="X", schema="x", channel_issuer="x", agent_keys=("a",), tools_scope="x:t")
