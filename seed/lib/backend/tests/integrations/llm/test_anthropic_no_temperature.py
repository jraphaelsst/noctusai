"""Anthropic provider — the current SDK dropped sampling-temperature control.

`AsyncMessages.create`/`.stream` on `anthropic` 1.x (our `anthropic>=0.40.0`
pin resolves 1.5.0 in the running prod image) accept neither `temperature`
nor `top_p` — forwarding either raises `TypeError` before any request
reaches the network. Because `chat_completion`/`chat_completion_stream`
forwarded `temperature=temperature` unconditionally, every Anthropic chat
call in prod failed this way since at least 2026-09-10: certidões AI
analysis, structured extraction, email marketing, media creation, digest —
every feature routed through the Anthropic provider. Prod rows stored the
`TypeError` string as the "analysis".

These tests assert the provider drops `temperature`/`top_p` before ever
reaching the SDK — both the named `temperature=` argument every caller
already passes, and a `top_p`/`temperature` smuggled through `**kwargs` —
while keeping its own public signature unchanged, so no caller needs to
change. `TestSdkContractGuard` is the regression guard for the NEXT SDK
change: it fails HERE, at test time, if `AsyncMessages.create`/`.stream`
ever stop accepting a keyword this provider actually sends — instead of
failing silently in prod with a bare `TypeError` traceback, which is
exactly how this defect first shipped.
"""
from __future__ import annotations

import inspect

import pytest
from anthropic.resources.messages import AsyncMessages

from noctusai_lib.integrations.llm.providers.anthropic_provider import (
    AnthropicProvider,
)


class _FakeContentBlock:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeUsage:
    def __init__(self, input_tokens: int = 10, output_tokens: int = 5) -> None:
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class _FakeMessage:
    """Mimics the SDK's `Message` response shape (`.content`, `.usage`)."""

    def __init__(self, text: str = "olá") -> None:
        self.content = [_FakeContentBlock(text)]
        self.usage = _FakeUsage()


class _FakeStreamContext:
    """Mimics `async with client.messages.stream(...) as stream:`.

    `.text_stream` must be re-iterable-looking (an async generator instance
    freshly produced on each attribute access), exactly like the real SDK's
    property.
    """

    def __init__(self, chunks: list[str], final_message: _FakeMessage) -> None:
        self._chunks = chunks
        self._final_message = final_message

    async def __aenter__(self) -> "_FakeStreamContext":
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    async def _gen(self):
        for chunk in self._chunks:
            yield chunk

    @property
    def text_stream(self):
        return self._gen()

    async def get_final_message(self) -> _FakeMessage:
        return self._final_message


class _FakeMessages:
    """Records exactly what the provider sent, standing in for
    `client.messages` (the `AsyncMessages` resource)."""

    def __init__(self, response=None, stream_ctx=None) -> None:
        self._response = response
        self._stream_ctx = stream_ctx
        self.create_kwargs: dict | None = None
        self.stream_kwargs: dict | None = None

    async def create(self, **kwargs):
        self.create_kwargs = kwargs
        return self._response

    def stream(self, **kwargs):
        self.stream_kwargs = kwargs
        return self._stream_ctx


class _FakeClient:
    def __init__(self, messages: _FakeMessages) -> None:
        self.messages = messages


def _provider(messages: _FakeMessages) -> tuple[AnthropicProvider, _FakeClient]:
    p = AnthropicProvider()
    client = _FakeClient(messages)
    # DI via the provider's own client seam — the same pattern
    # `test_gemini_embeddings.py` uses for `GeminiProvider._get_client`.
    p._client_for = lambda _key: client  # type: ignore[method-assign]
    return p, client


class TestChatCompletionDropsTemperature:
    @pytest.mark.asyncio
    async def test_named_temperature_is_not_forwarded(self):
        messages = _FakeMessages(response=_FakeMessage("hello"))
        p, _ = _provider(messages)

        result = await p.chat_completion(
            [{"role": "user", "content": "hi"}],
            model="claude-x",
            api_key="k",
            temperature=0.0,
        )

        assert messages.create_kwargs is not None
        assert "temperature" not in messages.create_kwargs
        assert "top_p" not in messages.create_kwargs
        # The response text still comes through — dropping temperature must
        # not change any other behaviour.
        assert result == "hello"

    @pytest.mark.asyncio
    async def test_kwargs_temperature_and_top_p_are_dropped(self):
        """A caller passing `top_p` (not in the named signature) goes
        through `**kwargs` — the smuggled-in case the guard also covers."""
        messages = _FakeMessages(response=_FakeMessage("hi"))
        p, _ = _provider(messages)

        await p.chat_completion(
            [{"role": "user", "content": "hi"}],
            model="claude-x",
            api_key="k",
            temperature=0.2,
            top_p=0.5,
        )

        assert "temperature" not in messages.create_kwargs
        assert "top_p" not in messages.create_kwargs


class TestChatCompletionStreamDropsTemperature:
    @pytest.mark.asyncio
    async def test_named_temperature_is_not_forwarded(self):
        stream_ctx = _FakeStreamContext(["ola", " mundo"], _FakeMessage("ola mundo"))
        messages = _FakeMessages(stream_ctx=stream_ctx)
        p, _ = _provider(messages)

        chunks = [
            chunk
            async for chunk in p.chat_completion_stream(
                [{"role": "user", "content": "hi"}],
                model="claude-x",
                api_key="k",
                temperature=0.9,
            )
        ]

        assert chunks == ["ola", " mundo"]
        assert messages.stream_kwargs is not None
        assert "temperature" not in messages.stream_kwargs
        assert "top_p" not in messages.stream_kwargs

    @pytest.mark.asyncio
    async def test_kwargs_top_p_is_dropped(self):
        stream_ctx = _FakeStreamContext(["x"], _FakeMessage("x"))
        messages = _FakeMessages(stream_ctx=stream_ctx)
        p, _ = _provider(messages)

        async for _ in p.chat_completion_stream(
            [{"role": "user", "content": "hi"}],
            model="claude-x",
            api_key="k",
            top_p=0.3,
        ):
            pass

        assert "top_p" not in messages.stream_kwargs


class TestSdkContractGuard:
    """Fails HERE, at test time, the next time the Anthropic SDK's Messages
    API changes shape — instead of in prod. Validates against the REALLY
    INSTALLED `anthropic` package's signature (not a hardcoded parameter
    list), so a future SDK bump that removes/renames anything else this
    provider sends is caught automatically.
    """

    @pytest.mark.asyncio
    async def test_every_kwarg_sent_to_create_is_in_the_installed_sdk_signature(self):
        messages = _FakeMessages(response=_FakeMessage("hi"))
        p, _ = _provider(messages)

        await p.chat_completion(
            [
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "hi"},
            ],
            model="claude-x",
            api_key="k",
            temperature=0.0,
            max_tokens=100,
        )

        sig_params = set(inspect.signature(AsyncMessages.create).parameters)
        sent = set(messages.create_kwargs)
        unsupported = sent - sig_params
        assert not unsupported, (
            f"anthropic_provider.chat_completion sends {unsupported}, which "
            "the installed anthropic SDK's AsyncMessages.create does not "
            "accept — this is the exact shape of the 2026-09-14 prod defect."
        )

    @pytest.mark.asyncio
    async def test_every_kwarg_sent_to_stream_is_in_the_installed_sdk_signature(self):
        stream_ctx = _FakeStreamContext(["x"], _FakeMessage("x"))
        messages = _FakeMessages(stream_ctx=stream_ctx)
        p, _ = _provider(messages)

        async for _ in p.chat_completion_stream(
            [{"role": "user", "content": "hi"}],
            model="claude-x",
            api_key="k",
            temperature=0.0,
        ):
            pass

        sig_params = set(inspect.signature(AsyncMessages.stream).parameters)
        sent = set(messages.stream_kwargs)
        unsupported = sent - sig_params
        assert not unsupported, (
            f"anthropic_provider.chat_completion_stream sends {unsupported}, "
            "which the installed anthropic SDK's AsyncMessages.stream does "
            "not accept — this is the exact shape of the 2026-09-14 prod "
            "defect."
        )
