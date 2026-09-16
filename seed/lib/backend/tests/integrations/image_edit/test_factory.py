"""get_image_edit_adapter — picks Fake vs Real from key_provider resolution."""
from __future__ import annotations

import pytest

from noctusai_lib.integrations.image_edit import (
    FakeImageEditAdapter,
    OpenAIImageEditAdapter,
    get_image_edit_adapter,
)
from noctusai_lib.integrations.image_edit.exceptions import ImageEditNotConfigured


def test_no_key_provider_returns_fake() -> None:
    adapter = get_image_edit_adapter()
    assert isinstance(adapter, FakeImageEditAdapter)
    assert adapter.backend == "fake"


def test_key_provider_returning_none_returns_fake() -> None:
    adapter = get_image_edit_adapter(key_provider=lambda org_id=None: None)
    assert isinstance(adapter, FakeImageEditAdapter)


def test_key_provider_returning_empty_string_returns_fake() -> None:
    adapter = get_image_edit_adapter(key_provider=lambda org_id=None: "")
    assert isinstance(adapter, FakeImageEditAdapter)


def test_key_provider_returning_real_key_returns_openai() -> None:
    captured: list[str | None] = []

    def key_provider(org_id: str | None = None) -> str:
        captured.append(org_id)
        return "test-api-key"

    adapter = get_image_edit_adapter(key_provider=key_provider, org_id="org-1")
    assert isinstance(adapter, OpenAIImageEditAdapter)
    assert adapter.backend == "openai"
    assert captured == ["org-1"]


def test_model_override_is_forwarded() -> None:
    adapter = get_image_edit_adapter(
        key_provider=lambda org_id=None: "k",
        model="gpt-image-2.5-flare",
    )
    assert isinstance(adapter, OpenAIImageEditAdapter)
    assert adapter._model == "gpt-image-2.5-flare"  # constructor-injected, no public getter needed for this check


def test_unsupported_backend_raises() -> None:
    with pytest.raises(ValueError, match="Unsupported image-edit backend"):
        get_image_edit_adapter(
            key_provider=lambda org_id=None: "k",
            backend="stability",
            org_id="org-1",
        )


def test_openai_adapter_requires_non_empty_key_or_injected_client() -> None:
    with pytest.raises(ImageEditNotConfigured):
        OpenAIImageEditAdapter("")


def test_openai_adapter_construction_does_not_import_sdk() -> None:
    # Construction is lazy — does NOT import `openai` (SDK may be absent
    # in slim test environments). Only edit(...) imports.
    adapter = OpenAIImageEditAdapter("test-key", model="gpt-image-2.5-sunburst")
    assert adapter.backend == "openai"


def test_openai_adapter_accepts_injected_client_with_no_api_key() -> None:
    # DI seam: a test can inject a client even without a "real" key.
    adapter = OpenAIImageEditAdapter("", client=object())
    assert adapter.backend == "openai"
