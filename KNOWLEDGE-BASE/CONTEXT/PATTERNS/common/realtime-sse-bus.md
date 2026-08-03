# Realtime SSE bus — the platform's first realtime transport

**What it is.** `noctusai_lib.realtime` (`bus.py` + `sse.py`) is the seed's
provider-neutral realtime capability: a `RealtimeBus` Protocol (publish/
subscribe onto an opaque `scope` string) with `FakeRealtimeBus` (in-memory) +
`RedisRealtimeBus` (Redis Streams) + `get_realtime_bus()` factory, and
`create_sse_router(...)` — a FastAPI router factory that turns any
`RealtimeBus` into a `text/event-stream` endpoint. Born 2026-08-03: before
this there was **no realtime transport anywhere on the platform** — zero
hits for Supabase `.channel(`, `postgres_changes`, WebSocket, or SSE
(`StreamingResponse` existed only for PDF/CSV downloads); every live surface
polled with TanStack `refetchInterval`. WhatsApp/Instagram DM inboxes, in-app
chat, and presence all consume this ONE bus going forward — mirrors
`KB § PATTERNS/backend/seed-fake-real-adapter.md`: Protocol + Fake + Real +
factory, the exact shape `dedup.WebhookDedup` and `buffer.RedisBufferClient`
already use.

## Why SSE, not WebSocket, not Supabase Realtime

- **Not WebSocket.** Every realtime need identified so far (WhatsApp/IG DM
  inbox, chat, presence, notifications) is **server→client push**; nothing
  needs client→server low-latency binary/duplex. A plain HTTP request
  already carries the client→server leg (send a message via the normal
  REST endpoint). WS buys bidirectionality we don't need at the cost of a
  second protocol, sticky-session/LB complications, and its own
  reconnect/backoff story to hand-roll. SSE rides plain HTTP — same auth,
  same proxy, same load balancer, same everything the rest of the platform
  already has wired.
- **Not Supabase Realtime.** `postgres_changes` ties the transport directly
  to a DB row change — fine for "reflect a table," wrong shape for a
  provider-agnostic inbox where the event ISN'T always a row write (a
  `session.status` transition, a debounced `chat.upsert` that batches N
  buffered messages into one UI update). It also means every consumer needs
  a Supabase client + RLS-shaped channel auth wired client-side, duplicating
  what the product's own backend auth already does. This bus stays in OUR
  process, behind OUR existing auth dependency (see wiring below), and never
  requires a schema/table match — an in-process job, a webhook handler, or a
  cron can `publish()` without ever touching Postgres.
- **SSE's actual constraints are all acceptable here**: one-way, text-only,
  browser-native reconnect + `Last-Event-ID` built into `EventSource`. That
  native reconnect story is *why* this bus's resume contract exists — SSE
  clients retry automatically; the bus has to make retrying safe.

## Streams, not pub/sub — the resume contract

`RedisRealtimeBus` uses **Redis Streams** (`XADD`/`XREAD`), never bare
pub/sub (`PUBLISH`/`SUBSCRIBE`). Bare pub/sub delivers to whoever is
*currently* connected and drops everything published while a subscriber is
disconnected — for a bus whose entire point is surviving reconnects (a
laptop sleeps, a mobile tab backgrounds, a proxy times out an idle
connection), that's the failure mode, not an edge case. A Stream is an
append-only, ID-addressable log: `subscribe(scope, last_event_id=X)` first
replays every buffered event with `id > X` (the reconnect gap), then
continues live — no duplicates, no loss, as long as the gap is still inside
the stream's `maxlen` window.

- `RealtimeEvent.id` is `f"{unix_ms}-{seq}"` — identical in shape to a
  native Redis Stream ID (`XADD ... id="*"` generates it natively).
  `FakeRealtimeBus` replicates the same `<ms>-<seq>` algorithm
  (`_MonotonicIdGenerator`) so Fake and Real ids are shape-identical — the
  conformance suite (`tests/realtime/test_bus.py`) runs the SAME assertions
  against both.
- `last_event_id=None` → **live-tail only**: nothing buffered before the
  subscribe call is replayed (Redis's own `$` — "only new" — cursor). This
  is the first-connect case.
- `last_event_id=<id>` → **resume**: replays the gap, then live. This is
  every reconnect after the first.
- `XADD ... maxlen=N approximate=True` caps stream length so a `scope` with
  a permanently-absent subscriber (an abandoned WhatsApp connection, a
  closed chat) can't grow the stream unbounded. Default `N=1000`,
  configurable per `get_realtime_bus(..., maxlen=)`. A resume gap wider than
  `maxlen` silently loses the oldest entries — same trade-off Redis Streams
  always make; a consumer that needs stronger durability persists messages
  to its own DB table and treats the bus as delivery, not storage.
- **Reuses the fleet's one Redis** (`noctusai_lib.integrations.redis`) — the
  same client shape `dedup.RedisWebhookDedup` / `buffer.ConversationBufferService`
  already use. No second client path, no second `REDIS_URL`.

## The proxy-buffering trap

A long-lived streaming response dies silently behind a buffering reverse
proxy: nginx (and the fleet's Cloudflare-fronted VPS proxy) holds the whole
response in a buffer until it fills or the connection closes — for an SSE
stream that means the client sees **nothing** until the connection times
out, then gets everything at once or nothing at all. `create_sse_router`
sets three response headers together and all three matter:
`Cache-Control: no-cache`, `Connection: keep-alive`, and
**`X-Accel-Buffering: no`** — the last one is nginx's specific opt-out and is
the one that's easy to skip because everything looks correct in local dev
(no proxy in the loop) and only breaks once it's behind one. Ship all three
or the local-dev-green / prod-silent-broken gap bites the same way the
Meta-ads-throttle and Cloudflare-MCP bursts did for a different concern —
correctness in dev proves nothing about correctness behind a proxy.

Heartbeat frames (`: heartbeat\n\n`, default every 20s) exist for the same
reason from the other side: an idle connection with genuinely nothing to say
still needs to emit *something* periodically or an intermediate proxy/LB
treats it as dead and closes it. A heartbeat is a bare SSE comment line
(leading `:`) — `EventSource` ignores it silently (no `id:`/`event:` fields),
so it never collides with a real `RealtimeEvent`'s `event` type namespace
(`message.new` / `chat.upsert` / etc.).

## Wiring a consumer

The seed does not know what a `scope` means — a WAHA connection id, a
conversation id, a user id — or how a request authenticates. Both are
supplied by the consumer:

```python
from noctusai_lib.realtime import create_sse_router, get_realtime_bus

bus = get_realtime_bus(settings.redis_url)  # Real when redis_url is set, Fake otherwise

async def resolve_scope(request: Request, org) -> str:
    connection_id = request.path_params["connection_id"]
    return f"wa:conn:{connection_id}"

app.include_router(
    create_sse_router(bus, scope_resolver=resolve_scope, auth_dependency=get_current_user_org),
    prefix="/realtime/whatsapp/{connection_id}",
)
```

The consumer's inbound handler (e.g. the WAHA webhook's `on_message`)
`await bus.publish(scope, "message.new", {...})`s after persisting — the bus
is a delivery mechanism, not the source of truth; the DB row is.

## Testing

`FakeRealtimeBus` needs no Redis and is full-parity — use it directly in
consumer tests. The seed's own conformance suite
(`tests/realtime/test_bus.py`) exercises `RedisRealtimeBus` against
`fakeredis` (`noctusai_lib.integrations.redis.make_fake_redis_client()`),
matching the `test_dedup.py` / `test_router.py` convention of covering the
Real code path without a live server.

**Harness note for anyone testing `create_sse_router` end-to-end**: neither
`fastapi.testclient.TestClient` (`portal.call(self.app, ...)` blocks until
the ASGI call fully completes) nor `httpx.AsyncClient(transport=ASGITransport(...))`
(`await self.app(...)` inline) can read a genuinely-never-ending stream
incrementally then bail — both fully drive the response to completion before
returning anything. Test disconnect/heartbeat behavior directly against
`sse_event_stream(...)` (the framework-agnostic core, takes a plain
`is_disconnected: Callable[[], Awaitable[bool]]`) with a bus double whose
`subscribe()` is finite or `is_disconnected`-controlled; reserve
`TestClient` for header/frame-format/resume-wiring assertions against a
bus double that naturally terminates.

## Anti-patterns

- **DON'T** open a second Redis client for a new realtime need — extend
  `get_realtime_bus(redis_client=<the existing one>)`.
- **DON'T** reach for bare `PUBLISH`/`SUBSCRIBE` "because it's simpler" —
  it silently drops the reconnect story this bus exists to provide.
- **DON'T** let a consumer interpret or validate `scope` inside the seed —
  `bus.py`/`sse.py` are provider-neutral by construction; scope semantics
  belong to the product's `scope_resolver`.
- **DON'T** ship `create_sse_router` without all three headers
  (`Cache-Control`/`Connection`/`X-Accel-Buffering`) — dev-green, prod-silent-broken.

## Composes with

- [`seed-fake-real-adapter`](../backend/seed-fake-real-adapter.md) — the Protocol+Fake+Real+factory shape this bus follows.
- [`outbound-rate-limiting`](outbound-rate-limiting.md) — sibling "one primitive, every integration adopts it" root-level concern.
- `KB § INTEGRATIONS/whatsapp.md` — the first real consumer (WhatsApp/IG DM inbox).
- `KB § PATTERNS/backend/whatsapp-chatbot-seed.md` — the buffer/dedup Redis wiring this bus's Real half reuses.
