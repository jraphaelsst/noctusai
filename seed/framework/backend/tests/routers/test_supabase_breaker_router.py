"""`/api/platform/supabase-breaker` — platform-admin only (strict 401 / 403), re-arm needs a reason.

KB § PATTERNS/backend/supabase-request-breaker.md
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Optional
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient

from noctusai_lib.primitives.supabase_breaker import (
    InMemoryBreakerStore,
    RecordingAlerter,
    configure_breaker,
    get_breaker,
    reset_breaker_for_tests,
)
from noctusai_seed.supabase_breaker_router import create_supabase_breaker_router

BASE = "/api/platform/supabase-breaker"


class _Deps:
    def __init__(self, role: Optional[str]) -> None:
        self._role = role

    async def get_current_user(self, authorization: Optional[str] = Header(None)):
        if not authorization:
            raise HTTPException(status_code=401, detail="no token")
        return SimpleNamespace(id="u1", email="ana@noctusai.com"), authorization

    def get_core_client(self):
        client = MagicMock()
        rows = [{"role": self._role}] if self._role else []
        client.from_.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = (
            SimpleNamespace(data=rows)
        )
        return client


def _client(role: Optional[str]) -> TestClient:
    deps = _Deps(role)
    # FastAPI needs the dependency to be a real callable bound on the instance
    app = FastAPI()
    app.include_router(create_supabase_breaker_router(deps))
    return TestClient(app)


@pytest.fixture(autouse=True)
def _breaker():
    reset_breaker_for_tests()
    configure_breaker(slug="prod-x", store=InMemoryBreakerStore(), alerter=RecordingAlerter())
    yield
    reset_breaker_for_tests()


@pytest.mark.parametrize("method,path", [("get", ""), ("post", "/rearm"), ("post", "/trip")])
def test_no_token_is_strictly_401(method, path):
    resp = getattr(_client("admin"), method)(BASE + path, **({"json": {"source": "worker:a", "reason": "x"}} if method == "post" else {}))
    assert resp.status_code == 401


@pytest.mark.parametrize("role", ["user", "manager", None])
@pytest.mark.parametrize("method,path", [("get", ""), ("post", "/rearm"), ("post", "/trip")])
def test_non_platform_admin_is_strictly_403(role, method, path):
    kw = {"headers": {"Authorization": "Bearer t"}}
    if method == "post":
        kw["json"] = {"source": "worker:a", "reason": "x"}
    resp = getattr(_client(role), method)(BASE + path, **kw)
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "platform_admin_required"


def test_admin_trips_and_rearms_with_a_reason():
    c, h = _client("admin"), {"Authorization": "Bearer t"}
    assert c.post(BASE + "/trip", json={"source": "worker:a", "reason": "manual stop"}, headers=h).status_code == 200
    assert get_breaker().hold_reason("worker:a") is not None
    assert c.get(BASE, headers=h).json()["held"]["worker:a"]["by"] == "ana@noctusai.com"
    assert c.post(BASE + "/rearm", json={"source": "worker:a", "reason": "  "}, headers=h).status_code == 422
    assert get_breaker().hold_reason("worker:a") is not None
    assert c.post(BASE + "/rearm", json={"source": "worker:a", "reason": "fixed, verified"}, headers=h).status_code == 200
    assert get_breaker().hold_reason("worker:a") is None


def test_http_source_cannot_be_tripped_and_extra_fields_are_refused():
    c, h = _client("admin"), {"Authorization": "Bearer t"}
    assert c.post(BASE + "/trip", json={"source": "http", "reason": "x"}, headers=h).status_code == 422
    assert c.post(BASE + "/trip", json={"source": "worker:a", "reason": "x", "oops": 1}, headers=h).status_code == 422
