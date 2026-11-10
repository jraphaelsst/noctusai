# Polling request budget — every loop pays per tick, forever

> Born 2026-11-10 from a prod incident: the Supabase project was put under Fair Use restriction
> (every REST call → HTTP 402) at ~22:00Z on 2026-11-09, after our own backends spent the Free-plan
> egress quota by polling an EMPTY job queue. Self-contained: you can act on this file alone.

## The rule

**A loop that runs forever has a cost per tick. Before you add or change one, write down: how often
it ticks, how many calls each tick makes, what each call returns, and who pays (which quota).
Multiply it out per day. If you can't, you are not done.**

- **Idle must be cheap.** A poller backs off when there is nothing to do (exponential, capped,
  reset on work). A fixed 1-second idle poll is a bug, not a default.
- **Never count by fetching.** Counting rows = a count query (`Prefer: count=exact` + `limit=0`,
  or an RPC), never `select=*` + a large limit.
- **Nothing expensive in a per-tick gate.** A `claim_gate` / health check runs on EVERY poll. It
  must be O(1) and cached; a stats read inside it multiplies by the poll rate.
- **Flags and settings are cached** in-process with a short TTL (30-60 s), never re-read per tick.
- **Tests with fakes cannot see this.** A fake Supabase client makes every call free, so a loop
  firing 15k calls/hour is green. Assert the call COUNT over N idle ticks, not just correctness.

## The incident (2026-11-09/10)

Measured from the Supabase edge logs (project `NoctusAI`, 2026-11-09 13:00-22:00Z):

| Calls | Source | Cause |
|---|---|---|
| ~15,300/h (~4/s) `rpc/claim_next_job` | seed `domain/jobs/worker.py` `Worker.run_forever`, ~10 product workers | fixed `poll_interval_seconds=1.0` idle sleep, no backoff, empty queue |
| ~5,000/h `GET jobs` (3 queries every ~2 s, `type=transcricao`) | SW `transcricoes/biblioteca_worker.py` `claim_gate` → `voz_ocupada` → seed `JobRepository.queue_stats` | stats computed by `select=*&limit=5000` (STATS_ROW_CAP), called on EVERY claim attempt; zero matching rows existed |
| ~55k/day `platform_settings`, `fotos_platform_settings` | flag reads | no cache |

Total ≈ 26k REST calls/hour ≈ 620k/day against a Free plan (5 GB egress/month). The data was small
(largest table 66 MB): the quota went on call volume, not payload. Org plan: **free**. Restriction
lifts only at the billing-cycle reset or on upgrade (Pro, spend cap off).

### How each piece got in (git `Co-Authored-By` trailers)

| Commit | Date | Piece | Model |
|---|---|---|---|
| `3f871dd0f` | 2026-05-04 | seed Worker, fixed 1 s idle poll | Claude Opus 4.7 |
| `6bbcd50f3` | 2026-09-16 | `queue_stats` = `select=*` limit 5000 | Claude Opus 5 |
| `656d2eb87` | 2026-10-10 | `claim_gate` calls `queue_stats` every tick (2 s) | Claude Sonnet 5.5 |

Owner decision (2026-11-10): the platform's models are **Opus 5.5, Sonnet 5.5 and Haiku 5.5** only.
Code authored by earlier generations (Opus 4.6/4.7/4.8, Opus 5, Sonnet 4.6/5, Fable 5; Apr-Sep 2026,
see `git log --format='%(trailers:key=Co-Authored-By,valueonly)'`) is legacy: when you touch it,
audit its hot paths (loops, schedulers, per-request reads) against this rule.

### Why nothing caught it
- Tests run on a fake client: calls are free and instant.
- Reviews, councils and security passes judge correctness, auth and LGPD; none asked "how often
  does this run and what does each run cost?".
- No prod telemetry on Supabase request volume or egress; the first signal was the 402.
- The same blind spot appeared the same day in tooling: a keeper fix added ~10 s to every commit
  fleet-wide and passed two reviews (see `noc-learn-refine` 2.2.0, "attack the fix's COST").

## What fixes it (and where)
- **Construction:** seed Worker idle backoff (1 s → 30 s cap, reset on claim) plus wake-on-enqueue;
  `queue_stats` via count queries; cached flags; per-tick gates cached. Branch `feat/supabase-egress-polling`.
  And the declaration below: the author multiplies the cost out before the loop ships.
- **Backstop (built, blocking): keeper `check_polling_request_budget`** (`cli.py --check-polling-request-budget`,
  `tools/noctus/dev/polling_request_budget.py`; AST only: `ast` for Python, ts-morph for TypeScript). Blocking in
  pre-commit (scoped to staged files) and in CI (full tree, `commit-range-keepers`); severity high; **no baseline**,
  so the tree is either declared or red. Rules:
  - **R1** a `while` loop whose body calls `sleep` / `time.sleep` / `wait_for(..., timeout)` /
    `asyncio.wait(..., timeout=)` / `Event.wait(<timeout>)` needs a declaration.
  - **R2** a periodic registration needs a declaration: the seed scheduler's
    `register(name, fn, hours|minutes|seconds=...)`, APScheduler `add_job` with an interval trigger, any call
    passing `poll_interval_seconds` / `max_idle_interval_seconds` (the seed `Worker` and its wrappers).
  - **R3** inside a function that holds an R1 loop, or whose name says tick / poll / gate / stats / run_once, a
    `.select("*")` (or `.select()`) or a `.limit(<int or module constant> > 1000)` is a finding **even when
    declared**: count (`count="exact"`, `limit(0)`) or name columns. `.single()` / `.maybe_single()` /
    `.limit(<=1)` are bounded and pass. Escape for a genuinely tiny table:
    `# poll-budget-ok: <reason of 10+ chars>` on the call's line or up to 3 lines above.
  - **R4** (TypeScript) a `refetchInterval` whose value is not literal `false` / `undefined` / `0`, any
    `setInterval(`, and `refetchIntervalInBackground: true` (needs `hidden=runs` in its declaration).
  - **The declaration** sits on the construct's line or up to 3 lines above, and is valid only if it carries a
    number followed by `/day` (so it was multiplied out); an empty or numberless declaration is itself a finding:
    - Python: `# poll-budget: <cadence>; <k> calls/tick; worst <N>/day; idle=<backoff|event|fixed>`
    - TypeScript: `// poll-budget: <cadence>; <k> calls/tick; worst <N>/day per open tab; hidden=<paused|runs>`
    - Worked example: `# poll-budget: every 30 s idle; 1 calls/tick; worst 2880/day; idle=backoff` (30 s cap =
      2 ticks/min x 1440 min = 2,880/day for one worker; multiply by the number of workers/replicas).
  - **What it cannot see** (so review still owns it): a read reached from a loop through a helper it does not
    name (the call graph is not followed); a poll driven by `for _ in range(n)` + sleep, a recursive
    `call_later` / timer re-arm, or a cadence set through a config value the registration does not show; per-request
    reads that repeat (uncached flag/settings/credentials reads per LLM call, a config reloaded every request,
    one `scheduler_runs` insert per tick, `select=*` reads in a worker that is not named tick/poll/gate/stats);
    `.range(0, N)` large pages. Those are caught only by the measurement below.
- **Telemetry (being built): `noctus.dev.supabase_request_budget`**: Supabase calls per product per route per
  minute from the edge logs, versus the plan quota, surfaced in the daily ops check (`noc-daily-ops`) with an alert
  well before the quota. It is the measurement that finds what the static keeper cannot.

## Depth
`KB § PATTERNS/backend/postgrest-row-cap.md` (the sibling: what a fake hides) ·
`KB § PATTERNS/backend/request-path-latency.md` · skill `noc-fast-responses` (round-trip counting).
