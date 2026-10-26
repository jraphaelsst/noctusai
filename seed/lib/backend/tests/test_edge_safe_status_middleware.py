"""Unit tests for `noctusai_lib.api.middleware.EdgeSafeStatusMiddleware`.

CloudFlare replaces an origin's 502/504 with its own page, so the app's
JSON never reaches the browser (verified live 2026-10-26). Asserts:
  - 502 and 504 leave as 503, body untouched, original in X-Upstream-Status.
  - Every other status (incl. 500/503) passes through unchanged.
  - The seed app factory installs it outside the request logger, so logs
    keep the handler's real status.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from noctusai_lib.api.middleware import (
    EDGE_SAFE_STATUS,
    UPSTREAM_STATUS_HEADER,
    EdgeSafeStatusMiddleware,
)


def _client() -> TestClient:
    app = FastAPI()
    app.add_middleware(EdgeSafeStatusMiddleware)

    @app.get("/raise/{code}")
    async def raise_(code: int):
        raise HTTPException(status_code=code, detail=f"falhou {code}")

    @app.get("/json/{code}")
    async def json_(code: int):
        return JSONResponse(status_code=code, content={"error": {"message": "Créditos esgotados"}})

    return TestClient(app)


@pytest.mark.parametrize("code", [502, 504])
@pytest.mark.parametrize("route", ["raise", "json"])
def test_masked_status_becomes_503_with_body_intact(route, code):
    resp = _client().get(f"/{route}/{code}")
    assert resp.status_code == EDGE_SAFE_STATUS == 503
    assert resp.headers[UPSTREAM_STATUS_HEADER] == str(code)
    body = resp.json()
    assert body == (
        {"detail": f"falhou {code}"} if route == "raise"
        else {"error": {"message": "Créditos esgotados"}}
    )


@pytest.mark.parametrize("code", [200, 400, 404, 500, 503])
def test_other_statuses_pass_through(code):
    resp = _client().get(f"/json/{code}")
    assert resp.status_code == code
    assert UPSTREAM_STATUS_HEADER not in resp.headers


def test_app_factory_installs_it_outside_the_request_logger():
    from noctusai_lib.api import app_factory

    src = open(app_factory.__file__, encoding="utf-8").read()
    install = src.index("app.add_middleware(EdgeSafeStatusMiddleware)")
    # Registered last => outermost: RequestLogging/Timing see the real 502.
    assert install > src.index("app.add_middleware(RequestLoggingMiddleware)")
    assert install > src.index("app.add_middleware(SecurityHeadersMiddleware)")


# ── noctusai_lib.testing.handler_status ─────────────────────────────────────


def test_handler_status_reads_the_handlers_choice():
    from noctusai_lib.testing import handler_status

    client = _client()
    assert handler_status(client.get("/raise/502")) == 502
    assert handler_status(client.get("/json/504")) == 504
    assert handler_status(client.get("/json/404")) == 404


def test_handler_status_refuses_a_raw_502_on_the_wire():
    """An app built without the seed factory would hand CloudFlare a 502."""
    from noctusai_lib.testing import handler_status

    app = FastAPI()

    @app.get("/x")
    async def x():
        raise HTTPException(status_code=502, detail="upstream")

    with pytest.raises(AssertionError, match="CloudFlare"):
        handler_status(TestClient(app).get("/x"))
