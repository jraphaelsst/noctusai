"""platform-admin-mfa M2: the assurance gate composed inside the admin factories.

Strict codes (KB § PATTERNS/compliance/auth-boundary-false-green.md). Fakes
injected through ``app.state.mfa_gate`` (a DI seam) — nothing of ours patched.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
from types import SimpleNamespace
from typing import Optional
from uuid import uuid4

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from noctusai_lib.api.audit import FakeAuditSink
from noctusai_lib.api.auth import make_require_role
from noctusai_lib.api.auth.mfa import FakeMfaClient, FakeMfaPolicy, MfaGateConfig, MfaFactor
from noctusai_lib.api.auth.platform import require_org_admin, require_platform_admin
from noctusai_lib.api.auth.session import (
    AuthContext, FakeApiTokenResolver, FakeSessionStore, make_get_auth_context,
)
from noctusai_lib.api.auth.session.scopes import (
    require_org_admin_role_assured, require_scopes,
)
from noctusai_lib.testing import MockSupabaseClient

ORG = uuid4()
PRODUCT = "demo"


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class _Core:
    def __init__(self, rows):
        self._sb = MockSupabaseClient(rows, validate_schema=False, schema="public")

    def from_(self, name):
        return self._sb.from_(name)


def _jwt(**claims) -> str:
    enc = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()
    return f"{enc({'alg': 'HS256'})}.{enc(claims)}.sig"


def _app(mode: Optional[str], *, sink=None, client=None):
    padmin, oadmin, member = uuid4(), uuid4(), uuid4()
    core = _Core([
        {"id": str(padmin), "role": "admin", "org_role": "member", "org_id": str(ORG)},
        {"id": str(oadmin), "role": "user", "org_role": "admin", "org_id": str(ORG)},
        {"id": str(member), "role": "user", "org_role": "member", "org_id": str(ORG)},
    ])
    store = FakeSessionStore()
    gac = make_get_auth_context(session_store=store, api_token_resolver=FakeApiTokenResolver())
    app = FastAPI()
    if mode is not None:
        app.state.mfa_gate = MfaGateConfig(
            product=PRODUCT, policy=FakeMfaPolicy({PRODUCT: mode}),
            client=client or FakeMfaClient(), audit_sink=sink,
            audit_enabled=sink is not None, cache_ttl=0,
        )
    dp = require_platform_admin(get_auth_context=gac, get_core_client=lambda: core)
    do = require_org_admin(get_auth_context=gac, get_core_client=lambda: core)
    ds = require_scopes(user_roles=frozenset({"owner", "admin", "member"}),
                        get_auth_context=gac, get_core_client=lambda: core)

    @app.get("/platform")
    async def _p(ctx: AuthContext = Depends(dp)):
        return {"ok": True}

    @app.get("/org")
    async def _o(ctx: AuthContext = Depends(do)):
        return {"ok": True}

    @app.get("/scoped")
    async def _s(ctx: AuthContext = Depends(ds)):
        return {"ok": True}

    async def _cur_user(authorization=None):
        tok = (authorization or "").removeprefix("Bearer ")
        if not tok:
            from fastapi import HTTPException
            raise HTTPException(status_code=401, detail="no token")
        sub = json.loads(base64.urlsafe_b64decode(tok.split(".")[1] + "=="))["sub"]
        return SimpleNamespace(id=sub), tok

    roles = {str(padmin): "platform_admin", str(oadmin): "admin", str(member): "member"}
    require_role = make_require_role(_cur_user, lambda u: roles[str(u.id)])

    @app.get("/legacy")
    async def _l(auth=Depends(require_role("platform_admin", "admin", "member"))):
        return {"ok": True}

    return app, store, SimpleNamespace(padmin=padmin, oadmin=oadmin, member=member)


def _cookie(store, uid, aal: Optional[str]):
    sid = _run(store.create(user_id=uid, org_id=ORG, supabase_refresh_token="rt", ttl_seconds=60))
    if aal:
        _run(store.write_tokens(sid, refresh_token="rt", access_token="at",
                                access_expires_at=None, aal=aal))
    return {"nai_session": sid}


ADMIN_ROUTES = ["/platform", "/org", "/scoped"]


class TestNoToken:
    @pytest.mark.parametrize("route", ADMIN_ROUTES)
    @pytest.mark.parametrize("mode", [None, "off", "warn", "enforce"])
    def test_no_credential_is_401(self, route, mode):
        app, _s, _u = _app(mode)
        assert TestClient(app).get(route).status_code == 401


class TestEnforce:
    @pytest.mark.parametrize("route,who", [("/platform", "padmin"), ("/org", "oadmin"), ("/scoped", "oadmin")])
    def test_aal1_admin_is_403_mfa_required(self, route, who):
        app, store, u = _app("enforce")
        c = TestClient(app)
        r = c.get(route, cookies=_cookie(store, getattr(u, who), "aal1"))
        assert r.status_code == 403
        assert r.json()["detail"]["code"] == "mfa_required"
        assert r.json()["detail"]["enrolled"] is None  # cookie session: unknown

    def test_unknown_aal_user_fails_closed(self):
        app, store, u = _app("enforce")
        r = TestClient(app).get("/platform", cookies=_cookie(store, u.padmin, None))
        assert r.status_code == 403
        assert r.json()["detail"]["code"] == "mfa_required"

    @pytest.mark.parametrize("route,who", [("/platform", "padmin"), ("/org", "oadmin"), ("/scoped", "oadmin")])
    def test_aal2_admin_is_200(self, route, who):
        app, store, u = _app("enforce")
        r = TestClient(app).get(route, cookies=_cookie(store, getattr(u, who), "aal2"))
        assert r.status_code == 200

    def test_aal1_member_on_member_route_is_200(self):
        app, store, u = _app("enforce")
        r = TestClient(app).get("/scoped", cookies=_cookie(store, u.member, "aal1"))
        assert r.status_code == 200

    def test_non_admin_keeps_role_403_not_mfa(self):
        app, store, u = _app("enforce")
        r = TestClient(app).get("/platform", cookies=_cookie(store, u.member, "aal1"))
        assert r.status_code == 403
        assert r.json()["detail"]["code"] == "platform_admin_required"

    def test_legacy_require_role_aal1_403_aal2_200(self):
        app, _s, u = _app("enforce")
        c = TestClient(app)
        t1 = _jwt(sub=str(u.padmin), aal="aal1")
        t2 = _jwt(sub=str(u.padmin), aal="aal2")
        r1 = c.get("/legacy", headers={"Authorization": f"Bearer {t1}"})
        assert r1.status_code == 403 and r1.json()["detail"]["code"] == "mfa_required"
        assert c.get("/legacy", headers={"Authorization": f"Bearer {t2}"}).status_code == 200
        tm = _jwt(sub=str(u.member), aal="aal1")
        assert c.get("/legacy", headers={"Authorization": f"Bearer {tm}"}).status_code == 200

    def test_enrolled_flag_from_bearer_factors(self):
        fake = FakeMfaClient()
        app, _s, u = _app("enforce", client=fake)
        c = TestClient(app)
        tok = _jwt(sub=str(u.padmin), aal="aal1")
        r = c.get("/legacy", headers={"Authorization": f"Bearer {tok}"})
        assert r.json()["detail"]["enrolled"] is False
        fake.factors[tok] = [MfaFactor("f1", "totp", "verified")]
        r = c.get("/legacy", headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 403 and r.json()["detail"]["enrolled"] is True


class TestWarn:
    def test_aal1_admin_passes_with_header_and_audit_row(self):
        sink = FakeAuditSink()
        app, store, u = _app("warn", sink=sink)
        r = TestClient(app).get("/platform", cookies=_cookie(store, u.padmin, "aal1"))
        assert r.status_code == 200
        assert r.headers["X-Noctus-MFA"] == "required"
        assert len(sink.entries) == 1
        e = sink.entries[0]
        assert (e.method, e.route_template, e.product_slug) == ("MFA_WARN", "/platform", PRODUCT)
        assert e.actor.user_id == str(u.padmin)

    def test_warn_without_audit_logs_warning_no_secrets(self, caplog):
        app, store, u = _app("warn")
        with caplog.at_level(logging.WARNING, logger="noctusai_lib.api.auth.mfa.gate"):
            r = TestClient(app).get("/org", cookies=_cookie(store, u.oadmin, "aal1"))
        assert r.status_code == 200 and r.headers["X-Noctus-MFA"] == "required"
        msg = " ".join(rec.getMessage() for rec in caplog.records)
        assert "/org" in msg and str(u.oadmin) in msg

    def test_aal2_admin_no_header(self):
        app, store, u = _app("warn")
        r = TestClient(app).get("/platform", cookies=_cookie(store, u.padmin, "aal2"))
        assert r.status_code == 200 and "X-Noctus-MFA" not in r.headers

    def test_member_no_header(self):
        app, store, u = _app("warn")
        r = TestClient(app).get("/scoped", cookies=_cookie(store, u.member, "aal1"))
        assert r.status_code == 200 and "X-Noctus-MFA" not in r.headers


class TestOffAndUnconfigured:
    @pytest.mark.parametrize("mode", [None, "off"])
    @pytest.mark.parametrize("aal", [None, "aal1", "aal2"])
    def test_admin_unchanged(self, mode, aal):
        app, store, u = _app(mode)
        c = TestClient(app)
        for route, who in [("/platform", u.padmin), ("/org", u.oadmin), ("/scoped", u.oadmin)]:
            r = c.get(route, cookies=_cookie(store, who, aal))
            assert r.status_code == 200 and "X-Noctus-MFA" not in r.headers

    def test_off_does_not_touch_the_client(self):
        fake = FakeMfaClient()
        app, store, u = _app("off", client=fake)
        TestClient(app).get("/platform", cookies=_cookie(store, u.padmin, "aal1"))
        assert fake.factors == {}


class TestProductTokensAndImperative:
    def test_product_token_is_not_challenged(self):
        app, _s, _u = _app("enforce")
        ctx = AuthContext(org_id=ORG, caller_kind="product", user_id=None,
                          scopes=["x:read"], raw_token="t", api_token_id=uuid4())
        dep = require_scopes("x:read", get_auth_context=lambda: ctx, restrict="product_only")
        req = SimpleNamespace(app=app)
        assert _run(dep(request=req, response=None, ctx=ctx)) is ctx

    def test_imperative_twin_enforces(self):
        from fastapi import HTTPException
        app, _s, u = _app("enforce")
        core = _Core([{"id": str(u.oadmin), "org_role": "admin"}])
        req = SimpleNamespace(app=app, headers={})
        with pytest.raises(HTTPException) as ei:
            _run(require_org_admin_role_assured(core, u.oadmin, "X", request=req, aal="aal1"))
        assert ei.value.status_code == 403 and ei.value.detail["code"] == "mfa_required"
        _run(require_org_admin_role_assured(core, u.oadmin, "X", request=req, aal="aal2"))
