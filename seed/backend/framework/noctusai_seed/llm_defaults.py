"""
Default LLM configuration — the seed-injector policy.

Every product that calls `create_product_app()` without passing an explicit
`llm_config` gets the result of `default_llm_config()`. That means multi-
provider LLM access is a seed-level inheritance, not a per-product wiring
task. When a product wants different defaults (e.g. Therapy preferring
`gpt-4o` over the platform's `gpt-4o-mini`), it passes
`llm_config=default_llm_config(default_chat_model="gpt-4o")` to override
just that field — the rest come from the shared defaults.

The `key_provider` here uses `noctusai_lib.credentials.resolve_credential`,
which implements the 3-tier chain (org → platform → env). Every product
inherits the same resolution policy.
"""
from __future__ import annotations

from typing import Any

from noctusai_lib.config.credentials import resolve_credential
from noctusai_lib.integrations.llm import LLMConfig


def _default_key_provider(provider: str, org_id: str | None = None) -> str | None:
    """Shared key provider — looks up `{provider}_api_key` through the
    3-tier chain. Products don't need to implement their own version unless
    they want a different policy (rare)."""
    return resolve_credential(f"{provider}_api_key", org_id)


def default_llm_config(
    *,
    redis_url: str | None = None,
    usage_tracking_db: Any = None,
    usage_tracking_schema: str | None = None,
    **overrides: Any,
) -> LLMConfig:
    """Build an LLMConfig using platform defaults, with optional overrides.

    - `redis_url`: when set, attaches a `RedisCacheBackend` and flips
      `cache_enabled=True`. The framework passes `settings.redis_url`.
    - `usage_tracking_db` + `usage_tracking_schema`: when both set, attaches
      a `SupabaseUsageSink(db, schema)` that writes to `<schema>.llm_usage`.
      The framework passes these when `settings.llm_usage_tracking=True`.

    Usage:
        default_llm_config()
        default_llm_config(redis_url="redis://localhost:6379/0")
        default_llm_config(default_chat_model="gpt-4o")
    """
    defaults: dict[str, Any] = {
        "key_provider": _default_key_provider,
        "default_provider": "openai",
        "default_chat_model": "gpt-4o-mini",
        "default_embedding_model": "text-embedding-3-small",
        "default_audio_model": "whisper-1",
        "default_vision_model": "gpt-4o",
    }

    # Auto-wire the Redis cache when a URL is supplied. Products with no
    # REDIS_URL stay on the in-memory default (`cache_enabled=False`).
    if redis_url:
        from noctusai_lib.integrations.llm.backends import RedisCacheBackend
        defaults["cache_backend"] = RedisCacheBackend(url=redis_url)
        defaults["cache_enabled"] = True

    # Auto-wire the DB-backed usage sink when opted in. Both the db client
    # (service role — bypasses RLS for writes) and schema are required;
    # missing either means we keep `usage_sink=None` (no tracking).
    if usage_tracking_db is not None and usage_tracking_schema:
        from noctusai_lib.integrations.llm.usage import SupabaseUsageSink
        defaults["usage_sink"] = SupabaseUsageSink(
            db_client=usage_tracking_db,
            schema=usage_tracking_schema,
        )

    defaults.update(overrides)
    return LLMConfig(**defaults)


# Convenience singleton for products that don't override anything — equivalent
# to `default_llm_config()`. Products can import either name; they're the same.
DEFAULT_LLM_CONFIG = default_llm_config()
