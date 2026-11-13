"""A provider override without a model gets that provider's own vision model.

Before 2026-11-13, `analyze_image(provider="anthropic")` sent
`LLMConfig.default_vision_model` (``gpt-4o``, an OpenAI id) to Anthropic, so
the per-org `llm_vision_provider` switch could never actually move vision off
OpenAI without every caller also pinning a model.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from noctusai_lib.integrations.llm.model_policy import resolve_model
from noctusai_lib.integrations.llm.vision import _vision_model

_CONFIG = SimpleNamespace(default_provider="openai", default_vision_model="gpt-4o")


def test_explicit_model_always_wins():
    assert _vision_model(_CONFIG, "anthropic", "claude-x") == "claude-x"


def test_default_provider_keeps_the_config_default():
    assert _vision_model(_CONFIG, "openai", None) == "gpt-4o"


def test_other_provider_gets_its_native_standard_model():
    expected = resolve_model("anthropic", "extract")
    assert expected is not None and expected.startswith("claude-")
    assert _vision_model(_CONFIG, "anthropic", None) == expected


def test_provider_without_a_routable_model_raises():
    with pytest.raises(ValueError, match="No routable vision model"):
        _vision_model(_CONFIG, "no-such-vendor", None)
