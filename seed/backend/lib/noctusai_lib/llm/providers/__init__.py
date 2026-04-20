"""LLM provider implementations.

Importing this subpackage side-effects the registration of OpenAI, Anthropic,
and Gemini with `noctusai_lib.llm.registry`. `FakeProvider` is deliberately
NOT registered — tests wire it in via `LLMConfig` override so production
code paths can't accidentally hit it.
"""
# Side-effect imports — each module calls `register()` at module scope.
from noctusai_lib.llm.providers import anthropic_provider  # noqa: F401
from noctusai_lib.llm.providers import gemini_provider  # noqa: F401
from noctusai_lib.llm.providers import openai_provider  # noqa: F401
from noctusai_lib.llm.providers.base import LLMProvider
from noctusai_lib.llm.providers.fake_provider import FakeProvider

__all__ = ["LLMProvider", "FakeProvider"]
