"""Tests for `app/services/api_keys_testers.py` — the Anthropic live probe.

`http_client_factory` is the injectable DI seam (never a real network
call, never a monkeypatch of `httpx.AsyncClient` itself) — every test
below builds an `httpx.AsyncClient(transport=httpx.MockTransport(...))`
via the factory, mirroring `community`'s own
`tests/services/test_api_keys_testers.py`.
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


class TestAnthropicTester:
    def test_success(self):
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url == "https://api.anthropic.com/v1/messages"
            assert request.headers["x-api-key"] == "sk-ant-test"
            return httpx.Response(200, json={"content": [{"type": "text", "text": "pong"}]})

        testers = make_testers(http_client_factory=_factory(handler))
        result = _run(testers["anthropic_api_key"]("sk-ant-test"))
        assert result.success is True
        assert result.key == "anthropic_api_key"

    def test_invalid_key_401(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"error": {"type": "authentication_error"}})

        testers = make_testers(http_client_factory=_factory(handler))
        result = _run(testers["anthropic_api_key"]("sk-ant-bad"))
        assert result.success is False
        assert "inválida" in result.message

    def test_no_credit_balance(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                400, json={"error": {"type": "invalid_request_error",
                                      "message": "credit_balance_too_low"}}
            )

        testers = make_testers(http_client_factory=_factory(handler))
        result = _run(testers["anthropic_api_key"]("sk-ant-x"))
        assert result.success is False
        assert "crédito" in result.message.lower()

    def test_rate_limited(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(429, json={"error": {"type": "rate_limit_error"}})

        testers = make_testers(http_client_factory=_factory(handler))
        result = _run(testers["anthropic_api_key"]("sk-ant-x"))
        assert result.success is False
        assert "limite" in result.message.lower()

    def test_connection_error_never_raises(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("boom")

        testers = make_testers(http_client_factory=_factory(handler))
        result = _run(testers["anthropic_api_key"]("sk-ant-x"))
        assert result.success is False
        assert "conexão" in result.message.lower()

    def test_unexpected_status(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500)

        testers = make_testers(http_client_factory=_factory(handler))
        result = _run(testers["anthropic_api_key"]("sk-ant-x"))
        assert result.success is False
        assert "500" in result.message


def test_exactly_one_tester_registered():
    testers = make_testers()
    assert set(testers) == {"anthropic_api_key"}
