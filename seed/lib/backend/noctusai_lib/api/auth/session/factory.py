"""Factory for the auth-session store — the seed-fake-real seam.

``make_session_store`` is the ONE place consumers construct a store, so a
product never hard-codes ``FakeSessionStore()`` (the fork that left every
consumer on non-durable in-memory sessions). Pass ``settings.redis_url``:
when set, you get the durable :class:`RedisSessionStore`; when ``None``
(dev / tests / no Redis configured) you get the in-memory
:class:`FakeSessionStore`. See ``KB § PATTERNS/backend/seed-fake-real-adapter.md``.
"""

from __future__ import annotations

from typing import Any, Optional, Sequence

from noctusai_lib.api.auth.session.redis_store import RedisSessionStore
from noctusai_lib.api.auth.session.store import FakeSessionStore, SessionStore


def make_session_store(
    redis_url: Optional[str] = None,
    *,
    client: Any = None,
    encryption_key: Optional[bytes] = None,
    extra_decrypt_keys: Optional[Sequence[bytes]] = None,
    require_encryption: bool = False,
) -> SessionStore:
    """Return the appropriate ``SessionStore`` for the environment.

    Args:
        redis_url: When set (prod), returns a Redis-backed store so sessions
            survive process restarts. When ``None``, returns the in-memory
            ``FakeSessionStore`` (dev / tests).
        client: Optional pre-built ``redis.asyncio``-compatible client (e.g.
            ``fakeredis.aioredis.FakeRedis`` in tests) — forces the Redis
            adapter regardless of ``redis_url``.
        encryption_key: Fernet key for at-rest encryption of the session
            tokens (SEC-3). Derive from ``settings.session_encryption_key``
            (``.encode()``). When ``None``, the Redis store keeps tokens
            plaintext.
        extra_decrypt_keys: Old Fernet keys still accepted on the read path
            during a key rotation window (see ``MultiKeyDecryptor``).
        require_encryption: When ``True``, refuse to return a Redis-backed
            store without an ``encryption_key`` — the refresh token would sit
            plaintext in the shared fleet Redis (SEC-3). Set this in
            production wiring so a missing key fails loudly at boot instead of
            silently storing impersonation credentials in the clear.

    Returns:
        A concrete object satisfying the ``SessionStore`` Protocol.

    Raises:
        ValueError: ``require_encryption`` is set but a Redis store would be
            built without an ``encryption_key``.
    """
    building_redis = client is not None or bool(redis_url)
    if require_encryption and building_redis and encryption_key is None:
        raise ValueError(
            "make_session_store: require_encryption is set but no "
            "encryption_key was provided — the Supabase refresh token would "
            "be stored plaintext in shared Redis (SEC-3). Set "
            "settings.session_encryption_key."
        )
    if client is not None:
        return RedisSessionStore(
            client=client,
            encryption_key=encryption_key,
            extra_decrypt_keys=extra_decrypt_keys,
        )
    if redis_url:
        return RedisSessionStore(
            url=redis_url,
            encryption_key=encryption_key,
            extra_decrypt_keys=extra_decrypt_keys,
        )
    return FakeSessionStore()


__all__ = ["make_session_store"]
