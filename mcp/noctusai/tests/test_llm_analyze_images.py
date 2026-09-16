"""S2 — `analyze_images` (multi-image, strict JSON schema) tests.

Covers:
  - `OpenAIProvider.analyze_images` request shape (one content block per
    image, Structured Outputs `response_format`) and error handling — no
    network, mocked `AsyncOpenAI` client via the same DI seam
    `TestOpenAIProviderBatchEmbedding` uses in `test_llm_providers.py`
    (`monkeypatch.setattr(provider, "_client_for", ...)`, an explicit
    injected collaborator, not a self-patch of our own module).
  - The high-level `noctusai_lib.integrations.llm.vision.analyze_images`
    dispatcher: routes to a provider's native method when present, raises
    `NotImplementedError` (no safe generic fallback exists) when absent.

Kept in its own file rather than added to `test_llm_providers.py` /
`test_llm_foundation.py`: see this dispatch's `drift-found:` footer.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

from noctusai_lib.testing.conftest_helpers import restore_real_llm_providers

_LIB = Path(__file__).resolve().parents[3] / "seed" / "lib" / "backend"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))


# ── OpenAIProvider.analyze_images — multi-image, strict JSON schema ────────


class _FakeChatMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeChatChoice:
    def __init__(self, content: str) -> None:
        self.message = _FakeChatMessage(content)


class _FakeChatResponse:
    def __init__(
        self,
        content: str,
        usage=None,
        model: str = "gpt-image-2.5-sunburst-2026-09-08",
    ) -> None:
        self.choices = [_FakeChatChoice(content)]
        self.usage = usage
        self.model = model


class TestOpenAIProviderAnalyzeImages:
    def _provider_with_mock_client(self, monkeypatch, response):
        """An OpenAIProvider whose `_client_for` returns a stub client with a
        mocked `chat.completions.create` — no network, no real API key
        needed. Same seam as `TestOpenAIProviderBatchEmbedding`."""
        from unittest.mock import AsyncMock, MagicMock
        from noctusai_lib.integrations.llm.providers.openai_provider import OpenAIProvider

        provider = OpenAIProvider()
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=response)
        monkeypatch.setattr(provider, "_client_for", lambda api_key: mock_client)
        return provider, mock_client

    def test_one_content_block_per_image_plus_strict_schema(self, monkeypatch):
        import json

        response = _FakeChatResponse(json.dumps({"same_property": True}))
        provider, mock_client = self._provider_with_mock_client(monkeypatch, response)
        schema = {
            "type": "object",
            "properties": {"same_property": {"type": "boolean"}},
            "required": ["same_property"],
        }
        result = asyncio.run(
            provider.analyze_images(
                [b"img-a", "https://example.com/img-b.jpg"],
                "Are these the same property?",
                response_schema=schema,
                model="gpt-image-2.5-sunburst",
                api_key="sk-x",
            )
        )
        assert result == {"same_property": True}
        assert mock_client.chat.completions.create.await_count == 1
        call_kwargs = mock_client.chat.completions.create.await_args.kwargs
        content = call_kwargs["messages"][0]["content"]
        # 1 text block + 2 image blocks (one bytes-encoded, one URL passthrough)
        assert [c["type"] for c in content] == ["text", "image_url", "image_url"]
        assert content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
        assert content[2]["image_url"]["url"] == "https://example.com/img-b.jpg"
        rf = call_kwargs["response_format"]
        assert rf["type"] == "json_schema"
        assert rf["json_schema"]["strict"] is True
        assert rf["json_schema"]["schema"] == schema

    def test_invalid_json_response_raises_llm_api_error(self, monkeypatch):
        """Structured Outputs mode SHOULD prevent this, but the provider
        must never trust that blindly."""
        from noctusai_lib.integrations.llm import LLMAPIError

        response = _FakeChatResponse("not json")
        provider, _client = self._provider_with_mock_client(monkeypatch, response)
        with pytest.raises(LLMAPIError):
            asyncio.run(
                provider.analyze_images(
                    [b"img"], "describe", response_schema={"type": "object"},
                    model="gpt-image-2.5-sunburst", api_key="k",
                )
            )

    def test_openai_error_wrapped_as_llm_api_error(self, monkeypatch):
        from unittest.mock import AsyncMock, MagicMock
        from openai import APIError
        from noctusai_lib.integrations.llm import LLMAPIError
        from noctusai_lib.integrations.llm.providers.openai_provider import OpenAIProvider

        provider = OpenAIProvider()
        mock_client = MagicMock()
        boom = APIError("rate limited", request=MagicMock(), body=None)
        mock_client.chat.completions.create = AsyncMock(side_effect=boom)
        monkeypatch.setattr(provider, "_client_for", lambda api_key: mock_client)
        with pytest.raises(LLMAPIError):
            asyncio.run(
                provider.analyze_images(
                    [b"img"], "describe", response_schema={"type": "object"},
                    model="m", api_key="k",
                )
            )

    def test_usage_recorded_with_model_version(self, monkeypatch):
        """Real seam, not a self-patch: `record_usage` reads the ACTIVE
        `LLMConfig.usage_sink` at call time via `get_llm_config()`, so
        installing a real `InMemoryUsageSink` through `configure_llm` and
        reading it back afterwards exercises the genuine code path — no
        `usage.record_usage` monkeypatch needed."""
        class _FakeUsage:
            prompt_tokens = 100
            completion_tokens = 10
            total_tokens = 110

        import json

        from noctusai_lib.integrations.llm import InMemoryUsageSink, LLMConfig
        from noctusai_lib.integrations.llm.client import _reset_for_testing, configure_llm

        response = _FakeChatResponse(
            json.dumps({"ok": True}),
            usage=_FakeUsage(),
            model="gpt-image-2.5-sunburst-2026-09-08",
        )
        provider, _client = self._provider_with_mock_client(monkeypatch, response)

        _reset_for_testing()
        sink = InMemoryUsageSink()
        configure_llm(LLMConfig(
            key_provider=lambda p, org_id=None: "sk-test",
            usage_sink=sink,
        ))
        try:
            asyncio.run(
                provider.analyze_images(
                    [b"img"], "describe", response_schema={"type": "object"},
                    model="gpt-image-2.5-sunburst", api_key="k", org_id="org-1",
                )
            )
        finally:
            restore_real_llm_providers()

        assert len(sink.events) == 1
        event = sink.events[0]
        assert event.model_version == "gpt-image-2.5-sunburst-2026-09-08"
        assert event.operation == "vision"
        assert event.org_id == "org-1"


# ── High-level `analyze_images` dispatcher ──────────────────────────────────
#
# Follows the same real-plumbing seam `test_llm_providers.py`'s
# `TestGenerateEmbeddingsBatchDispatcher` established: `register()` a
# test-owned provider class + `configure_llm()` — no monkeypatching of our
# own `get_provider`/`analyze_images` code.


class _ScriptedAnalyzeImagesProvider:
    """Registered test provider WITH `analyze_images`."""

    calls: list[dict] = []

    @classmethod
    def reset(cls) -> None:
        cls.calls = []

    async def analyze_images(
        self, images, prompt, *, response_schema, model, api_key, org_id=None, **kwargs
    ):
        type(self).calls.append(
            {"images": list(images), "prompt": prompt, "schema": response_schema}
        )
        return {"ok": True}

    async def close(self) -> None:  # pragma: no cover — cleanup
        return None


class _NoAnalyzeImagesProvider:
    """Registered test provider WITHOUT `analyze_images` — the no-fallback path."""

    async def close(self) -> None:  # pragma: no cover — cleanup
        return None


@pytest.fixture
def scripted_analyze_images_provider():
    from noctusai_lib.integrations.llm.client import _provider_cache, configure_llm
    from noctusai_lib.integrations.llm.config import LLMConfig
    from noctusai_lib.integrations.llm.registry import register

    _ScriptedAnalyzeImagesProvider.reset()
    register("scriptedanalyzeimages", _ScriptedAnalyzeImagesProvider)
    configure_llm(
        LLMConfig(
            key_provider=lambda provider, org_id=None: "test-key",
            default_provider="scriptedanalyzeimages",
        )
    )
    yield _ScriptedAnalyzeImagesProvider
    _provider_cache.clear()
    # Clearing the CACHE is not clearing the REGISTRY: the test provider
    # stays registered process-wide. See `restore_real_llm_providers`.
    restore_real_llm_providers()


@pytest.fixture
def no_analyze_images_provider():
    from noctusai_lib.integrations.llm.client import _provider_cache, configure_llm
    from noctusai_lib.integrations.llm.config import LLMConfig
    from noctusai_lib.integrations.llm.registry import register

    register("noanalyzeimages", _NoAnalyzeImagesProvider)
    configure_llm(
        LLMConfig(
            key_provider=lambda provider, org_id=None: "test-key",
            default_provider="noanalyzeimages",
        )
    )
    yield _NoAnalyzeImagesProvider
    _provider_cache.clear()
    restore_real_llm_providers()


class TestAnalyzeImagesDispatcher:
    def test_routes_to_provider_native_method(self, scripted_analyze_images_provider):
        from noctusai_lib.integrations.llm import analyze_images

        schema = {"type": "object"}
        result = asyncio.run(analyze_images([b"a", b"b"], "compare", response_schema=schema))
        assert result == {"ok": True}
        assert scripted_analyze_images_provider.calls == [
            {"images": [b"a", b"b"], "prompt": "compare", "schema": schema}
        ]

    def test_raises_not_implemented_when_provider_lacks_it(self, no_analyze_images_provider):
        from noctusai_lib.integrations.llm import analyze_images

        with pytest.raises(NotImplementedError):
            asyncio.run(analyze_images([b"a"], "describe", response_schema={"type": "object"}))
