"""Redis-backed CacheBackend for the LLM response cache.

Uses `redis.asyncio` — the official async Redis client. Supports:
  - `get` / `setex` / `delete` — satisfies the `CacheBackend` Protocol
  - `scan_keys(pattern)` — iterate matching keys via SCAN (non-blocking)
  - `flush_prefix(prefix)` — delete everything matching a prefix

The client is constructed lazily: `RedisCacheBackend(url=...)` stores the
URL; the actual Redis pool is opened on first use. This keeps import-time
clean (no network handshake during `configure_llm`) and lets tests construct
the backend even without a live Redis.

Errors propagate out of individual `get` / `setex` calls — the cache layer
in `cache.py` catches them and degrades to a miss, so a dead Redis never
breaks a successful LLM call.

LGPD: this backend stores `json.dumps(payload)` strings. `cache=False` on
the caller side short-circuits before the key is even hashed, so clinical
text never reaches Redis regardless of TTL.
"""
from __future__ import annotations

import logging
from typing import Any, AsyncIterator, Optional

logger = logging.getLogger(__name__)


class RedisCacheBackend:
    """`redis.asyncio`-backed cache for `noctusai_lib.llm.chat_completion`.

    Args:
        url: Redis connection URL (e.g. `redis://localhost:6379/0`).
        client: optional pre-built `redis.asyncio.Redis` — tests inject a
            `fakeredis.aioredis.FakeRedis` here. When `None`, the backend
            builds its own client on first use.

    Not thread-safe. Share one instance per process (per the `LLMConfig`
    singleton pattern).
    """

    def __init__(self, url: Optional[str] = None, client: Any = None) -> None:
        if not url and client is None:
            raise ValueError("RedisCacheBackend requires either `url` or `client`.")
        self._url = url
        self._client = client

    def _get_client(self) -> Any:
        """Lazily open the Redis connection. Importing `redis` at module
        scope would make the whole `noctusai_lib` import hard-depend on the
        package being installed; we keep it deferred so products that never
        enable the cache don't pay the import cost."""
        if self._client is not None:
            return self._client
        try:
            from redis.asyncio import Redis
        except ImportError as exc:
            raise RuntimeError(
                "redis package not installed — add `redis>=5.0.0` to deps "
                "or construct RedisCacheBackend with a `client=...` argument."
            ) from exc
        self._client = Redis.from_url(self._url, decode_responses=True)
        return self._client

    # ── CacheBackend Protocol ──────────────────────────────────────────

    async def get(self, key: str) -> Optional[str]:
        client = self._get_client()
        return await client.get(key)

    async def setex(self, key: str, ttl_seconds: int, value: str) -> None:
        client = self._get_client()
        await client.setex(key, ttl_seconds, value)

    async def delete(self, *keys: str) -> int:
        if not keys:
            return 0
        client = self._get_client()
        return int(await client.delete(*keys))

    # ── Extension: SCAN-based iteration for admin flush ───────────────

    async def scan_keys(self, pattern: str, count: int = 500) -> AsyncIterator[str]:
        """Yield every key matching `pattern` (Redis glob syntax — `*` etc.).

        Uses SCAN to avoid blocking the server on large keyspaces. `count` is
        a hint to Redis for batch size; the server may return more or fewer.
        """
        client = self._get_client()
        cursor = 0
        while True:
            cursor, batch = await client.scan(cursor=cursor, match=pattern, count=count)
            for key in batch:
                yield key
            if cursor == 0:
                break

    async def flush_prefix(self, prefix: str) -> int:
        """Delete every key matching `{prefix}*`. Returns the count deleted.

        Safe to call on large keyspaces — iterates via SCAN so the Redis
        server never blocks on a single command.
        """
        pattern = f"{prefix}*"
        keys_to_delete: list[str] = []
        async for key in self.scan_keys(pattern):
            keys_to_delete.append(key)
            # Drain in chunks so DEL doesn't build up an unbounded argument list.
            if len(keys_to_delete) >= 200:
                await self.delete(*keys_to_delete)
                keys_to_delete.clear()
        if keys_to_delete:
            await self.delete(*keys_to_delete)
        return await self._approximate_count(prefix)

    async def _approximate_count(self, prefix: str) -> int:
        """After a flush, return 0 — nothing matches. Preserved as a hook
        so admin tooling can read "x entries flushed" even if the caller
        doesn't track the count themselves."""
        count = 0
        async for _ in self.scan_keys(f"{prefix}*"):
            count += 1
        return count

    async def close(self) -> None:
        if self._client is not None:
            try:
                await self._client.aclose()
            except AttributeError:
                # Older redis-py / fakeredis expose `close()` not `aclose()`.
                await self._client.close()
