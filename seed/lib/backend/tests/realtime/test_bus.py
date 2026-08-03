"""`RealtimeBus` conformance suite — runs identically against
`FakeRealtimeBus` and `RedisRealtimeBus` (backed by `fakeredis` via
`make_fake_redis_client`, matching the `test_dedup.py` / `test_router.py`
convention of exercising the Real code path without a live Redis
server).

Covers: publish→subscribe roundtrip, resume-from-`last_event_id`
delivers the reconnect gap with no duplicates/no loss, live-tail-only
when no `last_event_id`, `maxlen` capping, and that both halves satisfy
the `RealtimeBus` Protocol.
"""

from __future__ import annotations

import asyncio

import pytest

from noctusai_lib.integrations.redis import make_fake_redis_client
from noctusai_lib.realtime import (
    FakeRealtimeBus,
    RealtimeBus,
    RedisRealtimeBus,
    get_realtime_bus,
)


def _fake_bus() -> RealtimeBus:
    return FakeRealtimeBus()


def _redis_bus() -> RealtimeBus:
    # poll_block_ms kept small — fakeredis's blocking XREAD sleeps for
    # real, and the conformance suite asserts on prompt delivery.
    return RedisRealtimeBus(make_fake_redis_client(), poll_block_ms=200)


BUS_FACTORIES = [_fake_bus, _redis_bus]
BUS_IDS = ["fake", "redis"]


async def _collect(bus: RealtimeBus, scope: str, count: int, **kwargs):
    """Pull exactly `count` events off `bus.subscribe(scope, **kwargs)`,
    bounded by a timeout so a bug that stops delivery fails fast instead
    of hanging the suite. `asyncio.wait_for` (not `asyncio.timeout` —
    3.11+ only; the seed targets `>=3.9`)."""

    async def _drain():
        subscription = bus.subscribe(scope, **kwargs)
        collected = []
        try:
            while len(collected) < count:
                collected.append(await subscription.__anext__())
        finally:
            await subscription.aclose()
        return collected

    return await asyncio.wait_for(_drain(), timeout=5)


@pytest.mark.asyncio
@pytest.mark.parametrize("make_bus", BUS_FACTORIES, ids=BUS_IDS)
async def test_publish_then_subscribe_roundtrip(make_bus) -> None:
    bus = make_bus()
    scope = "wa:conn:1"

    async def publisher():
        await asyncio.sleep(0.05)  # let the subscriber attach first
        await bus.publish(scope, "message.new", {"text": "oi"})

    subscribe_task = asyncio.create_task(_collect(bus, scope, 1))
    await publisher()
    events = await subscribe_task

    assert len(events) == 1
    assert events[0].event == "message.new"
    assert events[0].payload == {"text": "oi"}
    assert events[0].id  # non-empty, assigned by the bus


@pytest.mark.asyncio
@pytest.mark.parametrize("make_bus", BUS_FACTORIES, ids=BUS_IDS)
async def test_resume_from_last_event_id_delivers_gap_no_dup_no_loss(make_bus) -> None:
    bus = make_bus()
    scope = "wa:conn:resume"

    first_id = await bus.publish(scope, "message.new", {"seq": 1})
    # subscriber "was disconnected" here — misses nothing published
    # before or after this point until it resumes below.
    second_id = await bus.publish(scope, "message.new", {"seq": 2})
    third_id = await bus.publish(scope, "message.new", {"seq": 3})

    resumed = await _collect(bus, scope, 2, last_event_id=first_id)

    assert [e.id for e in resumed] == [second_id, third_id]
    assert [e.payload["seq"] for e in resumed] == [2, 3]
    # no duplicate of the id we resumed FROM
    assert first_id not in [e.id for e in resumed]


@pytest.mark.asyncio
@pytest.mark.parametrize("make_bus", BUS_FACTORIES, ids=BUS_IDS)
async def test_no_last_event_id_is_live_tail_only(make_bus) -> None:
    bus = make_bus()
    scope = "wa:conn:live"

    await bus.publish(scope, "message.new", {"seq": "before"})

    async def publisher():
        await asyncio.sleep(0.05)
        await bus.publish(scope, "message.new", {"seq": "after"})

    subscribe_task = asyncio.create_task(_collect(bus, scope, 1))
    await publisher()
    events = await subscribe_task

    assert len(events) == 1
    assert events[0].payload == {"seq": "after"}


@pytest.mark.asyncio
@pytest.mark.parametrize("make_bus", BUS_FACTORIES, ids=BUS_IDS)
async def test_event_ids_are_monotonically_sortable(make_bus) -> None:
    bus = make_bus()
    scope = "wa:conn:order"

    ids = [await bus.publish(scope, "message.new", {"seq": i}) for i in range(5)]

    def _key(event_id: str) -> tuple[int, int]:
        ms, _, seq = event_id.partition("-")
        return int(ms), int(seq)

    assert ids == sorted(ids, key=_key)
    assert len(set(ids)) == 5  # no id collisions


@pytest.mark.asyncio
async def test_fake_bus_maxlen_caps_stream_length() -> None:
    bus = FakeRealtimeBus(maxlen=3)
    scope = "wa:conn:capped"

    for i in range(10):
        await bus.publish(scope, "message.new", {"seq": i})

    assert len(bus._streams[scope]) == 3
    assert [e.payload["seq"] for e in bus._streams[scope]] == [7, 8, 9]


class _RecordingRedis:
    """Records `xadd`/`xread` call kwargs — used to assert
    `RedisRealtimeBus` forwards the stream-cap contract (`MAXLEN ~ N`)
    correctly without depending on fakeredis's own trim precision
    (`approximate=True` is a hint real Redis is allowed to over-retain
    for; asserting exact post-trim length against it would test
    fakeredis, not our wiring)."""

    def __init__(self) -> None:
        self.xadd_calls: list[dict] = []
        self.xread_calls: list[dict] = []

    def xadd(self, name, fields, id="*", maxlen=None, approximate=True):
        self.xadd_calls.append(
            {"name": name, "fields": fields, "id": id, "maxlen": maxlen, "approximate": approximate}
        )
        return f"{len(self.xadd_calls)}-0"

    def xread(self, streams, count=None, block=None):
        self.xread_calls.append({"streams": streams, "count": count, "block": block})
        return []


@pytest.mark.asyncio
async def test_redis_bus_forwards_maxlen_and_approximate_to_xadd() -> None:
    redis = _RecordingRedis()
    bus = RedisRealtimeBus(redis, maxlen=250)

    await bus.publish("wa:conn:x", "message.new", {"text": "hi"})

    assert redis.xadd_calls == [
        {
            "name": "rt:wa:conn:x",
            "fields": {"event": "message.new", "payload": '{"text":"hi"}'},
            "id": "*",
            "maxlen": 250,
            "approximate": True,
        }
    ]


@pytest.mark.asyncio
async def test_redis_bus_subscribe_uses_dollar_cursor_when_no_last_event_id() -> None:
    redis = _RecordingRedis()
    bus = RedisRealtimeBus(redis, poll_block_ms=10)
    subscription = bus.subscribe("wa:conn:x")

    task = asyncio.ensure_future(subscription.__anext__())
    await asyncio.sleep(0.05)  # let at least one poll happen
    task.cancel()
    try:
        await task
    except (asyncio.CancelledError, StopAsyncIteration):
        pass
    await subscription.aclose()

    assert redis.xread_calls
    assert redis.xread_calls[0]["streams"] == {"rt:wa:conn:x": "$"}
    assert redis.xread_calls[0]["block"] == 10


def test_both_halves_satisfy_realtime_bus_protocol() -> None:
    assert isinstance(FakeRealtimeBus(), RealtimeBus)
    assert isinstance(RedisRealtimeBus(make_fake_redis_client()), RealtimeBus)


def test_factory_returns_fake_without_redis_real_with_redis() -> None:
    assert isinstance(get_realtime_bus(), FakeRealtimeBus)
    assert isinstance(
        get_realtime_bus(redis_client=make_fake_redis_client()), RedisRealtimeBus
    )
