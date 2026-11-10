# Supabase request breaker — stop the runaway, alert, evaluate, re-arm

> Born 2026-11-10, owner: "transform this into a safety mechanism that will watch over that, so we stop and ALERT, the
> process is killed and we evaluate". Self-contained. Why it exists: `KB § PATTERNS/backend/polling-request-budget.md`
> (our own loops made ~620k REST calls/day; Supabase answered 402 to every product; nothing noticed until it was dead).

## The rule

**Every Supabase REST call is counted per source. A background source that runs away is stopped, the owner is emailed,
and it stays stopped until a human re-arms it. The product's API keeps serving.** Construction, not discipline: it is on
for every product, by the seed.

## How it works (seed organ; no per-product code)

| Piece | Where |
|---|---|
| Core (counting, budgets, trip/hold/re-arm, alert dedupe+retry) | `noctusai_lib/primitives/supabase_breaker.py` |
| Redis state store + owner email alerter (Fake+Real+factory) | `noctusai_lib/integrations/supabase_breaker_io.py` |
| THE count point | `integrations/http_pool.py` `TimingTransport.handle_request` — one `rest` call = one count; every seed-built client rides it (pooled, kill-switch, and the stock-client fallback via `force_postgrest_http1`) |
| Source attribution (contextvar) | `worker:<types>:loop` (claims/idle/bookkeeping) + `worker:<type>` per job (inside `Worker._dispatch`); `scheduler:<job>` by `api/scheduler.py` `_instrument`; `http` set EXPLICITLY per request by `SupabaseSourceMiddleware`; anything else is `unattributed` |
| Install per app | `create_product_app` step 3d (Fake store/alerter under pytest) |
| Platform-admin route | `GET/POST /api/platform/supabase-breaker[/rearm|/trip]` (auto-mounted, tier `platform`, canonical `require_platform_admin` incl. admin-MFA AAL2; refuses `fleet`/`http`) |
| Independent human tool | MCP `noctus.dev.supabase_breaker action=status|rearm|trip` (Redis over the VPS SSH chokepoint; works when Supabase is down) |

**Unattributed = background.** The contextvar default is `unattributed`, budgeted and trippable like a background source, so a lifespan `create_task` loop or bare `Thread(` outside the Worker/scheduler is stoppable; `http` is never the default. NOC-REMEDIATE[breaker-unscoped-loop] (keeper for a loop without `source_scope`) is routed to the polling keeper.

**Boot is its own source.** The seed lifespan startup (notification-catalog publish + the product's `lifespan_startup` hook) runs under `source_scope("startup")` and the scheduler registry-publish thread under `scheduler:_registry`, so a heavy boot never trips `unattributed`. `startup` budget: 1,500 calls / 60 s + the background 2,000 / h cap (the seed's own boot is ~2 batched upserts; the burst is for product recovery hooks, and the hour cap keeps a loop that inherits the scope bounded). `unattributed` still covers: import-time code, bare `Thread(`s and daemon threads (e.g. the audit sink's batch writer), tasks created outside startup/Worker/scheduler/requests.

**A held source refuses calls in flight.** `TimingTransport` raises `BreakerOpen` before a REST call of a held background source leaves the process (a job already running fails fast; a tight loop makes at most budget+1 calls). The Worker catches it and RELEASES the job (reschedule, retry budget untouched — never failed/dead-lettered).

**Productive workers are not tripped.** Idle/claim calls count under the loop source; each job's calls under its type. Each processed job refunds 3 calls to the loop (claim+mark+heartbeat) and, when it finished, 200 to its type (`credit`). Base stays 300/5 min + 2,000/h: a poller, a retry storm or a handler burning calls without finishing jobs trips; a worker draining a backlog (e.g. 50 jobs x 150 calls) never does.

**Budgets** (`BreakerConfig`, defaults are the canonical answer): background trips at **> 300 calls / 5 min** (1/s
sustained) or **> 2,000 / 1 h**; `http` NEVER stops, it ALERTS above **6,000 / 5 min / process** (cooldown 1 h). Per-source
override: env `NOCTUS_BREAKER_BUDGETS='{"worker:transcricao":[[300,600],[3600,4000]]}'` (a rule list may not be empty; the
breaker cannot be switched off by config). Evaluated at most once a second per source; the count itself is O(1), in-memory.

**Trip.** Held in memory at once (works with Redis down), persisted to `noctus:breaker:<product>:<source>` as
`{reason, rate, window, tripped_at, by}` with NO TTL (survives restarts), event logged (`breaker_event`, sink seam for an EOA
row — best effort), owner emailed once per trip. Worker: finishes/releases the in-flight job, then PARKS (zero Supabase
calls; one cached Redis read every 15 s) and resumes on re-arm. Scheduler job: skipped, no run-ledger row (that row is a
Supabase call). A held source never starts on boot.

**Fleet key** `noctus:breaker:fleet`: while it exists EVERY background source of EVERY product stays stopped, APIs keep
serving. Read from Redis at most every 10 s per process (one MGET for fleet + known sources), never Supabase. Set by the
off-host watcher or `noctus.dev.supabase_breaker action=trip source=fleet`.

**Redis down.** The trip still stops the source in memory and alerts (the alert says it is not persisted). Reading the
keys fails OPEN (sources keep running) and alerts "breaker BLIND" once per outage — loud, never silent.

**Alert channel** (no Supabase, no WhatsApp owner line): the seed Resend email sender. Needs `RESEND_API_KEY` +
`NOCTUS_BREAKER_ALERT_EMAIL` (falls back to `WATCHDOG_ALERT_EMAIL`); sender `NOCTUS_BREAKER_ALERT_FROM` (default
`NoctusAI <noreply@noctusai.com>`). Missing config raises `BreakerAlertNotConfigured` naming what is missing; the alert is
logged at CRITICAL and kept for retry (30 s doubling to 15 min). A trip with no alerter is still a trip.

**Re-arm is human-only and needs a reason** (route / MCP tool / `Breaker.rearm`): deletes the key, records who+why (route and MCP both: the capped (1,000) list `noctus:breaker:audit`), the parked source resumes within ~10-15 s. A re-arm that cannot delete a persisted key
raises — it never pretends.

## Rules for code that adds a loop

1. A new background loop sets its source (`with source_scope("worker:x")`) or rides the Worker / scheduler, which do.
2. A poll of the breaker itself is declared: `# poll-budget: <cadence>; <k> calls/tick; worst <N>/day; idle=...`.
3. Never call Supabase from a held source's park path. Never catch the trip and carry on.

## Gaps (named)
- A product that builds its own `supabase.create_client` / raw httpx to `*.supabase.co/rest` bypasses the count. Seed paths
  are covered; product-local ones are found by grep for `create_client(` outside the seed (list in the PR).
- Sources are per process: two containers each tripping is two keys' worth of alerts (deduped per product+source+time).
- The EOA event is a log line + sink seam; the table is `NOC-REMEDIATE[breaker-event-table]`.
