"""
Response cache for the shared LLM client — Redis-backed.

**LGPD-aware from day one.** Therapy's summary / longitudinal services pass
`cache=False` on every call to keep patient clinical free text out of the
cache entirely. The cache checks this gate before touching Redis.

Key format:
    llm:{product}:{provider}:{model}:{prompt_version}:org={org_id}:{sha256(messages_json)}

The `org_id` segment isolates per-org cache entries so two organizations
with identical (product, provider, model, prompt_version, messages) cannot
share a cache value. When `org_id is None`, the segment becomes
`org=__platform__` (used for prompts that don't carry per-org context, e.g.
docs Q&A). Added 2026-04-24 closing the cross-org-leak vector identified by
the ai-expansion Tier 1.5 G5 audit.

The `prompt_version` parameter lets services bump a single integer when
their system prompt changes — that invalidates cache entries for the old
prompt without needing a global flush.

Two cacheable surfaces:
  - `chat_completion(temperature=0)` — deterministic output
  - `generate_embedding(...)`        — input-deterministic

Audio / vision are never cached (Whisper transcripts + Vision responses
can both contain user-owned content beyond easy redaction).
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Optional, Protocol

logger = logging.getLogger(__name__)


class CacheBackend(Protocol):
    """Minimal Redis-like interface we need. Production uses `redis.asyncio`;
    tests swap in an in-memory fake."""

    async def get(self, key: str) -> Optional[str]: ...
    async def setex(self, key: str, ttl_seconds: int, value: str) -> None: ...
    async def delete(self, *keys: str) -> int: ...


def build_cache_key(
    *,
    product: str,
    provider: str,
    model: str,
    prompt_version: str,
    payload: Any,
    org_id: Optional[str] = None,
) -> str:
    """Build a deterministic cache key from the request shape.

    `payload` is anything JSON-serialisable — typically the messages list
    for chat or the input text for embeddings. Hashed with SHA-256; the key
    is bounded even for very long prompts.

    `org_id` isolates cache entries per organization (LGPD posture — see
    module docstring). Pass the org running this prompt; pass `None` only
    for prompts that have no org context (platform-wide docs Q&A, etc.).
    """
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    org_segment = org_id if org_id else "__platform__"
    return f"llm:{product}:{provider}:{model}:{prompt_version}:org={org_segment}:{digest}"


async def try_get(
    backend: CacheBackend,
    key: str,
) -> tuple[bool, Optional[Any]]:
    """Attempt a cache read. Returns (hit, value). Never raises — cache
    misses and cache-layer errors are both treated as misses."""
    try:
        raw = await backend.get(key)
        if raw is None:
            logger.debug("llm.cache.miss key=%s", key)
            return (False, None)
        logger.info("llm.cache.hit key=%s", key)
        return (True, json.loads(raw))
    except Exception as exc:
        logger.warning("llm.cache.error get key=%s: %s", key, exc)
        return (False, None)


async def try_set(
    backend: CacheBackend,
    key: str,
    value: Any,
    ttl_seconds: int,
) -> None:
    """Attempt a cache write. Never raises — write failures are swallowed
    (with a warning log) so cache problems can't break a successful LLM call."""
    try:
        raw = json.dumps(value, ensure_ascii=False)
        await backend.setex(key, ttl_seconds, raw)
    except Exception as exc:
        logger.warning("llm.cache.error set key=%s: %s", key, exc)


class InMemoryCacheBackend:
    """Simple dict-backed CacheBackend — for tests and dev environments
    without Redis. Not thread-safe; not suitable for multi-worker prod."""

    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    async def get(self, key: str) -> Optional[str]:
        return self._store.get(key)

    async def setex(self, key: str, ttl_seconds: int, value: str) -> None:
        # TTL intentionally unused — this backend is for dev/test only.
        self._store[key] = value

    async def delete(self, *keys: str) -> int:
        count = 0
        for k in keys:
            if k in self._store:
                del self._store[k]
                count += 1
        return count


async def flush_for_model(backend: CacheBackend, *, product: str, provider: str, model: str) -> int:
    """Delete every cached entry for a given (product, provider, model).

    Used by the platform_admin flush endpoint. Dispatches on backend type:
      - `InMemoryCacheBackend` — iterates its dict.
      - `RedisCacheBackend` — delegates to `flush_prefix` (SCAN + DEL).
      - Any other `CacheBackend` with a `flush_prefix(prefix: str) -> int` — called.
      - Otherwise — logs and returns 0.
    """
    prefix = f"llm:{product}:{provider}:{model}:"
    if isinstance(backend, InMemoryCacheBackend):
        to_del = [k for k in backend._store if k.startswith(prefix)]
        return await backend.delete(*to_del)
    flush_prefix = getattr(backend, "flush_prefix", None)
    if callable(flush_prefix):
        try:
            deleted = await flush_prefix(prefix)
            return int(deleted or 0)
        except Exception as exc:
            logger.warning("llm.cache.error flush prefix=%s: %s", prefix, exc)
            return 0
    logger.info("flush_for_model prefix=%s — backend %s has no flush_prefix; skipped",
                prefix, type(backend).__name__)
    return 0
