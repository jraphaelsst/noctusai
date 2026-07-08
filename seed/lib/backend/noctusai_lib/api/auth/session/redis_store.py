"""Redis-backed ``SessionStore`` — the Wave-2 real adapter (hardened).

Closes the seed-fake-real-adapter contract for the auth-session store:
the seed ships Protocol (``store.py``) + Fake (``store.py``) + **Real
(this module)** + factory (``factory.py``). Previously only Protocol+Fake
shipped, so every consumer ran the in-memory ``FakeSessionStore`` —
sessions died on every process restart (each deploy logged all users out).
See ``KB § PATTERNS/backend/seed-fake-real-adapter.md``.

Security hardening (2026-07-08, from the httpOnly-cookie-session threat
model — ``project-history/roadmaps/erp-httponly-cookie-session-2026-07.md``):

- **SEC-3 — encrypt at rest.** The Supabase refresh token is a long-lived,
  full-impersonation credential. This store lives in a Redis SHARED with the
  LLM cache + rate-limiter, so a single Redis read of plaintext tokens would
  harvest every user's credential. When constructed with an ``encryption_key``
  (a Fernet key), the ``refresh_token`` and the cached ``access_token`` are
  Fernet-encrypted (AES-128-CBC + HMAC) via
  ``noctusai_lib.security.encrypted_tokens`` before write and decrypted on
  read. The record carries an ``enc`` flag so a store can read rows written
  before a key was configured (and ``extra_decrypt_keys`` supports key
  rotation via ``MultiKeyDecryptor``). With no key, tokens are stored
  plaintext — acceptable ONLY for local dev with throwaway tokens; the
  factory refuses an unencrypted Redis store when ``require_encryption`` is
  set.
- **SEC-2 — access-token cache.** The record caches the most-recently-minted
  access token + its ``expires_at`` so the vast majority of requests skip the
  upstream refresh. ``read_tokens`` / ``write_tokens`` are the server-side
  seam the ``TokenExchanger`` uses; the tokens NEVER reach ``lookup`` /
  ``AuthContext`` / the browser.

The client is constructed lazily (mirrors ``integrations/llm/backends/
redis_backend.py``): ``RedisSessionStore(url=...)`` stores the URL; the pool
opens on first use, so importing this module never requires a live Redis.
Tests inject a ``fakeredis.aioredis.FakeRedis`` via ``client=``.

Storage shape: one key per session, ``nai_session:<session_id>`` → JSON
``{user_id, org_id, refresh_token, access_token, access_expires_at, scopes,
enc}``. TTL is native Redis key expiry (``SET ... EX`` / ``EXPIRE``), so
expired sessions vanish without a sweep and ``lookup`` returns ``None`` —
matching the Protocol contract.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional, Sequence
from uuid import UUID

import secrets

from noctusai_lib.api.auth.session.types import AuthContext, SessionTokens
from noctusai_lib.security.encrypted_tokens import (
    MultiKeyDecryptor,
    encrypt,
)

logger = logging.getLogger(__name__)

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
        encryption_key: Fernet key (44 url-safe-base64 bytes from
            ``encrypted_tokens.generate_key()``). When set, the refresh token
            and cached access token are encrypted at rest (SEC-3). When
            ``None``, tokens are stored plaintext (dev only).
        extra_decrypt_keys: Additional Fernet keys tried on the READ path
            (in order after ``encryption_key``) to support key rotation —
            rows written with an old key still decrypt during the migration
            window. See ``encrypted_tokens.MultiKeyDecryptor``.
    """

    def __init__(
        self,
        url: Optional[str] = None,
        client: Any = None,
        *,
        encryption_key: Optional[bytes] = None,
        extra_decrypt_keys: Optional[Sequence[bytes]] = None,
    ) -> None:
        if url is None and client is None:
            raise ValueError(
                "RedisSessionStore requires either `url` or `client`."
            )
        self._url = url
        self._client = client
        self._encryption_key = encryption_key
        # Read path: current write key first (so the common already-current
        # row succeeds on the first try), then any rotation keys.
        self._decryptor: Optional[MultiKeyDecryptor] = None
        if encryption_key is not None:
            keys = [encryption_key, *(extra_decrypt_keys or [])]
            self._decryptor = MultiKeyDecryptor(keys)

    @property
    def encrypts_at_rest(self) -> bool:
        """True when tokens are Fernet-encrypted before write (SEC-3)."""
        return self._encryption_key is not None

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

    # ── at-rest crypto (SEC-3) ────────────────────────────────────────

    def _enc(self, plaintext: Optional[str]) -> Optional[str]:
        """Encrypt a token for storage; pass ``None`` through unchanged."""
        if plaintext is None:
            return None
        if self._encryption_key is None:
            return plaintext
        return encrypt(plaintext, self._encryption_key)

    def _dec(self, stored: Optional[str], *, enc: bool) -> Optional[str]:
        """Decrypt a stored token; pass ``None`` through unchanged.

        ``enc`` is the per-record flag: a row written before a key was
        configured is plaintext even on a now-encrypting store, so we only
        decrypt when the row itself was encrypted.
        """
        if stored is None:
            return None
        if not enc:
            return stored
        if self._decryptor is None:
            # Row claims encryption but this store has no key — a
            # misconfiguration (key removed after rows were written). Fail
            # loud rather than hand back ciphertext as if it were a token.
            raise ValueError(
                "session record is encrypted but RedisSessionStore has no "
                "encryption_key configured — refusing to return ciphertext"
            )
        return self._decryptor.decrypt(stored)

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
            "refresh_token": self._enc(supabase_refresh_token),
            "access_token": None,  # SEC-2 cache — populated on first exchange
            "access_expires_at": None,
            "scopes": [],  # Wave 2 populates from user role mapping
            "enc": self.encrypts_at_rest,
        }
        client = self._get_client()
        await client.set(self._key(session_id), json.dumps(record), ex=ttl_seconds)
        return session_id

    async def lookup(self, session_id: str) -> AuthContext | None:
        record = await self._read_record(session_id)
        if record is None:
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

    async def read_tokens(self, session_id: str) -> SessionTokens | None:
        record = await self._read_record(session_id)
        if record is None:
            return None
        enc = bool(record.get("enc"))
        return SessionTokens(
            refresh_token=self._dec(record.get("refresh_token"), enc=enc) or "",
            access_token=self._dec(record.get("access_token"), enc=enc),
            access_expires_at=record.get("access_expires_at"),
        )

    async def write_tokens(
        self,
        session_id: str,
        *,
        refresh_token: str,
        access_token: str | None,
        access_expires_at: int | None,
    ) -> None:
        client = self._get_client()
        raw = await client.get(self._key(session_id))
        if raw is None:
            # Raced with logout/expiry — no session to update. No-op (the
            # caller re-resolves and 401s); do NOT recreate the key (that
            # would resurrect a logged-out session with no TTL).
            return
        try:
            record = json.loads(raw)
        except (ValueError, TypeError):
            logger.warning("write_tokens: corrupt record for a session — skipping")
            return
        record["refresh_token"] = self._enc(refresh_token)
        record["access_token"] = self._enc(access_token)
        record["access_expires_at"] = access_expires_at
        record["enc"] = self.encrypts_at_rest
        # keepttl: preserve the session's remaining lifetime. Rotating the
        # tokens is NOT activity — sliding-TTL is `refresh_ttl`'s job — so the
        # absolute expiry must not move here.
        await client.set(self._key(session_id), json.dumps(record), keepttl=True)

    async def _read_record(self, session_id: str) -> Optional[dict]:
        """GET + JSON-decode the raw record; ``None`` if absent/expired/corrupt."""
        client = self._get_client()
        raw = await client.get(self._key(session_id))
        if raw is None:
            # Absent OR expired (Redis evicted the key) — both are "no session".
            return None
        try:
            return json.loads(raw)
        except (ValueError, TypeError):
            # Corrupt record — treat as no session rather than 500.
            return None


__all__ = ["RedisSessionStore"]
