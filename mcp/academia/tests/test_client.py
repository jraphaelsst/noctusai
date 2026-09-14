"""`academia.client` — the transport seam (CONTRACT §B.0 status
taxonomy, §C build steps 1-2).

Exercises `HttpAcademiaApi.request` against `httpx.MockTransport` — a
real request/response/error-mapping round-trip with no network call
(the sanctioned external-boundary test seam, mirrors
`noctusai_lib.integrations.n8n.n8n_adapter`'s `transport` kwarg). Also
covers `FakeAcademiaApi` and the `configure_client`/`get_client` DI
seam every tool module builds through.
"""
from __future__ import annotations

import asyncio
import json as _json
import logging
from unittest.mock import patch

import httpx
import pytest

from academia.client import (
    DEFAULT_TIMEOUT_SECONDS,
    FakeAcademiaApi,
    HttpAcademiaApi,
    configure_client,
    get_client,
)
from academia.settings import AcademiaSettings


def _settings(**overrides) -> AcademiaSettings:
    base = {"api_url": "https://academia.test", "api_token": "pk_secrettoken123"}
    base.update(overrides)
    return AcademiaSettings(**base)


def _capturing_transport(status_code: int, json_body=None):
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(status_code, json=json_body)

    return httpx.MockTransport(handler), captured


# ─── success path — method/URL/auth-header/body wiring ──────────────────


def test_get_success_returns_ok_true_and_merges_body():
    transport, captured = _capturing_transport(200, {"items": [{"slug": "x"}], "total": 1})
    api = HttpAcademiaApi(_settings(), transport=transport)
    out = asyncio.run(api.request("GET", "/api/kb", params={"consulta": "x"}))
    assert out == {"ok": True, "items": [{"slug": "x"}], "total": 1}
    assert captured[0].method == "GET"
    assert captured[0].url.path == "/api/kb"
    assert captured[0].headers["authorization"] == "Bearer pk_secrettoken123"


def test_post_sends_bearer_auth_and_json_body():
    transport, captured = _capturing_transport(201, {"slug": "novo"})
    api = HttpAcademiaApi(_settings(), transport=transport)
    body = {"titulo": "T", "categoria": "geral", "corpo_md": "x", "motivo": "m"}
    out = asyncio.run(api.request("POST", "/api/kb", json_body=body))
    assert out == {"ok": True, "slug": "novo"}
    req = captured[0]
    assert req.method == "POST"
    assert req.url.path == "/api/kb"
    assert req.headers["authorization"] == "Bearer pk_secrettoken123"
    assert _json.loads(req.content) == body


@pytest.mark.parametrize("method", ["PUT", "PATCH", "DELETE"])
def test_every_http_method_is_honoured(method):
    transport, captured = _capturing_transport(200, {"marker": True})
    api = HttpAcademiaApi(_settings(), transport=transport)
    asyncio.run(api.request(method, "/api/x", json_body={"a": 1}))
    assert captured[0].method == method


def test_get_drops_none_valued_params_httpx_would_otherwise_send_empty():
    transport, captured = _capturing_transport(200, {"items": [], "total": 0})
    api = HttpAcademiaApi(_settings(), transport=transport)
    asyncio.run(api.request("GET", "/api/kb", params={"consulta": None, "limite": 20}))
    assert "consulta" not in captured[0].url.params
    assert captured[0].url.params["limite"] == "20"


def test_empty_2xx_body_returns_bare_ok():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(204)

    api = HttpAcademiaApi(_settings(), transport=httpx.MockTransport(handler))
    out = asyncio.run(api.request("POST", "/api/x"))
    assert out == {"ok": True}


def test_non_dict_2xx_body_wraps_in_result_key():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[1, 2, 3])

    api = HttpAcademiaApi(_settings(), transport=httpx.MockTransport(handler))
    out = asyncio.run(api.request("GET", "/api/x"))
    assert out == {"ok": True, "result": [1, 2, 3]}


def test_non_json_2xx_body_is_typed_unreachable_not_fabricated():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json")

    api = HttpAcademiaApi(_settings(), transport=httpx.MockTransport(handler))
    out = asyncio.run(api.request("GET", "/api/x"))
    assert out["ok"] is False
    assert out["error"]["status"] == 0
    assert out["error"]["code"] == "unreachable"
    assert "non-JSON" in out["error"]["detail"]


def test_default_timeout_is_30_seconds():
    assert DEFAULT_TIMEOUT_SECONDS == 30.0
    assert _settings().timeout_seconds == 30.0


# ─── error mapping — CONTRACT §B.0 status taxonomy ───────────────────────


@pytest.mark.parametrize(
    "status,code,detail",
    [
        (401, "unauthenticated", "Sessão expirada — entre novamente."),
        (403, "scope_missing", "Sem permissão para esta ação."),
        (404, "not_found", "Não encontrado."),
        (409, "conflict", "Slug já existe."),
        (422, "validation_error", "campo obrigatório ausente."),
    ],
)
def test_http_error_uses_the_servers_code_and_detail_when_present(status, code, detail):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"detail": detail, "code": code})

    api = HttpAcademiaApi(_settings(), transport=httpx.MockTransport(handler))
    out = asyncio.run(api.request("GET", "/api/kb/x"))
    assert out == {"ok": False, "error": {"status": status, "code": code, "detail": detail}}


def test_http_error_without_server_error_shape_falls_back_to_generic_code():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, content=b"internal server error")

    api = HttpAcademiaApi(_settings(), transport=httpx.MockTransport(handler))
    out = asyncio.run(api.request("GET", "/api/kb/x"))
    assert out["ok"] is False
    assert out["error"]["status"] == 500
    assert out["error"]["code"] == "http_error"


# ─── unreachable / timeout — never a fabricated success ──────────────────


def test_connection_error_maps_to_unreachable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    api = HttpAcademiaApi(_settings(), transport=httpx.MockTransport(handler))
    out = asyncio.run(api.request("GET", "/api/kb"))
    assert out["ok"] is False
    assert out["error"]["status"] == 0
    assert out["error"]["code"] == "unreachable"


def test_timeout_maps_to_unreachable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    api = HttpAcademiaApi(_settings(), transport=httpx.MockTransport(handler))
    out = asyncio.run(api.request("GET", "/api/kb"))
    assert out["ok"] is False
    assert out["error"]["status"] == 0
    assert out["error"]["code"] == "unreachable"
    assert "timed out" in out["error"]["detail"]


# ─── not-configured — no default URL, no crash at import ────────────────


_NOT_CONFIGURED_DETAIL = (
    "academia connector not configured — set ACADEMIA_API_URL "
    "and ACADEMIA_API_TOKEN (mcp/academia/.env or the "
    "environment)."
)


def test_missing_url_is_not_configured_no_network_call():
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("must not attempt a network call when unconfigured")

    api = HttpAcademiaApi(
        AcademiaSettings(api_url=None, api_token="pk_x"),
        transport=httpx.MockTransport(handler),
    )
    out = asyncio.run(api.request("GET", "/api/kb"))
    assert out == {
        "ok": False,
        "error": {"status": 0, "code": "not_configured", "detail": _NOT_CONFIGURED_DETAIL},
    }


def test_missing_token_is_not_configured_no_network_call():
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("must not attempt a network call when unconfigured")

    api = HttpAcademiaApi(
        AcademiaSettings(api_url="https://x.test", api_token=None),
        transport=httpx.MockTransport(handler),
    )
    out = asyncio.run(api.request("GET", "/api/kb"))
    assert out["ok"] is False
    assert out["error"]["code"] == "not_configured"


def test_settings_construction_never_raises_and_has_no_default_url():
    s = AcademiaSettings()
    assert s.api_url is None
    assert s.api_token is None
    assert s.configured is False


# ─── token never logged ───────────────────────────────────────────────────


def test_token_never_appears_in_any_log_record(caplog):
    token = "pk_super_secret_do_not_log_9f8e7d"
    settings = _settings(api_token=token)

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    api = HttpAcademiaApi(settings, transport=httpx.MockTransport(handler))
    with caplog.at_level(logging.DEBUG):
        asyncio.run(api.request("GET", "/api/kb"))
        asyncio.run(api.request("POST", "/api/kb", json_body={"a": 1}))

    assert caplog.records, "expected the unreachable path to log something"
    for record in caplog.records:
        assert token not in record.getMessage()
        assert token not in str(record.args or "")


def test_token_never_appears_in_log_on_http_error_path(caplog):
    token = "pk_another_secret_abc123"
    settings = _settings(api_token=token)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "no", "code": "unauthenticated"})

    api = HttpAcademiaApi(settings, transport=httpx.MockTransport(handler))
    with caplog.at_level(logging.DEBUG):
        asyncio.run(api.request("GET", "/api/kb"))

    for record in caplog.records:
        assert token not in record.getMessage()


# ─── FakeAcademiaApi — records calls, returns scripted envelopes ────────


def test_fake_records_calls_and_returns_scripted_envelope():
    fake = FakeAcademiaApi()
    fake.set_response("GET", "/api/kb", {"ok": True, "items": [{"slug": "a"}], "total": 1})
    out = asyncio.run(fake.request("GET", "/api/kb", params={"limite": 20}))
    assert out == {"ok": True, "items": [{"slug": "a"}], "total": 1}
    assert fake.calls == [
        {"method": "GET", "path": "/api/kb", "params": {"limite": 20}, "json_body": None}
    ]


def test_fake_default_envelope_for_unscripted_call():
    fake = FakeAcademiaApi()
    out = asyncio.run(fake.request("GET", "/api/anything"))
    assert out == {"ok": True, "items": [], "total": 0}


def test_fake_can_script_an_error_envelope():
    fake = FakeAcademiaApi()
    fake.set_response(
        "POST", "/api/kb", {"ok": False, "error": {"status": 409, "code": "conflict", "detail": "x"}}
    )
    out = asyncio.run(fake.request("POST", "/api/kb", json_body={"slug": "dup"}))
    assert out["ok"] is False
    assert out["error"]["status"] == 409


# ─── configure_client / get_client DI seam ───────────────────────────────


def test_configure_client_overrides_get_client():
    fake = FakeAcademiaApi()
    configure_client(fake)
    try:
        assert get_client() is fake
    finally:
        configure_client(None)


def test_get_client_default_builds_http_api_from_settings():
    configure_client(None)
    with patch("academia.client.get_settings", return_value=_settings()):
        c = get_client()
    assert isinstance(c, HttpAcademiaApi)
    assert c.settings.api_url == "https://academia.test"
