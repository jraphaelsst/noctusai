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

from datetime import date
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from pydantic import BaseModel, EmailStr, Field

from noctusai_lib.primitives.exceptions import (
    http_exception_handler,
    request_validation_exception_handler,
)


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


# ---------------------------------------------------------------------------
# request_validation_exception_handler — pt-BR 422 messages (finais)
# ---------------------------------------------------------------------------


class _Payload(BaseModel):
    model_config = {"extra": "forbid"}

    nome: str = Field(min_length=3, max_length=5)
    idade: int = Field(gt=0, le=120)
    email: EmailStr
    tipo: Literal["a", "b"]
    nascimento: date
    ativo: bool


def _make_validation_app() -> TestClient:
    app = FastAPI()
    app.add_exception_handler(RequestValidationError, request_validation_exception_handler)

    @app.post("/payload")
    async def create_payload(body: _Payload) -> dict:
        return {"ok": True}

    return TestClient(app)


class TestRequestValidationExceptionHandlerIsPtBr:
    """FastAPI raises `RequestValidationError` for a request-body failure —
    NOT the bare `pydantic.ValidationError` `validation_exception_handler`
    covers — so this exercises the actual 422 path every `StrictHttpModel`
    route uses. Before this handler existed, FastAPI's own default served
    pydantic's raw ENGLISH `msg` as `{"detail": [...]}`.
    """

    def test_missing_field_is_pt_br(self) -> None:
        client = _make_validation_app()
        resp = client.post("/payload", json={})
        assert resp.status_code == 422
        body = resp.json()
        assert "Campo obrigatório" in body["error"]["message"]
        # Machine-readable array stays untranslated (raw pydantic msg/type).
        by_field = {e["field"]: e for e in body["error"]["details"]["errors"]}
        assert by_field["nome"]["message"] == "Field required"
        assert by_field["nome"]["type"] == "missing"

    def test_string_too_short_and_too_long_are_pt_br(self) -> None:
        client = _make_validation_app()
        resp = client.post(
            "/payload",
            json={
                "nome": "a",
                "idade": 30,
                "email": "a@b.com",
                "tipo": "a",
                "nascimento": "2020-01-01",
                "ativo": True,
            },
        )
        assert resp.status_code == 422
        assert "pelo menos 3 caracteres" in resp.json()["error"]["message"]

    def test_greater_than_and_less_than_equal_are_pt_br(self) -> None:
        client = _make_validation_app()
        resp = client.post(
            "/payload",
            json={
                "nome": "abcd",
                "idade": 0,
                "email": "a@b.com",
                "tipo": "a",
                "nascimento": "2020-01-01",
                "ativo": True,
            },
        )
        assert resp.status_code == 422
        assert "maior que 0" in resp.json()["error"]["message"]

    def test_invalid_email_is_pt_br(self) -> None:
        client = _make_validation_app()
        resp = client.post(
            "/payload",
            json={
                "nome": "abcd",
                "idade": 30,
                "email": "not-an-email",
                "tipo": "a",
                "nascimento": "2020-01-01",
                "ativo": True,
            },
        )
        assert resp.status_code == 422
        assert "E-mail inválido" in resp.json()["error"]["message"]

    def test_literal_error_is_pt_br(self) -> None:
        client = _make_validation_app()
        resp = client.post(
            "/payload",
            json={
                "nome": "abcd",
                "idade": 30,
                "email": "a@b.com",
                "tipo": "z",
                "nascimento": "2020-01-01",
                "ativo": True,
            },
        )
        assert resp.status_code == 422
        assert "Valor inválido" in resp.json()["error"]["message"]

    def test_extra_forbidden_is_pt_br(self) -> None:
        client = _make_validation_app()
        resp = client.post(
            "/payload",
            json={
                "nome": "abcd",
                "idade": 30,
                "email": "a@b.com",
                "tipo": "a",
                "nascimento": "2020-01-01",
                "ativo": True,
                "campo_desconhecido": 1,
            },
        )
        assert resp.status_code == 422
        assert "Campo não permitido" in resp.json()["error"]["message"]
        campos = {e["field"] for e in resp.json()["error"]["details"]["errors"]}
        # Source prefix ("body") is stripped — the field name is the raw key.
        assert "campo_desconhecido" in campos

    def test_int_float_bool_date_parsing_are_pt_br(self) -> None:
        client = _make_validation_app()
        resp = client.post(
            "/payload",
            json={
                "nome": "abcd",
                "idade": "not-an-int",
                "email": "a@b.com",
                "tipo": "a",
                "nascimento": "not-a-date",
                "ativo": "not-a-bool",
            },
        )
        assert resp.status_code == 422
        message = resp.json()["error"]["message"]
        assert "número inteiro" in message
        assert "Data inválida" in message
        assert "verdadeiro ou falso" in message
