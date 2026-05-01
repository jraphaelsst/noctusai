"""
LLMProvider Protocol — the contract every provider implements.

A Provider is a stateless adapter between the shared LLM API (chat,
embeddings, audio, vision) and one vendor's SDK (OpenAI, Anthropic, Gemini).
Providers do **not** hold API keys — keys are passed per call by the
high-level `noctusai_lib.llm` entry points, which resolve them via
`LLMConfig.key_provider(provider_name, org_id)`.

Why stateless: one Provider instance can serve requests for any org. An
org's key changes don't require recycling the provider. A single connection
pool is shared across all tenants.

Providers raise:
  - `LLMNotConfigured`     when the passed api_key is empty
  - `LLMAPIError`          when the vendor's API returns an error
  - `ProviderNotImplemented` when a stub method is called without the dev flag

Every provider also implements `close()` so the framework's lifespan
shutdown can release pooled connections cleanly.
"""
from __future__ import annotations

from typing import Any, AsyncIterator, Optional, Protocol, Union, runtime_checkable


@runtime_checkable
class LLMProvider(Protocol):
    """Protocol all providers implement. See module docstring for the rules."""

    name: str  # e.g. "openai", "anthropic", "gemini", "fake"

    async def chat_completion(
        self,
        messages: list[dict],
        *,
        model: str,
        api_key: str,
        temperature: float = 1.0,
        max_tokens: Optional[int] = None,
        response_format: Optional[dict] = None,
        **kwargs: Any,
    ) -> str:
        """Send a chat completion request. Returns the assistant message text."""
        ...

    async def generate_embedding(
        self,
        text: str,
        *,
        model: str,
        api_key: str,
        **kwargs: Any,
    ) -> list[float]:
        """Return a single embedding vector for the given text."""
        ...

    async def transcribe_audio(
        self,
        audio: bytes,
        *,
        model: str,
        api_key: str,
        **kwargs: Any,
    ) -> str:
        """Transcribe raw audio bytes to text."""
        ...

    async def analyze_image(
        self,
        image: Union[bytes, str],
        prompt: str,
        *,
        model: str,
        api_key: str,
        **kwargs: Any,
    ) -> str:
        """Analyze an image (bytes or URL) against a text prompt.

        Returns the model's textual response.
        """
        ...

    async def close(self) -> None:
        """Release any pooled connections / resources. Called on app shutdown."""
        ...

    # Streaming — optional per provider. The high-level `chat_completion_stream`
    # raises `NotImplementedError` if a provider's method is absent. Providers
    # return an async iterator of string chunks (delta text only, not cumulative).
    # Implementations may ignore `response_format` or translate it to their
    # provider-specific format.
    def chat_completion_stream(
        self,
        messages: list[dict],
        *,
        model: str,
        api_key: str,
        temperature: float = 1.0,
        max_tokens: Optional[int] = None,
        response_format: Optional[dict] = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        ...
