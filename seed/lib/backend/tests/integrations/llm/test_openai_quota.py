"""`insufficient_quota` (429) is a typed, NON-retried error; a plain
`rate_limit_exceeded` 429 is still retried. No network: the SDK's real error
objects are raised from a fake client; backoff runs on a VirtualClock."""
from __future__ import annotations

from types import SimpleNamespace

import httpx
import openai
import pytest

from noctusai_lib.integrations import rate_limit
from noctusai_lib.integrations.llm.exceptions import LLMAPIError, ProviderQuotaExhausted
from noctusai_lib.integrations.llm.providers import openai_provider
from noctusai_lib.integrations.llm.providers.openai_provider import (
    OpenAIProvider,
    is_quota_exhausted,
)


def _err(code: str, type_: str = "insufficient_quota", headers: dict | None = None):
    req = httpx.Request("POST", "https://api.openai.com/v1/embeddings")
    resp = httpx.Response(429, request=req, headers=headers or {})
    body = {"message": "You exceeded your current quota", "type": type_, "code": code}
    return openai.RateLimitError("429", response=resp, body=body)


class _Embeddings:
    def __init__(self, errors: list[Exception]):
        self.errors = list(errors)
        self.calls = 0

    async def create(self, **kwargs):
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)
        data = [SimpleNamespace(index=0, embedding=[0.5])]
        return SimpleNamespace(data=data, usage=None, model="m")


def _provider(emb: _Embeddings) -> OpenAIProvider:
    p = OpenAIProvider()
    p._clients["k"] = SimpleNamespace(embeddings=emb)
    return p


@pytest.fixture(autouse=True)
def _virtual_time():
    rate_limit.set_default_clock(rate_limit.VirtualClock())
    rate_limit._reset_all_buckets()
    yield
    rate_limit.reset_default_clock()
    rate_limit._reset_all_buckets()


def test_classifier():
    assert is_quota_exhausted(_err("insufficient_quota"))
    assert is_quota_exhausted(_err("credit_balance_exhausted", "billing"))
    assert not is_quota_exhausted(_err("rate_limit_exceeded", "requests"))


@pytest.mark.asyncio
async def test_quota_is_typed_and_not_retried():
    emb = _Embeddings([_err("insufficient_quota")] * 10)
    with pytest.raises(ProviderQuotaExhausted) as ei:
        await _provider(emb).generate_embeddings_batch(["a"], model="m", api_key="k")
    assert emb.calls == 1
    assert isinstance(ei.value, LLMAPIError)
    assert ei.value.code == "LLM_QUOTA_EXHAUSTED"
    assert ei.value.status_code == 503


@pytest.mark.asyncio
async def test_single_embedding_quota_not_retried():
    emb = _Embeddings([_err("credit_balance_exhausted", "billing")] * 10)
    with pytest.raises(ProviderQuotaExhausted):
        await _provider(emb).generate_embedding("a", model="m", api_key="k")
    assert emb.calls == 1


@pytest.mark.asyncio
async def test_plain_rate_limit_still_retried():
    emb = _Embeddings([_err("rate_limit_exceeded", "requests")] * 2)
    out = await _provider(emb).generate_embeddings_batch(["a"], model="m", api_key="k")
    assert out == [[0.5]]
    assert emb.calls == 3


def test_client_built_without_sdk_retries():
    client = OpenAIProvider()._client_for("sk-test")
    assert client.max_retries == 0
    assert openai_provider._is_retryable(_err("rate_limit_exceeded", "requests"))
    assert not openai_provider._is_retryable(_err("insufficient_quota"))


# ── OpenAIClientAdapter (caller-owned client) translates the same way ────────


class _Completions:
    def __init__(self, error: Exception, *, sync: bool = False):
        self.error = error
        self.sync = sync
        self.calls = 0

    def _raise(self):
        self.calls += 1
        raise self.error

    def create(self, **kwargs):
        if self.sync:
            self._raise()

        async def _later():
            self._raise()

        return _later()


def _adapter(comp: _Completions) -> openai_provider.OpenAIClientAdapter:
    client = SimpleNamespace(chat=SimpleNamespace(completions=comp))
    return openai_provider.OpenAIClientAdapter(client)


def _user(text: str):
    from noctusai_lib.integrations.llm.tool_calling import ChatMessage

    return ChatMessage(role="user", content=text)


@pytest.mark.asyncio
@pytest.mark.parametrize("sync", [False, True])
async def test_client_adapter_quota_is_typed(sync):
    """Was a raw `openai.RateLimitError` -> the chat router's opaque 502
    (social-wiring YouTube chat, 2026-10-26)."""
    comp = _Completions(_err("insufficient_quota"), sync=sync)
    with pytest.raises(ProviderQuotaExhausted) as ei:
        await _adapter(comp).chat_with_tools([_user("oi")], [], model="m")
    assert ei.value.status_code == 503
    assert "esgotados" in ei.value.message
    assert isinstance(ei.value.__cause__, openai.RateLimitError)
    assert comp.calls == 1  # the adapter adds no retry loop


@pytest.mark.asyncio
async def test_client_adapter_other_sdk_error_is_llm_api_error():
    comp = _Completions(_err("rate_limit_exceeded", "requests"))
    with pytest.raises(LLMAPIError) as ei:
        await _adapter(comp).chat_with_tools([_user("oi")], [], model="m")
    assert not isinstance(ei.value, ProviderQuotaExhausted)
