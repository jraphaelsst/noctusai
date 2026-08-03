"""SSE transport for `RealtimeBus` — the FastAPI-facing half of
`KB § PATTERNS/common/realtime-sse-bus.md`.

`create_sse_router(...)` is a router FACTORY (the seed convention — see
`noctusai_lib.integrations.whatsapp.router.create_whatsapp_webhook_router`
for the sibling shape): the seed does NOT know what a "scope" means (a
WAHA connection id, a conversation id, a user id) or how a caller
authenticates — both are supplied by the consumer.

    from noctusai_lib.realtime import create_sse_router, get_realtime_bus

    bus = get_realtime_bus(settings.redis_url)

    async def resolve_scope(request: Request, org) -> str:
        connection_id = request.path_params["connection_id"]
        return f"wa:conn:{connection_id}"

    app.include_router(
        create_sse_router(
            bus,
            scope_resolver=resolve_scope,
            auth_dependency=get_current_user_org,
        ),
        prefix="/realtime/whatsapp/{connection_id}",
    )

`sse_event_stream(...)` is the framework-agnostic core (bus → text
frames) — factored out of the router so it's unit-testable without a
FastAPI `TestClient`'s ASGI streaming semantics: it takes a plain
`is_disconnected: Callable[[], Awaitable[bool]]` rather than a `Request`,
so tests can simulate a disconnect deterministically instead of racing a
real transport.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import time
from typing import Any, AsyncIterator, Awaitable, Callable

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import StreamingResponse

from noctusai_lib.realtime.bus import RealtimeBus, RealtimeEvent

logger = logging.getLogger(__name__)

_DEFAULT_HEARTBEAT_SECONDS = 20.0
_DEFAULT_DISCONNECT_POLL_SECONDS = 1.0
# SSE comment line (leading `:`) — valid keep-alive per the spec, silently
# ignored by `EventSource` (no `id:`/`event:`/`data:` fields), distinguishable
# from a real `RealtimeEvent` frame by construction. Not a domain "event"
# type, so it never collides with `message.new` / `chat.upsert` / etc.
_HEARTBEAT_FRAME = ": heartbeat\n\n"

ScopeResolver = Callable[[Request, Any], "str | Awaitable[str]"]
AuthDependency = Callable[..., Any]


async def _never_disconnected() -> bool:
    return False


async def _no_auth() -> None:
    return None


def _format_event_frame(event: RealtimeEvent) -> str:
    data = json.dumps(event.payload, separators=(",", ":"), default=str)
    return f"id: {event.id}\nevent: {event.event}\ndata: {data}\n\n"


async def sse_event_stream(
    bus: RealtimeBus,
    scope: str,
    *,
    last_event_id: str | None = None,
    heartbeat_seconds: float = _DEFAULT_HEARTBEAT_SECONDS,
    is_disconnected: Callable[[], Awaitable[bool]] | None = None,
    disconnect_poll_seconds: float = _DEFAULT_DISCONNECT_POLL_SECONDS,
) -> AsyncIterator[str]:
    """Turn a `bus.subscribe(scope, ...)` stream into SSE text frames.

    - Checks `is_disconnected()` every `disconnect_poll_seconds` (or every
      `heartbeat_seconds`, whichever is smaller) and returns cleanly the
      moment it's `True` — no more frames are yielded.
    - Emits `_HEARTBEAT_FRAME` when `heartbeat_seconds` have elapsed with
      no real event, so idle connections + proxies stay alive.
    - On exit (disconnect, StopAsyncIteration, or the caller simply
      stopping iteration / calling `.aclose()` on THIS generator), the
      in-flight `bus.subscribe(...)` iterator is cancelled + awaited
      *before* `aclose()`-ing it — calling `aclose()` on an async
      generator while a `__anext__()` task on it is still in flight
      raises `RuntimeError: aclose(): asynchronous generator is already
      running`; awaiting the cancellation first is what avoids that.
    """
    check_disconnected = is_disconnected or _never_disconnected
    subscription = bus.subscribe(scope, last_event_id=last_event_id)
    tick = (
        min(heartbeat_seconds, disconnect_poll_seconds)
        if heartbeat_seconds > 0
        else disconnect_poll_seconds
    )
    last_heartbeat = time.monotonic()
    next_task: asyncio.Task[RealtimeEvent] | None = None
    try:
        while True:
            if await check_disconnected():
                logger.debug("SSE stream disconnected scope=%s", scope)
                return
            if next_task is None:
                next_task = asyncio.ensure_future(subscription.__anext__())
            done, _pending = await asyncio.wait({next_task}, timeout=tick)
            if next_task in done:
                task, next_task = next_task, None
                try:
                    event = task.result()
                except StopAsyncIteration:
                    return
                last_heartbeat = time.monotonic()
                yield _format_event_frame(event)
                continue
            if heartbeat_seconds > 0 and (
                time.monotonic() - last_heartbeat >= heartbeat_seconds
            ):
                last_heartbeat = time.monotonic()
                yield _HEARTBEAT_FRAME
    finally:
        if next_task is not None:
            if not next_task.done():
                next_task.cancel()
            try:
                await next_task
            except (asyncio.CancelledError, StopAsyncIteration):
                pass
        aclose = getattr(subscription, "aclose", None)
        if aclose is not None:
            await aclose()


def create_sse_router(
    bus: RealtimeBus,
    *,
    scope_resolver: ScopeResolver,
    auth_dependency: AuthDependency | None = None,
    heartbeat_seconds: float = _DEFAULT_HEARTBEAT_SECONDS,
    path: str = "/",
) -> APIRouter:
    """Build a FastAPI `APIRouter` exposing `bus` as `text/event-stream`.

    - `scope_resolver(request, auth_ctx) -> str | Awaitable[str]` maps the
      request (path params, query, whatever) + the resolved
      `auth_dependency` value to the bus `scope` string. The seed does
      NOT interpret `scope` — pure pass-through to `bus.subscribe`.
    - `auth_dependency` is any FastAPI dependency callable (e.g. the
      product's `get_current_user_org`); its resolved value is handed to
      `scope_resolver` as the second argument. `None` → no auth is
      enforced here (the consumer's own middleware / router-level
      `dependencies=` is expected to gate access in that case).
    - Resume: `Last-Event-ID` request header wins; falls back to a
      `?since=` query param. Neither present → live-tail only (contract:
      `RealtimeBus.subscribe(last_event_id=None)`).
    - Response headers set `Cache-Control: no-cache`,
      `Connection: keep-alive`, and **`X-Accel-Buffering: no`** — without
      the last one, a buffering reverse proxy (nginx, and the fleet's own
      Cloudflare-fronted VPS proxy) holds the whole response in a buffer
      until it's full or the connection closes, which for a long-lived
      SSE stream means "never" — the client sees nothing until timeout.
    """
    router = APIRouter()
    dependency = auth_dependency if auth_dependency is not None else _no_auth

    @router.get(path)
    async def stream(
        request: Request,
        since: str | None = Query(default=None),
        last_event_id_header: str | None = Header(default=None, alias="Last-Event-ID"),
        auth_ctx: Any = Depends(dependency),
    ) -> StreamingResponse:
        resume_id = last_event_id_header or since
        scope = scope_resolver(request, auth_ctx)
        if inspect.isawaitable(scope):
            scope = await scope

        return StreamingResponse(
            sse_event_stream(
                bus,
                scope,
                last_event_id=resume_id,
                heartbeat_seconds=heartbeat_seconds,
                is_disconnected=request.is_disconnected,
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    return router
