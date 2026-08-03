"""Provider-neutral realtime transport — the platform's first realtime
capability. See `KB § PATTERNS/common/realtime-sse-bus.md` for the why
(SSE over WS / Supabase Realtime here, the stream-vs-pub/sub reasoning,
the resume contract, the proxy-buffering trap).

Public surface:
- Bus: `RealtimeEvent`, `RealtimeBus` Protocol, `FakeRealtimeBus`,
  `RedisRealtimeBus`, `StreamRedis` Protocol, `get_realtime_bus` factory.
- Transport: `create_sse_router` (FastAPI router factory) +
  `sse_event_stream` (the framework-agnostic bus→SSE-frames core).

Any live surface (WhatsApp/Instagram DM inbox, in-app chat, presence)
publishes onto an opaque `scope` string and mounts `create_sse_router`
with its own `scope_resolver` + `auth_dependency` — this module has no
knowledge of WhatsApp, connections, or auth.
"""

from noctusai_lib.realtime.bus import (
    FakeRealtimeBus,
    RealtimeBus,
    RealtimeEvent,
    RedisRealtimeBus,
    StreamRedis,
    get_realtime_bus,
)
from noctusai_lib.realtime.sse import (
    AuthDependency,
    ScopeResolver,
    create_sse_router,
    sse_event_stream,
)

__all__ = [
    "AuthDependency",
    "FakeRealtimeBus",
    "RealtimeBus",
    "RealtimeEvent",
    "RedisRealtimeBus",
    "ScopeResolver",
    "StreamRedis",
    "create_sse_router",
    "get_realtime_bus",
    "sse_event_stream",
]
