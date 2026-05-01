"""
High-level embedding entry point.

Services call `generate_embedding(...)` — never a provider directly. Mirrors
`chat_completion`'s dispatch + key-resolution pattern so product code stays
uniform across modalities.
"""
from __future__ import annotations

from typing import Any, Optional

from .client import get_llm_config, get_provider, resolve_api_key


async def generate_embedding(
    text: str,
    *,
    model: Optional[str] = None,
    provider: Optional[str] = None,
    org_id: Optional[str] = None,
    **kwargs: Any,
) -> list[float]:
    """Generate an embedding vector via the configured provider.

    Args:
        text: The text to embed.
        model: Override the provider's embedding model. Defaults to
            `LLMConfig.default_embedding_model`.
        provider: Override the active provider. Defaults to
            `LLMConfig.default_provider`.
        org_id: Scope the key resolution to a specific org.
        **kwargs: Forwarded to the provider.

    Returns:
        The embedding as a list of floats. Dimensionality depends on the
        model (OpenAI text-embedding-3-small = 1536, -large = 3072, etc.).

    Raises:
        LLMNotConfigured: API key missing.
        LLMAPIError: Downstream provider error.
        ProviderNotImplemented: Stub provider without dev flag set.
    """
    config = get_llm_config()
    effective_provider = provider or config.default_provider
    effective_model = model or config.default_embedding_model
    api_key = resolve_api_key(effective_provider, org_id)

    prov = get_provider(effective_provider)
    return await prov.generate_embedding(
        text,
        model=effective_model,
        api_key=api_key,
        org_id=org_id,
        **kwargs,
    )
