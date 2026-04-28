"""Phase 4 tests: high-level LLM API + prompt-cache helper.

Every test injects a FakeProvider via LLMConfig — no monkeypatching.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

_LIB = Path(__file__).resolve().parents[3] / "seed" / "backend" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

import noctusai_lib.llm  # noqa: F401,E402


def _install_fake(
    *,
    chat: list[str] | None = None,
    embeddings: list[list[float]] | None = None,
    transcriptions: list[str] | None = None,
    visions: list[str] | None = None,
    provider_name: str = "openai",
    api_key: str = "sk-test",
):
    """Helper: install a FakeProvider as `provider_name` in the registry,
    configure an LLMConfig that routes to it, and return the fake so tests
    can inspect its call log."""
    from noctusai_lib.llm import FakeProvider, LLMConfig
    from noctusai_lib.llm.client import _reset_for_testing, configure_llm
    from noctusai_lib.llm.registry import register

    _reset_for_testing()
    fake = FakeProvider(
        chat_responses=chat,
        embedding_responses=embeddings,
        transcription_responses=transcriptions,
        vision_responses=visions,
    )

    # Re-register the provider name to return the fake instance. Safe: the
    # registry's `register()` idempotently overwrites, and we restore the
    # original class in teardown.
    class _FakeClass:
        def __new__(cls):  # Return the pre-built instance every time.
            return fake

    register(provider_name, _FakeClass)  # type: ignore[arg-type]
    configure_llm(LLMConfig(
        key_provider=lambda p, org_id=None: api_key,
        default_provider=provider_name,
    ))
    return fake


def _restore_real_providers():
    """After each fake-install test, re-import provider modules to restore
    their real register() side-effects."""
    import importlib

    from noctusai_lib.llm.registry import _reset_for_testing as _reset_reg

    _reset_reg()
    for mod in (
        "noctusai_lib.llm.providers.openai_provider",
        "noctusai_lib.llm.providers.anthropic_provider",
        "noctusai_lib.llm.providers.gemini_provider",
    ):
        importlib.import_module(mod)
        importlib.reload(sys.modules[mod])


# ── chat_completion dispatch ────────────────────────────────────

class TestChatCompletion:
    def teardown_method(self):
        _restore_real_providers()

    def test_dispatches_to_configured_provider_and_model(self):
        from noctusai_lib.llm import chat_completion

        fake = _install_fake(chat=["hello"])
        result = asyncio.run(chat_completion(
            messages=[{"role": "user", "content": "hi"}],
        ))
        assert result == "hello"
        assert len(fake.calls) == 1
        call = fake.calls[0]
        assert call["method"] == "chat_completion"
        assert call["model"] == "gpt-4o-mini"  # default from LLMConfig
        assert call["api_key"] == "sk-test"

    def test_model_override_per_call(self):
        from noctusai_lib.llm import chat_completion

        fake = _install_fake(chat=["x"])
        asyncio.run(chat_completion(
            messages=[{"role": "user", "content": "hi"}],
            model="gpt-4o",
        ))
        assert fake.calls[0]["model"] == "gpt-4o"

    def test_org_id_passed_to_key_provider(self):
        from noctusai_lib.llm import LLMConfig, chat_completion
        from noctusai_lib.llm.client import configure_llm

        seen = []
        fake = _install_fake(chat=["x"])
        configure_llm(LLMConfig(
            key_provider=lambda p, org_id=None: (seen.append((p, org_id)) or "sk-x"),
            default_provider="openai",
        ))
        asyncio.run(chat_completion(
            messages=[{"role": "user", "content": "hi"}],
            org_id="org-123",
        ))
        assert seen == [("openai", "org-123")]
        assert fake.calls[0]["api_key"] == "sk-x"

    def test_raises_llm_not_configured_on_empty_key(self):
        from noctusai_lib.llm import (
            LLMConfig,
            LLMNotConfigured,
            chat_completion,
        )
        from noctusai_lib.llm.client import _reset_for_testing, configure_llm

        _reset_for_testing()
        configure_llm(LLMConfig(
            key_provider=lambda p, org_id=None: None,
            default_provider="openai",
        ))
        with pytest.raises(LLMNotConfigured):
            asyncio.run(chat_completion(
                messages=[{"role": "user", "content": "hi"}],
            ))


# ── Embedding / audio / vision dispatch ─────────────────────────

class TestEmbeddingDispatch:
    def teardown_method(self):
        _restore_real_providers()

    def test_dispatches_and_uses_default_model(self):
        from noctusai_lib.llm import generate_embedding

        fake = _install_fake(embeddings=[[0.1, 0.2, 0.3]])
        vec = asyncio.run(generate_embedding("hello"))
        assert vec == [0.1, 0.2, 0.3]
        assert fake.calls[0]["model"] == "text-embedding-3-small"


class TestAudioDispatch:
    def teardown_method(self):
        _restore_real_providers()

    def test_dispatches_and_uses_default_model(self):
        from noctusai_lib.llm import transcribe_audio

        fake = _install_fake(transcriptions=["hello there"])
        text = asyncio.run(transcribe_audio(audio=b"abc"))
        assert text == "hello there"
        assert fake.calls[0]["model"] == "whisper-1"
        assert fake.calls[0]["bytes_len"] == 3


class TestVisionDispatch:
    def teardown_method(self):
        _restore_real_providers()

    def test_dispatches_and_uses_default_model(self):
        from noctusai_lib.llm import analyze_image

        fake = _install_fake(visions=["a dog"])
        result = asyncio.run(
            analyze_image(image=b"\xff\xd8\xff", prompt="describe")
        )
        assert result == "a dog"
        assert fake.calls[0]["model"] == "gpt-4o"
        assert fake.calls[0]["prompt"] == "describe"


# ── build_cached_messages ───────────────────────────────────────

class TestBuildCachedMessages:
    def test_stable_first_dynamic_last(self):
        from noctusai_lib.llm import build_cached_messages

        msgs = build_cached_messages(
            static_system="stable instructions" * 300,
            dynamic_user="per-request content",
            provider="openai",
        )
        assert msgs[0]["role"] == "system"
        assert msgs[-1]["role"] == "user"
        assert msgs[-1]["content"] == "per-request content"

    def test_anthropic_adds_cache_control_to_system(self):
        from noctusai_lib.llm import build_cached_messages

        msgs = build_cached_messages(
            static_system="stable" * 300,
            dynamic_user="dynamic",
            provider="anthropic",
        )
        assert "cache_control" in msgs[0]
        assert msgs[0]["cache_control"] == {"type": "ephemeral"}

    def test_openai_does_not_add_cache_control(self):
        """OpenAI caches automatically — no marker needed / allowed."""
        from noctusai_lib.llm import build_cached_messages

        msgs = build_cached_messages(
            static_system="stable" * 300,
            dynamic_user="dynamic",
            provider="openai",
        )
        assert "cache_control" not in msgs[0]

    def test_extra_static_context_placed_before_user(self):
        from noctusai_lib.llm import build_cached_messages

        examples = [
            {"role": "user", "content": "example user"},
            {"role": "assistant", "content": "example reply"},
        ]
        msgs = build_cached_messages(
            static_system="instructions",
            dynamic_user="the real question",
            extra_static_context=examples,
        )
        # system, example user, example assistant, real user
        assert [m["role"] for m in msgs] == ["system", "user", "assistant", "user"]
        assert msgs[-1]["content"] == "the real question"

    def test_extra_dynamic_messages_after_user(self):
        from noctusai_lib.llm import build_cached_messages

        msgs = build_cached_messages(
            static_system="instructions",
            dynamic_user="q1",
            extra_dynamic_messages=[{"role": "assistant", "content": "a1"}],
        )
        assert msgs[-1]["content"] == "a1"
        assert msgs[-2]["content"] == "q1"

    def test_does_not_mutate_caller_lists(self):
        """Deep-copy of caller-provided messages — mutations in the result
        must not bleed into the caller's references."""
        from noctusai_lib.llm import build_cached_messages

        examples = [{"role": "user", "content": "x"}]
        msgs = build_cached_messages(
            static_system="inst",
            dynamic_user="q",
            extra_static_context=examples,
        )
        msgs[1]["content"] = "mutated"
        assert examples[0]["content"] == "x"

    def test_short_prefix_does_not_raise(self, caplog):
        """A short stable prefix still returns a valid message list — the
        helper only logs a debug message, never raises."""
        import logging

        from noctusai_lib.llm import build_cached_messages

        caplog.set_level(logging.DEBUG, logger="noctusai_lib.llm.chat")
        msgs = build_cached_messages(
            static_system="too short",
            dynamic_user="x",
        )
        assert msgs  # returned successfully
