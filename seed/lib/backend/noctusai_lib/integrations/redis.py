"""Redis client factory.

Mirrors the noctusai_lib `make_*` factory pattern (see `database.py`).
Consumers call `make_redis_client(redis_url)` with their settings'
`redis_url` and cache the result at module scope (typically inside a
`configure_*_module(...)` call).

Used by `noctusai_lib.domain.chatbot` for the buffer + debounce
ZSET; consumers may also use it directly for non-conversation Redis
needs.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any, Optional
from urllib.parse import quote, urlsplit, urlunsplit

if TYPE_CHECKING:
    from redis import Redis
    from redis.asyncio import Redis as AsyncRedis

__all__ = [
    "RedisAuthRequired",
    "make_async_redis_client",
    "make_fake_redis_client",
    "make_redis_client",
    "redact_redis_url",
    "redis_connection_url",
]

_TRUTHY = {"1", "true", "yes", "on"}


class RedisAuthRequired(RuntimeError):
    """``REDIS_REQUIRE_AUTH`` is on but no credentials resolved.

    Raised at client construction (fail-closed, loud) — the seam never
    connects unauthenticated when the deployment declared auth mandatory.
    """


def _url_has_credentials(url: str) -> bool:
    parts = urlsplit(url)
    return bool(parts.username or parts.password)


def _resolve_url(redis_url: Optional[str]) -> str:
    url = redis_url or os.environ.get("REDIS_URL") or ""
    if not url:
        raise ValueError(
            "No Redis URL: pass `redis_url` or set REDIS_URL (settings.redis_url)."
        )
    return url


def _resolve_split_credentials(
    username: Optional[str], password: Optional[str]
) -> tuple[Optional[str], Optional[str]]:
    """Explicit args win, then REDIS_USERNAME / REDIS_PASSWORD env."""
    user = username if username is not None else (os.environ.get("REDIS_USERNAME") or None)
    pw = password if password is not None else (os.environ.get("REDIS_PASSWORD") or None)
    return user or None, pw or None


def _require_auth(flag: Optional[bool]) -> bool:
    if flag is not None:
        return flag
    return os.environ.get("REDIS_REQUIRE_AUTH", "").strip().lower() in _TRUTHY


def _resolve(
    redis_url: Optional[str],
    username: Optional[str],
    password: Optional[str],
    require_auth: Optional[bool],
) -> tuple[str, dict[str, str]]:
    """Return ``(url, extra_from_url_kwargs)``.

    Precedence (documented, single source): credentials embedded in the URL
    WIN and the split ``username``/``password`` (args, then REDIS_USERNAME /
    REDIS_PASSWORD env) are ignored — never both. Split credentials are only
    used when the URL carries none. ``require_auth`` (arg, then
    REDIS_REQUIRE_AUTH) with neither source raises :class:`RedisAuthRequired`.
    """
    url = _resolve_url(redis_url)
    if _url_has_credentials(url):
        return url, {}
    user, pw = _resolve_split_credentials(username, password)
    if user is None and pw is None:
        if _require_auth(require_auth):
            raise RedisAuthRequired(
                "REDIS_REQUIRE_AUTH is set but no Redis credentials resolved "
                f"for {redact_redis_url(url)} — set REDIS_PASSWORD (and "
                "REDIS_USERNAME for ACL users) or embed them in REDIS_URL."
            )
        return url, {}
    kwargs: dict[str, str] = {}
    if user is not None:
        kwargs["username"] = user
    if pw is not None:
        kwargs["password"] = pw
    return url, kwargs


def redact_redis_url(url: str) -> str:
    """Password -> ``***``, username kept. The ONLY way to log a Redis URL."""
    try:
        parts = urlsplit(url)
        if parts.password is None:
            return url
        host = parts.hostname or ""
        if ":" in host:
            host = f"[{host}]"
        if parts.port is not None:
            host = f"{host}:{parts.port}"
        user = parts.username or ""
        return urlunsplit(parts._replace(netloc=f"{user}:***@{host}"))
    except ValueError:
        return "<unparseable redis url>"


def redis_connection_url(
    redis_url: Optional[str] = None,
    *,
    username: Optional[str] = None,
    password: Optional[str] = None,
    require_auth: Optional[bool] = None,
) -> str:
    """Resolve the Redis URL with credentials merged in, for libraries that
    only accept a URI (e.g. slowapi ``storage_uri``).

    Precedence: URL-embedded credentials win; split creds (args, then
    REDIS_USERNAME / REDIS_PASSWORD) are merged only when the URL has none.
    The result may contain a password — never log it; use
    :func:`redact_redis_url`.
    """
    url, extra = _resolve(redis_url, username, password, require_auth)
    if not extra:
        return url
    parts = urlsplit(url)
    userinfo = quote(extra.get("username", ""), safe="")
    if "password" in extra:
        userinfo += ":" + quote(extra["password"], safe="")
    host = parts.hostname or ""
    if ":" in host:
        host = f"[{host}]"
    if parts.port is not None:
        host = f"{host}:{parts.port}"
    return urlunsplit(parts._replace(netloc=f"{userinfo}@{host}"))


def make_redis_client(
    redis_url: Optional[str] = None,
    *,
    username: Optional[str] = None,
    password: Optional[str] = None,
    require_auth: Optional[bool] = None,
    **kwargs: Any,
) -> "Redis":
    """Construct a sync `redis.Redis` through the auth seam.

    Args:
        redis_url: redis:// or rediss:// URL (default: REDIS_URL env).
        username / password / require_auth: see :func:`redis_connection_url`
            for precedence; credentials are passed as ``from_url`` kwargs.
        **kwargs: forwarded to `Redis.from_url(...)`. `decode_responses=True`
            is set by default; pass `decode_responses=False` to opt out.

    Returns:
        Configured `Redis` instance. Caller owns lifecycle (no implicit
        connection-pool sharing across factory calls).
    """
    from redis import Redis

    url, extra = _resolve(redis_url, username, password, require_auth)
    kwargs.setdefault("decode_responses", True)
    return Redis.from_url(url, **extra, **kwargs)


def make_async_redis_client(
    redis_url: Optional[str] = None,
    *,
    username: Optional[str] = None,
    password: Optional[str] = None,
    require_auth: Optional[bool] = None,
    **kwargs: Any,
) -> "AsyncRedis":
    """`redis.asyncio.Redis` twin of :func:`make_redis_client` (same
    resolution, precedence and fail-closed behaviour)."""
    from redis.asyncio import Redis as _AsyncRedis

    url, extra = _resolve(redis_url, username, password, require_auth)
    kwargs.setdefault("decode_responses", True)
    return _AsyncRedis.from_url(url, **extra, **kwargs)


def make_fake_redis_client(**kwargs: Any) -> "Redis":
    """In-memory Redis-compatible client for tests + dev (no network).

    Wraps `fakeredis.FakeStrictRedis` with the same `decode_responses=True`
    default as `make_redis_client`. The returned instance satisfies
    `noctusai_lib.domain.chatbot.RedisBufferClient` Protocol naturally —
    drop-in for `make_redis_client(redis_url)` in test/dev paths.

    Per the gold-standard Fake+Real shape (`KB § PATTERNS/seed-fake-real-adapter.md`)
    every IO-touching seed module ships a Fake. The redis module's Fake
    delegates to `fakeredis` rather than hand-rolling because Redis's
    surface area is large and `fakeredis` is the de-facto Python fake.
    """
    import fakeredis  # lazy — only test/dev paths import this

    kwargs.setdefault("decode_responses", True)
    return fakeredis.FakeStrictRedis(**kwargs)
