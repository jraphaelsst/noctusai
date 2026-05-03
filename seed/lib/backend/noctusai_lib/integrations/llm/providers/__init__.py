"""LLM provider implementations.

Importing this subpackage side-effects the registration of OpenAI, Anthropic,
and Gemini with `noctusai_lib.llm.registry`. `FakeProvider` is deliberately
NOT registered — tests wire it in via `LLMConfig` override so production
code paths can't accidentally hit it.
"""
# Side-effect imports — each module calls `register()` at module scope.
from . import anthropic_provider  # noqa: F401
from . import gemini_provider  # noqa: F401
from . import openai_provider  # noqa: F401
from .base import LLMProvider
from .fake_provider import FakeProvider

__all__ = ["LLMProvider", "FakeProvider"]
