"""platform-admin-mfa M1: aal reader, AuthContext.aal population, MfaPolicy, MfaClient.

No monkeypatching of our own code: Fakes + injected seams (httpx.MockTransport,
fakeredis, refresh_fn) only.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
from types import SimpleNamespace
from uuid import uuid4

import fakeredis.aioredis
import httpx
import pytest
from fastapi import HTTPException

from noctusai_lib.api.auth import validate_bearer_token_with_aal
from noctusai_lib.api.auth.mfa import (
    FakeMfaClient, FakeMfaPolicy, MfaError, SupabaseMfaClient, SupabaseMfaPolicy,
    make_mfa_client, make_mfa_policy, read_aal, read_aal_issued,
)
from noctusai_lib.api.auth.session import FakeSessionStore, RedisSessionStore, SupabaseTokenExchanger
from noctusai_lib.api.auth.session.token_exchange import RefreshResult
from noctusai_lib.api.auth.session.types import AuthContext


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _jwt(**claims) -> str:
    enc = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()
    return f"{enc({'alg': 'HS256'})}.{enc(claims)}.sig"


# ── read_aal ────────────────────────────────────────────────────────────
USER = SimpleNamespace(id="u-1")


def test_read_aal_levels():
    assert read_aal(_jwt(sub="u-1", aal="aal2"), validated_user=USER) == "aal2"
    assert read_aal(_jwt(sub="u-1", aal="aal1"), validated_user=USER) == "aal1"


@pytest.mark.parametrize("token", [
    _jwt(sub="u-1"),                      # claim missing
    _jwt(sub="u-1", aal="aal3"),          # unknown value
    _jwt(sub="u-1", aal=2),               # wrong type
    "garbage", "a.b.c", "", "a..c",       # garbled
    _jwt(sub="someone-else", aal="aal2"), # not bound to the validated user
])
def test_read_aal_garbled_or_unbound_is_aal1(token):
    assert read_aal(token, validated_user=USER) == "aal1"


def test_read_aal_requires_a_validated_user():
    assert read_aal(_jwt(sub="u-1", aal="aal2"), validated_user=None) == "aal1"
    assert read_aal(_jwt(aal="aal2"), validated_user=SimpleNamespace(id=None)) == "aal1"
    with pytest.raises(TypeError):
        read_aal(_jwt(sub="u-1", aal="aal2"))  # type: ignore[call-arg]


def test_read_aal_issued():
    assert read_aal_issued(_jwt(aal="aal2")) == "aal2"
    assert read_aal_issued(_jwt()) == "aal1"
    assert read_aal_issued("garbage") == "aal1"
    assert read_aal_issued(None) is None


# ── AuthContext.aal population ──────────────────────────────────────────
def test_authcontext_aal_defaults_none():
    ctx = AuthContext(org_id=uuid4(), caller_kind="product", user_id=None, scopes=[],
                      raw_token="t", api_token_id=None)
    assert ctx.aal is None


class _Auth:
    def __init__(self, user): self._user = user
    def get_user(self, token): return SimpleNamespace(user=self._user)


def test_bearer_path_fills_aal():
    client = SimpleNamespace(auth=_Auth(USER))
    user, aal = validate_bearer_token_with_aal(client, _jwt(sub="u-1", aal="aal2"))
    assert user is USER and aal == "aal2"
    _, aal = validate_bearer_token_with_aal(client, _jwt(sub="u-1"))
    assert aal == "aal1"


def test_bearer_path_rejection_unchanged():
    client = SimpleNamespace(auth=_Auth(None))
    with pytest.raises(HTTPException) as e:
        validate_bearer_token_with_aal(client, _jwt(sub="u-1", aal="aal2"))
    assert e.value.status_code == 401


def test_cookie_path_fake_store_aal():
    async def go():
        store = FakeSessionStore()
        sid = await store.create(user_id=uuid4(), org_id=uuid4(), supabase_refresh_token="r")
        assert (await store.lookup(sid)).aal is None
        await store.write_tokens(sid, refresh_token="r2", access_token="a", access_expires_at=1, aal="aal2")
        assert (await store.lookup(sid)).aal == "aal2"
    _run(go())


def test_cookie_path_redis_store_and_exchanger_aal():
    async def go():
        redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
        store = RedisSessionStore(client=redis)
        sid = await store.create(user_id=uuid4(), org_id=uuid4(), supabase_refresh_token="r")
        assert (await store.lookup(sid)).aal is None
        tok = _jwt(aal="aal2")
        ex = SupabaseTokenExchanger(
            store, lock_client=redis,
            refresh_fn=lambda rt: RefreshResult(tok, "r2", 9999999999),
        )
        assert await ex.access_token_for(sid) == tok
        assert (await store.lookup(sid)).aal == "aal2"
    _run(go())


# ── MfaPolicy ───────────────────────────────────────────────────────────
def test_policy_resolution_fake():
    async def go():
        assert await FakeMfaPolicy().resolve("agents") == "off"
        p = FakeMfaPolicy({"fleet": "warn"})
        assert await p.resolve("agents") == "warn"
        p = FakeMfaPolicy({"fleet": "warn", "agents": "enforce"})
        assert await p.resolve("agents") == "enforce"
        assert await p.resolve("igig") == "warn"
        assert await FakeMfaPolicy({"fleet": "bogus"}).resolve("x") == "off"
    _run(go())


class _Query:
    def __init__(self, data=None, exc=None): self.data, self.exc, self.scopes = data, exc, None
    def select(self, *_): return self
    def in_(self, _col, vals): self.scopes = vals; return self
    def execute(self):
        if self.exc: raise self.exc
        return SimpleNamespace(data=[r for r in self.data if r["scope"] in self.scopes])


class _Db:
    def __init__(self, q): self.q, self.tables = q, []
    def from_(self, name): self.tables.append(name); return self.q


def test_supabase_policy_override_wins_and_default_off():
    rows = [{"scope": "fleet", "mode": "warn"}, {"scope": "agents", "mode": "enforce"}]
    pol = SupabaseMfaPolicy(_Db(_Query(rows)))
    assert _run(pol.resolve("agents")) == "enforce"
    assert _run(pol.resolve("igig")) == "warn"
    assert _run(SupabaseMfaPolicy(_Db(_Query([]))).resolve("agents")) == "off"


def test_supabase_policy_read_error_is_off_and_logged(caplog):
    pol = SupabaseMfaPolicy(_Db(_Query(exc=RuntimeError("db down"))))
    with caplog.at_level(logging.ERROR):
        assert _run(pol.resolve("agents")) == "off"
    assert "defaulting to off" in caplog.text


def test_policy_factory():
    assert isinstance(make_mfa_policy(use_fake=True, rows={"fleet": "warn"}), FakeMfaPolicy)
    assert isinstance(make_mfa_policy(core_client=object()), SupabaseMfaPolicy)
    with pytest.raises(ValueError):
        make_mfa_policy()


# ── MfaClient ───────────────────────────────────────────────────────────
def test_fake_client_enroll_challenge_verify():
    async def go():
        c = FakeMfaClient()
        enr = await c.enroll_totp("tok", friendly_name="phone")
        assert (await c.list_factors("tok"))[0].status == "unverified"
        ch = await c.challenge("tok", enr.factor_id)
        with pytest.raises(MfaError) as e:
            await c.verify("tok", enr.factor_id, ch.id, "000000")
        assert e.value.code == "invalid_code"
        sess = await c.verify("tok", enr.factor_id, ch.id, "123456")
        assert sess.aal == "aal2"
        assert (await c.list_factors("tok"))[0].status == "verified"
        with pytest.raises(MfaError):  # challenge is single-use
            await c.verify("tok", enr.factor_id, ch.id, "123456")
        await c.delete_factor("u", enr.factor_id)
        assert c.admin_deleted == [("u", enr.factor_id)] and await c.list_factors("tok") == []
        with pytest.raises(MfaError):
            await c.challenge("tok", "nope")
    _run(go())


def test_real_client_rest_shapes():
    seen = []
    aal2 = _jwt(aal="aal2")

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append((req.method, req.url.path, req.headers["authorization"]))
        p = req.url.path
        if p == "/auth/v1/user":
            return httpx.Response(200, json={"factors": [{"id": "f1", "factor_type": "totp", "status": "verified"}]})
        if p == "/auth/v1/factors":
            return httpx.Response(200, json={"id": "f1", "totp": {"secret": "S", "uri": "otpauth://x", "qr_code": "<svg/>"}})
        if p.endswith("/challenge"):
            return httpx.Response(200, json={"id": "c1", "expires_at": 5})
        if p.endswith("/verify"):
            body = json.loads(req.content)
            if body["code"] != "123456":
                return httpx.Response(422, json={})
            return httpx.Response(200, json={"access_token": aal2, "refresh_token": "r", "expires_in": 3600})
        if req.method == "DELETE":
            return httpx.Response(200, json={})
        return httpx.Response(500)

    c = make_mfa_client(supabase_url="https://x.supabase.co", anon_key="anon", service_role_key="svc",
                        transport=httpx.MockTransport(handler))
    assert isinstance(c, SupabaseMfaClient)

    async def go():
        assert (await c.list_factors("utok"))[0].id == "f1"
        assert (await c.enroll_totp("utok", friendly_name="p")).secret == "S"
        assert (await c.challenge("utok", "f1")).id == "c1"
        sess = await c.verify("utok", "f1", "c1", "123456")
        assert sess.aal == "aal2" and sess.refresh_token == "r"
        with pytest.raises(MfaError) as e:
            await c.verify("utok", "f1", "c1", "999999")
        assert e.value.code == "invalid_code"
        await c.delete_factor("uid", "f1")
    _run(go())
    assert ("DELETE", "/auth/v1/admin/users/uid/factors/f1", "Bearer svc") in seen
    assert seen[0][2] == "Bearer utok"


def test_real_client_delete_needs_service_role_and_factory_validates():
    c = SupabaseMfaClient(supabase_url="https://x", anon_key="a")
    with pytest.raises(MfaError):
        _run(c.delete_factor("u", "f"))
    assert isinstance(make_mfa_client(use_fake=True), FakeMfaClient)
    with pytest.raises(ValueError):
        make_mfa_client()
