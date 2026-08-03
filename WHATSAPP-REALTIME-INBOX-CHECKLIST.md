# WhatsApp/WAHA — session recovery + canonical realtime inbox · CHECKLIST

> **Branch** `feat/whatsapp-realtime-inbox` (worktree `.claude/worktrees/whatsapp-realtime-inbox`, off `origin/dev`)
> **Started** 2026-08-03 · **Owner** tech-lead-inline
> **Status legend** `[ ]` not started · `[~]` in flight · `[x]` done · `[!]` blocked/surfaced · `[-]` dropped (with reason)
>
> ⚠️ **Parallel-agent notice.** Another agent is working inside `products/social-wiring` concurrently
> and has not published a branch pointer. My collision zone is published at
> `project-history/branch-tree.ndjson` — the WhatsApp/WAHA surface only.
>
> 📍 **Placement note.** This lives at repo root by explicit request (visibility while the work runs).
> Per `KB § PATTERNS/common/roadmap-tracking.md` the canonical durable home for a multi-slice
> initiative is `project-history/roadmaps/whatsapp-realtime-inbox-2026-08.md` — move it there at
> close-out, along with the retrospective.

---

## Why this work exists

Two problems on one surface (`products/social-wiring`, social.noctusai.com).

**1 · QR pairing is dead.** Session `default` is `FAILED` and cannot re-pair through the UI. Three
compounding defects, each proven from the live server:

| # | Defect | Evidence |
|---|---|---|
| A | Recovery calls `restart`, which retries the *stored* credentials rather than clearing them. NOWEB hangs in `STARTING`; WAHA's watchdog force-stops it ~5 min later. | `noctus-services-waha-1`: restart 17:44:14 → `Session stuck in STARTING status, force stopping the session` 17:49:13. Repeats 17:57:46 → 18:02:50. Session carries `me: 5511992694172 "One Chat"` ⇒ creds exist. |
| B | The QR poll terminates itself permanently on the first non-scannable response — but `STARTING`/`STOPPED`/`FAILED` are exactly the states to poll *through*. | `useWhatsAppConnections.ts:212` returns `false` when `!data.scannable`. `/auth/qr` hit **twice in 35 min**; `/status` every 5s. |
| C | Each QR call blocks ~10s in WAHA's `waitUntilStatus` before 422-ing, against an 8s interval — requests overlap, never catching the `SCAN_QR_CODE` window. | `responseTime: 10135` / `10204` on `GET /api/default/auth/qr`. |

The screenshot's `STARTING` badge over `Aguardando QR (STOPPED)` is defect B: two queries, one live,
one frozen on a stale value.

**2 · The chat surface is structurally slow with no read/unread system.** Chat-list and thread
requests are assembled *inside the request handler* by merging Postgres with live WAHA calls
(`whatsapp_connections_router.py:755`, `:996`); `fetch_chat_messages` takes ~13s on NOWEB behind a
process-local 25s cache that dies each deploy. No realtime transport exists anywhere in the repo. No
chats table (threads are a Python `GROUP BY`). No read cursor. `unread` is hardcoded `0` for
WAHA-sourced chats (`:701`).

**Outcome sought.** A provider-neutral realtime inbox built **in the seed**, proven on social-wiring
as the canonical instance every future chat UI consumes.

## Decisions taken (and why)

- **Postgres becomes the read source of truth; WAHA leaves the read path.** Current latency is a
  WhatsApp-protocol round trip — latency we don't own and can't cache around (the 25s cache is
  per-process). Indexed Postgres reads are ~10ms vs ~13s, and survive a `FAILED` session. Price: a
  one-time background backfill, because the DB is currently incomplete (see `fullSync` + `message.any` below).
- **SSE fed by Redis pub/sub** for realtime. The webhook already lands in FastAPI, so the backend
  sees each write first; Redis is already a fleet dependency; the payload is a semantic event
  (`message.new` / `message.ack` / `chat.read` / `session.status`) shaped like the cache patch the
  client needs. Supabase Realtime would need a publication change plus RLS correctness under its auth
  path (`current_org_id()` is `SECURITY DEFINER`) — research risk on the critical path. One stream
  also carries session status, so the **QR screen stops polling too**.
- **Read state mirrors real WhatsApp** (`sendSeen` + `message.ack`). ⚠️ Accepted side effect: opening
  a chat here marks it read **on the real phone**.
- **Seed-first.** Mechanism lands in `noctusai_lib` / `@noctusai/lib`; social-wiring is the proof.
  Other chat forks (therapy, erp `WhatsAppInbox`, `ChatPanel`) stay untouched this pass.

## Target architecture

```
                    ┌─ POST /sendText ──────────────┐
                    │  POST /sendSeen               │
   FastAPI ─────────┤                               ├──▶  WAHA (NOWEB)
                    │                               │
   webhook ◀────────┴─ message · message.any ───────┘
      │               message.ack · session.status
      │
      ├──▶ Postgres  (whatsapp_chats + conversation_messages)  ◀── backfill job (APScheduler)
      │
      └──▶ redis.publish("wa:conn:{id}")
                       │
        GET /api/whatsapp/connections/{id}/stream   (SSE, Last-Event-ID + ?since=)
                       │
        FE: qc.setQueryData(...)   — no polling anywhere
```

---

## Slice 0 · Immediate manual unblock (ops, no code)

- [ ] **0.1** Run `logout` → `start` on WAHA session `default` to clear the dead credentials so NOWEB
      enters `SCAN_QR_CODE`. ⚠️ Writes to the live account — unlinks the device; re-pair by scanning.
      *Requires explicit user go-ahead; not an agent's call.*
- [ ] **0.2** Confirm `waha_session_get` → `SCAN_QR_CODE`, then `WORKING` with `me` populated after scan.

## Slice 1 · Seed WAHA client completion  `[C1 · seed/lib/backend/.../integrations/whatsapp/]` — **DISPATCHED**

> worktree `.claude/worktrees/wa-seed-client` · branch `feat/wa-seed-client`

- [ ] **1.1** Fix `_session_config` casing — `client.py:86` sends `full_sync`, WAHA's key is
      `fullSync`. Live session reports `"fullSync": false`; NOWEB has therefore **never** backfilled
      history. Add a test asserting the emitted JSON key (this failed silently for weeks).
- [ ] **1.2** Add `send_seen(chat_id, message_id=None, participant=None)` → `POST /api/sendSeen`.
- [ ] **1.3** Verify `GET /api/{session}/chats/overview` exists on WAHA 2026.6.1 CORE/NOWEB. Present ⇒
      add `get_chats_overview()` for real per-chat `unreadCount`. Absent ⇒ unread derives from the
      read cursor alone; record the verdict here.
- [ ] **1.4** Move the six session-admin methods into the `WhatsAppClient` Protocol (`types.py:50`) —
      they exist on both impls but aren't in the contract, so a partial connector type-checks clean.
- [ ] **1.5** Add `recover_session()` escalation ladder replacing the FE's one-shot guess:
      `start` → not `SCAN_QR_CODE|WORKING` within N s → `restart` → still stuck → `logout` + `start`.
      The ladder converges regardless of which rung is individually correct.
- [ ] **1.6** `FakeWahaClient` parity for every new method (seed IO ships Fake+Real+factory).
- [ ] **1.7** Tests green: `noctus.dev.pytest` on seed.

## Slice 2 · Seed realtime bus + SSE  `[C1 · NEW seed/lib/backend/noctusai_lib/realtime/]` — **DISPATCHED**

> worktree `.claude/worktrees/wa-realtime-bus` · branch `feat/wa-realtime-bus`

- [ ] **2.1** `bus.py` — `RealtimeBus` Protocol (`publish(scope, event, payload)` / `subscribe(scope)`),
      `RedisRealtimeBus`, `FakeRealtimeBus`, `get_realtime_bus(...)` factory.
- [ ] **2.2** `sse.py` — `create_sse_router(...)` factory: `text/event-stream`, heartbeat,
      `Last-Event-ID` resume, `?since=` cursor replay, `X-Accel-Buffering: no`.
- [ ] **2.3** Reuse the existing Redis wiring (same URL as the chatbot buffer / `RedisWebhookDedup`) —
      do not open a second client path.
- [ ] **2.4** Author `KB § PATTERNS/common/realtime-sse-bus.md` — no realtime/live-data pattern doc
      exists in the KB at all today.
- [ ] **2.5** Tests: publish→subscribe roundtrip, reconnect replay, Fake parity.

## Slice 3 · Schema  `[C2 · products/social-wiring/backend/migrations/040_*.sql]` — **DISPATCHED**

> worktree `.claude/worktrees/wa-inbox-schema` · branch `feat/wa-inbox-schema`

- [ ] **3.1** `social_wiring.whatsapp_chats` — one row per conversation. PK `(connection_id, chat_id)`;
      `org_id`, `title`, `last_message_at`, `last_message_preview`, `last_direction`, `unread_count`,
      `last_read_at`, `last_read_message_id`, `archived`, `pinned`, `synced_through`.
      Index `(connection_id, archived, last_message_at DESC)` — that index **is** the chat-list query.
      Stops the list being a `GROUP BY` over a growing message table.
- [ ] **3.2** `conversation_messages`: add `ack SMALLINT` (WAHA −1 error … 3 read, 4 played),
      `chat_id TEXT`, `acked_at`. Index `(connection_id, chat_id, created_at DESC)` — the thread query.
- [ ] **3.3** RLS mirroring the existing pattern exactly: `current_org_id()` SELECT for `authenticated`
      + service-role ALL (template: `011_rls_current_org_id.sql:448`).
- [ ] **3.4** No FK on `connection_id` — consistent with the deliberate choice at `014:30`.
- [ ] **3.5** Migration applies clean; RLS asserted by test.

## Slice 4 · Ingest rewrite  `[C3 · whatsapp_router.py · after 1–3]`

- [ ] **4.1** Subscribe the full event set + re-wire existing connections: `message`, `message.any`,
      `message.ack`, `message.reaction`, `session.status`. Today only `message` + `session.status`
      (`whatsapp_connections_router.py:335`) — which is why messages sent from the phone never land.
- [ ] **4.2** Persist instead of discard: `message.ack` → `conversation_messages.ack`;
      `session.status` → persisted state (currently logged and dropped, `whatsapp_router.py:316-324`).
- [ ] **4.3** Maintain `whatsapp_chats` on every write (upsert last-message fields, bump `unread_count`).
- [ ] **4.4** Publish each event to the realtime bus after the DB write.
- [ ] **4.5** **Fix-on-contact:** hand-rolled `_verify_hmac` (`:592-603`) is the exact anti-shape
      `KB § PATTERNS/security/webhook-signatures.md` forbids. Move to `webhook_endpoint(...)` with a
      per-request `ResolvedSecret` resolver — all 5 pins.
- [ ] **4.6** Backfill job on the existing seed APScheduler (`noctusai_lib/api/scheduler.py`;
      social-wiring already calls `start_scheduler()` at `lifespan.py:108`). Walks chats, pulls
      history via `fetch_chat_messages`, advances `synced_through`.
      Default depth **90 days or 500 messages per chat, whichever is smaller** — configurable.
      `max_instances=1` is per-process: fine at one replica, documented not assumed.

## Slice 5 · Read endpoints go DB-only  `[C3 · whatsapp_connections_router.py]`

- [ ] **5.1** `GET /chats` → pure `whatsapp_chats` query + keyset pagination. Delete the WAHA merge,
      the `list_lids` call, the 40-call name-resolution budget, and `_thread_cache` (`:96-98`).
- [ ] **5.2** `GET /chats/{id}/messages` → pure Postgres + keyset pagination. The `before` cursor
      already exists server-side (`:996-1021`); the FE simply never sent it.
- [ ] **5.3** **New** `POST /chats/{id}/read` → advance read cursor, zero `unread_count`, publish
      `chat.read`, fire `send_seen` in the background (never on the response path).
- [ ] **5.4** Session endpoints adopt `recover_session()` and persist status.
- [ ] **5.5** Auth tests assert strict `== 401` (never `in (401, 404)`).

## Slice 6 · Seed frontend  `[C1 · seed/lib/frontend/src/]`

- [ ] **6.1** `useRealtimeStream(scopeId)` — one `EventSource` per scope, backoff reconnect, reducer
      calling `qc.setQueryData`. This is the "WS-v2 seam" already named at `useWhatsAppChats.ts:70-74`.
- [ ] **6.2** Extend `ChatWindowAdapter` (`design-system/chat/ChatWindow.tsx:48-100`) with
      `useReadState` / `markRead` / `useLoadMore`. The organ is already provider-agnostic — **do not fork it**.
- [ ] **6.3** Infinite scroll in the thread pane via `useInfiniteQuery` (threads are hard-capped at 50
      messages today, `useWhatsAppChats.ts:102`).
- [ ] **6.4** Persist the query cache so a reload paints the last-known chat list at 0ms and reconciles
      behind it — this is what answers *"on page refresh it loads chats everytime"*. Prefer
      `@tanstack/query-persist-client`; fallback is a seed-level `createPersistedQueryClient` over
      sessionStorage (no new dep).
- [ ] **6.5** `ChatWindow.organ.yaml` — the organ reports `consumers_count: 0`,
      `validation_status: "shelfware"` because it is the only design-system organ without a sidecar,
      which actively misleads `noc-organ-consume-check` into telling the next engineer to fork it.
- [ ] **6.6** All loading gates on `isPending || isFetching`, never `isLoading` (`check_lying_loading_state`).

## Slice 7 · Product frontend  `[C3 · products/social-wiring/frontend/]`

- [ ] **7.1** `WhatsAppChatWindow.tsx` — adapter consumes the stream; delete both `refetchInterval`s.
- [ ] **7.2** `ConnectionDetailDialog.tsx` — QR panel driven by `session.status` over SSE. Remove the
      self-terminating poll and the one-shot `autoRecoveryFiredRef` guess (`:574-592`); "Gerar nova
      sessão / QR" calls `recover_session`, not `restart` (`:656`); show real ladder state, not a
      frozen stale string.
- [ ] **7.3** **DRY:** `useConnectionChats` (`useWhatsAppConnections.ts:223`) and `useWhatsAppChats`
      (`useWhatsAppChats.ts:75`) share an identical query key + URL with different options, and
      `ChatSummary` is declared twice. Collapse to one hook + one type.
- [ ] **7.4** Wire the `configureWebhook` mutation (defined, never called) so the event-set change can
      be re-applied to existing connections from the UI.

## Slice 8 · Docs · KB · tests  `[C1]`

- [ ] **8.1** KB: `realtime-sse-bus.md` (new) · `inbox-chat-surface.md` (new — no inbox pattern exists).
- [ ] **8.2** Update `KB § INTEGRATIONS/whatsapp.md` + `KB § MCP-SERVERS/waha.md` with the session
      ladder and the `fullSync` casing trap.
- [ ] **8.3** 8-way sync: CLAUDE.md §1 pointer · MEMORY topic pointer · `.claude/agents/` `owns_kb` ·
      `KB § INDEX.md`.
- [ ] **8.4** Tests: `fullSync` key assertion · QR poll continues through transient states · ladder
      converges from `FAILED` · SSE reconnect replays via `since` without duplicates · read-cursor
      arithmetic · RLS on both new surfaces.

---

## Verification (end-to-end, run before calling this done)

- [ ] **V1 · QR** `waha_session_get` → `SCAN_QR_CODE`; QR renders; pairing completes → `WORKING` with
      `me`. `Session stuck in STARTING` stops appearing in `noctus-services-waha-1`.
- [ ] **V2 · fullSync** after a fresh pairing `waha_session_get` reports `"fullSync": true`. It reports
      `false` today — that flip **is** the proof 1.1 landed.
- [ ] **V3 · Read latency** time `GET /chats` and `GET /chats/{id}/messages` on the deployed container.
      Target **< 50ms p95** (from ~13s).
- [ ] **V4 · WAHA off the read path** stop the WAHA container; both endpoints still return complete data.
- [ ] **V5 · Realtime** message from another phone appears with **no new XHR** (SSE frame only). Kill
      the tunnel mid-stream, restore, confirm `Last-Event-ID` replay fills the gap with no duplicates.
- [ ] **V6 · Read/unread** open a chat → badge clears **and** the chat reads as read on the real phone;
      reply from the phone → ack ticks progress via `message.ack`.
- [ ] **V7 · Gates** `noctus.dev.pytest` (social-wiring + seed) · `noctus.dev.vite_build` ·
      `check_lying_loading_state` · `check_canonical_organ_consumption` · `check_eight_way_sync` ·
      `noctus.dev.predeploy_check`. **Re-run on the merged tip**, not just per-branch — per-branch
      green ≠ integration green.

## Open assumptions (correct me if wrong)

- Backfill depth defaults to 90 days / 500 messages per chat.
- `GET /chats/overview` availability on WAHA CORE 2026.6.1 is **unverified** — first task of Slice 1.
- Single replica per product ⇒ APScheduler `max_instances=1` suffices, no distributed lock.
- The three other chat forks stay untouched; social-wiring is the canonical proof first.

## Appendix · The contract (authored 2026-08-03, BEFORE any endpoint or hook was written)

Per `KB § PATTERNS/architect/fe-be-contract-first-dispatch.md` — both sides build to this. A change
here is a contract bump: announce it, don't drift into it.

### Realtime bus (seed, provider-neutral)

```python
@dataclass(frozen=True)
class RealtimeEvent:
    id: str          # monotonic, sortable: f"{unix_ms}-{seq}"
    event: str
    payload: dict

class RealtimeBus(Protocol):
    async def publish(self, scope: str, event: str, payload: dict) -> str: ...
    def subscribe(self, scope: str, *, last_event_id: str | None = None) -> AsyncIterator[RealtimeEvent]: ...
```

Backed by a **Redis Stream, not bare pub/sub** — bare pub/sub drops anything published while a
subscriber is disconnected, which would defeat the entire reconnect story. Stream capped via `MAXLEN`.

### SSE endpoint

`GET /api/whatsapp/connections/{connection_id}/stream` · same auth dependency as every other live op.

Headers: `text/event-stream` · `Cache-Control: no-cache` · `Connection: keep-alive` ·
**`X-Accel-Buffering: no`** (without it the proxy buffers the stream to death).
Resume: `Last-Event-ID` request header, falling back to `?since=<event_id>`.
Frame: `id: <event id>\nevent: <name>\ndata: <json>\n\n`. Heartbeat every ~20s.

| Event | Payload |
|---|---|
| `message.new` | `{chat_id, message: MessageDTO}` |
| `message.ack` | `{chat_id, provider_message_id, ack, acked_at}` |
| `chat.read` | `{chat_id, unread_count, last_read_at}` |
| `chat.upsert` | `ChatDTO` |
| `session.status` | `{connection_id, status, paired, stage}` |
| `heartbeat` | `{ts}` |

`session.status` on the same stream is what lets the **QR screen stop polling** — it is told the
moment the session reaches `SCAN_QR_CODE`.

### DTOs

```jsonc
// ChatDTO
{ "chat_id": "5511992694172@c.us", "title": "…", "last_message_at": "…",
  "last_message_preview": "…", "last_direction": "inbound", "unread_count": 3,
  "last_read_at": "…", "archived": false, "pinned": false }

// MessageDTO
{ "id": "uuid", "provider_message_id": "…", "chat_id": "…", "direction": "inbound",
  "body": "…", "ack": 3, "acked_at": "…", "created_at": "…", "structured_payload": null }
```

### REST (all reads pure Postgres — WAHA is never on this path)

| Method | Path | Returns |
|---|---|---|
| `GET` | `/connections/{id}/chats?limit=30&before=<ISO>&archived=false` | `{items: ChatDTO[], next_before: ISO\|null}` |
| `GET` | `/connections/{id}/chats/{chat_id:path}/messages?limit=50&before=<ISO>` | `{items: MessageDTO[], next_before: ISO\|null}` |
| `POST` | `/connections/{id}/chats/{chat_id:path}/read` body `{up_to_message_id?}` | `{chat_id, unread_count: 0, last_read_at}` |
| `POST` | `/connections/{id}/recover` | `{connection_id, status, paired, stage}` |

⚠️ **Breaking change, deliberate:** the two GETs currently return bare arrays; they become paginated
envelopes. The FE is updated in the same wave (Slice 7) — that is why this is contract-first rather
than additive. `chat_id` is a JID containing `@` and **must** be `encodeURIComponent`'d by callers.

`POST …/read` fires `send_seen` in the background — never on the response path, so a slow WAHA can
never make the badge feel slow.

## Decision log

| Date | Decision | Rationale |
|---|---|---|
| 2026-08-03 | Postgres becomes read source of truth | ~13s → ~10ms; WAHA latency is not ours to optimize; survives `FAILED` sessions |
| 2026-08-03 | SSE + Redis pub/sub over Supabase Realtime | backend sees writes first · zero new infra · semantic payloads · carries `session.status` · provider-neutral for future chat UIs |
| 2026-08-03 | Read state mirrors real WhatsApp (`sendSeen`) | user's explicit choice, accepting the real-phone side effect |
| 2026-08-03 | Seed-first, social-wiring as canonical proof | user directive: the mechanism serves every future chat UI |
