---
name: noc-fast-responses
description: Use when adding or changing an endpoint, handler, service or query in any product or the seed, or when someone says "slow page", "slow endpoint", "latency", "it takes seconds", "p95", "budget", "N+1", "round trips", "Server-Timing", or after a deploy. Fast responses are mandatory - server budget, handlers rule, round-trip counting, cache-writes for the perceived half, latency_report after deploy.
version: 1.0.0
---

# noc-fast-responses - responses are fast by construction, and measured

Owner mandate 2026-10-22: fast responses are mandatory, on every product and on the noc app itself. The seed already makes the shared path fast and measures every request; this skill is how a NEW endpoint stays inside budget. → `KB § PATTERNS/backend/request-path-latency.md`

## Budget (p95, one file: `deploy/fleet/latency-budgets.json`)
shell / `/api/me*` / notifications **150 ms** · reads **300 ms** · writes **500 ms**. A route that cannot meet it gets an `overrides` entry WITH a reason, never a silent miss.

## Writing a new endpoint
1. **Count round trips first.** Each PostgREST call costs ~25-50 ms (VPS Campinas to Supabase sa-east-1). A 600 ms endpoint is ~10+ sequential calls or a blocked event loop. Write the count down before and after.
2. **Collapse them**: one query with embedded selects / an `.in_()` batch (paged, `iter_paged_rows`) instead of a loop of per-row calls; independent calls concurrently (`anyio.to_thread` per call), never sequentially.
3. **Handlers rule**: an `async def` handler that awaits nothing is a plain `def`; one that must stay async wraps sync DB work in `await anyio.to_thread.run_sync(...)`. Keeper `check_async_handler_sync_db`; codemod `noctus.dev.async_handlers_to_def`.
4. **Use the seed's auth deps and clients** (token cache, pooled client, admin client cached). Never build a client per request or re-verify the token yourself.
5. **Caches only when counting proves you need one**: short TTL, keyed per user/org (never cross-tenant), evicted on the write that changes it, positive-only where a denial matters. Document the trade-off. Never weaken auth/RLS for speed.
6. **Perceived half**: the write path must put what it knows into the client cache (`useCacheWriteMutation`) and never lie while loading. → skill `noc-cache-writes`

## Measuring
- Every response carries `Server-Timing: app;dur=<ms>` (browser devtools) and logs a `req_timing` line with the ROUTE TEMPLATE (`RequestTimingMiddleware`, in every product by construction).
- **After deploy**: `noctus.dev.latency_report product=<slug>` (CLI `--latency-report <slug>`). `over_budget` = fix before walking away. `inconclusive` (no data) is not a pass: browse the product, re-run. The new route must appear in the report.
- Pin the mechanism in tests (round-trip count via a counting fake client, concurrency overlap, cache eviction), not wall-clock numbers.

## Guardrails
- Never add a per-product timing middleware or hand-rolled timer: the seed owns it.
- Inactive products (`ativo=false`) are asleep; do not chase their numbers.

## Depth
`KB § PATTERNS/backend/request-path-latency.md` · `KB § PATTERNS/frontend/mutation-cache-writes.md` · `KB § PATTERNS/backend/postgrest-row-cap.md`.
