"""Provider-neutral realtime event bus — the platform's first realtime
transport (`KB § PATTERNS/common/realtime-sse-bus.md`).

Any live surface (WhatsApp/Instagram DM inbox, in-app chat, presence,
notifications) publishes onto a `scope` string (an opaque per-consumer
channel key, e.g. `"wa:conn:{id}"`) and every subscriber for that scope
receives every event in order — including ones published while it was
disconnected, via `last_event_id` resume.

**Redis Streams, not bare pub/sub.** `RedisRealtimeBus` uses `XADD` /
`XREAD` against the SAME Redis the fleet already runs (chatbot buffer +
webhook dedup + rate limiter — see `noctusai_lib.domain.chatbot.buffer`
and `noctusai_lib.integrations.whatsapp.dedup`), not a second client
path. Bare Redis pub/sub drops every message published while a
subscriber is disconnected — that defeats the whole reconnect/resume
story an SSE inbox needs. A Stream is an append-only, ID-addressable log
`XREAD <id>` can resume from; `XADD ... MAXLEN ~ N` caps growth so a
scope with a permanently-absent subscriber can't grow it unbounded.

Mirrors `KB § PATTERNS/backend/seed-fake-real-adapter.md`: Protocol +
Fake + Real + factory, the same shape as `dedup.WebhookDedup` /
`buffer.RedisBufferClient`. `FakeRealtimeBus` is full-parity in-memory
(no network) — usable in tests without Redis, and exercised by the same
conformance suite as the Real bus (see `tests/realtime/test_bus.py`).
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any, AsyncIterator, Protocol, runtime_checkable

_DEFAULT_KEY_PREFIX = "rt:"
_DEFAULT_STREAM_MAXLEN = 1000
_DEFAULT_POLL_BLOCK_MS = 20_000  # XREAD BLOCK per poll — bounds the leaked
# background thread on disconnect (see RedisRealtimeBus docstring) while
# staying well under typical proxy/LB idle timeouts.


@dataclass(frozen=True)
class RealtimeEvent:
    """One event on the bus. `id` is monotonic + sortable within a scope,
    shaped `f"{unix_ms}-{seq}"` — identical in shape to a Redis Stream ID
    (Redis generates it natively via `XADD ... id="*"`; `FakeRealtimeBus`
    replicates the same `<ms>-<seq>` algorithm via `_MonotonicIdGenerator`
    so Fake and Real ids are indistinguishable in shape)."""

    id: str
    event: str
    payload: dict[str, Any]


@runtime_checkable
class RealtimeBus(Protocol):
    """The provider-neutral realtime transport seam. Every live surface —
    WhatsApp DMs, Instagram DMs, in-app chat, presence — publishes onto a
    `scope` and every subscriber to that `scope` sees every event, in
    order, including a `subscribe(..., last_event_id=...)` resume across
    a disconnect. The seed does NOT know what a `scope` means (a WAHA
    connection id, a conversation id, a user id) — that's the consumer's
    concern; the bus only orders + delivers.
    """

    async def publish(self, scope: str, event: str, payload: dict[str, Any]) -> str:
        """Append an event to `scope`. Returns the assigned event id."""
        ...

    def subscribe(
        self, scope: str, *, last_event_id: str | None = None
    ) -> AsyncIterator[RealtimeEvent]:
        """Yield every event for `scope`, in order, forever (until the
        caller stops iterating / closes the generator).

        `last_event_id=None` → live-tail only: catch every event
        published *after* the subscribe call, nothing buffered before it
        (the "$": Redis's own "only new" cursor).

        `last_event_id=<id>` → resume: first replays every buffered event
        with `id > last_event_id` (the reconnect gap), then continues
        live. No duplicates, no loss, as long as the gap is still inside
        the stream's `maxlen` window.
        """
        ...


def _parse_event_id(event_id: str) -> tuple[int, int]:
    ms_str, _, seq_str = event_id.partition("-")
    return int(ms_str), int(seq_str or "0")


def _event_id_gt(candidate: str, cursor: str | None) -> bool:
    """True when `candidate` is strictly newer than `cursor`. `cursor is
    None` means "everything is newer" (used for the live-tail-from-start
    case where no cursor has been established yet)."""
    if cursor is None:
        return True
    return _parse_event_id(candidate) > _parse_event_id(cursor)


class _MonotonicIdGenerator:
    """Redis-Stream-style `<ms>-<seq>` id generator: monotonic within one
    generator instance, sequence resets when the millisecond advances,
    increments when two ids would otherwise collide within the same
    millisecond. Mirrors Redis's own `XADD ... id="*"` algorithm so
    `FakeRealtimeBus` ids are shape-identical to `RedisRealtimeBus` ids —
    required for Fake/Real parity tests to assert on id ORDERING, not
    just id presence."""

    def __init__(self) -> None:
        self._last_ms = 0
        self._last_seq = -1

    def next_id(self) -> str:
        ms = int(time.time() * 1000)
        if ms > self._last_ms:
            self._last_ms = ms
            self._last_seq = 0
        else:
            self._last_seq += 1
        return f"{self._last_ms}-{self._last_seq}"


class FakeRealtimeBus:
    """In-memory `RealtimeBus` — the Fake half. Deterministic, no
    network, full parity with `RedisRealtimeBus` (same id shape, same
    resume semantics, same `maxlen` cap). Used in tests and as the
    dev/local fallback when no Redis client is configured.

    One `asyncio.Condition` per scope: `publish` appends under the lock
    and `notify_all`s; `subscribe` waits on it when there's nothing new
    yet — no busy-polling, matching `RedisRealtimeBus`'s `XREAD BLOCK`
    behavior (which sleeps inside Redis rather than spinning)."""

    def __init__(self, *, maxlen: int = _DEFAULT_STREAM_MAXLEN) -> None:
        self._maxlen = maxlen
        self._streams: dict[str, list[RealtimeEvent]] = {}
        self._conditions: dict[str, asyncio.Condition] = {}
        self._id_generators: dict[str, _MonotonicIdGenerator] = {}

    def _condition_for(self, scope: str) -> asyncio.Condition:
        cond = self._conditions.get(scope)
        if cond is None:
            cond = asyncio.Condition()
            self._conditions[scope] = cond
        return cond

    def _id_generator_for(self, scope: str) -> _MonotonicIdGenerator:
        gen = self._id_generators.get(scope)
        if gen is None:
            gen = _MonotonicIdGenerator()
            self._id_generators[scope] = gen
        return gen

    async def publish(self, scope: str, event: str, payload: dict[str, Any]) -> str:
        cond = self._condition_for(scope)
        async with cond:
            event_id = self._id_generator_for(scope).next_id()
            record = RealtimeEvent(id=event_id, event=event, payload=payload)
            buf = self._streams.setdefault(scope, [])
            buf.append(record)
            if len(buf) > self._maxlen:
                del buf[: len(buf) - self._maxlen]
            cond.notify_all()
        return event_id

    async def subscribe(
        self, scope: str, *, last_event_id: str | None = None
    ) -> AsyncIterator[RealtimeEvent]:
        cond = self._condition_for(scope)
        async with cond:
            if last_event_id is not None:
                cursor: str | None = last_event_id
            else:
                buf = self._streams.get(scope, [])
                cursor = buf[-1].id if buf else None
        while True:
            async with cond:
                buf = self._streams.get(scope, ())
                pending = [e for e in buf if _event_id_gt(e.id, cursor)]
                if not pending:
                    await cond.wait()
                    continue
            for record in pending:
                cursor = record.id
                yield record


@runtime_checkable
class StreamRedis(Protocol):
    """The minimal (sync) redis-py surface `RedisRealtimeBus` needs —
    `XADD` / `XREAD`. `redis.Redis` from `redis-py` satisfies this
    naturally; tests use `noctusai_lib.integrations.redis.make_fake_redis_client()`
    (fakeredis), matching the `SetnxRedis` / `RedisBufferClient`
    convention per `KB § PATTERNS/backend/seed-fake-real-adapter.md`."""

    def xadd(
        self,
        name: str,
        fields: dict[str, str],
        id: str = "*",
        maxlen: int | None = None,
        approximate: bool = True,
    ) -> Any: ...

    def xread(
        self,
        streams: dict[str, str],
        count: int | None = None,
        block: int | None = None,
    ) -> Any: ...


def _decode(value: Any) -> str:
    """redis-py returns `str` when `decode_responses=True` (the seed's
    `make_redis_client` default) and `bytes` otherwise — normalize."""
    return value.decode() if isinstance(value, bytes) else value


class RedisRealtimeBus:
    """Redis-Streams-backed `RealtimeBus` — the Real half.

    Uses `XADD`/`XREAD` (never bare pub/sub — see module docstring) so
    `last_event_id` resume actually replays the reconnect gap.
    `XADD ... maxlen=N approximate=True` caps stream length so a scope
    with no active subscriber can't grow it unbounded.

    The underlying redis client is SYNC (`redis-py`'s default — the same
    client shape `dedup.RedisWebhookDedup` / `buffer.ConversationBufferService`
    already use against the ONE fleet Redis URL; this bus does not open a
    second client path). Every blocking call is dispatched via
    `asyncio.to_thread` so it never stalls the event loop; `XREAD
    BLOCK=<poll_block_ms>` itself sleeps efficiently inside Redis rather
    than busy-polling from our side.

    Trade-off, documented (not a silent gap): `asyncio.to_thread`
    schedules the blocking `XREAD` on a worker thread. If the awaiting
    task is cancelled (client disconnect) while that thread is mid-block,
    the OS thread cannot be preempted — it keeps blocking until Redis
    returns (bounded by `poll_block_ms`, default 20s) and its result is
    then simply discarded. No Redis-side subscription state is held
    (XREAD is a stateless poll, not a subscription) so nothing leaks past
    that bound.
    """

    def __init__(
        self,
        redis_client: StreamRedis,
        *,
        key_prefix: str = _DEFAULT_KEY_PREFIX,
        maxlen: int = _DEFAULT_STREAM_MAXLEN,
        poll_block_ms: int = _DEFAULT_POLL_BLOCK_MS,
    ) -> None:
        self._redis = redis_client
        self._prefix = key_prefix
        self._maxlen = maxlen
        self._poll_block_ms = poll_block_ms

    def _key(self, scope: str) -> str:
        return f"{self._prefix}{scope}"

    async def publish(self, scope: str, event: str, payload: dict[str, Any]) -> str:
        fields = {
            "event": event,
            "payload": json.dumps(payload, separators=(",", ":"), default=str),
        }
        raw_id = await asyncio.to_thread(
            self._redis.xadd,
            self._key(scope),
            fields,
            id="*",
            maxlen=self._maxlen,
            approximate=True,
        )
        return _decode(raw_id)

    async def subscribe(
        self, scope: str, *, last_event_id: str | None = None
    ) -> AsyncIterator[RealtimeEvent]:
        key = self._key(scope)
        cursor = last_event_id if last_event_id is not None else "$"
        while True:
            result = await asyncio.to_thread(
                self._redis.xread,
                {key: cursor},
                count=None,
                block=self._poll_block_ms,
            )
            if not result:
                # XREAD BLOCK timed out with nothing new — poll again.
                # "$" is safe to re-issue: it re-resolves to "current
                # stream tail" each call, so re-using it across empty
                # polls cannot skip anything that hasn't been consumed.
                continue
            for _stream_key, entries in result:
                for raw_id, raw_fields in entries:
                    event_id = _decode(raw_id)
                    fields = {_decode(k): _decode(v) for k, v in dict(raw_fields).items()}
                    cursor = event_id
                    yield RealtimeEvent(
                        id=event_id,
                        event=fields["event"],
                        payload=json.loads(fields["payload"]),
                    )


def get_realtime_bus(
    redis_url: str | None = None,
    *,
    redis_client: StreamRedis | None = None,
    key_prefix: str = _DEFAULT_KEY_PREFIX,
    maxlen: int = _DEFAULT_STREAM_MAXLEN,
    poll_block_ms: int = _DEFAULT_POLL_BLOCK_MS,
) -> RealtimeBus:
    """Return `RedisRealtimeBus` when a Redis client/url is supplied;
    `FakeRealtimeBus` otherwise. Mirrors `get_webhook_dedup()`'s
    configured-vs-not factory shape per
    `KB § PATTERNS/backend/seed-fake-real-adapter.md`.

    Pass `redis_client` to reuse an already-constructed client — the
    fleet convention is ONE `redis.Redis` per process, shared across
    dedup / buffer / bus, built once via `make_redis_client(settings.redis_url)`
    in the product's `configure_*_module`. `redis_url` is a convenience
    for callers that don't already hold a client (constructs one lazily
    via the seed's own `noctusai_lib.integrations.redis.make_redis_client`
    — never a bespoke client path)."""
    client = redis_client
    if client is None and redis_url:
        from noctusai_lib.integrations.redis import make_redis_client

        client = make_redis_client(redis_url)
    if client is None:
        return FakeRealtimeBus(maxlen=maxlen)
    return RedisRealtimeBus(
        client, key_prefix=key_prefix, maxlen=maxlen, poll_block_ms=poll_block_ms
    )
