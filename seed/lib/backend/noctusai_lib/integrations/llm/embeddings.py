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


async def generate_embeddings_batch(
    texts: list[str],
    *,
    model: Optional[str] = None,
    provider: Optional[str] = None,
    org_id: Optional[str] = None,
    **kwargs: Any,
) -> list[list[float]]:
    """Generate embedding vectors for MANY texts in as few provider
    round-trips as possible — the fix for the self-inflicted retry-storm a
    per-chunk `generate_embedding()` loop causes (508 chunks → 508 HTTP
    requests → 507 429-retries even though the account/provider was healthy
    the whole time; the embeddings endpoint accepts an array `input`).

    Providers that implement `generate_embeddings_batch` (OpenAI: one
    `/embeddings` call, `input=texts`) get ONE HTTP request for the whole
    list. Providers that don't (no native batch support wired yet) degrade
    to one `generate_embedding` call per text — same provider resolution,
    same result shape, just without the round-trip win. Callers never need
    to special-case by provider.

    Order-preserving: `result[i]` is the embedding for `texts[i]`.
    Returns `[]` for empty `texts` without making any call.

    Raises the same exceptions as `generate_embedding` (`LLMNotConfigured`,
    `LLMAPIError`, `ProviderNotImplemented`) — a batch call is atomic at the
    provider boundary: it fails or succeeds as a whole, never partially.
    """
    if not texts:
        return []
    config = get_llm_config()
    effective_provider = provider or config.default_provider
    effective_model = model or config.default_embedding_model
    api_key = resolve_api_key(effective_provider, org_id)

    prov = get_provider(effective_provider)
    batch_fn = getattr(prov, "generate_embeddings_batch", None)
    if batch_fn is not None:
        return await batch_fn(
            texts,
            model=effective_model,
            api_key=api_key,
            org_id=org_id,
            **kwargs,
        )
    # Fallback for a provider without native batch support: preserve the
    # funnel + result contract, just without the request-count win.
    return [
        await prov.generate_embedding(
            text, model=effective_model, api_key=api_key, org_id=org_id, **kwargs
        )
        for text in texts
    ]
