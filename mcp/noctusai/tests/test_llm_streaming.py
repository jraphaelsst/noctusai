"""Phase 12 — streaming chat completion tests.

Network-free. Uses FakeProvider with scripted stream responses.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

_LIB = Path(__file__).resolve().parents[3] / "seed" / "backend" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

import noctusai_lib.integrations.llm  # noqa: E402,F401


def _install_fake_with_streams(streams):
    from noctusai_lib.integrations.llm import FakeProvider, LLMConfig
    from noctusai_lib.integrations.llm.client import _reset_for_testing, configure_llm
    from noctusai_lib.integrations.llm.registry import register

    _reset_for_testing()
    fake = FakeProvider(stream_responses=streams)

    class _FakeClass:
        def __new__(cls):
            return fake

    register("openai", _FakeClass)  # type: ignore[arg-type]
    configure_llm(LLMConfig(
        key_provider=lambda p, org_id=None: "sk-test",
        default_provider="openai",
    ))
    return fake


def _restore_real_providers():
    import importlib

    from noctusai_lib.integrations.llm.registry import _reset_for_testing as _reset_reg

    _reset_reg()
    for mod in (
        "noctusai_lib.integrations.llm.providers.openai_provider",
        "noctusai_lib.integrations.llm.providers.anthropic_provider",
        "noctusai_lib.integrations.llm.providers.gemini_provider",
    ):
        importlib.import_module(mod)
        importlib.reload(sys.modules[mod])


# ── High-level dispatch ─────────────────────────────────────────

class TestChatCompletionStream:
    def teardown_method(self):
        _restore_real_providers()

    def test_yields_chunks_in_order(self):
        from noctusai_lib.integrations.llm import chat_completion_stream

        fake = _install_fake_with_streams([["Hello", " ", "world"]])

        async def collect():
            chunks = []
            async for c in chat_completion_stream(
                messages=[{"role": "user", "content": "hi"}],
            ):
                chunks.append(c)
            return chunks

        chunks = asyncio.run(collect())
        assert chunks == ["Hello", " ", "world"]
        # Full call was logged — tests can assert on args
        assert fake.calls[0]["method"] == "chat_completion_stream"

    def test_default_chunk_when_no_scripted_stream(self):
        from noctusai_lib.integrations.llm import chat_completion_stream

        _install_fake_with_streams([])  # no scripted streams

        async def collect():
            out = []
            async for c in chat_completion_stream(
                messages=[{"role": "user", "content": "hi"}],
            ):
                out.append(c)
            return out

        chunks = asyncio.run(collect())
        assert len(chunks) == 1
        assert "FAKE stream" in chunks[0]

    def test_each_call_consumes_one_scripted_stream(self):
        from noctusai_lib.integrations.llm import chat_completion_stream

        fake = _install_fake_with_streams([
            ["A", "B"],
            ["C", "D"],
        ])

        async def run():
            out1 = []
            async for c in chat_completion_stream(
                messages=[{"role": "user", "content": "1"}],
            ):
                out1.append(c)
            out2 = []
            async for c in chat_completion_stream(
                messages=[{"role": "user", "content": "2"}],
            ):
                out2.append(c)
            return out1, out2

        out1, out2 = asyncio.run(run())
        assert out1 == ["A", "B"]
        assert out2 == ["C", "D"]
        assert len(fake.calls) == 2

    def test_cache_kwargs_are_dropped(self):
        """`cache=`, `cache_namespace=`, `prompt_version=` are inert for
        streams. Provider should not see them in its call log."""
        from noctusai_lib.integrations.llm import chat_completion_stream

        fake = _install_fake_with_streams([["x"]])

        async def run():
            async for _ in chat_completion_stream(
                messages=[{"role": "user", "content": "hi"}],
                cache=True,
                cache_namespace="llm",
                prompt_version="v2",
            ):
                pass

        asyncio.run(run())
        # FakeProvider records only its own schema; cache-only kwargs are
        # stripped at dispatch time and never reach the provider.
        recorded = fake.calls[0]
        assert "cache" not in recorded
        assert "cache_namespace" not in recorded
        assert "prompt_version" not in recorded

    def test_provider_without_stream_raises_not_implemented(self):
        """A provider whose `chat_completion_stream` is missing surfaces as
        NotImplementedError at the high-level call site."""
        from noctusai_lib.integrations.llm import LLMConfig, chat_completion_stream
        from noctusai_lib.integrations.llm.client import _reset_for_testing, configure_llm
        from noctusai_lib.integrations.llm.registry import register

        class _NoStreamProvider:
            name = "nostream"

            async def chat_completion(self, messages, **kwargs):
                return "ok"

            async def generate_embedding(self, text, **kwargs):
                return [0.0]

            async def transcribe_audio(self, audio, **kwargs):
                return ""

            async def analyze_image(self, image, prompt, **kwargs):
                return ""

            async def close(self):
                pass

        _reset_for_testing()
        register("nostream", _NoStreamProvider)  # type: ignore[arg-type]
        configure_llm(LLMConfig(
            key_provider=lambda p, org_id=None: "k",
            default_provider="nostream",
        ))

        async def run():
            async for _ in chat_completion_stream(
                messages=[{"role": "user", "content": "hi"}],
            ):
                pass

        with pytest.raises(NotImplementedError):
            asyncio.run(run())
