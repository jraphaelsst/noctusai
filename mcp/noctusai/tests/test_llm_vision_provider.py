"""`llm.vision.analyze` routes to Anthropic by default and self-configures the LLM.

Two regressions this pins (2026-11-13):
- the MCP server never called `configure_llm`, so the tool always raised
  "LLM not configured" (the funnel must satisfy its own precondition);
- the owner chose Anthropic for vision; the shared `llm_vision_provider`
  switch can still move it, and an explicit `provider=` always wins.
"""
from __future__ import annotations

import asyncio
import base64

import pytest


def test_default_is_anthropic_when_switch_unset():
    from tools.llm.vision.analyze import resolve_vision_provider

    assert resolve_vision_provider(None, None, resolver=lambda k, o: None) == "anthropic"


def test_switch_value_is_honoured():
    from tools.llm.vision.analyze import resolve_vision_provider

    seen = {}

    def resolver(key, org_id):
        seen["key"] = key
        return "openai"

    assert resolve_vision_provider(None, "org-1", resolver=resolver) == "openai"
    assert seen["key"] == "llm_vision_provider"


def test_unknown_switch_value_falls_back_to_anthropic():
    from tools.llm.vision.analyze import resolve_vision_provider

    assert resolve_vision_provider(None, None, resolver=lambda k, o: "nope") == "anthropic"


def test_explicit_provider_wins():
    from tools.llm.vision.analyze import resolve_vision_provider

    assert resolve_vision_provider("gemini", None, resolver=lambda k, o: "openai") == "gemini"


def test_tool_configures_llm_before_reaching_the_seed():
    """No patching: an unroutable provider makes the seed refuse at model
    resolution, which happens AFTER `get_llm_config()`. Reaching that refusal
    (instead of "LLM not configured") proves the tool ran the bootstrap."""
    from tools.llm.vision.analyze import AnalyzeInput, analyze

    payload = AnalyzeInput(
        prompt="room?",
        image_base64=base64.b64encode(b"\x89PNG fake").decode(),
        provider="no-such-vendor",
    )
    with pytest.raises(ValueError, match="No routable vision model"):
        asyncio.run(analyze(payload))
