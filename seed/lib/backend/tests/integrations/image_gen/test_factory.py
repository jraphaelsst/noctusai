"""get_image_gen_adapter — picks Fake vs Real from key_provider resolution."""

import pytest

from noctusai_lib.integrations.image_gen import (
    FakeImageGenAdapter,
    GeminiImageGenAdapter,
    get_image_gen_adapter,
)


def test_no_key_provider_returns_fake() -> None:
    adapter = get_image_gen_adapter()
    assert isinstance(adapter, FakeImageGenAdapter)
    assert adapter.backend == "fake"


def test_key_provider_returning_none_returns_fake() -> None:
    adapter = get_image_gen_adapter(key_provider=lambda org_id=None: None)
    assert isinstance(adapter, FakeImageGenAdapter)


def test_key_provider_returning_empty_string_returns_fake() -> None:
    adapter = get_image_gen_adapter(key_provider=lambda org_id=None: "")
    assert isinstance(adapter, FakeImageGenAdapter)


def test_key_provider_returning_real_key_returns_gemini() -> None:
    captured: list[str | None] = []

    def key_provider(org_id: str | None = None) -> str:
        captured.append(org_id)
        return "test-api-key"

    adapter = get_image_gen_adapter(key_provider=key_provider, org_id="org-1")
    assert isinstance(adapter, GeminiImageGenAdapter)
    assert adapter.backend == "gemini"
    assert captured == ["org-1"]


def test_unsupported_backend_raises() -> None:
    with pytest.raises(ValueError, match="Unsupported image-gen backend"):
        get_image_gen_adapter(
            key_provider=lambda org_id=None: "k",
            backend="stability",
            org_id="org-1",
        )


def test_gemini_adapter_requires_non_empty_key() -> None:
    with pytest.raises(ValueError, match="non-empty api_key"):
        GeminiImageGenAdapter("")


def test_gemini_adapter_construction_does_not_import_sdk() -> None:
    # Construction is lazy — does NOT import google-genai (the SDK may
    # be absent in slim test environments). Only generate(...) imports.
    adapter = GeminiImageGenAdapter("test-key", model="imagen-3.0-generate-001")
    assert adapter.backend == "gemini"
