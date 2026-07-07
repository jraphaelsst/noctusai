"""Redis-backed ``SessionStore`` — the Wave-2 real adapter.

Closes the seed-fake-real-adapter contract for the auth-session store:
the seed now ships Protocol (``store.py``) + Fake (``store.py``) + **Real
(this module)** + factory (``factory.py``). Previously only Protocol+Fake
shipped, so every consumer ran the in-memory ``FakeSessionStore`` — sessions
died on every process restart (each deploy logged all users out). See
``KB § PATTERNS/backend/seed-fake-real-adapter.md``.

The client is constructed lazily (mirrors ``integrations/llm/backends/
redis_backend.py``): ``RedisSessionStore(url=...)`` stores the URL; the pool
opens on first use, so importing this module never requires a live Redis.
Tests inject a ``fakeredis.aioredis.FakeRedis`` via ``client=``.

Storage shape: one key per session, ``nai_session:<session_id>`` → JSON
``{user_id, org_id, refresh_token, scopes}``. TTL is native Redis key
expiry (``SET ... EX`` / ``EXPIRE``), so expired sessions vanish without a
sweep and ``lookup`` returns ``None`` — matching the Protocol contract. The
Supabase refresh token is held server-side only; it is stored in the record
but never surfaced in the returned ``AuthContext``.
"""

from __future__ import annotations

import json
from typing import Any, Optional
from uuid import UUID

import secrets

from noctusai_lib.api.auth.session.types import AuthContext

# Namespaced so session keys never collide with the LLM cache or rate-limiter
# in a shared Redis db.
_KEY_PREFIX = "nai_session:"


class RedisSessionStore:
    """``redis.asyncio``-backed ``SessionStore`` (satisfies the Protocol).

    Args:
        url: Redis connection URL (e.g. ``redis://localhost:6379/0``). The
            framework passes ``settings.redis_url``.
        client: optional pre-built ``redis.asyncio.Redis`` — tests inject a
            ``fakeredis.aioredis.FakeRedis`` here. When ``None``, the client
            is opened lazily from ``url`` on first use.
    """

    def __init__(self, url: Optional[str] = None, client: Any = None) -> None:
        if url is None and client is None:
            raise ValueError(
                "RedisSessionStore requires either `url` or `client`."
            )
        self._url = url
        self._client = client

    def _get_client(self) -> Any:
        """Lazily open the Redis connection (import-time stays Redis-free)."""
        if self._client is None:
            try:
                from redis.asyncio import Redis
            except ImportError as exc:  # pragma: no cover - dep always present
                raise RuntimeError(
                    "redis package not installed — add `redis>=5.0.0` to deps "
                    "or construct RedisSessionStore with a `client=...` argument."
                ) from exc
            self._client = Redis.from_url(self._url, decode_responses=True)
        return self._client

    @staticmethod
    def _key(session_id: str) -> str:
        return f"{_KEY_PREFIX}{session_id}"

    async def create(
        self,
        *,
        user_id: UUID,
        org_id: UUID,
        supabase_refresh_token: str,
        ttl_seconds: int = 86400,
    ) -> str:
        session_id = secrets.token_urlsafe(32)
        record = {
            "user_id": str(user_id),
            "org_id": str(org_id),
            "refresh_token": supabase_refresh_token,
            "scopes": [],  # Wave 2 populates from user role mapping
        }
        client = self._get_client()
        await client.set(self._key(session_id), json.dumps(record), ex=ttl_seconds)
        return session_id

    async def lookup(self, session_id: str) -> AuthContext | None:
        client = self._get_client()
        raw = await client.get(self._key(session_id))
        if raw is None:
            # Absent OR expired (Redis evicted the key) — both are "no session".
            return None
        try:
            record = json.loads(raw)
        except (ValueError, TypeError):
            # Corrupt record — treat as no session rather than 500.
            return None
        return AuthContext(
            org_id=UUID(record["org_id"]),
            caller_kind="user",
            user_id=UUID(record["user_id"]) if record.get("user_id") else None,
            scopes=list(record.get("scopes") or []),
            raw_token=session_id,
            api_token_id=None,
        )

    async def refresh_ttl(self, session_id: str, ttl_seconds: int = 86400) -> None:
        client = self._get_client()
        # EXPIRE is a no-op (returns 0) when the key is absent — matches the
        # Protocol's "no-op when the session is already absent".
        await client.expire(self._key(session_id), ttl_seconds)

    async def delete(self, session_id: str) -> None:
        client = self._get_client()
        await client.delete(self._key(session_id))


__all__ = ["RedisSessionStore"]
