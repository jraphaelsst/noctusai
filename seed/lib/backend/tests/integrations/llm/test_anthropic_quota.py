"""An empty Anthropic balance surfaces as `ProviderQuotaExhausted`, not a 502.

Anthropic answers "no credit left" with HTTP 400 `invalid_request_error`
("Your credit balance is too low…"). Left as a plain `LLMAPIError` it renders
as a 502, which Cloudflare masks — the operator saw an HTML wall instead of
"Créditos da API Anthropic esgotados". Sibling of `test_openai_quota.py`.
"""
from __future__ import annotations

import httpx
import pytest
from anthropic import BadRequestError, RateLimitError

from noctusai_lib.integrations.llm import LLMAPIError, ProviderQuotaExhausted
from noctusai_lib.integrations.llm.providers.anthropic_provider import (
    AnthropicProvider,
    is_quota_exhausted,
)
from noctusai_lib.integrations.llm.tool_calling import ChatMessage

_REQUEST = httpx.Request("POST", "https://api.anthropic.com/v1/messages")


def _credit_error() -> BadRequestError:
    body = {
        "type": "error",
        "error": {
            "type": "invalid_request_error",
            "message": "Your credit balance is too low to access the Anthropic API.",
        },
    }
    return BadRequestError(
        "Your credit balance is too low to access the Anthropic API.",
        response=httpx.Response(400, request=_REQUEST),
        body=body,
    )


def _rate_limit_error() -> RateLimitError:
    body = {"type": "error", "error": {"type": "rate_limit_error", "message": "slow down"}}
    return RateLimitError("slow down", response=httpx.Response(429, request=_REQUEST), body=body)


def _plain_bad_request() -> BadRequestError:
    body = {"type": "error", "error": {"type": "invalid_request_error", "message": "bad tool schema"}}
    return BadRequestError("bad tool schema", response=httpx.Response(400, request=_REQUEST), body=body)


def test_credit_balance_is_quota_exhausted():
    assert is_quota_exhausted(_credit_error())


@pytest.mark.parametrize("make", [_rate_limit_error, _plain_bad_request])
def test_other_errors_are_not_quota(make):
    assert not is_quota_exhausted(make())


class _Messages:
    def __init__(self, exc):
        self._exc = exc

    async def create(self, **_kwargs):
        raise self._exc


class _Client:
    def __init__(self, exc):
        self.messages = _Messages(exc)


def _provider(exc) -> AnthropicProvider:
    provider = AnthropicProvider()
    provider._clients["k"] = _Client(exc)  # the provider's own per-key client pool
    return provider


@pytest.mark.asyncio
async def test_chat_with_tools_raises_typed_quota_error():
    provider = _provider(_credit_error())
    with pytest.raises(ProviderQuotaExhausted) as info:
        await provider.chat_with_tools([ChatMessage.user("oi")], [], model="m", api_key="k")
    assert info.value.status_code == 503
    assert info.value.code == "LLM_QUOTA_EXHAUSTED"
    assert "Anthropic" in info.value.message


@pytest.mark.asyncio
async def test_chat_completion_raises_typed_quota_error():
    provider = _provider(_credit_error())
    with pytest.raises(ProviderQuotaExhausted):
        await provider.chat_completion([{"role": "user", "content": "oi"}], model="m", api_key="k")


@pytest.mark.asyncio
async def test_other_api_errors_stay_plain():
    provider = _provider(_plain_bad_request())
    with pytest.raises(LLMAPIError) as info:
        await provider.chat_with_tools([ChatMessage.user("oi")], [], model="m", api_key="k")
    assert not isinstance(info.value, ProviderQuotaExhausted)
    assert info.value.status_code == 502
