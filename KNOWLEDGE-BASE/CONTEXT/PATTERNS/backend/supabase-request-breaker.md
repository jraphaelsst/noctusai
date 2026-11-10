# Supabase request breaker — stop the runaway loop, alert, evaluate, re-arm

> Born 2026-11-10, owner: "transform this into a safety mechanism that will watch over that, so we stop and ALERT, the
> process is killed and we evaluate". Self-contained. Why it exists: `KB § PATTERNS/backend/polling-request-budget.md`
> (our own loops made ~620k REST calls/day; Supabase answered 402 to every product; nothing noticed until it was dead).
> Redesigned in round 4 (security re-check): the breaker used to HOLD sources it could not reliably attribute and to credit
> work; it now holds only what it can name and own.

## The rule

**Only a named, owned loop can ever be held. Everything else is counted and ALERTED, never stopped.** A request handler,
boot work, an unattributed thread or a spawned background task can never be refused because of a source it did not name.
On for every product by construction (seed); no per-product code.

| Source | Set by | On overrun |
|---|---|---|
| `worker:<job types>` (HOLDABLE) | the jobs Worker: ONLY the cost of an EMPTY poll (claim + claim-gate calls when nothing was claimed) | trip -> the Worker loop PARKS (zero Supabase calls) until a human re-arms |
| `scheduler:<job>` (HOLDABLE) | `api/scheduler.py`: one unit per RUN START (a job firing every second is the runaway) | trip -> the job does not run; no ledger row (that row is a Supabase call) |
| `job:<type>` / `job:scheduler:<job>` | each job's own execution | alert-only + the per-JOB cap below |
| `http` | `SupabaseSourceMiddleware`, the OUTERMOST middleware | alert (6,000 / 5 min / process) |
| `startup` | seed lifespan startup (catalog publish + the product's `lifespan_startup`) | alert-only (1,500 / 60 s, 2,000 / h) |
| `bg:<name>` | `spawn_background` / `run_in_thread` (`primitives/background.py`) | alert-only |
| `unattributed` | the contextvar default (a bare `create_task` / `Thread`, import-time code) | alert-only at 300 / 5 min — "somebody forgot a scope" |
| `egress:auth|storage|functions|other` | the same transport, non-REST calls | alert-only |

## Counting and holding

- THE count point: `integrations/http_pool.py` `TimingTransport.handle_request` — every seed-built client rides it (pooled,
  kill-switch, stock fallback). In-memory, O(1), no network (~0.4 us per call).
- **Worker split.** (a) LOOP: an empty poll bills `max(1, calls made)` to `worker:<types>`; budget 300 / 5 min or 2,000 / h
  holds the loop. A poll that claims a job bills nothing — productive work needs no credit, **there is no credit scheme**, so
  nothing can be inflated into headroom. (b) JOB: everything one job does is capped at `job_call_cap` (default 2,000,
  per Worker): call number cap+1 raises `JobBudgetExceeded` and the job is DEAD-LETTERED with the reason — never the type,
  never other tenants. Scheduler runs are capped per run (default 20,000 = the ceiling).
- **Absolute ceiling.** A configured budget above `MAX_BUDGET_CALLS` (20,000) is rejected; `NOCTUS_BREAKER_BUDGETS`
  (JSON per source) can tune but never disable or exceed it. The hourly 2,000 on a holdable source is the default floor.
- **Fleet key** `noctus:breaker:fleet` holds every Worker loop and scheduler tick of every product. It does NOT stop request
  handling, boot, or jobs already running (their per-job cap still applies). Read from Redis at most every 10 s per process
  (one MGET); a seed-owned `refresh_loop` ticker runs it even in processes with no Worker or scheduler.

## Trip, persistence, alert

Held in memory at once (works with Redis down); persisted to `noctus:breaker:<product>:<source>` as
`{reason, rate, window, tripped_at, by}` with no TTL; per-slug index set `noctus:breaker:<slug>:index` (no SCAN anywhere);
owner emailed once per trip via the seed Resend sender (`RESEND_API_KEY` + `NOCTUS_BREAKER_ALERT_EMAIL` or
`WATCHDOG_ALERT_EMAIL`; `NOCTUS_BREAKER_ALERT_FROM`); failures raise `BreakerAlertNotConfigured`, logged CRITICAL, kept and
retried. Redis down: the trip still stops the source in memory and alerts; reading fails OPEN, loudly. **No REDIS_URL:** one
alert and `/api/health` reports `breaker_degraded`.

**A persisted hold is never silently released.** If the key vanishes (flush, eviction, tampering) the product rewrites it and
alerts CRITICAL; it releases only on a matching re-arm marker `noctus:breaker:<slug>:rearm:<source>` whose `tripped_at`
equals the trip's (written by every real re-arm, consumed on release).

## Re-arm (human only, reason required)

Reason: printable text, no control characters, <= 300 (`BREAKER_REASON_RE`, route and tool). Surfaces:
- platform-admin route `GET/POST /api/platform/supabase-breaker[/rearm|/trip]`: canonical `require_platform_admin` incl.
  admin-MFA AAL2; sources must match `BREAKER_SOURCE_RE` (`worker:*` / `scheduler:*`); `fleet` and everything alert-only are 422.
  The product writes its audit to `noctus:breaker:<slug>:audit` (its ACL namespace), `claimed_by` = the authenticated user id.
- MCP `noctus.dev.supabase_breaker action=status|rearm|trip|audit`: Redis over the VPS SSH chokepoint, independent of
  Supabase; the ONLY way to set/re-arm the fleet key. Audit rows (ops-only `noctus:breaker:audit`, capped 1,000) carry
  `claimed_by` plus the unspoofable `session` (CLAUDE_CODE_SESSION_ID), `os_user`, `host`. `rearm`/`trip` with `confirm=True`
  are steward-class: refused INSIDE `supabase_breaker()` for a non-steward session (CLI, fresh subprocess, peer servers).

## Redis ACL compatibility (feat/redis-acl-lockdown)

Product identity = read `noctus:breaker:fleet`, read/write `noctus:breaker:<slug>:*` only (source keys, index, audit,
markers); it can never delete the fleet key. The MCP tool probes the VPS ONCE (`docker ps` + the ops password file): a running
`noctus-redis-acl` REQUIRES the ACL path (secret read on the VPS into `REDISCLI_AUTH`, never over SSH or on argv, `--user ops`)
and never falls back to the plain `noctus-redis`; no ACL container and no password file = today's unauthenticated Redis; an
unreachable probe raises. `NOAUTH`/`WRONGPASS`/`NOPERM` fail loud. `status` reads the fleet key + each live product's index
(`SMEMBERS`, products from `deploy/fleet/build-scope.txt`), keeps only well-formed keys of that product (<= 200), then ONE
`MGET --json`; product-written values are data (control characters stripped, length capped) before they are echoed. The audit
cap needs `+ltrim` on the ops user; a denied LTRIM is a returned warning, never a lost re-arm.

## Rules for code that adds a loop
1. A long-lived loop is a registered Worker or scheduler job. Anything else that detaches work uses `spawn_background(name,
   coro|fn)` / `run_in_thread(name, fn)` (explicit `bg:<name>`, context-carrying).
2. A poll of the breaker itself is declared: `# poll-budget: <cadence>; <k> calls/tick; worst <N>/day; idle=...`.
3. Never catch `BreakerOpen` / `JobBudgetExceeded` and carry on.
4. Known migrated sites: social-wiring `start_worker` (`bg:social-wiring-conversation-worker`), `ads_router` sync threads,
   `pos_aceite_service`, `youtube_chat_commands`; seed `tool_loop` carries the caller's context; the audit flush runs as `bg:audit-flush`.

## Gaps (named)
- A product that builds its own `supabase.create_client` / raw httpx to `*.supabase.co/rest` bypasses the count.
- Counts are per process; two containers each hold/alert separately (alerts dedupe per product+source+time).
- The EOA event is a log line + sink seam: `NOC-REMEDIATE[breaker-event-table]`. A keeper flagging `create_task(` / `Thread(`
  without a scope is `NOC-REMEDIATE[breaker-unscoped-loop]` (routed to the polling keeper).
- The route's audit lives in the product namespace (the product cannot write the ops-only list); read both with `action=audit`.
