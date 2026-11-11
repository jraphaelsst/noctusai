"""`/api/platform/supabase-breaker` — canonical `require_platform_admin` (strict 401/403 + admin-MFA AAL2),
bounded bodies, no fleet/http on the routes, audit row on every change.

KB § PATTERNS/backend/supabase-request-breaker.md
"""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from noctusai_lib.api.auth.mfa import FakeMfaClient, FakeMfaPolicy, MfaGateConfig
from noctusai_lib.primitives.supabase_breaker import (
    InMemoryBreakerStore,
    RecordingAlerter,
    configure_breaker,
    get_breaker,
    reset_breaker_for_tests,
)
from noctusai_lib.testing import MockSupabaseClient
from noctusai_seed.auth_router import get_session_store
from noctusai_seed.supabase_breaker_router import create_supabase_breaker_router

BASE = "/api/platform/supabase-breaker"
ORG = uuid4()
PRODUCT = "demo"


class _Core:
    def __init__(self, rows):
        self._sb = MockSupabaseClient(rows, validate_schema=False, schema="public")

    def from_(self, name):
        return self._sb.from_(name)


def _build(mode=None):
    padmin, member = uuid4(), uuid4()
    core = _Core([
        {"id": str(padmin), "role": "admin", "org_role": "member", "org_id": str(ORG)},
        {"id": str(member), "role": "user", "org_role": "member", "org_id": str(ORG)},
    ])
    settings = SimpleNamespace(redis_url=None, redis_session_encryption_key="")
    deps = SimpleNamespace(get_core_client=lambda: core)
    app = FastAPI()
    if mode is not None:
        app.state.mfa_gate = MfaGateConfig(product=PRODUCT, policy=FakeMfaPolicy({PRODUCT: mode}),
                                           client=FakeMfaClient(), audit_sink=None, audit_enabled=False, cache_ttl=0)
    app.include_router(create_supabase_breaker_router(deps, settings))
    store = get_session_store(settings)

    def cookie(uid, aal):
        sid = asyncio.new_event_loop().run_until_complete(
            store.create(user_id=uid, org_id=ORG, supabase_refresh_token="rt", ttl_seconds=60))
        if aal:
            asyncio.new_event_loop().run_until_complete(
                store.write_tokens(sid, refresh_token="rt", access_token="at", access_expires_at=None, aal=aal))
        return {"nai_session": sid}

    return TestClient(app), cookie, SimpleNamespace(padmin=padmin, member=member)


@pytest.fixture(autouse=True)
def _breaker():
    reset_breaker_for_tests()
    configure_breaker(slug="prod-x", store=InMemoryBreakerStore(), alerter=RecordingAlerter())
    get_breaker()._sync_io = True
    yield
    reset_breaker_for_tests()


BODY = {"source": "worker:a", "reason": "x"}
ROUTES = [("get", "", None), ("post", "/rearm", BODY), ("post", "/trip", BODY)]


@pytest.mark.parametrize("method,path,body", ROUTES)
def test_no_credential_is_strictly_401(method, path, body):
    c, _cookie, _u = _build()
    assert getattr(c, method)(BASE + path, **({"json": body} if body else {})).status_code == 401


@pytest.mark.parametrize("method,path,body", ROUTES)
def test_non_platform_admin_is_strictly_403(method, path, body):
    c, cookie, u = _build()
    resp = getattr(c, method)(BASE + path, cookies=cookie(u.member, "aal2"), **({"json": body} if body else {}))
    assert resp.status_code == 403 and resp.json()["detail"]["code"] == "platform_admin_required"


@pytest.mark.parametrize("path", ["/rearm", "/trip"])
def test_F2_aal1_admin_under_enforced_mfa_policy_is_403_mfa_required(path):
    c, cookie, u = _build("enforce")
    resp = c.post(BASE + path, json=BODY, cookies=cookie(u.padmin, "aal1"))
    assert resp.status_code == 403 and resp.json()["detail"]["code"] == "mfa_required"
    assert get_breaker().hold_reason("worker:a") is None, "the refused call must change nothing"
    ok = c.post(BASE + path, json=BODY, cookies=cookie(u.padmin, "aal2"))
    assert ok.status_code == 200


def test_admin_trips_and_rearms_with_a_reason_and_both_are_audited():
    c, cookie, u = _build()
    ck = cookie(u.padmin, "aal2")
    assert c.post(BASE + "/trip", json={"source": "worker:a", "reason": "manual stop"}, cookies=ck).status_code == 200
    assert get_breaker().hold_reason("worker:a") is not None
    assert c.post(BASE + "/rearm", json={"source": "worker:a", "reason": "   "}, cookies=ck).status_code == 422
    assert get_breaker().hold_reason("worker:a") is not None
    assert c.post(BASE + "/rearm", json={"source": "worker:a", "reason": "fixed, verified"}, cookies=ck).status_code == 200
    assert get_breaker().hold_reason("worker:a") is None
    audit = [json.loads(r) for r in get_breaker()._store.audits["noctus:breaker:prod-x:audit"]]
    assert [a["op"] for a in audit] == ["trip", "rearm"] and audit[1]["claimed_by"] == str(u.padmin)


@pytest.mark.parametrize("path", ["/rearm", "/trip"])
@pytest.mark.parametrize("source", ["fleet", "http", "startup", "unattributed", "bg:x", "worker:a b", "x" * 200, "rm -rf", "worker:"])
def test_F9_fleet_http_and_malformed_sources_are_refused(path, source):
    c, cookie, u = _build()
    resp = c.post(BASE + path, json={"source": source, "reason": "x"}, cookies=cookie(u.padmin, "aal2"))
    assert resp.status_code == 422


def test_F9_bodies_are_bounded_and_strict():
    c, cookie, u = _build()
    ck = cookie(u.padmin, "aal2")
    assert c.post(BASE + "/trip", json={"source": "worker:a", "reason": "r" * 301}, cookies=ck).status_code == 422
    assert c.post(BASE + "/trip", json={"source": "worker:a", "reason": "x", "oops": 1}, cookies=ck).status_code == 422


@pytest.mark.parametrize("reason", ["line\nbreak", "esc\x1b[31m", "nul\x00", "tab\t", "x" * 301])
@pytest.mark.parametrize("path", ["/rearm", "/trip"])
def test_P3_5_control_characters_and_overlong_reasons_are_422(reason, path):
    c, cookie, u = _build()
    resp = c.post(BASE + path, json={"source": "worker:a", "reason": reason}, cookies=cookie(u.padmin, "aal2"))
    assert resp.status_code == 422
    assert get_breaker().hold_reason("worker:a") is None


def test_builds_in_a_deploy_context_without_a_fake_token_resolver(monkeypatch):
    """P0 regression: the auto-mounted router must not need a real API-token resolver to build in production."""
    monkeypatch.setenv("APP_ENV", "production")
    _build()


@pytest.mark.parametrize("token", ["pk_abc", "noc_abc"])
def test_api_token_bearer_is_a_strict_401(token):
    client, _cookie, _ = _build()
    r = client.get(BASE, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401
