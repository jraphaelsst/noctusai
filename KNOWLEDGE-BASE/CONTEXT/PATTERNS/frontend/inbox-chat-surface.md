# Inbox / chat surface — the canonical shape

> **Rule.** A chat surface = the `ChatWindow` organ + a provider **adapter** + a
> **DB-first** read model + **one** realtime stream. Never a fork of the organ,
> never a vendor call on the read path, never a poll.
> → organ `seed/lib/frontend/src/design-system/chat/ChatWindow.tsx` ·
> transport `CONTEXT/PATTERNS/common/realtime-sse-bus.md`

Canonical instance: `products/social-wiring` WhatsApp inbox (2026-08).

---

## 1 · Why this doc exists

Three independent forks of the same 2-pane chat UI shipped before it did
(`therapy-platform/components/messaging/` ×7 files, `erp` `WhatsAppInbox.tsx`,
`ChatPanel.tsx`). The root cause was **not** carelessness: `ChatWindow` was the
only design-system organ without an `.organ.yaml`, so the catalog reported it as
`shelfware` with zero consumers, and `noc-organ-consume-check` therefore told
each engineer to build one. **A missing registration actively manufactures
forks.** Registering the organ is part of shipping it, not paperwork after.

## 2 · The four legs

| Leg | Rule | Why |
|---|---|---|
| **Organ** | Consume `ChatWindow` from `@noctusai/lib/design-system`. A new provider authors an **adapter**, never a component. | The 2-pane + composer + async-state matrix is identical across providers; only the data source differs. |
| **Read model** | The **database** is the source of truth. The vendor API is ingest + send only. | Vendor latency is latency you do not own and cannot cache around. WAHA `fetch_chat_messages` ≈ 13s; an indexed Postgres read ≈ 10ms — and it still works when the vendor session is `FAILED`. |
| **Realtime** | **One** stream per scope, patching the query cache. Never `refetchInterval`. | A poll is O(clients × interval) for usually-unchanged data *and* still not realtime. → `realtime-sse-bus.md` |
| **Read state** | A **cursor** on the conversation row, not a heuristic. | "inbound since my last reply" is not unread, and it silently degrades to `0` on any path that doesn't compute it. |

## 3 · The adapter contract

```ts
interface ChatWindowAdapter {
  useThreads:   (scopeId) => ChatAsyncResult<ChatThread[]>;
  useMessages:  (scopeId, threadId) => ChatAsyncResult<ChatMessage[]>;
  useSend:      (scopeId, threadId) => ChatSendResult;   // MUST throw, never fake success
  useAutoReply?: (scopeId) => ChatAutoReplyResult;       // optional
  useReadState?: (scopeId) => ChatReadStateResult;       // optional
  useLoadMore?: (scopeId, threadId) => ChatLoadMoreResult; // optional
}
```

Optional members are load-bearing: a provider without read receipts omits
`useReadState` and the organ renders exactly as before. That is what keeps one
organ serving providers with genuinely different capabilities.

## 4 · Non-obvious rules (each one cost something)

- **`markRead` may reach outside the app.** The WhatsApp adapter marks the chat
  read on the user's *real phone*. The organ therefore calls it **exactly once
  per opened thread** — never on hover, prefetch, or re-render. Assert the call
  **count**, not just that it happened.
- **Loading gates on `isPending || isFetching`, never `isLoading`.** In TanStack
  v5 `isLoading` is false during a background refetch, so an `isEmpty` branch
  renders "no conversations" over data that exists. → `lying-loading-state.md`
- **`staleTime: Infinity` once a stream owns the cache.** A background refetch
  is not merely wasted — it can clobber a newer stream-applied patch with an
  older server read.
- **Every stream handler must be idempotent.** A resumed connection redelivers.
  "Insert if absent, replace if present" — never blind append.
- **Order the DTO once, in the hook.** Keyset pagination reads newest-first; the
  UI renders oldest-first. Invert in one place or the mismatch leaks into every
  consumer.
- **Denormalize the conversation row.** Deriving the thread list by `GROUP BY`
  over the message table is O(all messages) per page-load and gets slower every
  day the product is used. One row per conversation + an index on
  `(scope, archived, last_message_at DESC)` **is** the list query.
- **Recount unread; never increment it.** Vendors deliver the same message twice
  (WhatsApp fires `message` *and* `message.any` for one send), so a
  read-modify-write counter loses updates silently and permanently. A scoped
  indexed COUNT is cheap and self-heals a dropped webhook.
- **An id-deduped write cannot be repaired by a later echo.** If `/send` stores a
  row keyed by `UNIQUE(provider_message_id)`, the vendor's echo of that same
  message is dropped as a duplicate — so any column the send path forgot stays
  empty *forever*, not just until the echo arrives. Populate every read-path
  column at first write. (Caught on the merged tip 2026-08-03: sent messages
  would have vanished from their own thread.)

## 5 · Adoption checklist

- [ ] Organ consumed, not forked (`noc-organ-consume-check`)
- [ ] `.organ.yaml` sidecar exists for any new organ — else the catalog breeds forks
- [ ] Conversation table + `(scope, archived, last_message_at DESC)` index
- [ ] Read cursor + recounted unread
- [ ] Vendor absent from both read paths (test it with the vendor **stopped**)
- [ ] One stream per scope; zero `refetchInterval`
- [ ] Backfill job for history the webhook never saw

## 6 · Pointers

`realtime-sse-bus.md` (transport) · `lying-loading-state.md` (loading gates) ·
`products-consume-canonical-organs.md` (fork prevention) ·
`CONTEXT/INTEGRATIONS/whatsapp.md §4a` (session-config traps) ·
`MCP-SERVERS/waha.md` (session recovery ladder)
