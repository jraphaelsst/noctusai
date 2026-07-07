"""Factory for the auth-session store — the seed-fake-real seam.

``make_session_store`` is the ONE place consumers construct a store, so a
product never hard-codes ``FakeSessionStore()`` (the fork that left every
consumer on non-durable in-memory sessions). Pass ``settings.redis_url``:
when set, you get the durable :class:`RedisSessionStore`; when ``None``
(dev / tests / no Redis configured) you get the in-memory
:class:`FakeSessionStore`. See ``KB § PATTERNS/backend/seed-fake-real-adapter.md``.
"""

from __future__ import annotations

from typing import Any, Optional

from noctusai_lib.api.auth.session.redis_store import RedisSessionStore
from noctusai_lib.api.auth.session.store import FakeSessionStore, SessionStore


def make_session_store(
    redis_url: Optional[str] = None,
    *,
    client: Any = None,
) -> SessionStore:
    """Return the appropriate ``SessionStore`` for the environment.

    Args:
        redis_url: When set (prod), returns a Redis-backed store so sessions
            survive process restarts. When ``None``, returns the in-memory
            ``FakeSessionStore`` (dev / tests).
        client: Optional pre-built ``redis.asyncio``-compatible client (e.g.
            ``fakeredis.aioredis.FakeRedis`` in tests) — forces the Redis
            adapter regardless of ``redis_url``.

    Returns:
        A concrete object satisfying the ``SessionStore`` Protocol.
    """
    if client is not None:
        return RedisSessionStore(client=client)
    if redis_url:
        return RedisSessionStore(url=redis_url)
    return FakeSessionStore()


__all__ = ["make_session_store"]
