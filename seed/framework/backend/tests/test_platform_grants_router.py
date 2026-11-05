"""Receiver router for platform grants: strict 401 without a token, 403 on wrong
scope/issuer/caller, org from the token (never the body), sink callbacks, and the
auth_router's resolver fallback refusing the Fake in a deploy context."""
from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from noctusai_lib.api.auth.session import (
    FakeApiTokenResolver,
    FakeSessionStore,
    GRANT_RECEIVE_SCOPE,
    make_get_auth_context,
)
from noctusai_seed.platform_grants_router import (
    GrantReceived,
    GrantRevoked,
    create_platform_grants_router,
)

ORG = uuid4()
OTHER_ORG = uuid4()
BODY = {"credential": "noc_" + "d" * 32, "agent_id": "agent-1", "metadata": {"k": "v"}}


class _Harness:
    def __init__(self):
        self.resolver = FakeApiTokenResolver()
        self.received: list[GrantReceived] = []
        self.revoked: list[GrantRevoked] = []
        dep = make_get_auth_context(
            session_store=FakeSessionStore(), api_token_resolver=self.resolver,
            session_cookie_name="nai_session",
        )
        app = FastAPI()
        app.include_router(create_platform_grants_router(
            get_auth_context=dep, on_grant=self.received.append, on_revoke=self.revoked.append,
        ))
        self.client = TestClient(app)

    def token(self, secret="noc_deliv", *, org=ORG, scopes=(GRANT_RECEIVE_SCOPE,), issuer="agents"):
        self.resolver.register(secret, org_id=org, scopes=list(scopes), issuer=issuer)
        return {"Authorization": f"Bearer {secret}"}


@pytest.fixture
def h():
    return _Harness()


def test_put_without_token_is_strict_401(h):
    assert h.client.put("/api/platform/grants/agents", json=BODY).status_code == 401
    assert h.received == []


def test_delete_without_token_is_strict_401(h):
    assert h.client.delete("/api/platform/grants/agents").status_code == 401


def test_unknown_token_is_strict_401(h):
    r = h.client.put("/api/platform/grants/agents", json=BODY, headers={"Authorization": "Bearer noc_nope"})
    assert r.status_code == 401


def test_put_hands_the_credential_to_the_sink_with_org_from_the_token(h):
    r = h.client.put("/api/platform/grants/agents", json=BODY, headers=h.token(org=ORG))
    assert r.status_code == 204
    [got] = h.received
    assert got.org_id == ORG and got.issuer == "agents"
    assert got.credential == BODY["credential"] and got.agent_id == "agent-1"
    assert got.metadata == {"k": "v"} and got.delivery_token_id is not None


def test_body_cannot_name_an_org(h):
    r = h.client.put("/api/platform/grants/agents", json={**BODY, "org_id": str(OTHER_ORG)},
                     headers=h.token())
    assert r.status_code == 422
    assert h.received == []


def test_wrong_scope_is_403(h):
    r = h.client.put("/api/platform/grants/agents", json=BODY, headers=h.token(scopes=["x:read"]))
    assert r.status_code == 403 and r.json()["detail"] == "scope_missing"
    assert h.received == []


def test_wrong_token_issuer_is_403(h):
    r = h.client.put("/api/platform/grants/agents", json=BODY, headers=h.token(issuer="someone-else"))
    assert r.status_code == 403 and r.json()["detail"] == "issuer_not_allowed"


def test_token_without_issuer_is_403(h):
    r = h.client.put("/api/platform/grants/agents", json=BODY, headers=h.token(issuer=None))
    assert r.status_code == 403


def test_other_issuer_in_the_path_is_403(h):
    r = h.client.put("/api/platform/grants/someone-else", json=BODY, headers=h.token())
    assert r.status_code == 403
    assert h.received == []


def test_delete_revokes_for_the_token_org(h):
    r = h.client.delete("/api/platform/grants/agents", headers=h.token(org=OTHER_ORG))
    assert r.status_code == 204
    assert h.revoked == [GrantRevoked(org_id=OTHER_ORG, issuer="agents")]


def test_delete_with_wrong_scope_is_403(h):
    assert h.client.delete("/api/platform/grants/agents", headers=h.token(scopes=[])).status_code == 403
    assert h.revoked == []


def test_async_sink_is_awaited():
    seen = []

    async def sink(grant):
        seen.append(grant)

    resolver = FakeApiTokenResolver()
    resolver.register("noc_a", org_id=ORG, scopes=[GRANT_RECEIVE_SCOPE], issuer="agents")
    dep = make_get_auth_context(session_store=FakeSessionStore(), api_token_resolver=resolver,
                                session_cookie_name="nai_session")
    app = FastAPI()
    app.include_router(create_platform_grants_router(
        get_auth_context=dep, on_grant=sink, on_revoke=lambda g: None))
    r = TestClient(app).put("/api/platform/grants/agents", json=BODY,
                            headers={"Authorization": "Bearer noc_a"})
    assert r.status_code == 204 and len(seen) == 1


def test_sink_failure_is_500_and_never_echoes_the_credential():
    def bad(grant):
        raise RuntimeError("db down " + grant.credential)

    resolver = FakeApiTokenResolver()
    resolver.register("noc_a", org_id=ORG, scopes=[GRANT_RECEIVE_SCOPE], issuer="agents")
    dep = make_get_auth_context(session_store=FakeSessionStore(), api_token_resolver=resolver,
                                session_cookie_name="nai_session")
    app = FastAPI()
    app.include_router(create_platform_grants_router(
        get_auth_context=dep, on_grant=bad, on_revoke=lambda g: None))
    r = TestClient(app).put("/api/platform/grants/agents", json=BODY,
                            headers={"Authorization": "Bearer noc_a"})
    assert r.status_code == 500 and BODY["credential"] not in r.text


def test_auth_router_refuses_the_fake_resolver_in_deploy(monkeypatch):
    from types import SimpleNamespace

    from noctusai_seed.auth_router import create_auth_router

    monkeypatch.setenv("APP_ENV", "production")
    settings = SimpleNamespace(redis_url=None, redis_session_encryption_key=None,
                               supabase_url="http://x", supabase_anon_key="k")
    with pytest.raises(RuntimeError, match="deploy context"):
        create_auth_router(SimpleNamespace(), settings)
