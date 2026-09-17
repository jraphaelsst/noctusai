"""Tests for `app/services/api_keys_testers.py` — live-probe testers for
Stripe / Asaas API keys.

`http_client_factory` is the injectable DI seam (never a real network
call, never a monkeypatch of `httpx.AsyncClient` itself) — every test
below builds an `httpx.AsyncClient(transport=httpx.MockTransport(...))`
via the factory, mirroring `noctusai_lib.integrations.payments.
real_asaas.AsaasPaymentGateway`'s own `transport=` test seam.
"""
from __future__ import annotations

import asyncio

import httpx

from app.services.api_keys_testers import make_testers


def _run(coro):
    return asyncio.run(coro)


def _factory(handler):
    def _make() -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(handler))

    return _make


class TestStripeTester:
    def test_success(self):
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url == "https://api.stripe.com/v1/balance"
            assert request.headers["authorization"].startswith("Basic ")
            return httpx.Response(200, json={"object": "balance"})

        testers = make_testers(http_client_factory=_factory(handler))
        result = _run(testers["stripe_secret_key"]("sk_test_x"))
        assert result.success is True
        assert result.key == "stripe_secret_key"

    def test_invalid_key_401(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"error": {"message": "invalid"}})

        testers = make_testers(http_client_factory=_factory(handler))
        result = _run(testers["stripe_secret_key"]("sk_bad"))
        assert result.success is False
        assert "inválida" in result.message

    def test_connection_error_never_raises(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("boom")

        testers = make_testers(http_client_factory=_factory(handler))
        result = _run(testers["stripe_secret_key"]("sk_x"))
        assert result.success is False
        assert "conexão" in result.message.lower()

    def test_unexpected_status(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500)

        testers = make_testers(http_client_factory=_factory(handler))
        result = _run(testers["stripe_secret_key"]("sk_x"))
        assert result.success is False
        assert "500" in result.message


class TestAsaasTester:
    def test_success(self):
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path.endswith("/myAccount")
            assert request.headers["access_token"] == "asaas_key"
            return httpx.Response(200, json={"name": "Test Account"})

        testers = make_testers(http_client_factory=_factory(handler))
        result = _run(testers["asaas_api_key"]("asaas_key"))
        assert result.success is True
        assert result.key == "asaas_api_key"

    def test_invalid_key_401(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"errors": [{"description": "invalid"}]})

        testers = make_testers(http_client_factory=_factory(handler))
        result = _run(testers["asaas_api_key"]("bad_key"))
        assert result.success is False
        assert "inválida" in result.message


def test_no_testers_registered_for_non_testable_specs():
    testers = make_testers()
    assert set(testers) == {"stripe_secret_key", "asaas_api_key"}
