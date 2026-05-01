"""
Shared rate limiter factory for all NoctusAI backends.

Creates a slowapi Limiter instance, optionally backed by Redis.
If redis_url is set and reachable, uses Redis storage for distributed
rate limiting. Otherwise, falls back to in-memory storage.
"""
from __future__ import annotations

import logging
from typing import Optional

from slowapi import Limiter
from slowapi.util import get_remote_address

logger = logging.getLogger(__name__)


def create_limiter(
    redis_url: Optional[str] = None,
    default_limits: Optional[list[str]] = None,
) -> Limiter:
    """
    Create a slowapi Limiter with optional Redis backing.

    Args:
        redis_url: Redis connection URL (e.g. "redis://localhost:6379").
                   If set and reachable, uses Redis as the storage backend.
                   On failure, logs a warning and falls back to in-memory.
        default_limits: Default rate limits (e.g. ["100/minute"]).

    Returns:
        Configured Limiter instance.
    """
    if default_limits is None:
        default_limits = ["100/minute"]

    storage_uri = None

    if redis_url:
        try:
            import redis

            r = redis.from_url(redis_url, socket_connect_timeout=2)
            r.ping()
            storage_uri = redis_url
            logger.info("Rate limiter using Redis backend: %s", redis_url)
        except Exception as exc:
            logger.warning(
                "Redis not reachable for rate limiting (%s), falling back to in-memory: %s",
                redis_url,
                exc,
            )

    if storage_uri:
        return Limiter(
            key_func=get_remote_address,
            default_limits=default_limits,
            storage_uri=storage_uri,
        )

    return Limiter(key_func=get_remote_address, default_limits=default_limits)
