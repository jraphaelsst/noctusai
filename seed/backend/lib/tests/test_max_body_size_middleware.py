"""Unit tests for `noctusai_lib.api.middleware.MaxBodySizeMiddleware`.

Asserts:
  - Below cap: handler runs, body is readable.
  - Content-Length above cap: 413 short-circuit, handler never invoked.
  - Invalid Content-Length: 400.
  - max_bytes <= 0 raises at construction time (not silently accepted).
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from noctusai_lib.api.middleware import MaxBodySizeMiddleware


def _make_app(*, max_bytes: int) -> tuple[TestClient, dict]:
    app = FastAPI()
    app.add_middleware(MaxBodySizeMiddleware, max_bytes=max_bytes)
    counter = {"handled": 0}

    @app.post("/echo")
    async def echo(request: Request):
        counter["handled"] += 1
        body = await request.body()
        return {"len": len(body)}

    return TestClient(app), counter


def test_under_cap_request_succeeds():
    client, counter = _make_app(max_bytes=1024)
    resp = client.post("/echo", content=b"x" * 100)
    assert resp.status_code == 200
    assert resp.json() == {"len": 100}
    assert counter["handled"] == 1


def test_content_length_over_cap_returns_413_without_invoking_handler():
    client, counter = _make_app(max_bytes=512)
    resp = client.post("/echo", content=b"x" * 1024)
    assert resp.status_code == 413
    body = resp.json()
    assert body["error"] == "request body too large"
    assert body["limit_bytes"] == 512
    assert counter["handled"] == 0  # short-circuit before handler


def test_invalid_content_length_returns_400():
    client, _ = _make_app(max_bytes=1024)
    resp = client.post(
        "/echo", content=b"x", headers={"content-length": "not-a-number"},
    )
    assert resp.status_code == 400
    assert "Content-Length" in resp.json()["detail"]


def test_construction_rejects_non_positive_max_bytes():
    with pytest.raises(ValueError):
        MaxBodySizeMiddleware(app=None, max_bytes=0)
    with pytest.raises(ValueError):
        MaxBodySizeMiddleware(app=None, max_bytes=-1)


def test_default_cap_via_configure_app(monkeypatch):
    """`configure_app` honors `settings.max_body_bytes`."""
    from types import SimpleNamespace

    from noctusai_lib.api.app_factory import configure_app

    settings = SimpleNamespace(
        cors_origins_list=["http://localhost"],
        sentry_dsn="",
        is_production=False,
        debug=True,
        max_body_bytes=256,
    )
    app = FastAPI()

    @app.post("/echo")
    async def echo(request: Request):
        return {"len": len((await request.body()))}

    configure_app(app, settings)
    client = TestClient(app)
    # 200B fits under 256-byte cap
    assert client.post("/echo", content=b"x" * 200).status_code == 200
    # 300B trips the cap
    assert client.post("/echo", content=b"x" * 300).status_code == 413
