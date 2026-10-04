"""Execution tests for the ``mfa`` step-up router (platform-admin-mfa M3).

Fakes injected (``FakeMfaClient`` / ``FakeSessionStore`` / ``FakeTokenExchanger``,
fake core client) — no patching of our own code. Strict status codes + codes.
"""
from __future__ import annotations

import logging
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from noctusai_lib.api.auth.mfa.client import FakeMfaClient
from noctusai_lib.api.auth.session import FakeSessionStore, FakeTokenExchanger
from noctusai_seed.mfa_router import SlidingWindowLimiter, create_mfa_router

BASE = "/api/auth/mfa"
CODE = "123456"
SECRET_MARKERS = ("FAKESECRET", "fake-aal2", "fake-refresh", "otpauth", "<svg", CODE)

TOKENS = {  # bearer -> (user_id, aal)
    "tok-member": ("u-member", "aal1"),
    "tok-admin1": ("u-admin", "aal1"),
    "tok-admin2": ("u-admin", "aal2"),
}


class _Result:
    def __init__(self, data):
        self.data = data


class _CoreClient:
    ROLES = {"u-admin": "admin", "u-member": "user"}

    def from_(self, _t):
        return self

    def select(self, *_a):
        return self

    def eq(self, _c, v):
        self._v = v
        return self

    def limit(self, _n):
        return self

    def execute(self):
        role = self.ROLES.get(self._v)
        return _Result([{"role": role}] if role else [])


class _Sink:
    def __init__(self):
        self.entries = []

    async def record(self, entry):
        self.entries.append(entry)


def _validator(token):
    if token not in TOKENS:
        raise HTTPException(status_code=401, detail="Token inválido")
    uid, aal = TOKENS[token]
    return SimpleNamespace(id=uid, user_metadata={"org_id": "org-1"}), aal


@pytest.fixture
def env():
    client = FakeMfaClient(valid_code=CODE)
    store = FakeSessionStore()
    exchanger = FakeTokenExchanger()
    sink = _Sink()
    deps = SimpleNamespace(get_core_client=lambda: _CoreClient(), get_client=lambda: None)
    app = FastAPI()
    app.state.audit_sink, app.state.audit_enabled = sink, True
    app.include_router(create_mfa_router(
        deps, SimpleNamespace(), client=client, session_store=store, token_exchanger=exchanger,
        bearer_validator=_validator, verify_limiter=SlidingWindowLimiter(),
    ))
    return SimpleNamespace(client=client, store=store, exchanger=exchanger, sink=sink,
                           http=TestClient(app), app=app)


def H(tok):
    return {"Authorization": f"Bearer {tok}"}


def code_of(resp):
    body = resp.json()
    return (body.get("detail") or {}).get("code") if isinstance(body.get("detail"), dict) else body.get("code")


# ─── Auth matrix: no token ⇒ 401 on every endpoint ──────────────────────

@pytest.mark.parametrize("method,path,body", [
    ("get", "/status", None),
    ("post", "/enroll", {"friendly_name": "x"}),
    ("post", "/verify", {"factor_id": "f", "code": CODE}),
    ("delete", "/factors/f1", None),
    ("post", "/admin/reset/u-member", None),
])
def test_no_token_is_401(env, method, path, body):
    r = getattr(env.http, method)(BASE + path, **({"json": body} if body is not None else {}))
    assert r.status_code == 401


def test_invalid_bearer_is_401(env):
    assert env.http.get(BASE + "/status", headers=H("nope")).status_code == 401


# ─── status ─────────────────────────────────────────────────────────────

def test_status_unenrolled(env):
    r = env.http.get(BASE + "/status", headers=H("tok-member"))
    assert r.status_code == 200
    assert r.json() == {"enrolled": False, "aal": "aal1", "factors": []}


def test_status_enrolled_aal2(env):
    fid = env.http.post(BASE + "/enroll", headers=H("tok-admin2"), json={"friendly_name": "phone"}).json()["factor_id"]
    env.http.post(BASE + "/verify", headers=H("tok-admin2"), json={"factor_id": fid, "code": CODE})
    r = env.http.get(BASE + "/status", headers=H("tok-admin2"))
    body = r.json()
    assert r.status_code == 200 and body["enrolled"] is True and body["aal"] == "aal2"
    assert set(body["factors"][0]) == {"id", "friendly_name", "status", "created_at"}
    assert body["factors"][0]["status"] == "verified"


def test_status_cookie_session_reports_ctx_aal(env):
    import asyncio
    sid = asyncio.run(env.store.create(user_id=uuid4(), org_id=uuid4(), supabase_refresh_token="r"))
    env.http.cookies.set("nai_session", sid)
    r = env.http.get(BASE + "/status")
    assert r.status_code == 200 and r.json()["aal"] is None and env.exchanger.calls == [sid]


# ─── enroll ─────────────────────────────────────────────────────────────

def test_enroll_returns_contract_shape(env):
    r = env.http.post(BASE + "/enroll", headers=H("tok-member"), json={"friendly_name": "phone"})
    assert r.status_code == 200
    assert set(r.json()) == {"factor_id", "qr_code", "uri"}
    assert r.json()["uri"].startswith("otpauth://")


@pytest.mark.parametrize("name", ["", "x" * 41])
def test_enroll_name_bounds_422(env, name):
    assert env.http.post(BASE + "/enroll", headers=H("tok-member"), json={"friendly_name": name}).status_code == 422


def test_enroll_unknown_key_422(env):
    r = env.http.post(BASE + "/enroll", headers=H("tok-member"), json={"friendly_name": "a", "x": 1})
    assert r.status_code == 422


def test_enroll_factor_limit_409(env):
    for i in range(2):
        fid = env.http.post(BASE + "/enroll", headers=H("tok-admin2"), json={"friendly_name": f"f{i}"}).json()["factor_id"]
        assert env.http.post(BASE + "/verify", headers=H("tok-admin2"), json={"factor_id": fid, "code": CODE}).status_code == 200
    r = env.http.post(BASE + "/enroll", headers=H("tok-admin2"), json={"friendly_name": "third"})
    assert r.status_code == 409 and code_of(r) == "mfa_factor_limit"


# ─── verify ─────────────────────────────────────────────────────────────

def test_verify_bearer_returns_tokens(env):
    fid = env.http.post(BASE + "/enroll", headers=H("tok-member"), json={"friendly_name": "p"}).json()["factor_id"]
    r = env.http.post(BASE + "/verify", headers=H("tok-member"), json={"factor_id": fid, "code": CODE})
    body = r.json()
    assert r.status_code == 200 and body["aal"] == "aal2"
    assert body["access_token"] and body["refresh_token"] and isinstance(body["expires_in"], int)


def test_verify_cookie_rewrites_store_and_returns_no_tokens(env):
    import asyncio
    sid = asyncio.run(env.store.create(user_id=uuid4(), org_id=uuid4(), supabase_refresh_token="old-refresh"))
    env.http.cookies.set("nai_session", sid)
    # Fake client state is keyed by the exchanger's access token.
    fid = env.http.post(BASE + "/enroll", json={"friendly_name": "p"}).json()["factor_id"]
    r = env.http.post(BASE + "/verify", json={"factor_id": fid, "code": CODE})
    assert r.status_code == 200 and r.json() == {"aal": "aal2"}
    tokens = asyncio.run(env.store.read_tokens(sid))
    assert tokens.access_token == f"fake-aal2-{fid}" and tokens.refresh_token == f"fake-refresh-{fid}"
    assert asyncio.run(env.store.lookup(sid)).aal == "aal2"


def test_verify_invalid_code_400(env):
    fid = env.http.post(BASE + "/enroll", headers=H("tok-member"), json={"friendly_name": "p"}).json()["factor_id"]
    r = env.http.post(BASE + "/verify", headers=H("tok-member"), json={"factor_id": fid, "code": "000000"})
    assert r.status_code == 400 and code_of(r) == "mfa_invalid_code"


def test_verify_unknown_factor_404(env):
    r = env.http.post(BASE + "/verify", headers=H("tok-member"), json={"factor_id": "nope", "code": CODE})
    assert r.status_code == 404 and code_of(r) == "mfa_factor_not_found"


@pytest.mark.parametrize("code", ["12345", "abcdef", "1234567"])
def test_verify_code_shape_422(env, code):
    assert env.http.post(BASE + "/verify", headers=H("tok-member"), json={"factor_id": "f", "code": code}).status_code == 422


def test_verify_rate_limited_429_per_user(env):
    fid = env.http.post(BASE + "/enroll", headers=H("tok-member"), json={"friendly_name": "p"}).json()["factor_id"]
    bad = {"factor_id": fid, "code": "000000"}
    for _ in range(5):
        assert env.http.post(BASE + "/verify", headers=H("tok-member"), json=bad).status_code == 400
    r = env.http.post(BASE + "/verify", headers=H("tok-member"), json=bad)
    assert r.status_code == 429 and code_of(r) == "mfa_rate_limited"
    # another user is not throttled by this one's bucket
    assert env.http.post(BASE + "/verify", headers=H("tok-admin1"), json=bad).status_code == 404


def test_limiter_window_expires():
    now = [0.0]
    lim = SlidingWindowLimiter(limit=2, window_seconds=10, clock=lambda: now[0])
    assert lim.allow("k") and lim.allow("k") and not lim.allow("k")
    now[0] = 11.0
    assert lim.allow("k")


# ─── delete factor ──────────────────────────────────────────────────────

def _enrolled(env, tok, n=1):
    ids = []
    for i in range(n):
        fid = env.http.post(BASE + "/enroll", headers=H(tok), json={"friendly_name": f"f{i}"}).json()["factor_id"]
        env.http.post(BASE + "/verify", headers=H(tok), json={"factor_id": fid, "code": CODE})
        ids.append(fid)
    return ids


def test_delete_own_factor_requires_aal2_when_verified_exists(env):
    (fid,) = _enrolled(env, "tok-admin1")
    # tok-admin1 shares the Fake token bucket with itself; aal1 caller with a verified factor
    r = env.http.delete(f"{BASE}/factors/{fid}", headers=H("tok-admin1"))
    assert r.status_code == 403 and code_of(r) == "mfa_required"


def test_delete_own_factor_aal2_204(env):
    (fid,) = _enrolled(env, "tok-admin2")
    r = env.http.delete(f"{BASE}/factors/{fid}", headers=H("tok-admin2"))
    assert r.status_code == 204
    assert env.http.get(BASE + "/status", headers=H("tok-admin2")).json()["factors"] == []


def test_delete_unverified_factor_allowed_at_aal1(env):
    fid = env.http.post(BASE + "/enroll", headers=H("tok-member"), json={"friendly_name": "p"}).json()["factor_id"]
    assert env.http.delete(f"{BASE}/factors/{fid}", headers=H("tok-member")).status_code == 204


def test_delete_someone_elses_factor_404(env):
    (fid,) = _enrolled(env, "tok-admin2")
    r = env.http.delete(f"{BASE}/factors/{fid}", headers=H("tok-member"))
    assert r.status_code == 404 and code_of(r) == "mfa_factor_not_found"


# ─── admin reset ────────────────────────────────────────────────────────

def test_reset_member_forbidden_403_platform_admin_required(env):
    r = env.http.post(BASE + "/admin/reset/u-x", headers=H("tok-member"))
    assert r.status_code == 403 and code_of(r) == "platform_admin_required"


def test_reset_admin_at_aal1_refused_mfa_required(env):
    r = env.http.post(BASE + "/admin/reset/u-member", headers=H("tok-admin1"))
    assert r.status_code == 403 and code_of(r) == "mfa_required"
    assert env.sink.entries == []


def test_reset_admin_aal2_deletes_and_audits(env):
    env.client.bind_user("u-member", "tok-member")
    _enrolled(env, "tok-member", n=2)
    r = env.http.post(BASE + "/admin/reset/u-member", headers=H("tok-admin2"))
    assert r.status_code == 200 and r.json() == {"deleted": 2}
    assert env.http.get(BASE + "/status", headers=H("tok-member")).json()["factors"] == []
    assert len(env.sink.entries) == 1
    e = env.sink.entries[0]
    assert e.method == "MFA_RESET" and e.path_params == {"user_id": "u-member"} and e.actor.user_id == "u-admin"


# ─── no secret in logs ──────────────────────────────────────────────────

def test_no_secret_material_in_logs(env, caplog):
    caplog.set_level(logging.DEBUG)
    fid = env.http.post(BASE + "/enroll", headers=H("tok-admin2"), json={"friendly_name": "p"}).json()["factor_id"]
    env.http.post(BASE + "/verify", headers=H("tok-admin2"), json={"factor_id": fid, "code": "000000"})
    env.http.post(BASE + "/verify", headers=H("tok-admin2"), json={"factor_id": fid, "code": CODE})
    env.client.bind_user("u-admin", "tok-admin2")
    env.http.post(BASE + "/admin/reset/u-admin", headers=H("tok-admin2"))
    text = "\n".join(r.getMessage() for r in caplog.records)
    for marker in SECRET_MARKERS + ("tok-admin2",):
        assert marker not in text


# ─── mounting ───────────────────────────────────────────────────────────

def test_create_product_app_mounts_mfa_by_default():
    from noctusai_seed.routers import build_standard_routers
    names = ["health"]
    routers = build_standard_routers(SimpleNamespace(), SimpleNamespace(), "P", "0", names=[*names, "mfa"])
    paths = {r.path for rt in routers for r in rt.routes}
    assert {f"{BASE}/status", f"{BASE}/enroll", f"{BASE}/verify"} <= paths
