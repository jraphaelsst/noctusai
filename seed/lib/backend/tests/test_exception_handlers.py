"""Unit tests for `noctusai_lib.primitives.exceptions.http_exception_handler`.

Regression pin for the fix-on-contact found wiring contract §E.11's 429
`julia_capacidade` (`projects/julia-agents-academia-CONTRACT.md`,
`products/agents/backend/app/routers/conversations_router.py`): a route
raising `HTTPException(status_code, detail=..., headers={"Retry-After":
"10"})` had `exc.headers` silently dropped — the `JSONResponse` the
handler built never carried a `headers=` kwarg at all — for BOTH response
shapes the handler produces (the flat `{detail, code}` "seed error shape"
and the legacy `{error: {code, message}}` envelope).
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from noctusai_lib.primitives.exceptions import http_exception_handler


def _make_app() -> TestClient:
    app = FastAPI()
    app.add_exception_handler(HTTPException, http_exception_handler)

    @app.get("/flat-with-headers")
    async def flat_with_headers():
        raise HTTPException(
            status_code=429,
            detail={"detail": "muitas conversas", "code": "julia_capacidade"},
            headers={"Retry-After": "10"},
        )

    @app.get("/legacy-with-headers")
    async def legacy_with_headers():
        raise HTTPException(
            status_code=404, detail="não encontrado", headers={"Retry-After": "10"}
        )

    @app.get("/flat-without-headers")
    async def flat_without_headers():
        raise HTTPException(
            status_code=409, detail={"detail": "conflito", "code": "conflict"}
        )

    @app.get("/legacy-without-headers")
    async def legacy_without_headers():
        raise HTTPException(status_code=404, detail="não encontrado")

    return TestClient(app)


class TestHttpExceptionHandlerForwardsHeaders:
    def test_flat_seed_error_shape_keeps_headers(self) -> None:
        client = _make_app()
        resp = client.get("/flat-with-headers")
        assert resp.status_code == 429
        assert resp.json() == {"detail": "muitas conversas", "code": "julia_capacidade"}
        assert resp.headers["retry-after"] == "10"

    def test_legacy_envelope_shape_keeps_headers(self) -> None:
        client = _make_app()
        resp = client.get("/legacy-with-headers")
        assert resp.status_code == 404
        assert resp.json() == {"error": {"code": "NOT_FOUND", "message": "não encontrado"}}
        assert resp.headers["retry-after"] == "10"

    def test_flat_seed_error_shape_without_headers_is_unaffected(self) -> None:
        client = _make_app()
        resp = client.get("/flat-without-headers")
        assert resp.status_code == 409
        assert resp.json() == {"detail": "conflito", "code": "conflict"}
        assert "retry-after" not in resp.headers

    def test_legacy_envelope_shape_without_headers_is_unaffected(self) -> None:
        client = _make_app()
        resp = client.get("/legacy-without-headers")
        assert resp.status_code == 404
        assert resp.json() == {"error": {"code": "NOT_FOUND", "message": "não encontrado"}}
        assert "retry-after" not in resp.headers
