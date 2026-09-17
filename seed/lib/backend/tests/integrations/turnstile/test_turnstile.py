"""Canonical adapter tests for `noctusai_lib.integrations.turnstile`.

Zero network: the Fake covers the Protocol contract, the Real adapter is
exercised via `httpx.MockTransport` (same convention as
`tests/integrations/payments/test_asaas_gateway.py`). Async methods are
driven via `asyncio.run(...)` inside plain `def test_...()` — this repo
has no `pytest-asyncio` plugin installed (see
`products/community/backend/tests/services/test_membros_service.py` for
the same convention on the product side).
"""
from __future__ import annotations

import asyncio

import httpx

from noctusai_lib.integrations.turnstile import (
    FakeTurnstileVerifier,
    RealTurnstileVerifier,
    TurnstileVerifier,
    make_turnstile_verifier,
)


# ── factory ──────────────────────────────────────────────────────────────


def test_factory_defaults_to_fake_when_no_secret():
    verifier = make_turnstile_verifier()
    assert isinstance(verifier, FakeTurnstileVerifier)


def test_factory_use_fake_true_overrides_secret():
    verifier = make_turnstile_verifier(use_fake=True, secret="a-real-secret")
    assert isinstance(verifier, FakeTurnstileVerifier)


def test_factory_real_when_secret_configured():
    verifier = make_turnstile_verifier(secret="a-real-secret")
    assert isinstance(verifier, RealTurnstileVerifier)
    assert not isinstance(verifier, FakeTurnstileVerifier)


def test_fake_satisfies_protocol():
    assert isinstance(FakeTurnstileVerifier(), TurnstileVerifier)


# ── Fake ─────────────────────────────────────────────────────────────────


def test_fake_accepts_nonempty_token_by_default():
    verifier = FakeTurnstileVerifier()
    result = asyncio.run(verifier.verify("some-token"))
    assert result.success is True
    assert verifier.calls == [("some-token", None)]


def test_fake_rejects_empty_token():
    verifier = FakeTurnstileVerifier()
    result = asyncio.run(verifier.verify(""))
    assert result.success is False
    assert "missing-input-response" in result.error_codes


def test_fake_accept_false_rejects_everything():
    verifier = FakeTurnstileVerifier(accept=False)
    result = asyncio.run(verifier.verify("some-token"))
    assert result.success is False


def test_fake_rejected_tokens_overrides_one_value():
    verifier = FakeTurnstileVerifier()
    verifier.rejected_tokens.add("bad-token")
    ok = asyncio.run(verifier.verify("good-token"))
    bad = asyncio.run(verifier.verify("bad-token"))
    assert ok.success is True
    assert bad.success is False


# ── Real (httpx.MockTransport, zero network) ──────────────────────────────


def test_real_success_response():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"success": True, "error-codes": []})

    verifier = RealTurnstileVerifier(
        secret="s", transport=httpx.MockTransport(handler),
    )
    result = asyncio.run(verifier.verify("token-123", remote_ip="1.2.3.4"))
    assert result.success is True
    assert result.raw["success"] is True


def test_real_failure_response_carries_error_codes():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"success": False, "error-codes": ["invalid-input-response"]},
        )

    verifier = RealTurnstileVerifier(secret="s", transport=httpx.MockTransport(handler))
    result = asyncio.run(verifier.verify("bad-token"))
    assert result.success is False
    assert result.error_codes == ("invalid-input-response",)


def test_real_empty_token_never_calls_cloudflare():
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("must not call Cloudflare for an empty token")

    verifier = RealTurnstileVerifier(secret="s", transport=httpx.MockTransport(handler))
    result = asyncio.run(verifier.verify(""))
    assert result.success is False


def test_real_transport_error_fails_closed():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    verifier = RealTurnstileVerifier(secret="s", transport=httpx.MockTransport(handler))
    result = asyncio.run(verifier.verify("token-123"))
    assert result.success is False
    assert "internal-error" in result.error_codes
