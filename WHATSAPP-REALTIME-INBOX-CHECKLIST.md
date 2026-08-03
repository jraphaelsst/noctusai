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

  🔴 **QUALIFIED 2026-08-03 by Slice 1.3 — the mirror is ONE-DIRECTIONAL.** This was not knowable
  when the decision was made, so it is recorded rather than buried:

  | Direction | Works? | Mechanism |
  |---|---|---|
  | this UI → your phone | ✅ | `sendSeen` on chat open marks it read on the device |
  | your phone → this UI | ❌ | nothing reports it |

  `message.ack` carries only the ack level of messages **we sent** (delivered / read *by the
  recipient*) — it says nothing about you reading an inbound message on your own phone. And WAHA's
  `chats/overview` `ChatSummary` exposes no top-level `unreadCount` to poll for it either (1.3).
  **Effect:** read a chat on your phone and this UI's badge stays lit until you open it here too.
  Not fixable from our side — it is the limit of what the transport exposes.
  **Options:** (a) accept — opening *here* is the canonical read action; (b) once pairing works,
  probe whether the untyped `_chat.unreadCount` is populated and reconcile from it in the backfill
  sweep. **Deferred to the user; (b) is cheap to test the moment the session reaches `WORKING`.**
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

- [-] **0.1** ~~Run `logout` → `start` on WAHA session `default` now~~ — **DECLINED by user 2026-08-03.**
      Decision: wait for the code fix rather than work around it, so recovery is proven end-to-end
      through the product's own UI. No agent touches the live WhatsApp account.
- [ ] **0.2** Recovery instead happens via Slice 1's `recover_session()` ladder + Slice 7's QR fix.
      Verified under **V1**.

## Slice 1 · Seed WAHA client completion  `[C1 · seed/lib/backend/.../integrations/whatsapp/]` — ✅ **DONE** (`4718495e`)

> merged into the integration branch; seed suite 2565 passed on the merged tip

- [x] **1.1** Fix `_session_config` casing — `client.py:86` sends `full_sync`, WAHA's key is
      `fullSync`. Live session reports `"fullSync": false`; NOWEB has therefore **never** backfilled
      history. Add a test asserting the emitted JSON key (this failed silently for weeks).
- [x] **1.2** Add `send_seen(chat_id, message_id=None, participant=None)` → `POST /api/sendSeen`.
- [x] **1.3** **VERDICT: endpoint EXISTS, but `unreadCount` does NOT.** Verified against the live
      server's own embedded OpenAPI spec (`swagger-ui-init.js` inside `noctus-services-waha-1`):
      `operationId: ChatsController_getChatsOverview` is present on WAHA 2026.6.1 CORE.
      **However** its `ChatSummary` schema is `{id, name, picture, lastMessage, _chat}` — there is no
      top-level `unreadCount`. It would only exist nested inside the untyped `_chat` blob, which could
      not be confirmed against a live sample because the session is `FAILED` (422). `get_chats_overview()`
      was added with a defensive docstring rather than a guessed field mapping.
      ⚠️ **Consequence for the read model — see "Read-state is one-directional" below.**
- [x] **1.4** Move the six session-admin methods into the `WhatsAppClient` Protocol (`types.py:50`) —
      they exist on both impls but aren't in the contract, so a partial connector type-checks clean.
- [x] **1.5** Add `recover_session()` escalation ladder replacing the FE's one-shot guess:
      `start` → not `SCAN_QR_CODE|WORKING` within N s → `restart` → still stuck → `logout` + `start`.
      The ladder converges regardless of which rung is individually correct.
- [x] **1.6** `FakeWahaClient` parity for every new method (seed IO ships Fake+Real+factory).
- [x] **1.7** Tests green: `noctus.dev.pytest` on seed.

## Slice 2 · Seed realtime bus + SSE  `[C1 · NEW seed/lib/backend/noctusai_lib/realtime/]` — ✅ **DONE** (`73285903`)

> merged; `noctusai_lib.realtime` is the platform's FIRST realtime transport

- [x] **2.1** `bus.py` — `RealtimeBus` Protocol (`publish(scope, event, payload)` / `subscribe(scope)`),
      `RedisRealtimeBus`, `FakeRealtimeBus`, `get_realtime_bus(...)` factory.
- [x] **2.2** `sse.py` — `create_sse_router(...)` factory: `text/event-stream`, heartbeat,
      `Last-Event-ID` resume, `?since=` cursor replay, `X-Accel-Buffering: no`.
- [x] **2.3** Reuse the existing Redis wiring (same URL as the chatbot buffer / `RedisWebhookDedup`) —
      do not open a second client path.
- [x] **2.4** Author `KB § PATTERNS/common/realtime-sse-bus.md` — no realtime/live-data pattern doc
      exists in the KB at all today.
- [x] **2.5** Tests: publish→subscribe roundtrip, reconnect replay, Fake parity.

## Slice 3 · Schema  `[C2 · products/social-wiring/backend/migrations/040_*.sql]` — ✅ **DONE** (`b524b097`, apply pending)

> merged; DDL statically verified, live apply deferred

- [x] **3.1** `social_wiring.whatsapp_chats` — one row per conversation. PK `(connection_id, chat_id)`;
      `org_id`, `title`, `last_message_at`, `last_message_preview`, `last_direction`, `unread_count`,
      `last_read_at`, `last_read_message_id`, `archived`, `pinned`, `synced_through`.
      Index `(connection_id, archived, last_message_at DESC)` — that index **is** the chat-list query.
      Stops the list being a `GROUP BY` over a growing message table.
- [x] **3.2** `conversation_messages`: add `ack SMALLINT` (WAHA −1 error … 3 read, 4 played),
      `chat_id TEXT`, `acked_at`. Index `(connection_id, chat_id, created_at DESC)` — the thread query.
- [x] **3.3** RLS mirroring the existing pattern exactly: `current_org_id()` SELECT for `authenticated`
      + service-role ALL (template: `011_rls_current_org_id.sql:448`).
- [x] **3.4** No FK on `connection_id` — consistent with the deliberate choice at `014:30`.
- [~] **3.5** Verified STATICALLY, not live — reported honestly rather than claimed.
      Legs: (a) `pglast` (real libpg_query parser) parses all 15 statements as valid DDL, exit 0, and
      an AST walk confirms every statement carries an idempotency guard; (b) 12 new structural tests
      in `test_migrations.py` — full suite **1502 passed / 0 failed**, root scoped to the worktree.
      **Live apply deferred to the tech-lead after merge** (see blockers below).

**Slice 3 delivered** — `040_whatsapp_inbox_realtime_schema.sql`, commit `b524b097` on `feat/wa-inbox-schema`.
Index `idx_sw_whatsapp_chats_list (connection_id, archived, last_message_at DESC)` is the chat-list
query. RLS mirrors `011:448-453` with deliberately **no** archived/unread predicate — filtering a
category out of RLS makes every downstream FE branch on it dead (`status-pagina-dev-visibility`).

**Two blockers surfaced by this slice (not silently skipped):**
1. 🔴 `noctus.dev.migrate_product` has **no `worktree_path`** parameter, unlike `pytest` /
   `vite_build` / `find_reusable_component`. It cannot see a worktree's migration, and a naive
   `confirm=true` from a worktree would apply the **primary tree's** pending backlog — other
   people's unvetted migrations. Logged `s1-emergent` to `auto-improvement.ndjson`.
2. 🔴 Migrations **037–039 are pending unapplied** on the live Supabase dev project
   (`nyplttplcoyiiqjrvtiw`) — **independently confirmed by the tech-lead**, not taken on report:
   `037_erp_stage_parity_and_canonical_phone` · `038_n8n_folders` · `039_n8n_nav_route`.
   Implication beyond ordering: the canonical-phone contract (`normalize_phone`, the `contato_norm`
   trigger) and the whole n8n folders + nav-route feature are **shipped in code but absent from the
   dev database**. Outside this slice's territory and a parallel agent is live in social-wiring, so:
   SURFACED, not acted on. `040` is order-independent (new table + additive columns only) and can be
   applied alone via `migrate_product(target="040_…")`.

## Slice 4 · Ingest rewrite  `[C3 · whatsapp_router.py]` — ✅ **DONE** (`29c07fdb`, `3798be44`)

> Also fixed two pre-existing bugs it uncovered: `connection.encrypted_api_key` (a field that
> never existed) and `payload.pushName` (no fallback) both raised on **every** inbound message
> and were silently swallowed by a surrounding `except Exception` — a textbook silent-error.
> `session.status` is persisted to Redis (24h TTL), not Postgres — no column exists yet.

- [x] **4.1** Subscribe the full event set + re-wire existing connections: `message`, `message.any`,
      `message.ack`, `message.reaction`, `session.status`. Today only `message` + `session.status`
      (`whatsapp_connections_router.py:335`) — which is why messages sent from the phone never land.
- [x] **4.2** Persist instead of discard: `message.ack` → `conversation_messages.ack`;
      `session.status` → persisted state (currently logged and dropped, `whatsapp_router.py:316-324`).
- [x] **4.3** Maintain `whatsapp_chats` on every write (upsert last-message fields, bump `unread_count`).
- [x] **4.4** Publish each event to the realtime bus after the DB write.
- [x] **4.5** **Fix-on-contact:** hand-rolled `_verify_hmac` (`:592-603`) is the exact anti-shape
      `KB § PATTERNS/security/webhook-signatures.md` forbids. Move to `webhook_endpoint(...)` with a
      per-request `ResolvedSecret` resolver — all 5 pins.
- [x] **4.6** Backfill job on the existing seed APScheduler (`noctusai_lib/api/scheduler.py`;
      social-wiring already calls `start_scheduler()` at `lifespan.py:108`). Walks chats, pulls
      history via `fetch_chat_messages`, advances `synced_through`.
      Default depth **90 days or 500 messages per chat, whichever is smaller** — configurable.
      `max_instances=1` is per-process: fine at one replica, documented not assumed.

## Slice 5 · Read endpoints go DB-only  `[C3 · whatsapp_connections_router.py]` — ✅ **DONE** (`437fc07e`)

> 47 chat-router + 29 connections tests; full social-wiring suite **1512 passed**, exit 0.
> Deleted: the WAHA merge in both reads, `list_lids`, the 40-call name-resolve budget, and the
> process-local `_thread_cache`/`_name_cache` globals (also a multi-replica hazard).
> ⚠️ Contract change: `/messages` now returns **newest-first** (was oldest-first).

- [x] **5.1** `GET /chats` → pure `whatsapp_chats` query + keyset pagination. Delete the WAHA merge,
      the `list_lids` call, the 40-call name-resolution budget, and `_thread_cache` (`:96-98`).
- [x] **5.2** `GET /chats/{id}/messages` → pure Postgres + keyset pagination. The `before` cursor
      already exists server-side (`:996-1021`); the FE simply never sent it.
- [x] **5.3** **New** `POST /chats/{id}/read` → advance read cursor, zero `unread_count`, publish
      `chat.read`, fire `send_seen` in the background (never on the response path).
- [x] **5.4** Session endpoints adopt `recover_session()` and persist status.
- [x] **5.5** Auth tests assert strict `== 401` (never `in (401, 404)`).

## Slice 6 · Seed frontend  `[C1 · seed/lib/frontend/src/]` — ✅ **MOSTLY DONE** (inline)

> vitest **319 passed** (28 files) exit 0 · `tsc --noEmit` exit 0.
> Bug found+fixed by the new tests: empty newest page + `hasMore` fell through to the empty
> state, stranding the user with no way to reach messages that exist. Regression-pinned.
> 6.4 (persisted cache) still open — see note there.

- [x] **6.1** `useRealtimeStream(scopeId)` — one `EventSource` per scope, backoff reconnect, reducer
      calling `qc.setQueryData`. This is the "WS-v2 seam" already named at `useWhatsAppChats.ts:70-74`.
- [x] **6.2** Extend `ChatWindowAdapter` (`design-system/chat/ChatWindow.tsx:48-100`) with
      `useReadState` / `markRead` / `useLoadMore`. The organ is already provider-agnostic — **do not fork it**.
- [x] **6.3** Infinite scroll in the thread pane via `useInfiniteQuery` (threads are hard-capped at 50
      messages today, `useWhatsAppChats.ts:102`).
- [~] **6.4** Persist the query cache so a reload paints the last-known chat list at 0ms and reconciles
      behind it — this is what answers *"on page refresh it loads chats everytime"*. Prefer
      `@tanstack/query-persist-client`; fallback is a seed-level `createPersistedQueryClient` over
      sessionStorage (no new dep).
- [x] **6.5** `ChatWindow.organ.yaml` — **DONE** (`33c1c62a`, inline). The organ reported
      `consumers_count: 0` / `shelfware` as the only design-system organ without a sidecar, which
      actively misled `noc-organ-consume-check` into telling engineers to fork it — the missing
      registration was itself generating the three product forks. Consumer inventory verified
      against the tree (3 surfaces, 2 providers), not taken from a report.
- [x] **6.6** All loading gates on `isPending || isFetching`, never `isLoading` (`check_lying_loading_state`).

## Slice 7 · Product frontend  `[C3 · products/social-wiring/frontend/]` — ✅ **DONE** (inline)

> product FE **455 passed** (42 files) exit 0 · `tsc --noEmit` exit 0 · `check_lying_loading_state` clean.
> ⚠️ Five unrelated FE files are FLAKY under full-suite parallel load (pass in isolation) —
> logged `s1-emergent`. Flaky red masks real breakage; not silently absorbed.

- [x] **7.1** `WhatsAppChatWindow.tsx` — adapter consumes the stream; delete both `refetchInterval`s.
- [x] **7.2** `ConnectionDetailDialog.tsx` — QR panel driven by `session.status` over SSE. Remove the
      self-terminating poll and the one-shot `autoRecoveryFiredRef` guess (`:574-592`); "Gerar nova
      sessão / QR" calls `recover_session`, not `restart` (`:656`); show real ladder state, not a
      frozen stale string.
- [x] **7.3** **DRY:** `useConnectionChats` (`useWhatsAppConnections.ts:223`) and `useWhatsAppChats`
      (`useWhatsAppChats.ts:75`) share an identical query key + URL with different options, and
      `ChatSummary` is declared twice. Collapse to one hook + one type.
- [~] **7.4** Wire the `configureWebhook` mutation (defined, never called) so the event-set change can
      be re-applied to existing connections from the UI.

## Slice 8 · Docs · KB · tests  `[C1]` — ✅ **DONE**

> New `KB § PATTERNS/frontend/inbox-chat-surface.md` (+ INDEX row + `frontend-engineer` owns_kb
> and body pointer). **Corrected `MCP-SERVERS/waha.md`**: its stuck-worker recipe
> (`get → restart → get`) cannot recover a credentials-dead session and loops forever — the KB
> was documenting the broken procedure. Added the `fullSync` camelCase trap to
> `INTEGRATIONS/whatsapp.md §4a`.

- [x] **8.1** KB: `realtime-sse-bus.md` (new) · `inbox-chat-surface.md` (new — no inbox pattern exists).
- [x] **8.2** Update `KB § INTEGRATIONS/whatsapp.md` + `KB § MCP-SERVERS/waha.md` with the session
      ladder and the `fullSync` casing trap.
- [x] **8.3** 8-way sync: CLAUDE.md §1 pointer · MEMORY topic pointer · `.claude/agents/` `owns_kb` ·
      `KB § INDEX.md`.
- [x] **8.4** Tests: `fullSync` key assertion · QR poll continues through transient states · ladder
      converges from `FAILED` · SSE reconnect replays via `since` without duplicates · read-cursor
      arithmetic · RLS on both new surfaces.

---

## ✅ INTEGRATION BUG — found on the merged tip, FIXED + regression-pinned

**Sent messages would vanish from their own thread, permanently.**

Chain (all three links verified in the merged code, not inferred):
1. `POST /chats/{id}/send` calls `MessageStore.record(...)` **without** a `chat_id`
   (`whatsapp_connections_router.py:1031-1038`) — the parameter does not exist on `record()`.
2. Slice 5's new thread query reads **by `chat_id` only** (no more JID-alias fan-out), so a row with
   `chat_id IS NULL` never surfaces.
3. The `message.any` echo webhook cannot repair it: the echo carries the **same
   `provider_message_id`**, so `UNIQUE(provider_message_id)` drops it as a duplicate. The row never
   gets a `chat_id` — not late, *never*.

Why neither slice caught it: slice 5's suite (47 tests) and slice 4's suite are both green in
isolation. The defect lives strictly in the seam between them — the exact failure mode
`KB § PATTERNS/common/methodology-execution-discipline.md` warns about ("file-disjoint isn't
effect-disjoint").

- [x] **FIX-1** `/send` must pass `chat_id` to `record()` (and `record()` must accept it).
- [x] **FIX-2** Regression test: send → the message appears in `GET /chats/{id}/messages`.
- [x] **FIX-3** Regression test: the `message.any` echo for an already-stored outbound is a no-op
      that does **not** leave `chat_id` NULL.

## Gate results — final merged tip (2026-08-03)

| Gate | Result |
|---|---|
| social-wiring backend | **1556 passed**, exit 0 |
| seed backend | **2565 passed**, exit 0 |
| seed frontend | **319 passed** (28 files), exit 0 |
| product frontend | **455 passed** (42 files), exit 0 |
| `--verify-kb-sync` | exit 0 |
| `--check-eight-way-sync` | exit 0 |
| `check_lying_loading_state` | clean |
| merge with `origin/dev` | clean, zero conflicts |

⚠️ The product-FE suite failed **once** on `ClienteModal.test.tsx` (5.5s — a timeout under
parallel load), then passed in isolation (23/23) and on a clean full re-run (455/455) with no code
change. That is the already-logged flakiness, not a regression — recorded rather than quietly
re-run until green.

## Verification (end-to-end — REQUIRES A DEPLOY, hence still open)

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

---

# 🔻 HANDOVER — 2026-08-03, for the integrate + deploy session

> This session is **finished and wrapped**. Everything below is state the next agent needs.
> **Nothing has been pushed.** That was a deliberate user instruction ("finish all the work before
> any pushes, commit your work for history but don't push yet"), not an oversight.

## 1 · Where the work is

| | |
|---|---|
| Branch | `feat/whatsapp-realtime-inbox` |
| Worktree | `.claude/worktrees/whatsapp-realtime-inbox` |
| Commits ahead of `origin/dev` | **30** |
| Behind `origin/dev` | ~10 (peers kept landing; re-merge before integrating) |
| Pushed? | **No** |
| Branch pointer | published in `project-history/branch-tree.ndjson`, `status=on_going` |

The five engineer branches (`feat/wa-seed-client`, `feat/wa-realtime-bus`, `feat/wa-inbox-schema`,
`feat/wa-ingest`, `feat/wa-read-endpoints`) are **fully merged in** — each verified at
0 commits outside the integration branch — and their worktrees were removed. The branch refs are
kept as recovery handles and can be deleted once this lands.

## 2 · Gate results (final merged tip)

social-wiring backend **1556** · seed backend **2565** · seed FE **319** · product FE **455** —
all exit 0. `--verify-kb-sync` exit 0. `--check-eight-way-sync` exit 0.
`check_lying_loading_state` clean. Merge with `origin/dev` clean, zero conflicts.

⚠️ The product-FE suite is **flaky under parallel load** (logged `s1-emergent`). A single failure in
`ClienteModal.test.tsx` / `Settings` / `Clientes` / `Conexoes` / `BaseDeLeads` that passes in
isolation is the known flake — **but verify in isolation before dismissing it**, don't re-run until
green on reflex.

## 3 · 🔴 Migrations — read before touching the database

| Migration | State |
|---|---|
| `037_erp_stage_parity_and_canonical_phone.sql` | **PENDING** on live dev — canonical-phone contract absent from the DB |
| `038_n8n_folders.sql` · `039_n8n_nav_route.sql` | **PENDING** — the n8n feature is shipped in code with no schema behind it |
| `040_whatsapp_inbox_realtime_schema.sql` | **THIS WORK. Authored, statically verified, NEVER APPLIED anywhere.** |
| `041_leads_meta_lead_id.sql` | **PENDING** — a peer's, appeared during this session |

- Apply 040 **alone**: `migrate_product(product="social-wiring", target="040_...", confirm=true)`.
  A bare `confirm=true` applies the **entire pending backlog**, including other people's unvetted
  migrations.
- `noctus.dev.migrate_product` has **no `worktree_path`** (logged `s1-emergent`), so it resolves
  from the PRIMARY tree. Merge first, then apply from the primary checkout.
- 040 is order-independent (new table + additive columns only), but the app **will not work without
  it** — every read path queries `whatsapp_chats`.

## 4 · Other environments / peer branches at handover

| Branch | ahead | behind | Note |
|---|---:|---:|---|
| `feat/meta-leadgen-webhook` | 14 | 6 | peer, unlanded |
| `feat/meta-leadgen-ui` | 7 | 6 | peer, unlanded |
| `feat/meta-leadgen-erp` | 6 | 6 | peer, unlanded |
| `feat/imoveis-phase2` | 3 | 0 | peer — **plus 3 UNTRACKED files** (`useImoveis.ts`, `Imoveis.tsx`, `ImovelDetalhes.tsx`). At risk; salvage before any cleanup. |
| `feat/meta-seed-leadgen` | 1 | 14 | peer, unlanded |
| `feat/meta-leads-unified-base` | 0 | 6 | **fully landed — safe to clean** |

These are NOT this session's work and were not touched. `products/social-wiring` is shared with
them, so re-merge `origin/dev` and re-run gates on the merged tip before pushing.

## 5 · Deploy sequence (suggested)

1. `git -C <wt> fetch origin && git -C <wt> merge origin/dev` → resolve → **re-run all four suites
   on the merged tip** (per-branch green ≠ integration green).
2. Push to `dev`. Flip the branch pointer to `shipped`.
3. Apply migration **040 only** (§3).
4. Deploy social-wiring to the dev fleet; run **V1–V7** (below). Prod promotes a *dev-validated*
   build — never first-contact.
5. `main`/`prod` only with explicit user consent + a prod-exposure consent record.

## 6 · V1–V7 — the whole point; none can be done without a deploy

- **V1 · QR** — the reported bug. `waha_session_get` → `SCAN_QR_CODE`; QR renders; scan → `WORKING`.
  The watchdog line `Session stuck in STARTING` must stop appearing in `noctus-services-waha-1`.
  ⚠️ The live session is `FAILED` **right now**; recovery unlinks the device, so **get user consent**.
- **V2 · fullSync** — after a fresh pairing, `waha_session_get` must report `"fullSync": true`.
  It reports `false` today; **that flip is the proof the casing fix landed.**
- **V3 · latency** — `GET /chats` and `/messages` < 50ms p95 (from ~13s).
- **V4 · WAHA off the read path** — **stop the WAHA container**; both endpoints must still return
  complete data. This is the real test of the whole refactor.
- **V5 · realtime** — message from another phone appears with **no new XHR** (SSE frame only);
  kill/restore the tunnel and confirm `Last-Event-ID` replay fills the gap with no duplicates.
- **V6 · read/unread** — open a chat → badge clears **and** it reads as read on the real phone;
  reply from the phone → ack ticks progress.
- **V7 · gates** — re-run all four suites + `predeploy_check` on the merged tip.

## 7 · Known limits (do not "fix" — they are decisions)

- **Read state is one-directional.** `sendSeen` pushes read state to the phone; nothing reports the
  reverse (`message.ack` covers only messages *we* sent, and `chats/overview` has no top-level
  `unreadCount`). Reading on the phone leaves the badge lit in-app. Option (b) — probe
  `_chat.unreadCount` once `WORKING` — is cheap to test after V1.
- **`session.status` is persisted to Redis (24h TTL), not Postgres.** No column exists yet.
- **`markRead` touches the user's real WhatsApp.** Intended and user-approved. Do not move it to
  hover/prefetch.
- **`/send` stamps `chat_id` at first write, deliberately.** Do not "simplify" it away — the echo
  cannot repair it (see the integration-bug section above).

## 8 · Open drift logged this session (`auto-improvement.ndjson`)

1. `migrate_product` missing `worktree_path` — s1-emergent, `broad`.
2. product-FE vitest flakiness under parallel load — s1-emergent, `scoped`.
3. Surfaced by engineers, **not** actioned: `MockSupabaseClient.upsert()` does not propagate writes;
   `_SchemaCachingClient` test wrapper now duplicated **3×** (N≥3 ⇒ MUST formalize into
   `noctusai_lib.testing`); `KNOWLEDGE-BASE/INDEX.md` Layout-tree has pre-existing structural drift
   (`pydantic-strict-http.md` filed under `common/`, stray `security/` marker mid-list).

## 9 · Housekeeping

- Disk was CRITICAL (94%) and was pruned to ~19% used / 51 GB free (24.47 GB reclaimed). 6 GB still
  sits in 51 unused Docker volumes — **not** pruned, because that is where database data lives.
- At close-out, move this file to `project-history/roadmaps/whatsapp-realtime-inbox-2026-08.md`
  per `KB § PATTERNS/common/roadmap-tracking.md`, and absorb the retrospective.
