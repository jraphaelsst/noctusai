"""The seed middleware stack must stay pure ASGI.

🔴 WHY THIS FILE EXISTS
`BaseHTTPMiddleware` re-frames the downstream response through an anyio
task group and a memory stream. When a client disappears mid-response it
can emit a final empty body chunk for a response whose `Content-Length`
was already sent, and uvicorn answers by killing the connection:

    RuntimeError: Response content shorter than Content-Length

CloudFlare renders that reset as **502 Bad Gateway**, and the app logs
nothing that looks like a failure. Production, 2026-08-25:
`erp.noctusai.com` served Bad Gateway to a browser 260 times in six hours
while every health check passed and the container reported healthy. It hit
erp alone because erp is the only product shipping a service worker — the
prefetch/abort traffic that produces mid-response disconnects. Every other
product carried the identical latent bug with no traffic shaped to fire it.

So "is it pure ASGI" is not a style question here, and it is asserted
structurally: the functional tests below would all pass just as happily
under `BaseHTTPMiddleware`, because the bug needs a disconnect at exactly
the wrong moment to show itself. Only the type check catches a well-meant
rewrite back to the convenient `dispatch` shape.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware

from noctusai_lib.api.middleware import (
    CorrelationIdMiddleware,
    MaxBodySizeMiddleware,
    RequestLoggingMiddleware,
)

MIDDLEWARES = (
    CorrelationIdMiddleware,
    RequestLoggingMiddleware,
    MaxBodySizeMiddleware,
)


@pytest.mark.parametrize("cls", MIDDLEWARES, ids=lambda c: c.__name__)
def test_never_subclasses_base_http_middleware(cls) -> None:
    """The one assertion that actually prevents the 502 from returning."""
    assert not issubclass(cls, BaseHTTPMiddleware), (
        f"{cls.__name__} is a BaseHTTPMiddleware again — this reintroduces "
        "the erp.noctusai.com 502 (see this module's docstring)."
    )


@pytest.mark.parametrize("cls", MIDDLEWARES, ids=lambda c: c.__name__)
def test_implements_the_asgi_callable_shape(cls) -> None:
    """Pure ASGI means `__call__(scope, receive, send)`, not `dispatch`."""
    assert not hasattr(cls, "dispatch")
    assert list(cls.__call__.__code__.co_varnames[:4]) == [
        "self", "scope", "receive", "send",
    ]


def _app(tmp_path):
    app = FastAPI()
    app.add_middleware(MaxBodySizeMiddleware, max_bytes=1024)
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(CorrelationIdMiddleware)

    shell = tmp_path / "index.html"
    shell.write_bytes(b"<!doctype html><title>spa</title>" + b"x" * 1500)

    @app.get("/spa")
    async def spa():
        # A Content-Length response served from disk — the exact shape that
        # was arriving empty in production.
        return FileResponse(shell)

    @app.get("/json")
    async def json_route():
        return {"ok": True}

    return app, shell


class TestTheStackStillDoesItsJob:
    """Pure ASGI must not have cost us the behaviour we converted it for."""

    def test_a_file_response_arrives_whole(self, tmp_path) -> None:
        app, shell = _app(tmp_path)
        expected = shell.read_bytes()
        with TestClient(app) as client:
            resp = client.get("/spa")
        assert resp.status_code == 200
        assert len(resp.content) == len(expected), (
            "body shorter than Content-Length — the production symptom"
        )
        assert resp.content == expected
        assert int(resp.headers["content-length"]) == len(expected)

    def test_correlation_id_is_echoed_when_supplied(self, tmp_path) -> None:
        app, _ = _app(tmp_path)
        with TestClient(app) as client:
            resp = client.get("/json", headers={"X-Correlation-ID": "abc-123"})
        assert resp.headers["X-Correlation-ID"] == "abc-123"

    def test_correlation_id_is_generated_when_absent(self, tmp_path) -> None:
        app, _ = _app(tmp_path)
        with TestClient(app) as client:
            resp = client.get("/json")
        assert len(resp.headers["X-Correlation-ID"]) >= 32

    def test_x_request_id_is_honoured_as_the_fallback_header(self, tmp_path) -> None:
        app, _ = _app(tmp_path)
        with TestClient(app) as client:
            resp = client.get("/json", headers={"X-Request-ID": "req-9"})
        assert resp.headers["X-Correlation-ID"] == "req-9"

    def test_timing_header_is_present_on_a_streamed_file(self, tmp_path) -> None:
        """The header goes on `http.response.start`, so it must survive a
        response whose body is streamed afterwards."""
        app, _ = _app(tmp_path)
        with TestClient(app) as client:
            resp = client.get("/spa")
        assert float(resp.headers["X-Response-Time-Ms"]) >= 0

    def test_the_body_cap_still_rejects(self, tmp_path) -> None:
        app, _ = _app(tmp_path)
        with TestClient(app) as client:
            resp = client.post("/json", content=b"x" * 2048)
        assert resp.status_code == 413
