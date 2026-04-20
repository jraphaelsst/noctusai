"""
LLM client state — module-level singletons that hold the active `LLMConfig`
and the per-provider instance cache.

Populated at application startup (typically by `create_product_app()` in the
seed framework). High-level entry points (`chat_completion`, etc. — Phase 4)
read from here to dispatch to the right provider without the caller having
to plumb anything through.

Lifecycle:
  configure_llm(config)   # at startup
  get_llm_config()        # anywhere
  get_provider(name)      # anywhere
  shutdown_llm()          # at shutdown — closes every provider cleanly
"""
from __future__ import annotations

import logging
from typing import Optional

from noctusai_lib.llm.config import LLMConfig
from noctusai_lib.llm.providers.base import LLMProvider
from noctusai_lib.llm.registry import get_provider_class

logger = logging.getLogger(__name__)

_active_config: Optional[LLMConfig] = None
_provider_cache: dict[str, LLMProvider] = {}


def configure_llm(config: LLMConfig) -> None:
    """Install an LLMConfig as the process-wide active configuration.

    Called once at startup. Safe to call multiple times — last wins, and the
    provider cache is cleared so the next `get_provider()` rebuilds from
    fresh state.
    """
    global _active_config
    _active_config = config
    _provider_cache.clear()
    logger.info(
        "LLM configured (default_provider=%s, default_chat_model=%s, cache_enabled=%s)",
        config.default_provider,
        config.default_chat_model,
        config.cache_enabled,
    )


def get_llm_config() -> LLMConfig:
    """Return the active LLMConfig. Raises if `configure_llm()` wasn't called."""
    if _active_config is None:
        raise RuntimeError(
            "LLM not configured. Call configure_llm(config) at application "
            "startup (usually auto-wired by create_product_app())."
        )
    return _active_config


def get_provider(name: Optional[str] = None) -> LLMProvider:
    """Return a Provider instance by name (or the configured default).

    Instances are cached per name so a single Provider serves all calls.
    Providers are stateless wrt API keys (keys are resolved per call via
    the config's key_provider), so sharing one instance across orgs is safe
    and efficient (connection pools live inside the Provider).
    """
    config = get_llm_config()
    provider_name = name or config.default_provider
    provider = _provider_cache.get(provider_name)
    if provider is None:
        cls = get_provider_class(provider_name)
        provider = cls()
        _provider_cache[provider_name] = provider
    return provider


async def shutdown_llm() -> None:
    """Close every cached provider and clear the active config.

    Called on app shutdown (lifespan). Best-effort: logs but does not raise
    if a provider's close() fails (cleanup should never prevent shutdown).
    """
    global _active_config
    for name, provider in list(_provider_cache.items()):
        try:
            await provider.close()
        except Exception as exc:  # pragma: no cover — cleanup path
            logger.warning("Provider %s close() failed: %s", name, exc)
    _provider_cache.clear()
    _active_config = None
    logger.info("LLM shut down")


def _reset_for_testing() -> None:
    """Test-only hook. Clears config + provider cache without awaiting close()."""
    global _active_config
    _active_config = None
    _provider_cache.clear()


def resolve_api_key(provider: str, org_id: Optional[str] = None) -> str:
    """Resolve an API key via the active config's key_provider.

    Phase 4's high-level entry points call this before dispatching to the
    Provider. Centralised here so every entry point handles
    LLMNotConfigured identically.
    """
    from noctusai_lib.llm.exceptions import LLMNotConfigured

    config = get_llm_config()
    key = config.key_provider(provider, org_id)
    if not key:
        raise LLMNotConfigured(provider)
    return key
