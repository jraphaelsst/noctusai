"""`sse_event_stream` (framework-agnostic core) + `create_sse_router`
(FastAPI factory) tests.

`sse_event_stream` is tested directly against `_SpyBus` doubles with an
injected `is_disconnected` predicate — deterministic, no ASGI transport
timing races.

Router-level tests use `fastapi.testclient.TestClient` with a
`_FiniteBus` double whose `subscribe()` yields its fixed events and then
simply RETURNS (instead of hanging live-tail-forever like the real
Fake/Redis buses do). This isn't a test shortcut around the disconnect
story — it's a hard constraint of the harness: both `TestClient`
(`portal.call(self.app, ...)`, which blocks until the ASGI call fully
completes) and `httpx.AsyncClient(transport=ASGITransport(...))`
(`await self.app(...)` inline) fully DRIVE the ASGI response to
completion before handing anything back to the test — neither supports
reading a genuinely-never-ending stream incrementally then bailing.
Disconnect/heartbeat behavior against an infinite stream is exactly what
the `sse_event_stream` + `_SpyBus` tests above already cover directly;
the router tests below are scoped to what they CAN verify end-to-end:
headers, frame format, and the Last-Event-ID / `?since=` / auth→scope
wiring.
"""

from __future__ import annotations

import asyncio
import json

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from noctusai_lib.realtime import RealtimeEvent, create_sse_router
from noctusai_lib.realtime.sse import sse_event_stream


class _SpyBus:
    """A `RealtimeBus` double that records whether its `subscribe`
    generator was properly unwound (`aclose`d / hit `GeneratorExit`) —
    the direct check for "no leaked subscription" on disconnect."""

    def __init__(self, events: list[RealtimeEvent] | None = None) -> None:
        self._events = events or []
        self.aclose_called = False
        self.subscribe_calls: list[tuple[str, str | None]] = []

    async def publish(self, scope: str, event: str, payload: dict) -> str:
        raise NotImplementedError("not used by these tests")

    async def subscribe(self, scope: str, *, last_event_id: str | None = None):
        self.subscribe_calls.append((scope, last_event_id))
        try:
            for record in self._events:
                yield record
                await asyncio.sleep(0)
            # Then behave like a live bus with nothing further to deliver
            # — hangs until cancelled/closed, exactly like the real
            # Fake/Redis buses waiting on their next event.
            never = asyncio.Event()
            await never.wait()
        finally:
            self.aclose_called = True


class _FiniteBus:
    """A `RealtimeBus` double whose `subscribe()` yields its buffered
    events (filtered by `last_event_id`, same semantics as the real
    buses) and then simply ENDS — no live-tail. Only used to make a
    router-level `TestClient` request naturally terminate; see module
    docstring for why."""

    def __init__(self, events: list[RealtimeEvent]) -> None:
        self._events = events

    async def publish(self, scope: str, event: str, payload: dict) -> str:
        raise NotImplementedError("seed events at construction instead")

    async def subscribe(self, scope: str, *, last_event_id: str | None = None):
        from noctusai_lib.realtime.bus import _event_id_gt

        for record in self._events:
            if _event_id_gt(record.id, last_event_id):
                yield record


async def _disconnect_after(n: int):
    calls = {"count": 0}

    async def _check() -> bool:
        calls["count"] += 1
        return calls["count"] > n

    return _check


@pytest.mark.asyncio
async def test_sse_event_stream_formats_events_and_stops_on_disconnect() -> None:
    events = [
        RealtimeEvent(id="1700000000000-0", event="message.new", payload={"text": "oi"}),
        RealtimeEvent(id="1700000000000-1", event="message.ack", payload={"id": "m1"}),
    ]
    bus = _SpyBus(events)
    is_disconnected = await _disconnect_after(3)

    frames = [
        frame
        async for frame in sse_event_stream(
            bus,
            "wa:conn:1",
            heartbeat_seconds=100,  # long enough that no heartbeat fires
            is_disconnected=is_disconnected,
            disconnect_poll_seconds=0.01,
        )
    ]

    assert frames == [
        "id: 1700000000000-0\nevent: message.new\ndata: {\"text\":\"oi\"}\n\n",
        "id: 1700000000000-1\nevent: message.ack\ndata: {\"id\":\"m1\"}\n\n",
    ]
    assert bus.aclose_called is True  # no leaked subscription
    assert bus.subscribe_calls == [("wa:conn:1", None)]


@pytest.mark.asyncio
async def test_sse_event_stream_emits_heartbeat_when_idle() -> None:
    bus = _SpyBus()  # no events — pure idle/live-tail
    is_disconnected = await _disconnect_after(4)

    frames = [
        frame
        async for frame in sse_event_stream(
            bus,
            "wa:conn:idle",
            heartbeat_seconds=0.01,
            is_disconnected=is_disconnected,
            disconnect_poll_seconds=0.01,
        )
    ]

    assert frames  # at least one heartbeat tick fired before disconnect
    assert all(frame == ": heartbeat\n\n" for frame in frames)
    assert bus.aclose_called is True


@pytest.mark.asyncio
async def test_sse_event_stream_cleans_up_when_caller_closes_generator_early() -> None:
    """Covers the OTHER disconnect path: the ASGI server simply stops
    iterating (calls `.aclose()` on our generator) rather than us
    observing `is_disconnected() -> True` first — e.g. Starlette's own
    client-disconnect handling around `StreamingResponse`."""
    events = [RealtimeEvent(id="1-0", event="message.new", payload={"n": 1})]
    bus = _SpyBus(events)

    agen = sse_event_stream(bus, "wa:conn:early-close", heartbeat_seconds=100)
    first = await agen.__anext__()
    assert first.startswith("id: 1-0")

    await agen.aclose()

    assert bus.aclose_called is True


def test_router_streams_sse_headers_and_frame_format() -> None:
    bus = _FiniteBus(
        [RealtimeEvent(id="1700000000000-0", event="message.new", payload={"text": "oi"})]
    )

    async def resolve_scope(request: Request, auth_ctx) -> str:
        return "wa:conn:abc"

    app = FastAPI()
    app.include_router(
        create_sse_router(bus, scope_resolver=resolve_scope, heartbeat_seconds=100)
    )

    client = TestClient(app)
    response = client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["connection"] == "keep-alive"
    assert response.headers["x-accel-buffering"] == "no"

    frame = response.text
    assert frame == 'id: 1700000000000-0\nevent: message.new\ndata: {"text":"oi"}\n\n'
    assert json.loads(frame.split("data: ", 1)[1].strip()) == {"text": "oi"}


def test_router_resume_via_last_event_id_header_delivers_only_the_gap() -> None:
    bus = _FiniteBus(
        [
            RealtimeEvent(id="1-0", event="message.new", payload={"seq": 1}),
            RealtimeEvent(id="2-0", event="message.new", payload={"seq": 2}),
        ]
    )

    async def resolve_scope(request: Request, auth_ctx) -> str:
        return "wa:conn:resume"

    app = FastAPI()
    app.include_router(
        create_sse_router(bus, scope_resolver=resolve_scope, heartbeat_seconds=100)
    )

    client = TestClient(app)
    response = client.get("/", headers={"Last-Event-ID": "1-0"})

    assert "seq\":2" in response.text
    assert "seq\":1" not in response.text  # not re-delivered


def test_router_resume_via_since_query_param_fallback() -> None:
    bus = _FiniteBus(
        [
            RealtimeEvent(id="1-0", event="message.new", payload={"seq": 1}),
            RealtimeEvent(id="2-0", event="message.new", payload={"seq": 2}),
        ]
    )

    async def resolve_scope(request: Request, auth_ctx) -> str:
        return "wa:conn:since"

    app = FastAPI()
    app.include_router(
        create_sse_router(bus, scope_resolver=resolve_scope, heartbeat_seconds=100)
    )

    client = TestClient(app)
    response = client.get("/", params={"since": "1-0"})

    assert "seq\":2" in response.text
    assert "seq\":1" not in response.text


def test_router_last_event_id_header_wins_over_since_query_param() -> None:
    bus = _FiniteBus(
        [
            RealtimeEvent(id="1-0", event="message.new", payload={"seq": 1}),
            RealtimeEvent(id="2-0", event="message.new", payload={"seq": 2}),
            RealtimeEvent(id="3-0", event="message.new", payload={"seq": 3}),
        ]
    )

    async def resolve_scope(request: Request, auth_ctx) -> str:
        return "wa:conn:precedence"

    app = FastAPI()
    app.include_router(
        create_sse_router(bus, scope_resolver=resolve_scope, heartbeat_seconds=100)
    )

    client = TestClient(app)
    response = client.get(
        "/", params={"since": "1-0"}, headers={"Last-Event-ID": "2-0"}
    )

    assert "seq\":3" in response.text
    assert "seq\":2" not in response.text  # header (2-0), not query (1-0), won


def test_router_scope_resolver_receives_resolved_auth_dependency() -> None:
    bus = _FiniteBus([RealtimeEvent(id="1-0", event="message.new", payload={"text": "hi"})])
    seen: dict = {}

    async def fake_auth() -> dict:
        return {"org_id": "org-42"}

    async def resolve_scope(request: Request, auth_ctx: dict) -> str:
        seen["auth_ctx"] = auth_ctx
        return f"{auth_ctx['org_id']}:inbox"

    app = FastAPI()
    app.include_router(
        create_sse_router(
            bus,
            scope_resolver=resolve_scope,
            auth_dependency=fake_auth,
            heartbeat_seconds=100,
        )
    )

    client = TestClient(app)
    response = client.get("/")

    assert seen["auth_ctx"] == {"org_id": "org-42"}
    assert "hi" in response.text
