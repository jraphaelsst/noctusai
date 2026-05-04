"""Redis-backed conversation buffer + debounce + idle-timeout.

Ported from
`whatsapp-google-scheduling/app/services/conversation_buffer_service.py`
2026-05-03 via `projects/whatsapp-seed-absorption/`. Redis key names,
TTL defaults, debounce semantics preserved exactly so the upstream
test suite ports without behavioral changes.

Provider-agnostic — channel-neutral by design. The connector
(`noctusai_lib.integrations.whatsapp` for WAHA today, Twilio / Cloud
API tomorrow) feeds messages in via `buffer_inbound`; the worker
(`domain/chatbot/worker.py`) drains via `claim_due_conversations`.

Debounce-race mitigation (2026-05-03): the old `due_conversations`
+ `mark_conversation_claimed` two-step had a documented race — a new
inbound between read and claim would bump the due score past `now`,
but the worker would blindly `zrem` and dispatch on a still-debouncing
conversation. New `claim_due_conversations` re-checks the score
immediately before `zrem` and leaves bumped entries for the next pass.
Residual TOCTOU window (microseconds between `zscore` and `zrem`) is
acceptable for chat scheduling; swap to a Lua script if strict
atomicity is ever required. Legacy `due_conversations` +
`mark_conversation_claimed` retained for backwards compatibility.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class RedisBufferClient(Protocol):
    """The Redis surface the buffer uses. `redis.Redis` from `redis-py`
    satisfies this naturally; tests use an in-memory `FakeRedis`.

    `@runtime_checkable` so consumers can `isinstance(client, RedisBufferClient)`
    in tests — matches the convention `WhatsAppClient`, `CalendarAdapter`,
    `RoutingAdapter` follow per `KB § PATTERNS/seed-fake-real-adapter.md`.
    """

    def rpush(self, name: str, *values: str) -> int: ...

    def ltrim(self, name: str, start: int, end: int) -> bool: ...

    def expire(self, name: str, time: int) -> bool: ...

    def lrange(self, name: str, start: int, end: int) -> list[str]: ...

    def delete(self, *names: str) -> int: ...

    def xadd(
        self,
        name: str,
        fields: dict[str, str],
        id: str = "*",
        maxlen: int | None = None,
        approximate: bool = True,
    ) -> str: ...

    def zadd(self, name: str, mapping: dict[str, float]) -> int: ...

    def zrangebyscore(
        self,
        name: str,
        min: float | str,
        max: float | str,
        start: int | None = None,
        num: int | None = None,
    ) -> list[str]: ...

    def zrem(self, name: str, *values: str) -> int: ...

    def zscore(self, name: str, value: str) -> float | None: ...


def make_in_memory_buffer_client() -> RedisBufferClient:
    """Return a Protocol-compatible in-memory buffer client (no network).

    Thin wrapper around `noctusai_lib.integrations.redis.make_fake_redis_client()`
    — re-exported here for the import-shortcut UX. Tests + dev paths can do
    `from noctusai_lib.domain.chatbot import make_in_memory_buffer_client`
    instead of remembering it lives in the redis integration.

    Per `KB § PATTERNS/seed-fake-real-adapter.md` — every IO-touching seed
    module ships a Fake. `domain.chatbot.buffer` is IO-touching via Redis,
    so it gets one too.
    """
    from noctusai_lib.integrations.redis import make_fake_redis_client

    return make_fake_redis_client()


@dataclass(frozen=True)
class QueuedConversationMessage:
    """One message in a conversation. `direction` is `"inbound"` or
    `"outbound"` (consumer-defined values; the buffer doesn't enforce a
    schema, but the worker's dispatcher reads this to decide whether to
    feed it to the LLM as a user / assistant turn)."""

    conversation_id: str
    text: str
    direction: str
    provider_message_id: str | None = None
    user_id: int | None = None
    timestamp: float | None = None
    metadata: dict[str, Any] | None = None


class ConversationBufferService:
    """Redis-backed conversation memory + debounce + idle queue.

    Three sorted sets + one stream + N lists (one per conversation):
    - `conversation:memory:{id}` — RPUSH list of JSON-encoded messages,
      capped to `max_memory_messages`, expires after `memory_ttl_seconds`.
    - `queue:conversation_messages` — XADD stream of every message
      (audit + downstream consumers).
    - `queue:conversation_due` — ZSET of conversations awaiting a reply;
      score = now + `debounce_seconds`. Worker reads via
      `due_conversations(now)` returning IDs with score ≤ now.
    - `queue:conversation_idle_due` — ZSET for idle-timeout sweeping
      (e.g. summary generation); score = now + `idle_timeout_seconds`.

    Stateless beyond the Redis client. Safe to share across requests.
    """

    memory_prefix = "conversation:memory"
    stream_key = "queue:conversation_messages"
    due_set_key = "queue:conversation_due"
    idle_due_set_key = "queue:conversation_idle_due"

    def __init__(
        self,
        redis_client: RedisBufferClient,
        memory_ttl_seconds: int = 3600,
        debounce_seconds: int = 8,
        idle_timeout_seconds: int = 1800,
        stream_maxlen: int = 10_000,
        max_memory_messages: int = 80,
    ):
        self.redis = redis_client
        self.memory_ttl_seconds = memory_ttl_seconds
        self.debounce_seconds = debounce_seconds
        self.idle_timeout_seconds = idle_timeout_seconds
        self.stream_maxlen = stream_maxlen
        self.max_memory_messages = max_memory_messages

    def buffer_inbound(
        self,
        message: QueuedConversationMessage,
        trigger_reply: bool = True,
    ) -> str:
        """Append an inbound message to memory + stream, schedule
        debounce reply (unless `trigger_reply=False` — e.g. media-only
        message that should buffer but not trigger LLM call), bump
        idle-timeout. Returns the stream ID."""
        timestamp = message.timestamp or time.time()
        normalized = (
            message
            if message.timestamp
            else QueuedConversationMessage(
                conversation_id=message.conversation_id,
                text=message.text,
                direction=message.direction,
                provider_message_id=message.provider_message_id,
                user_id=message.user_id,
                timestamp=timestamp,
                metadata=message.metadata,
            )
        )

        self._append_memory(normalized)
        stream_id = self._enqueue_message(normalized)
        if trigger_reply:
            self.redis.zadd(
                self.due_set_key,
                {message.conversation_id: timestamp + self.debounce_seconds},
            )
        self.redis.zadd(
            self.idle_due_set_key,
            {message.conversation_id: timestamp + self.idle_timeout_seconds},
        )
        return stream_id

    def append_to_memory(self, message: QueuedConversationMessage) -> None:
        """Append a message to memory (typically outbound — bot reply)
        without triggering a reply debounce. Bumps idle-timeout."""
        timestamp = message.timestamp or time.time()
        normalized = (
            message
            if message.timestamp
            else QueuedConversationMessage(
                conversation_id=message.conversation_id,
                text=message.text,
                direction=message.direction,
                provider_message_id=message.provider_message_id,
                user_id=message.user_id,
                timestamp=timestamp,
                metadata=message.metadata,
            )
        )
        self._append_memory(normalized)
        self.redis.zadd(
            self.idle_due_set_key,
            {message.conversation_id: timestamp + self.idle_timeout_seconds},
        )

    def memory_for(self, conversation_id: str) -> list[dict[str, Any]]:
        """Return the conversation's memory as a list of payload dicts
        (JSON-decoded). Excludes stream/queue metadata."""
        raw_items = self.redis.lrange(self._memory_key(conversation_id), 0, -1)
        return [json.loads(item) for item in raw_items]

    def due_conversations(self, now: float | None = None, limit: int = 25) -> list[str]:
        """IDs whose debounce timer has fired (score ≤ now).

        Legacy two-step pull (paired with `mark_conversation_claimed`).
        Prefer `claim_due_conversations` — it closes the race window where
        a late inbound bumped the score but the worker zrem'd anyway.
        Kept for backwards compatibility."""
        score = now if now is not None else time.time()
        return self.redis.zrangebyscore(self.due_set_key, "-inf", score, start=0, num=limit)

    def claim_due_conversations(
        self, now: float | None = None, limit: int = 25
    ) -> list[str]:
        """Pull-and-claim due conversations with score recheck.

        Race fix vs legacy `due_conversations` + `mark_conversation_claimed`:
        between the zrangebyscore and the zrem, a new inbound's `zadd`
        may bump the score past `now`. We re-check `zscore` immediately
        before `zrem` and skip entries whose score is no longer ≤ now —
        they're left for the next worker tick once their (new) debounce
        fires. Residual TOCTOU between zscore and zrem is microseconds;
        for strict atomicity wrap in a Lua script.

        Returns the IDs that were both due AND successfully claimed."""
        score = now if now is not None else time.time()
        candidates = self.redis.zrangebyscore(
            self.due_set_key, "-inf", score, start=0, num=limit
        )
        claimed: list[str] = []
        for conversation_id in candidates:
            current = self.redis.zscore(self.due_set_key, conversation_id)
            if current is None or current > score:
                # Bumped past `now` between zrangebyscore and zscore —
                # leave for next pass.
                continue
            if self.redis.zrem(self.due_set_key, conversation_id) > 0:
                claimed.append(conversation_id)
        return claimed

    def idle_conversations(self, now: float | None = None, limit: int = 25) -> list[str]:
        """IDs whose idle-timeout has fired (score ≤ now). Worker may
        invoke summary / cleanup."""
        score = now if now is not None else time.time()
        return self.redis.zrangebyscore(
            self.idle_due_set_key, "-inf", score, start=0, num=limit
        )

    def mark_conversation_claimed(self, conversation_id: str) -> None:
        """Remove from the due set after the worker has claimed it.
        Idempotent. Idle-due set is NOT touched (separate concern)."""
        self.redis.zrem(self.due_set_key, conversation_id)

    def clear_conversation(self, conversation_id: str) -> None:
        """Forget a conversation entirely — drop memory + both queues.
        Used for explicit reset or post-summary cleanup."""
        self.redis.delete(self._memory_key(conversation_id))
        self.redis.zrem(self.due_set_key, conversation_id)
        self.redis.zrem(self.idle_due_set_key, conversation_id)

    # --- private --------------------------------------------------------

    def _append_memory(self, message: QueuedConversationMessage) -> None:
        key = self._memory_key(message.conversation_id)
        self.redis.rpush(
            key, json.dumps(self._memory_payload(message), separators=(",", ":"))
        )
        self.redis.ltrim(key, -self.max_memory_messages, -1)
        self.redis.expire(key, self.memory_ttl_seconds)

    def _enqueue_message(self, message: QueuedConversationMessage) -> str:
        fields: dict[str, str] = {
            "conversation_id": message.conversation_id,
            "direction": message.direction,
            "text": message.text,
            "timestamp": str(message.timestamp or time.time()),
        }
        if message.provider_message_id:
            fields["provider_message_id"] = message.provider_message_id
        if message.user_id is not None:
            fields["user_id"] = str(message.user_id)
        if message.metadata:
            fields["metadata"] = json.dumps(message.metadata, separators=(",", ":"))

        return self.redis.xadd(
            self.stream_key,
            fields,
            maxlen=self.stream_maxlen,
            approximate=True,
        )

    def _memory_payload(self, message: QueuedConversationMessage) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "direction": message.direction,
            "text": message.text,
            "timestamp": message.timestamp,
        }
        if message.provider_message_id:
            payload["provider_message_id"] = message.provider_message_id
        if message.user_id is not None:
            payload["user_id"] = message.user_id
        if message.metadata:
            payload["metadata"] = message.metadata
        return payload

    def _memory_key(self, conversation_id: str) -> str:
        return f"{self.memory_prefix}:{conversation_id}"
