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

from noctusai_lib.integrations.redis import (
    RedisAuthRequired,
    make_redis_client,
    redact_redis_url,
    redis_connection_url,
)

logger = logging.getLogger(__name__)

# Set by Cloudflare's edge on every proxied request, overwriting any value
# the client sent — so, unlike X-Forwarded-For, it cannot be spoofed from
# outside. Prod containers are reachable only through the Cloudflare tunnel.
_CF_CONNECTING_IP = "cf-connecting-ip"


def client_ip_key(request) -> str:
    """Rate-limit key = the real visitor IP behind the Cloudflare tunnel.

    `get_remote_address` (the default key) returns the socket peer, which in
    prod is the tunnel connector — every visitor shares ONE bucket. Use this
    as `@limiter.limit(..., key_func=client_ip_key)` on public routes where a
    per-visitor limit is the point. Falls back to the socket peer when the
    header is absent (local dev, tests).
    """
    forwarded = request.headers.get(_CF_CONNECTING_IP, "").strip()
    return forwarded or get_remote_address(request)


def resolve_limiter_storage_uri(
    redis_url: Optional[str], *, probe_client=None
) -> Optional[str]:
    """Authenticated slowapi ``storage_uri`` for ``redis_url``, or ``None``.

    Probes reachability through the Redis auth seam (``probe_client`` is the
    injection point for tests); on an unreachable Redis logs a REDACTED
    warning and returns ``None`` (in-memory fallback). ``RedisAuthRequired``
    is never swallowed (fail-closed).
    """
    if not redis_url:
        return None
    try:
        candidate_uri = redis_connection_url(redis_url)
        client = probe_client or make_redis_client(
            redis_url, decode_responses=False, socket_connect_timeout=2
        )
        client.ping()
        logger.info(
            "Rate limiter using Redis backend: %s", redact_redis_url(candidate_uri)
        )
        return candidate_uri
    except RedisAuthRequired:
        # Fail-closed: auth was declared mandatory (REDIS_REQUIRE_AUTH) —
        # a silent in-memory fallback would hide the misconfiguration.
        raise
    except Exception as exc:
        logger.warning(
            "Redis not reachable for rate limiting (%s), falling back to in-memory: %s",
            redact_redis_url(redis_url),
            exc,
        )
        return None


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

    storage_uri = resolve_limiter_storage_uri(redis_url)

    # `client_ip_key`, not the bare `get_remote_address` slowapi default: in
    # prod every product sits behind the Cloudflare tunnel, so the socket
    # peer `get_remote_address` reads is the TUNNEL CONNECTOR — the same
    # address for every visitor. Every `@limiter.limit(...)` decorator across
    # the fleet that does not pass its own `key_func=` (the overwhelming
    # majority — auth/OTP, AI, portal and webhook routes alike) inherits
    # THIS Limiter's key_func, so that bug was live fleet-wide: one shared
    # bucket per product, not one per visitor. A burst of legitimate
    # concurrent users could exhaust e.g. a "10/minute" login limit for
    # EVERYONE, or a single caller could starve it for everyone else.
    # `client_ip_key` already falls back to `get_remote_address` when the
    # `CF-Connecting-IP` header is absent (local dev / tests behind no
    # tunnel), so this is a same-behavior-in-dev, correct-in-prod change —
    # never a regression.
    if storage_uri:
        return Limiter(
            key_func=client_ip_key,
            default_limits=default_limits,
            storage_uri=storage_uri,
        )

    return Limiter(key_func=client_ip_key, default_limits=default_limits)
