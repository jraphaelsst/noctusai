"""
LLMConfig — per-product configuration for the shared LLM client.

Each product instantiates one `LLMConfig` at startup and passes it to
`create_product_app(llm_config=...)`. The framework wires it into a module-
level singleton and closes providers on shutdown.

Design:
  - Stateless: no API keys baked in. The `key_provider` callable is invoked
    on every call to resolve the right key for the right provider + org.
  - Defaults are explicit: `default_provider`, `default_chat_model`, etc.
    Services can override per call (e.g. ERP uses gpt-4o-mini, Therapy uses
    gpt-4o for clinical summaries).
  - Cache fields are inert until Phase 8 ships `noctusai_lib.llm.cache`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

# The signature every product must implement for the key_provider callable:
#
#   def my_key_provider(provider: str, org_id: Optional[str] = None) -> Optional[str]:
#       return resolve_credential(f"{provider}_api_key", org_id)
#
# Returns the resolved API key, or None if the provider isn't configured
# anywhere (org / platform / env). Callers that receive None raise
# `LLMNotConfigured`.
KeyProvider = Callable[..., Optional[str]]


@dataclass
class LLMConfig:
    """Product-level LLM configuration."""

    key_provider: KeyProvider
    """`(provider: str, org_id: Optional[str] = None) -> Optional[str]`."""

    # Defaults — overrideable per call
    default_provider: str = "openai"
    default_chat_model: str = "gpt-4o-mini"
    default_embedding_model: str = "text-embedding-3-small"
    default_audio_model: str = "whisper-1"
    default_vision_model: str = "gpt-4o"

    # Phase 8 — response cache
    cache_enabled: bool = False
    cache_backend: Optional[Any] = None  # Redis-like; set in Phase 8
    default_cache_ttl_chat: int = 24 * 60 * 60           # 24h
    default_cache_ttl_embedding: int = 30 * 24 * 60 * 60  # 30d

    # Phase 15 — token + cost accounting. When set, every provider call
    # records a UsageEvent against this sink. `None` disables tracking.
    # See `noctusai_lib.llm.usage.UsageSink` for the protocol.
    usage_sink: Optional[Any] = None

    # Future: per-environment branching, per-org overrides, streaming, etc.
    # — intentionally not here yet per Phase 1 scope.
