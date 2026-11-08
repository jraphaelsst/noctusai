"""SSO lifecycle S2 -- the seed auth dependency resolves ``session_product`` (observe mode).

Real ``ProductDependencies`` behind a real FastAPI app; only the registry client is faked (a DB
seam, not one of our guards). Observe NEVER blocks: a registry outage is a log line, never a 401.
"""
from __future__ import annotations

import logging
import time
import uuid
from types import SimpleNamespace

import jwt as pyjwt
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from noctusai_lib.api.auth import session_audience as sa
from noctusai_seed.dependencies import ProductDependencies

SESSION_ID = str(uuid.uuid4())


def _jwt(session_id: str | None = SESSION_ID) -> str:
    claims = {"sub": "u1", "exp": int(time.time() + 3600)}
    if session_id:
        claims["session_id"] = session_id
    return pyjwt.encode(claims, "x" * 32, algorithm="HS256")


class _Registry:
    def __init__(self, rows=None, fail=False):
        self.rows, self.fail, self.reads = rows or [], fail, 0

    def table(self, name):
        assert name == "sso_product_sessions"
        return self

    def select(self, *_a):
        return self

    def eq(self, *_a):
        return self

    def limit(self, *_a):
        return self

    def execute(self):
        self.reads += 1
        if self.fail:
            raise ConnectionError("registry down")
        return SimpleNamespace(data=self.rows)


class _Db:
    def __init__(self, registry):
        self.registry = registry

    def get_client(self):
        def get_user(_t):
            return SimpleNamespace(user=SimpleNamespace(id="u1", user_metadata={}))

        return SimpleNamespace(auth=SimpleNamespace(get_user=get_user))

    def get_core_client(self):
        return self.registry


@pytest.fixture(autouse=True)
def _restore_mode():
    yield
    sa.configure_session_audience(mode="off", is_core=False)


def _app(registry):
    deps = ProductDependencies(_Db(registry))
    app = FastAPI()

    @app.get("/plain")
    async def plain(auth=Depends(deps.get_current_user_ungated)):
        return {"ok": True}

    @app.get("/twice")
    async def twice(auth=Depends(deps.get_current_user_ungated), again=Depends(deps.get_current_user_ungated)):
        return {"ok": True}

    @app.get("/tagged")
    @sa.product_session_ok("bell token mint")
    async def tagged(auth=Depends(deps.get_current_user_ungated)):
        return {"ok": True}

    return app


def _get(client, path, token=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.get(path, headers=headers)


def _lines(caplog, event):
    return [r for r in caplog.records if r.getMessage().startswith(event)]


def test_core_logs_product_session_on_untagged_route_exactly_once_and_never_blocks(caplog):
    sa.configure_session_audience(mode="observe", is_core=True)
    reg = _Registry(rows=[{"product_slug": "agents"}])
    with caplog.at_level(logging.WARNING):
        r = _get(TestClient(_app(reg)), "/plain", _jwt())
    assert r.status_code == 200
    assert len(_lines(caplog, "product_session_on_core_route")) == 1


def test_one_request_with_two_auth_deps_still_logs_once(caplog):
    sa.configure_session_audience(mode="observe", is_core=True)
    with caplog.at_level(logging.WARNING):
        r = _get(TestClient(_app(_Registry(rows=[{"product_slug": "agents"}]))), "/twice", _jwt())
    assert r.status_code == 200
    assert len(_lines(caplog, "product_session_on_core_route")) == 1


def test_tagged_route_is_silent(caplog):
    sa.configure_session_audience(mode="observe", is_core=True)
    with caplog.at_level(logging.WARNING):
        r = _get(TestClient(_app(_Registry(rows=[{"product_slug": "agents"}]))), "/tagged", _jwt())
    assert r.status_code == 200
    assert _lines(caplog, "product_session_on_core_route") == []


def test_product_backend_does_not_log_core_route_event(caplog):
    sa.configure_session_audience(mode="observe", is_core=False)
    with caplog.at_level(logging.WARNING):
        r = _get(TestClient(_app(_Registry(rows=[{"product_slug": "agents"}]))), "/plain", _jwt())
    assert r.status_code == 200
    assert _lines(caplog, "product_session_on_core_route") == []


def test_unregistered_session_is_a_core_session_and_silent(caplog):
    sa.configure_session_audience(mode="observe", is_core=True)
    with caplog.at_level(logging.WARNING):
        assert _get(TestClient(_app(_Registry(rows=[]))), "/plain", _jwt()).status_code == 200
    assert _lines(caplog, "product_session_on_core_route") == []


def test_lookup_is_cached_per_token_across_requests():
    sa.configure_session_audience(mode="observe", is_core=True)
    reg = _Registry(rows=[{"product_slug": "agents"}])
    client = TestClient(_app(reg))
    tok = _jwt()
    for _ in range(3):
        assert _get(client, "/plain", tok).status_code == 200
    assert reg.reads == 1
    assert _get(client, "/plain", _jwt(str(uuid.uuid4()))).status_code == 200  # another session, another read
    assert reg.reads == 2


def test_registry_outage_logs_and_continues_never_401(caplog):
    sa.configure_session_audience(mode="observe", is_core=True)
    reg = _Registry(fail=True)
    client = TestClient(_app(reg))
    tok = _jwt()
    with caplog.at_level(logging.ERROR):
        r = _get(client, "/plain", tok)
        r2 = _get(client, "/plain", tok)
    assert r.status_code == 200 and r2.status_code == 200
    assert len(_lines(caplog, "sso_registry_unavailable")) == 2  # an outage is never cached
    assert reg.reads == 2


def test_missing_token_is_still_strictly_401():
    sa.configure_session_audience(mode="observe", is_core=True)
    assert _get(TestClient(_app(_Registry())), "/plain").status_code == 401


def test_mode_off_resolves_nothing():
    sa.configure_session_audience(mode="off", is_core=True)
    reg = _Registry(rows=[{"product_slug": "agents"}])
    assert _get(TestClient(_app(reg)), "/plain", _jwt()).status_code == 200
    assert reg.reads == 0


def test_enforce_is_refused_at_startup():
    with pytest.raises(RuntimeError, match="not implemented"):
        sa.configure_session_audience(mode="enforce", is_core=True)


def test_unknown_mode_is_refused():
    with pytest.raises(ValueError):
        sa.configure_session_audience(mode="obsreve", is_core=True)
