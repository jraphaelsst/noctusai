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
| `worker:<job types>` (HOLDABLE) | the jobs Worker: ONLY an empty poll that VIOLATES THE LOOP'S CADENCE (see below) | trip -> the Worker loop PARKS (zero Supabase calls) until a human re-arms |
| `scheduler:<job>` (HOLDABLE) | `api/scheduler.py`: a run is billed (at its REAL Supabase call count) ONLY when it started less than the platform idle-poll floor after the previous run AND made >= 1 call — a tick an `IdleGate` skipped makes none and is free, a nightly job is never "frequent" | trip -> the job does not run; no ledger row (that row is a Supabase call) |
| `job:<type>` / `job:scheduler:<job>` | each job's own execution | alert-only + the per-JOB cap below |
| `http` | `SupabaseSourceMiddleware`, outermost: the seed app is a `SeedFastAPI` whose built stack is always wrapped by it, so product middleware added later runs inside `http` | alert (6,000 / 5 min / process) |
| `startup` | seed lifespan startup (catalog publish + the product's `lifespan_startup`) | alert-only (1,500 / 60 s, 2,000 / h) |
| `bg:<name>` | `spawn_background` / `run_in_thread` (`primitives/background.py`; drops the spawner's per-job budget/tally) | alert-only (600 / 5 min, 2,000 / h) |
| `*` (aggregate) | every call of the process | alert when the projected daily total passes a share of the quota (below) |
| `unattributed` | the contextvar default (a bare `create_task` / `Thread`, import-time code) | alert-only at 300 / 5 min — "somebody forgot a scope" |
| `egress:auth|storage|functions|other` | the same transport, non-REST calls | alert-only |

## Counting and holding

- THE count point: `integrations/http_pool.py` `TimingTransport.handle_request` — every seed-built client rides it (pooled,
  kill-switch, stock fallback). In-memory, O(1), no network (~0.4 us per call).
- **Worker split — platform-FLOOR billing, not volume.** (a) LOOP: every consecutive EMPTY poll whose gap from the previous
  empty poll is below the PLATFORM floor `NOCTUS_MIN_IDLE_POLL_S` (default 10 s) is billed (`max(1, calls made)`) to
  `worker:<types>`. Not the Worker's own declared cadence: a loop declaring `poll=max_idle=1 s` is "on its cadence" every
  time, so billing against it could never trip (the round-6 hole; the test now uses a REAL Worker with the default idle sleep).
  Free: the first empty poll after a processed job; the first 6 sub-floor polls of a backoff ramp (1,2,4,8 s...); wake-followed
  empty polls, at most 30 per 5 min (a producer that keeps waking an empty loop cannot launder it); failed claims while the
  loop applies its error backoff (1 s doubling to the idle cap; the loop survives). Idle at >= the floor is never billed.
  What is TRUE: the loop is held when its billed empty polls exceed 300 / 5 min or 2,000 / h. On ONE clock, a loop polling
  faster than once per second trips inside 5 minutes; exactly once per second is 300 / 5 min (not above it), so the hourly rule
  trips it after ~33 min (2,001 polls); a steady gap above ~1.8 s is NOT held (it falls under the alert-only rules).
  Billing uses the polls' REAL call count (claim + gate Supabase calls), never a floor of 1, and a poll that attempted NO claim
  (claim gate closed: a paused Worker) is never billed, whatever wakes it; a paused Worker also IGNORES job wakes and backs off toward max_idle (so its gate is read a bounded number of times per hour). A wake does NOT reset the ramp allowance (that reopened wake laundering: a wake, then two sub-floor polls, then a wake was never billed); only a gap at or above the floor does. The floor itself
  is bounded: finite, at most 60 s, and below the default (10 s) it is alerted and, in a deploy context, clamped to the default.
  The error-backoff sleep ignores the job waker; `RescheduleLater` delays are clamped to at least the floor. Job arrivals (1-2 jobs/s) are free: each poll after work claims a job or is the free first
  empty. In a DEPLOY context a `max_idle_interval_seconds` below the floor is clamped to it with a loud warning (no product sets
  `max_idle_interval_seconds` today: all use the default idle cap, 300 s since W1-C). A poll that claims a job bills nothing; **there is no credit
  scheme**. (b) JOB: everything one job does counts toward its own cap (`job_call_cap`, per-type
  `job_call_caps`), both clamped to `MAX_BUDGET_CALLS`. **OBSERVE mode (default):** reaching the cap only ALERTS (`job-cap:*`,
  once per job) and the job is dead-lettered at the hard ceiling; **ENFORCE** (`NOCTUS_BREAKER_JOB_CAP_ENFORCE=1`)
  dead-letters at the cap. The Worker checks the budget AFTER the handler however it ended, so a handler's own `except` cannot
  swallow it. Scheduler runs likewise (default per-run 20,000). `NOC-REMEDIATE[breaker-job-cap-calibration]`: tighten per-type
  caps from measured p99, then flip the default.
- **Per-process AGGREGATE (the incident shape).** Every call also feeds `*`: alert when the projected daily total (last hour
  x24, last 5 min x288) passes `NOCTUS_BREAKER_AGGREGATE_SHARE` (default 0.5) of `NOCTUS_SUPABASE_DAILY_QUOTA`. Default quota
  500,000 calls/day = the incident-derived planning figure for the Free plan (Supabase publishes an egress quota, 5 GB/month,
  not a call count; ~620k/day exhausted it). ~620k/day spread over six loops each under its own threshold raises exactly
  this alert. It only ALERTS: the FLEET-WIDE aggregate trip is the off-host watchdog's job (feat/supabase-request-telemetry).
  Opt-in `NOCTUS_BREAKER_FLEET_HOLDS_BG=1` lets the fleet key also refuse `bg:*` (default off).
- **Env cannot loosen the nets.** A budget override looser than the default rules is accepted but alerted. `NOCTUS_SUPABASE_DAILY_QUOTA` above the default raises a config alert and is clamped to 2x the default; overrides of `*`, `http`, `startup`, `unattributed` are ignored (alerted). A per-source rule is a RATE (`max_calls x 3600 / window`) and may not exceed the ceiling DERIVED from the quota (quota x share / 24 per hour, ~10,416 by default) — rejected otherwise; `NOCTUS_BREAKER_BUDGETS`
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

**Re-arm order.** The `rearm` audit row is appended FIRST and is mandatory: if it cannot be written the key is NOT deleted and the route answers 502. Its nonce is the PERSISTED key's `tripped_at` (read first), so a serving process that holds the trip only remotely can re-arm one a peer holds locally. Every release by this path is announced (event + alert with claimed_by/host/pid/at). The audit row and the RO `rearm:*` are SIGNALS, **not a security boundary** (the product's own Redis identity can write its audit list). Route re-arms are mutating requests, so they reach core's append-only `audit_logs` via the `AuditMiddleware`; a dedicated EOA row is `NOC-REMEDIATE[breaker-rearm-eoa]` (with `breaker-event-table`). The audit lookback scans the whole capped list (1,000), filtered by key.

**Re-arm is not atomic.** The persisted-key GET is load-bearing (an error raises before the audit row or the DEL); if the DEL fails after the row, a compensating `rearm_aborted` row is appended and the lookback honours the NEWEST row for that key+nonce. `NOC-REMEDIATE[breaker-rearm-cas]`: a compare-and-delete needs WATCH/MULTI/EXEC in the product ACL (feat/redis-acl-lockdown) and then here (feat/supabase-breaker).

**A persisted hold is never silently released.** If the key vanishes (flush, eviction) the product rewrites it and alerts
CRITICAL; it releases only on a matching re-arm marker `noctus:breaker:<slug>:rearm:<source>` (TTL 1 day, never deleted by a
product) whose `tripped_at` equals the PERSISTED key's `tripped_at` (so several processes and a deploy overlap agree). The marker
guards against eviction/flush, NOT against the product: human re-arm is enforced by who can call it (the AAL2 platform-admin
route and the steward-gated tool). Trips made while Redis was down are re-persisted when it returns.

## Re-arm (human only, reason required)

Reason: printable text, no control characters, <= 300 (`BREAKER_REASON_RE`, route and tool). Surfaces:
- platform-admin route `GET/POST /api/platform/supabase-breaker[/rearm|/trip]`: canonical `require_platform_admin` incl.
  admin-MFA AAL2; sources must match `BREAKER_SOURCE_RE` (`worker:*` / `scheduler:*`); `fleet` and everything alert-only are 422.
  The product writes its audit to `noctus:breaker:<slug>:audit` (its ACL namespace), `claimed_by` = the authenticated user id.
- MCP `noctus.dev.supabase_breaker action=status|rearm|trip|audit`: Redis over the VPS SSH chokepoint, independent of
  Supabase; the ONLY way to set/re-arm the fleet key. Audit rows (ops-only `noctus:breaker:audit`, capped 1,000) carry
  `claimed_by` plus the unspoofable `session` (CLAUDE_CODE_SESSION_ID), `os_user`, `host`. `rearm`/`trip` with `confirm=True`
  are steward-class: refused INSIDE `supabase_breaker()` for a non-steward session (CLI, fresh subprocess, peer servers).

## Redis: the dedicated breaker instance (feat/redis-acl-lockdown)

The breaker lives on its own Redis, `noctus-breaker-redis` (breaker keys ONLY, `noeviction`), never on the app Redis.
- **Connection.** `make_breaker_store` reads `NOCTUS_BREAKER_REDIS_URL` + `NOCTUS_BREAKER_REDIS_USERNAME` /
  `NOCTUS_BREAKER_REDIS_PASSWORD` and passes them to `make_redis_client` explicitly; `REDIS_*` stays the app connection.
  Unset: in a deploy context it FALLS BACK to the app Redis with a loud warning (`NOC-REMEDIATE[breaker-redis-cutover]`: the
  cutover is per service and gradual; after the ACL cutover the app user has no breaker keys and every write is NOPERM);
  outside a deploy it keeps the in-memory Fake. A deployed process whose store is not Redis, OR is on the app-Redis fallback,
  sets `breaker_degraded` (also on a Redis refusal of this service's credentials/ACL: NoPermission/Authentication is
  configuration, not an outage), and a boot probe (GET of the fleet key) degrades it at startup — an unreachable-at-boot state is TRANSIENT and clears on the first successful refresh, a configuration refusal stays sticky. The client resolves ONLY the
  breaker credentials (never `REDIS_USERNAME`/`REDIS_PASSWORD`) and refuses to connect unauthenticated. MCP `status` lists the
  services whose container has no `NOCTUS_BREAKER_REDIS_URL` (`on_app_redis_fallback`), those with the URL but no USERNAME/PASSWORD
  (`breaker_credentials_incomplete`) and the ones it could not inspect (`unverified_services`: never assumed healthy).
- **Product grant (pinned by a test).** RW `noctus:breaker:<slug>:{worker:*,scheduler:*,gate:*,audit,index}`; READ-ONLY
  `noctus:breaker:<slug>:rearm:*` and `noctus:breaker:fleet`. Commands: GET MGET SET DEL EXISTS TTL PTTL SADD SREM SMEMBERS
  SISMEMBER SCARD RPUSH LTRIM LRANGE LLEN PING — no MULTI/EXEC, SCAN, KEYS or scripting (the audit cap is a non-transactional
  pipeline). A spy test lists every key and command the store touches against that grant. The product never writes `rearm:*`
  nor the fleet key nor the global audit list, and cannot re-arm the fleet (`Breaker.rearm("fleet")` raises).
- **Re-arm signal between processes.** A re-arm by ops (MCP tool) writes the read-only marker `rearm:<source>` (TTL 1 day) and
  the global audit row. A re-arm by a product process (the platform-admin route) writes NO marker: it DELs the key and appends
  a `rearm` row carrying the PERSISTED key's `tripped_at` to `noctus:breaker:<slug>:audit`; another process of the same product
  whose key vanished releases only on a matching marker OR a matching audit row, else it rewrites the key and alerts CRITICAL.
- **MCP tool** (`VpsRedisOps`): probes the VPS once. A running `noctus-breaker-redis` REQUIRES the ACL path (`ops` user, secret
  read on the VPS into `REDISCLI_AUTH`, never over SSH or on argv) and never falls back to the plain `noctus-redis` (used only
  before the cutover, when neither the container nor `ops.pass` exists). An unreachable probe raises. `NOAUTH`/`WRONGPASS`/
  `NOPERM` fail loud, read from the exit code and STDERR only. `status` reads the fleet key + each live product's index
  (`SMEMBERS`, products from `deploy/fleet/build-scope.txt`), keeps only well-formed keys of that product (<= 200), then ONE
  `MGET --json`; product-written values are data (control characters stripped, length capped) before they are echoed. The
  off-host `breaker-trip.sh` (feat/supabase-request-telemetry) targets the same container.
- `rearm`/`trip` with `confirm=True` are steward-class (in-tool refusal for non-steward sessions).

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
