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


async def analyze_images(
    images: list[Union[bytes, str]],
    prompt: str,
    *,
    response_schema: dict,
    model: Optional[str] = None,
    provider: Optional[str] = None,
    org_id: Optional[str] = None,
    **kwargs: Any,
) -> dict:
    """Analyze MULTIPLE images together against a text prompt, constrained
    to a caller-supplied strict JSON schema.

    Unlike `analyze_image` (one image, free-text answer), this reasons over
    the whole `images` set in one call and returns a dict guaranteed to
    conform to `response_schema` — the shape S3b's image_edit organ (and
    any future multi-image structured-extraction consumer) needs to compare/
    align several images without hand-parsing free text.

    `analyze_images` is OPTIONAL per provider (duck-typed exactly like
    `generate_embeddings_batch`) because there is no safe generic fallback:
    looping `analyze_image` per image and merging the results would not
    satisfy a schema describing ONE structured object across the whole set.
    A provider without it raises `NotImplementedError` rather than silently
    degrading to a wrong shape.

    Args:
        images: Raw image bytes or URL strings, one content block each.
        prompt: The text prompt describing what to extract / analyze.
        response_schema: The bare JSON Schema `schema` object the response
            must conform to (no outer `{"type": "json_schema", ...}`
            envelope — the provider builds that).
        model: Override the vision model. Defaults to `LLMConfig.default_vision_model`.
        provider: Override the active provider.
        org_id: Scope the key resolution to a specific org.
        **kwargs: Forwarded to the provider (e.g. `schema_name`).

    Returns:
        The parsed JSON response as a dict.

    Raises:
        LLMNotConfigured: API key missing.
        LLMAPIError: Downstream error, or an invalid JSON response.
        NotImplementedError: the active provider doesn't implement
            `analyze_images`.
    """
    config = get_llm_config()
    effective_provider = provider or config.default_provider
    effective_model = model or config.default_vision_model
    api_key = resolve_api_key(effective_provider, org_id)

    prov = get_provider(effective_provider)
    fn = getattr(prov, "analyze_images", None)
    if fn is None:
        raise NotImplementedError(
            f"Provider {effective_provider!r} does not implement analyze_images()."
        )
    return await fn(
        images,
        prompt,
        response_schema=response_schema,
        model=effective_model,
        api_key=api_key,
        org_id=org_id,
        **kwargs,
    )
