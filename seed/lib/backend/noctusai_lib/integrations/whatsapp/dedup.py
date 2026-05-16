"""Persistent webhook deduplication — Redis SETNX pre-filter.

Reconciled to the live-validated `noctusai-youtube-crawler` workspace
(workspace commits `f9839d4` "real multimodal bot" + `fedd4cf` "WAHA
media URL rewrite + early dedup"). See the in-home handoff note
`SESSION-NOTES_chatbot-multichannel-2026-05-12.md` §4.1 for the
production race this closes.

The race (production-observed, durable)
---------------------------------------
WAHA subscribes the webhook URL to BOTH ``message`` AND ``message.any``
for every inbound. The platform receives the *same* ``provider_message_id``
twice, in two HTTP calls arriving within milliseconds. Without dedup
EVERY chatbot invocation runs twice — once per event — and OpenAI cost
+ latency double silently (~$0.001 + 1-2s each).

Two-layer dedup (validated in production)
-----------------------------------------
1. **Redis SETNX pre-filter** (THIS module) — at the TOP of the webhook
   handler, before parsing / media download / OpenAI. ``SET <key>
   <ts> NX EX <ttl>`` returns truthy only for the FIRST event with a
   given ``provider_message_id``; the duplicate gets a falsy result and
   the handler returns 200 in ~25ms without touching OpenAI. Fast,
   cheap, covers the millisecond-apart race.
2. **DB ``UNIQUE(provider_message_id)`` backstop** — owned by the
   chatbot ``message_store`` seam (Engineer CHATBOT, `noctusai_lib.
   domain.chatbot`). Survives process/Redis restart: the second INSERT
   trips an ``IntegrityError`` the consumer catches. THIS module does
   NOT own the DB side — it exposes the SETNX seam and a ``WebhookDedup``
   Protocol; the consumer composes the SETNX pre-filter with the
   message-store's persistence-on-IntegrityError backstop.

The SETNX TTL is intentionally short (default 1h): it only needs to
outlive WAHA's duplicate-delivery window (milliseconds) plus a generous
margin for retries. Restart-survival is the DB backstop's job, not the
pre-filter's. A SETNX miss after Redis eviction simply falls through to
the DB UNIQUE constraint — fail-safe, never fail-open.

Mirrors `KB § PATTERNS/seed-fake-real-adapter.md`: Protocol + Fake +
Real + factory. The Fake is an in-process dict (deterministic, no
network); the Real is Redis SETNX. `redis.Redis` and the in-memory
`fakeredis.FakeStrictRedis` (via
`noctusai_lib.integrations.redis.make_fake_redis_client`) both satisfy
the `SetnxRedis` Protocol naturally.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

_DEFAULT_KEY_PREFIX = "wa:dedup:"
_DEFAULT_TTL_SECONDS = 3600  # 1h — outlives WAHA dup-delivery + retries.


@runtime_checkable
class SetnxRedis(Protocol):
    """The minimal Redis surface the SETNX pre-filter needs.

    `redis.Redis` from `redis-py` satisfies this naturally; tests use
    `fakeredis.FakeStrictRedis` via
    `noctusai_lib.integrations.redis.make_fake_redis_client()`.

    `@runtime_checkable` so consumers can `isinstance(client, SetnxRedis)`
    — matches the `RedisBufferClient` / `WhatsAppClient` convention per
    `KB § PATTERNS/seed-fake-real-adapter.md`.
    """

    def set(  # noqa: A003 - mirrors redis-py's method name
        self,
        name: str,
        value: str,
        *,
        nx: bool = False,
        ex: int | None = None,
    ) -> bool | None: ...


@runtime_checkable
class WebhookDedup(Protocol):
    """First-seen check for a webhook ``provider_message_id``.

    ``claim(message_id)`` returns ``True`` the FIRST time a given id is
    seen and ``False`` for every subsequent call within the TTL window.
    Both `RedisWebhookDedup` (real) and `InMemoryWebhookDedup` (fake)
    satisfy this Protocol. The consumer composes this fast pre-filter
    with the chatbot ``message_store`` DB ``UNIQUE`` backstop for
    restart-survival.
    """

    def claim(self, message_id: str) -> bool: ...


class InMemoryWebhookDedup:
    """Deterministic in-process dedup (no network).

    The Fake half of the Fake+Real pair. Used in tests and as the
    dev/local fallback when no Redis client is configured. NOT
    restart-safe and NOT shared across processes — that is the DB
    UNIQUE backstop's job, exactly as in production (the SETNX
    pre-filter is also process-bounded across Redis eviction).
    """

    def __init__(self) -> None:
        self._seen: set[str] = set()

    def claim(self, message_id: str) -> bool:
        if message_id in self._seen:
            return False
        self._seen.add(message_id)
        return True

    def clear(self) -> None:
        """Reset between test cases."""
        self._seen.clear()


class RedisWebhookDedup:
    """Redis SETNX-backed first-seen check.

    The Real half of the Fake+Real pair. ``SET <prefix><id> 1 NX EX
    <ttl>`` is atomic: only the first caller for a given id gets a
    truthy reply. A falsy reply (key already existed) ⇒ duplicate.
    Redis returning ``None`` for an NX collision is normalized to
    ``False``.
    """

    def __init__(
        self,
        redis_client: SetnxRedis,
        *,
        key_prefix: str = _DEFAULT_KEY_PREFIX,
        ttl_seconds: int = _DEFAULT_TTL_SECONDS,
    ) -> None:
        self._redis = redis_client
        self._prefix = key_prefix
        self._ttl = ttl_seconds

    def _key(self, message_id: str) -> str:
        return f"{self._prefix}{message_id}"

    def claim(self, message_id: str) -> bool:
        # redis-py SET ... NX returns True on set, None on NX-collision.
        result = self._redis.set(
            self._key(message_id), "1", nx=True, ex=self._ttl
        )
        return bool(result)


def get_webhook_dedup(
    *,
    redis_client: SetnxRedis | None = None,
    key_prefix: str = _DEFAULT_KEY_PREFIX,
    ttl_seconds: int = _DEFAULT_TTL_SECONDS,
) -> WebhookDedup:
    """Return `RedisWebhookDedup` when a Redis client is supplied;
    `InMemoryWebhookDedup` otherwise.

    Mirrors `get_whatsapp_client()` / `get_lid_phone_cache()` factory
    shape per `KB § PATTERNS/seed-fake-real-adapter.md`. The presence
    of a Redis client is the configured-vs-not signal.
    """
    if redis_client is None:
        return InMemoryWebhookDedup()
    return RedisWebhookDedup(
        redis_client, key_prefix=key_prefix, ttl_seconds=ttl_seconds
    )
