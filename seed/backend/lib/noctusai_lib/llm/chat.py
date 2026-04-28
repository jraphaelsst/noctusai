"""
High-level chat completion entry point + prompt-cache helper.

Services call `chat_completion(...)` — never a provider directly. The entry
point resolves the active provider from the `LLMConfig` singleton, resolves
the API key via `key_provider(provider, org_id)`, and dispatches to the
provider's `chat_completion()`.

Providers are stateless wrt API keys. The cached provider instance serves
every org — per-call key resolution lets one process handle many tenants.
"""
from __future__ import annotations

import copy
import logging
from typing import Any, AsyncIterator, Optional

from noctusai_lib.llm.budget import enforce_budget
from noctusai_lib.llm.cache import build_cache_key, try_get, try_set
from noctusai_lib.llm.client import get_llm_config, get_provider, resolve_api_key

logger = logging.getLogger(__name__)

# Minimum stable-prefix size (in approximate tokens; 1 token ≈ 4 chars) below
# which neither OpenAI automatic caching nor Anthropic ephemeral caching can
# meaningfully help. The helper warns when the prefix is shorter so authors
# can restructure or accept that caching is inactive for that call.
_MIN_CACHE_PREFIX_CHARS = 1024 * 4


async def chat_completion(
    messages: list[dict],
    *,
    model: Optional[str] = None,
    provider: Optional[str] = None,
    org_id: Optional[str] = None,
    temperature: float = 1.0,
    max_tokens: Optional[int] = None,
    response_format: Optional[dict] = None,
    cache: bool = True,
    **kwargs: Any,
) -> str:
    """Route a chat completion through the configured provider.

    Args:
        messages: Full message list (use `build_cached_messages(...)` to
            structure for prompt caching).
        model: Override the provider's chat model for this call. Defaults to
            `LLMConfig.default_chat_model`.
        provider: Override the active provider name. Defaults to
            `LLMConfig.default_provider`.
        org_id: Scope the key resolution to a specific org (Tier 1 lookup).
        temperature, max_tokens, response_format: Standard OpenAI-shaped
            inference knobs. Gemini / Anthropic providers translate as needed.
        cache: Whether this call is eligible for Phase 8 response caching.
            Set to `False` for non-deterministic prompts or LGPD-protected
            patient data (Therapy clinical flows MUST pass False).
        **kwargs: Forwarded to the provider unchanged.

    Returns:
        The assistant message text.

    Raises:
        LLMNotConfigured: API key missing for the chosen provider.
        LLMAPIError: Downstream provider error.
        ProviderNotImplemented: Stub provider without dev flag set.
    """
    config = get_llm_config()
    effective_provider = provider or config.default_provider
    effective_model = model or config.default_chat_model
    api_key = resolve_api_key(effective_provider, org_id)

    # Phase 18 budget guardrails — raises LLMBudgetExceeded at the org's
    # hard threshold before we hit the provider. Soft-warn just logs.
    # No-op when the budget module isn't configured (tests, dev runs).
    await enforce_budget(org_id)

    # Response-cache consult (Phase 8). Gated by:
    #  - cache=True at the call site (services with patient data pass False).
    #  - LLMConfig.cache_enabled at the platform level.
    #  - temperature == 0 (only deterministic calls are cacheable).
    #  - A configured cache backend.
    cache_key: Optional[str] = None
    cache_ttl = config.default_cache_ttl_chat
    cache_live = (
        cache
        and config.cache_enabled
        and config.cache_backend is not None
        and temperature == 0
    )
    if cache_live:
        prompt_version = str(kwargs.pop("prompt_version", "v1"))
        cache_key = build_cache_key(
            product=kwargs.pop("cache_namespace", "llm"),
            provider=effective_provider,
            model=effective_model,
            prompt_version=prompt_version,
            payload=messages,
            org_id=org_id,
        )
        hit, value = await try_get(config.cache_backend, cache_key)
        if hit and isinstance(value, str):
            return value

    prov = get_provider(effective_provider)
    result = await prov.chat_completion(
        messages,
        model=effective_model,
        api_key=api_key,
        temperature=temperature,
        max_tokens=max_tokens,
        response_format=response_format,
        org_id=org_id,
        **kwargs,
    )

    if cache_live and cache_key is not None:
        await try_set(config.cache_backend, cache_key, result, cache_ttl)

    return result


async def chat_completion_stream(
    messages: list[dict],
    *,
    model: Optional[str] = None,
    provider: Optional[str] = None,
    org_id: Optional[str] = None,
    temperature: float = 1.0,
    max_tokens: Optional[int] = None,
    response_format: Optional[dict] = None,
    **kwargs: Any,
) -> AsyncIterator[str]:
    """Stream a chat completion as an async iterator of text deltas.

    Each yielded string is a **delta** — the new text chunk, not the
    cumulative response. Callers concatenate the chunks as they arrive.

    Response-cache is never consulted for streams: streaming outputs aren't
    stable snapshots and the cache key design is built around whole-response
    storage. The `cache` kwarg is accepted for forward-compat but ignored.

    Raises:
        LLMNotConfigured: key resolution returned None.
        LLMAPIError: downstream provider error at stream open.
        NotImplementedError: the active provider does not support streaming
            (e.g. `FakeProvider` without scripted streams).
    """
    config = get_llm_config()
    effective_provider = provider or config.default_provider
    effective_model = model or config.default_chat_model
    api_key = resolve_api_key(effective_provider, org_id)
    # Drop cache-only kwargs some callers pass — they're inert here.
    kwargs.pop("cache", None)
    kwargs.pop("cache_namespace", None)
    kwargs.pop("prompt_version", None)

    # Phase 18 budget guardrails — same posture as the non-streaming entry.
    await enforce_budget(org_id)

    prov = get_provider(effective_provider)
    stream_fn = getattr(prov, "chat_completion_stream", None)
    if stream_fn is None:
        raise NotImplementedError(
            f"Provider {effective_provider!r} does not implement chat_completion_stream()."
        )

    async for chunk in stream_fn(
        messages,
        model=effective_model,
        api_key=api_key,
        temperature=temperature,
        max_tokens=max_tokens,
        response_format=response_format,
        org_id=org_id,
        **kwargs,
    ):
        yield chunk


def build_cached_messages(
    static_system: str,
    dynamic_user: str,
    *,
    provider: Optional[str] = None,
    extra_static_context: Optional[list[dict]] = None,
    extra_dynamic_messages: Optional[list[dict]] = None,
) -> list[dict]:
    """Structure a message list for maximum prompt-cache hit rate.

    The rule for both OpenAI (automatic) and Anthropic (explicit) is the
    same: **stable content first, dynamic content last.** OpenAI caches the
    longest common prefix across consecutive requests automatically.
    Anthropic requires explicit `cache_control` markers — this helper adds
    them when `provider="anthropic"`.

    Args:
        static_system: The stable system prompt — the part that doesn't
            change between requests. Usually a few hundred to a few thousand
            tokens of instructions, few-shot examples, schema definitions.
        dynamic_user: The per-request user content. The only part that
            changes call to call.
        provider: Which provider's caching rules to apply. Omit to use the
            configured default. Only affects whether Anthropic-style
            cache_control markers are emitted; the stable-first ordering
            applies to every provider.
        extra_static_context: Additional stable messages to cache alongside
            the system prompt (e.g. few-shot assistant/user exchanges).
        extra_dynamic_messages: Additional dynamic messages appended after
            the user content (e.g. a prior assistant turn).

    Returns:
        A messages list ready to pass to `chat_completion(messages=...)`.

    Warns (via logger) when the stable prefix is below ~1024 tokens, since
    neither provider can cache that short.
    """
    from noctusai_lib.llm.client import get_llm_config

    effective_provider = provider
    if effective_provider is None:
        try:
            effective_provider = get_llm_config().default_provider
        except RuntimeError:
            effective_provider = "openai"  # Safe fallback for offline test paths

    total_static_len = len(static_system) + sum(
        len(m.get("content", "")) if isinstance(m.get("content"), str) else 0
        for m in (extra_static_context or [])
    )
    if total_static_len < _MIN_CACHE_PREFIX_CHARS:
        logger.debug(
            "build_cached_messages: static prefix is %d chars (~%d tokens) — "
            "below the ~1024-token threshold for effective prompt caching. "
            "Consider lengthening the system prompt or accepting that caching "
            "will miss on this call.",
            total_static_len,
            total_static_len // 4,
        )

    system_message: dict = {"role": "system", "content": static_system}
    if effective_provider == "anthropic":
        # Anthropic caches up to 4 breakpoints marked with cache_control.
        # We mark the system message — the longest stable thing — as cacheable.
        system_message["cache_control"] = {"type": "ephemeral"}

    messages: list[dict] = [system_message]
    if extra_static_context:
        # Deep-copy so we don't mutate the caller's list of dicts.
        for m in extra_static_context:
            messages.append(copy.deepcopy(m))
    messages.append({"role": "user", "content": dynamic_user})
    if extra_dynamic_messages:
        for m in extra_dynamic_messages:
            messages.append(copy.deepcopy(m))
    return messages
