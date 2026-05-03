"""
High-level image analysis (vision) entry point.

Wraps the active provider's `analyze_image`. `image` accepts either raw
bytes (the provider encodes to data URL) or a URL string the provider
fetches directly.
"""
from __future__ import annotations

from typing import Any, Optional, Union

from .client import get_llm_config, get_provider, resolve_api_key


async def analyze_image(
    image: Union[bytes, str],
    prompt: str,
    *,
    model: Optional[str] = None,
    provider: Optional[str] = None,
    org_id: Optional[str] = None,
    **kwargs: Any,
) -> str:
    """Analyze an image against a text prompt via the configured provider.

    Args:
        image: Raw image bytes or a URL string.
        prompt: The text prompt describing what to extract / analyze.
        model: Override the vision model. Defaults to `LLMConfig.default_vision_model`.
        provider: Override the active provider.
        org_id: Scope the key resolution to a specific org.
        **kwargs: Forwarded to the provider.

    Returns:
        The model's textual response.

    Raises:
        LLMNotConfigured: API key missing.
        LLMAPIError: Downstream error.
        ProviderNotImplemented: Stub provider without dev flag set.
    """
    config = get_llm_config()
    effective_provider = provider or config.default_provider
    effective_model = model or config.default_vision_model
    api_key = resolve_api_key(effective_provider, org_id)

    prov = get_provider(effective_provider)
    return await prov.analyze_image(
        image,
        prompt,
        model=effective_model,
        api_key=api_key,
        org_id=org_id,
        **kwargs,
    )
