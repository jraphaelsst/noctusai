# Backend craft canon — the profession's standards, mapped onto the house

> **What this is.** The general backend-engineering canon (architecture, FastAPI, Pydantic, API
> design, data, reliability, observability, testing, Python quality) that a master-level backend
> engineer brings to this codebase, with every principle mapped to the house mechanism that
> implements it, a checklist, and anti-patterns. Owner: `backend-engineer`
> (`.claude/agents/backend-engineer.md`). Authored 2026-11-05 (agent-refinement W1-S3, from the
> verified audit `projects/agent-refinement/audits/audit-backend-engineer.md`).
>
> **Why it exists.** The house docs record incidents and their gates very well; they barely teach
> the discipline those incidents are instances of. An engineer who knows only the incident list
> re-derives zero-downtime migrations, idempotency and retry budgets by hand
> (`products/agents/backend/migrations/035_julia_v2_threads_constraints.sql:23-26` is that,
> done carefully, once).
>
> **How to use it.** (1) **The seed mechanism wins.** If a seed primitive, keeper or `noctus.dev.*`
> tool covers a point, use it — the canon explains why it exists and covers only what the house
> has not built yet. A canon idea with no house mechanism is a *proposal to surface*, never a
> licence to hand-roll a per-product version (CLAUDE.md §1 seed-first, replication-to-seed).
> (2) Read the section your slice touches, run its checklist, and use § 12 for the one-page
> new-endpoint / table / migration / integration / job checklists. (3) Data-layer depth lives in
> `KB § PATTERNS/backend/postgres-craft.md` (§ 5 here is its summary).

## 0 · Standard term ↔ house term

| Standard term | House mechanism | Where |
|---|---|---|
| Application factory | `create_product_app(name, schema, settings, routers, standard_routers=…)` | `seed/framework/backend/noctusai_seed/app.py:70` |
| DI container / providers | dep factories: module slots + `configure_X_module(...)`, `make_get_current_user_org` | `KB § PATTERNS/backend/backend.md` § FastAPI dependency factories |
| Ports & adapters | Protocol + Fake + Real + `make_<x>` factory | `KB § PATTERNS/backend/seed-fake-real-adapter.md` |
| Problem Details (RFC 9457) | `AppException` → `{"error": {code, message, details?}}` | `seed/lib/backend/noctusai_lib/primitives/exceptions.py:24-36,174-188` |
| Transaction script / aggregate boundary | one Postgres function called via `.rpc(...)` | `KB § PATTERNS/backend/postgres-craft.md` § 5 |
| Work queue / transactional outbox | jobs organ (`jobs` table, `claim_next_job` RPC, `Worker`) | `seed/lib/backend/noctusai_lib/domain/jobs/` |
| Idempotent consumer / inbox | `EventInbox` (durable), `message_store` UNIQUE, WhatsApp SETNX pre-filter | `domain/payments/event_inbox.py:28`, `domain/chatbot/message_store.py:1-12`, `integrations/whatsapp/dedup.py:1-36` |
| Rate limiter / backoff | `noctusai_lib.integrations.rate_limit` | `KB § PATTERNS/common/outbound-rate-limiting.md` |
| Trace / correlation id | `X-Correlation-ID` via `CorrelationIdMiddleware` | `seed/lib/backend/noctusai_lib/api/middleware.py:94-134` |
| RED metrics (partial) | `req_timing` log line + `Server-Timing` + `noctus.dev.latency_report` | `seed/lib/backend/noctusai_lib/api/request_timing.py:7,150,187`; `KB § PATTERNS/backend/request-path-latency.md` § Budget + gate |
| Health / readiness | `/api/health` (+ `startup_hook_error`) | `KB § PATTERNS/backend/startup-hook-must-not-be-fatal.md` |
| Contract tests | boundary-contract tests B1–B7; skill `noc-contract-first` | `KB § PATTERNS/backend/boundary-contract-tests.md` |
| Migration framework | `scaffold_migration` → `migrate_product` → `migration_replay` (PGlite) → `schema_drift` | `KB § PATTERNS/backend/database-rls.md` § Migrations |

---

## 1 · Service architecture

**Principle.** Layer by responsibility, keep the domain independent of transport, and make every
dependency explicit. Use the tactical parts of DDD lightly. An **aggregate** is a consistency
boundary: the set of rows that must change together. A **value object** is an immutable, validated
value such as money, a phone number or a CPF. A **domain service** is logic that belongs to no
single entity. From 12-factor: config lives in the environment (III), and processes are disposable
(IX). Disposable means fast startup and graceful shutdown.

**House application.**
- Layers: `routers/ → services/ → schemas/` + `dependencies.py`, `database.py`; routers thin
  (<30 lines), services take dependencies explicitly (`KB § PATTERNS/backend/backend.md` § Layer
  structure, § Router → Service discipline). FastAPI's own "Bigger Applications" layout
  (one `APIRouter` per module, shared deps module) is the same shape.
- Value objects live in `noctusai_lib.primitives` (`money.py:22-45`, `phone.py:91`); never
  re-normalize a phone or a currency inline in a service.
- Aggregate = transaction boundary. Over PostgREST, one call is one transaction, so a multi-row
  aggregate write is **one RPC** (`postgres-craft.md` § 5).
- Config: `ProductSettings` (pydantic-settings) — never `BaseAppSettings` directly
  (keeper `check_config_extends_product_settings`, `KB § 03-SEED-ARCHITECTURE.md`).
- Disposability: lifespan hooks are side effects, never boot preconditions
  (`app.py:444-510`; `startup-hook-must-not-be-fatal.md`); workers stop on an event (§ 6.7).

**Checklist.** [ ] business rule lives in a service, not a router · [ ] the write set that must be
atomic is named and lives in one RPC or one constraint · [ ] new value type ⇒ a primitive, not a
helper in a product · [ ] config read from settings, never `os.environ` scattered in services.

**Anti-patterns.** Fat routers; a service importing `fastapi.Request`; module-level singletons
bound at import (the boot-order trap, `backend.md` § The boot-order trap); "repository" classes
that wrap PostgREST one-to-one and add nothing.

---

## 2 · FastAPI mastery

### 2.1 Dependencies
- **Per-request cache.** A dependency used several times in one request is called once and its
  value is reused; `Depends(dep, use_cache=False)` opts out. The house relies on this through the
  request-scoped memo (`request-path-latency.md` § Async dependencies + the request-scoped memo).
- **`yield` dependencies** give you setup and teardown. Exit code runs after the response by
  default. If you catch an exception in one, re-raise it unless you are converting it to an
  `HTTPException`.
- **The 422 trap.** `ProductDependencies.get_*` are used WITHOUT `Depends()`. Wrapping them makes
  FastAPI treat their parameters as query params (`backend.md` § Why `Depends(get_org_id)` … is broken).
- Auth is a dependency factory, never per-route code: `make_get_current_user_org`
  (`KB § backend/07-AUTH-SECURITY.md`; `KB § PATTERNS/backend/no-metadata-authz.md`).

### 2.2 `def` vs `async def` — decision table
FastAPI runs a `def` endpoint/dependency in a threadpool and an `async def` on the event loop.

| Handler body | Declare | Why |
|---|---|---|
| Sync supabase / sync SDK / file IO, awaits nothing | `def` | runs in the threadpool; loop stays free |
| Awaits async IO only (`httpx.AsyncClient`, async Redis) | `async def` | native concurrency |
| Mixes awaits with a sync call | `async def` + `await run_blocking(...)` / `anyio.to_thread.run_sync(...)` | never block the loop |
| CPU-heavy work (>~50 ms) | a job (§ 6.4) | threadpool is shared with every request |

House: keeper `check_async_handler_sync_db` (ratchet) + codemod `noctus.dev.async_handlers_to_def`;
`run_blocking` at `seed/lib/backend/noctusai_lib/api/auth/_blocking.py:48`
(`KB § PATTERNS/backend/request-path-latency.md`).

### 2.3 Lifespan
FastAPI's `lifespan` context manager replaces the deprecated `@app.on_event`. The seed owns the
lifespan and exposes `lifespan_startup` / `lifespan_shutdown` callables
(`app.py:76-77,444-510`). A failing startup hook is caught, parked on
`app.state.startup_hook_error` and surfaced on `/api/health`, so it never kills uvicorn
(`app.py:464-492`). Rule: **never** add `@app.on_event` (0 uses in seed or active products,
grep 2026-11-05); **never** make a startup hook a precondition for serving.

### 2.4 `dependency_overrides` vs the DI seam
- `app.dependency_overrides[dep] = fake` is FastAPI's test hook for **route-level** dependencies.
  It is right when the thing under test is the HTTP surface. Seed routers use it as the
  replacement point (e.g. `seed/lib/backend/noctusai_lib/domain/commerce/router.py`).
- The **DI seam** (constructor / factory injection, `configure_X_module`) is right for services and
  adapters. It is the house default (`KB § PATTERNS/backend/di-test-seam.md` § The fix).
- Never monkey-patch our own module attributes to get either (CLAUDE.md §1; `test_seam_guard`).

### 2.5 Background tasks vs the jobs organ

| Need | Use |
|---|---|
| Tiny best-effort follow-up that may be lost on restart (a log line, a cache warm) | `BackgroundTasks`, or `primitives.tasks.schedule_coro` (logs failures with a traceback; `seed/lib/backend/noctusai_lib/primitives/tasks.py:1-40`) |
| Anything that must happen (email, webhook out, LLM call, provider sync), needs retry, or is slow | jobs organ: `JobRepository.enqueue(..., dedupe_key=…)` + `Worker` (§ 6.4) |

FastAPI's own docs say to use a real queue for heavy work. `BackgroundTasks` runs after the
response, in the same process, and dies with it.

### 2.6 Response models
Responses go through `success_response` / `paginated_response` / `ok_response`
(`backend.md` § Responses; `seed/lib/backend/noctusai_lib/primitives/responses.py:31-92`). A typed
response model that the FE consumes inherits `StrictHttpModel` so drift fails loudly (§ 3).

**Checklist (§ 2).** [ ] handler `def`/`async def` chosen by the table · [ ] deps via factories,
no `Depends()` on `ProductDependencies.get_*` · [ ] no `on_event` · [ ] must-happen side effects
go through the jobs organ.

---

## 3 · Pydantic v2

- **Strict at the HTTP boundary.** Pydantic ignores unknown fields by default, so a misspelt
  field is silently dropped and the write never happens. Inbound schemas inherit
  `StrictHttpModel` (`model_config = ConfigDict(extra="forbid")`,
  `seed/lib/backend/noctusai_lib/api/schemas.py:50-67`; `KB § PATTERNS/backend/pydantic-strict-http.md`).
  Subclass configs merge, so strictness propagates.
- **Dump for PostgREST with `mode="json"`.** `UUID`, `datetime` and `Decimal` must become JSON
  types before supabase-py serializes them (`backend.md` § Pydantic → supabase writes; keeper
  via `noctus.dev.check_model_dump_json_mode`).
- **Validators vs domain logic.** A validator checks the *shape* of a single value or object
  (format, range, cross-field consistency within one payload). A rule that needs the DB, the
  caller or the clock belongs in the service.
- **Polymorphic payloads → discriminated unions** (`Field(discriminator="kind")` with a `Literal`
  tag per member). This is faster, more predictable, and gives one error list instead of N.
  Typical uses are webhook event families and automation steps.
- **`TypeAdapter`** validates a non-model type (`list[Item]`, a `TypedDict`) without a wrapper model.
- **Settings** are pydantic-settings models (`ProductSettings`); secrets never get defaults.

**Anti-patterns.** `BaseModel` on a request body; `dict` bodies (`body.get("x")` — the team router
still has these, `seed/framework/backend/noctusai_seed/routers.py:479-490`); business rules in
`@field_validator`; untagged `Union[A, B, C]` for event payloads.

---

## 4 · API design

### 4.1 Resources and status codes
Plural nouns, nested only one level for ownership (`/orders/{id}/refunds`). Use 201 + body on
create, 204 on delete, 409 on a state conflict, and 422 on validation (FastAPI). Use 401 only for
"who are you?" and 403 for "you may not". Auth tests assert `== 401` strictly (CLAUDE.md §1).
Behind Cloudflare, a 502/504 body never reaches the browser, so the seed rewrites them to 503
(`seed/lib/backend/noctusai_lib/api/middleware.py:517-545`).

### 4.2 Error envelope — a declared deviation from RFC 9457
RFC 9457 (Problem Details, obsoletes 7807) defines `application/problem+json` with `type`,
`title`, `status`, `detail`, `instance`. **The house envelope is
`{"error": {"code", "message", "details?"}}`** (`exceptions.py:174-188`). Every FE consumer reads
`error.code`, so the house keeps it **on purpose**. This is a declared deviation, not ignorance.
Mapping, for any external API we publish:

| RFC 9457 | House |
|---|---|
| `type` (URI) | `error.code` (stable machine code, `UPPER_SNAKE` or pt-BR snake) |
| `title` | — (derive from `code`) |
| `status` | HTTP status (not repeated in body) |
| `detail` | `error.message` (human, pt-BR) |
| extension members | `error.details` |

Raise `AppException(code, message, status_code)`, never `HTTPException(detail=dict)`. The latter
gets stringified (`backend.md` § Error handling). A public, third-party-facing API would emit
`problem+json`; flag it to the architect first.

### 4.3 Pagination — offset vs keyset
- **Offset** (`page`, `page_size`, `total`): the house default
  (`responses.py:48-76`, `calculate_pagination` caps size at 200, `:110`). Its costs are that the
  DB still reads and discards the skipped rows, pages drift when rows are inserted, and
  `count="exact"` re-counts the filtered set on every page (87 call sites, grep 2026-11-05).
- **Keyset / seek**: `WHERE (sort_col, id) < (:last_sort, :last_id) ORDER BY sort_col DESC, id DESC
  LIMIT n`. It is constant cost per page and stable under inserts, but you cannot jump to page N.
- **Opaque cursor (Google AIP-158)**: return `next_page_token` (base64 of the keyset). Clients
  must not parse it, and the token is bound to the original filter.
- **Rule:** offset is fine for admin lists that stay small. Use keyset + opaque token for feeds,
  timelines, logs, messages, and any list that grows without bound. Internal batch reads go
  through `iter_paged_rows` (`KB § PATTERNS/backend/postgrest-row-cap.md`).

### 4.4 PATCH semantics
Partial update. Declare all fields optional and apply only the ones that were sent:
`body.model_dump(exclude_unset=True)`. That way an omitted field is untouched and an explicit
`null` clears it, which matches JSON Merge Patch (RFC 7396). Arrays are replaced wholesale. Never
`exclude_none=True` on PATCH, because it makes "clear this field" impossible.

### 4.5 Idempotency
- **Safe retries need a key.** The IETF `Idempotency-Key` header draft (-08) defines it. A missing
  key on an endpoint that requires one is 400. Reusing a key with a different payload (a
  different *fingerprint*) is 422. A key whose first request is still in flight is 409.
- **Stripe's semantics** are the reference implementation. Store the first response (status +
  body) under the key and replay it on retries. Error on a parameter mismatch. Prune keys after
  24 h.
- **House state (verified 2026-11-05):** the FE can send the header (`seed/lib/frontend/src/api.ts:191`).
  Only commerce refunds read it (`seed/lib/backend/noctusai_lib/domain/commerce/router.py:383`),
  and it is checked inside the refund RPC (`money_sql.py:144,213-214`). Inbound events have
  durable primitives (`EventInbox`, `message_store` UNIQUE). Products also carry ad-hoc keys
  (adconnect `financial_service.py:357`, community `ingest_service.py:153`, p-studio
  `financeiro_service.py:153`, agents `stores/transcripts.py:16`, social-wiring
  `automation_executor.py:21`). **There is no generic request-level primitive.** The design is
  worked example B.

### 4.6 Versioning and deprecation
Our FE and BE ship together (one container per product), so URL versioning is unnecessary for
first-party routes. For anything consumed outside the product (webhooks we emit, public
APIs, the MCP surface): use additive changes only, never repurpose a field, and mark removals with
`Deprecation` + `Sunset` (RFC 8594) headers plus a dated removal. A breaking change gets a new path
(`/v2/…`) running alongside the old one for one release.

### 4.7 OWASP API Security Top 10 (2023) — quick map (security owns depth)

| Risk | House control |
|---|---|
| API1 BOLA | every query scoped by the trusted `org_id` from `make_get_current_user_org`; never `user_metadata` (`no-metadata-authz.md`) |
| API2 Broken authentication | seed auth deps, token cache ≤30 s (`request-path-latency.md` § Token cache contract) |
| API3 Broken object property level authz | `StrictHttpModel` inbound; explicit response models outbound |
| API4 Unrestricted resource consumption | 1 MB default body cap + per-route overrides (`upload-route-body-override-derivation.md`); row cap + pagination; slowapi inbound limits |
| API5 Broken function level authz | `org_admin_dep` / `platform_admin_dep` route deps (`commerce/router.py:379,396`); license gate by construction (`tenancy-license-gate.md`) |
| API7 SSRF | outbound URLs from config, never from request bodies |
| API8 Security misconfiguration | `security_headers.py`; no public buckets (`database-rls.md` § Storage buckets) |
| API10 Unsafe consumption of APIs | webhook signature verify-before-side-effect (`KB § PATTERNS/security/webhook-signatures.md`) |

**Checklist (§ 4).** [ ] status codes per 4.1 · [ ] errors via `AppException` · [ ] growing list ⇒
keyset · [ ] PATCH uses `exclude_unset` · [ ] non-idempotent POST that a client may retry ⇒
idempotency key · [ ] the OWASP row for this endpoint is satisfied.

---

## 5 · Data & Postgres (summary — depth in `KB § PATTERNS/backend/postgres-craft.md`)

1. **Model invariants in the schema.** Use a tenant key, FKs with `ON DELETE`, `CHECK`, partial
   UNIQUE, `timestamptz`, and integer cents or `numeric` for money.
2. **Index for named queries.** Use equality columns first, then the range or sort column. Index
   every RLS policy column. A new query on a growing table ships with its
   `EXPLAIN (ANALYZE, BUFFERS)`.
3. **RLS performance.** Use `(SELECT auth.uid())`, filter explicitly as well, and add
   `TO authenticated`. Service-role paths must carry their own org filter.
4. **Locks.** Know which DDL takes ACCESS EXCLUSIVE. Use `SET lock_timeout` on every migration
   that alters an existing table.
5. **Transactions.** Read Committed is the default, so check-then-act is a race. One PostgREST
   call is one transaction, which means an invariant that spans rows or tables needs one RPC.
6. **Zero-downtime migrations.** The N-1 image must run on schema N because `deploy_image`
   auto-rolls back. Use expand → migrate → contract, `NOT VALID` → `VALIDATE`,
   `CONCURRENTLY` (blocked today by the runner's implicit transaction,
   `migrate_product.py:1542-1544`), and batched backfills.

---

## 6 · Reliability

### 6.1 Timeout budgets
Every outbound call has an explicit timeout. **httpx's implicit default is 5 s of network
inactivity, split into connect / read / write / pool**. That is a default, not a budget. Size the
timeout from the caller's budget: request p95 budgets are 150/300/500 ms
(`deploy/fleet/latency-budgets.json`, `request-path-latency.md` § Budget + gate). So a
synchronous provider call inside a request must either fit inside that budget or move to a job.
A budget is **total**: 15 s × 3 retries is a 45 s+ request. House state: direct calls set a
per-request timeout (e.g. `integrations/email/digest.py:252-260` `timeout=15`,
`integrations/llm/credit_probe.py:174-177`), but several build a fresh `httpx.AsyncClient()` per
call (`digest.py:252`, `credit_probe.py:176`, `transcription/local_whisper_http.py:62`), paying a
TLS handshake each time. Prefer a shared client. The sync Supabase path already shares one
transport (`seed/lib/backend/noctusai_lib/integrations/http_pool.py:1-35,153`).

### 6.2 Retries — exactly one layer, with jitter
Retry only **retryable** failures: timeouts, connection resets, 429, 502/503/504. Do not retry
4xx validation or auth errors. Do not retry a non-idempotent call whose outcome is unknown unless
it carries an idempotency key. The toolkit's Management-API executor does exactly this with
`retry_ambiguous=False` (`mcp/noctusai/tools/noctus/dev/migrate_product.py:603-609`). Use
**full jitter** (`sleep = uniform(0, min(cap, base·2^n))`) and honour `Retry-After`. **Retry in one
layer only**: retries at the SDK, the adapter and the job multiply (3×3×3 = 27 attempts).
- **Two house implementations, and they differ:** `integrations/rate_limit.py:398-404` uses full
  jitter and honours `Retry-After` (`:375,442`). `domain/jobs/retry_policy.py:39-67` is
  deterministic exponential with **no jitter**, so jobs that fail together retry together. This is
  a seed fix candidate (the `next_retry_at` purity contract can take a seeded RNG or a jitter
  fraction). Until it lands, do not stack a `retry_with_backoff` *inside* a job handler that the
  `Worker` also retries. Pick one layer and say which in the handler docstring.

### 6.3 Circuit breaker
A breaker stops calling a provider that is failing and returns a fast fallback. It moves
closed → open → half-open, and probes before it closes again (Fowler, "CircuitBreaker"). The house
has no breaker. The shared rate limiter paces calls but does not stop them. Add one only when a
provider outage measurably degrades unrelated requests (a thread pool or loop saturated by
timeouts). Before you hand-roll one, surface it as a seed primitive candidate.

### 6.4 Transactional outbox — the jobs organ
Problem: "write row, then call provider" loses the call on crash, and "call, then write" duplicates
it on retry. The outbox fixes this. Write the business row and the *intent* (a job row) in the same
transaction, and let a worker deliver it at-least-once (microservices.io, "Transactional outbox").
House: the jobs organ is the outbox-and-worker.
- `enqueue(..., dedupe_key=…)` — a UNIQUE `dedupe_key` makes re-enqueue idempotent
  (`domain/jobs/migrations/jobs.sql.template:19,49,59-60`; `repo.py:165-182`).
- `claim_next_job` does `FOR UPDATE SKIP LOCKED` in an RPC (`jobs.sql.template:81-111`).
- Lease + heartbeat: half-lease by default (`domain/jobs/worker.py:87-114`), `LeaseLostError` on takeover.
- Outcomes: `DeadLetterError` → dead letter, `RescheduleLater` → back to pending, any other
  exception → retry per policy (`worker.py:232-260`). Dead letters can be listed and requeued (`repo.py:183-195`).
- **Same-transaction caveat:** a PostgREST insert of the business row followed by a separate
  `enqueue` call is two transactions. For a true outbox, insert both inside one RPC, or make the
  job idempotent and the business write re-derivable.
- Open gap: the LLM usage ledger is not yet durable (`NOC-REMEDIATE[ai-usage-durable-outbox]`,
  `KB § PATTERNS/backend/llm-usage.md:66`).
- The jobs organ has no dedicated owned KB doc. Today its depth lives in this section and the
  module docstrings. A `jobs-organ.md` is a Wave-2 candidate.

### 6.5 Idempotent consumers
Every provider redelivers: WAHA within milliseconds, Stripe and Asaas hours later, Meta on any non-2xx.
The consumer's dedupe must be **durable** and must **release on failure**, otherwise the
provider's retry is treated as a duplicate and the event is lost. House layers:
- `WebhookDedup` SETNX pre-filter, 1 h TTL, for the millisecond double-delivery
  (`integrations/whatsapp/dedup.py:1-36`).
- `EventInbox.claim(gateway, event_id)` / `.release(...)`, which is durable because the PK
  `(gateway, event_id)` survives a restart (`domain/payments/event_inbox.py:28-51`,
  `event_inbox_sql.py:33`, factory `make_event_inbox` `:152`).
- `message_store` UNIQUE(`provider_message_id`) → `DuplicateMessage` (`domain/chatbot/message_store.py:1-12`).
Use them. A new inbound integration claims on the provider's event id **before** side effects and
releases on the failure path.

### 6.6 Sagas and compensation
When a business operation spans systems that cannot share a transaction (GoTrue admin API +
Postgres, Stripe + Postgres), it becomes a **saga**: a sequence of local transactions, each with
a **named compensating action**, coordinated by an orchestrator (our handler) or by events
(microservices.io, "Saga"). Rules: order steps so the hardest-to-undo comes last. Each
compensation is idempotent and only undoes what *this* call created. Log a failed compensation at
ERROR with what a human must clean up. The reference implementation is team accept (worked
example C). Commerce compensates its ledger rows the same way
(`domain/commerce/profile.py:8,186`; `fiscal.py:178,202`).

### 6.7 Graceful shutdown
On SIGTERM uvicorn stops accepting, drains in-flight requests and runs lifespan shutdown. The seed
runs `lifespan_shutdown` and logs (rather than raises) a failure (`app.py:495-510`). Workers take a
`stop_event` and exit between jobs (`worker.py:163-195`). A `BaseException` mid-job (cancel or
interrupt) marks the job failed so it is retried, not lost (`worker.py:242-244`). Rule: long work
lives in jobs (lease-protected), never in a request or a `BackgroundTasks` callback that a deploy
kills.

**Checklist (§ 6).** [ ] explicit timeout sized to a budget · [ ] one retry layer, jitter, only
retryable errors · [ ] must-happen side effect ⇒ job with `dedupe_key` · [ ] inbound event ⇒
claim before side effects, release on failure · [ ] cross-system write ⇒ named compensations ·
[ ] nothing long-running outside a lease.

---

## 7 · Observability

- **Structured logs + correlation id.** `CorrelationIdMiddleware` reads or creates
  `X-Correlation-ID` and echoes it (`api/middleware.py:94-134`). The request logger stamps it on
  every line (`:166-229`). Propagate it on outbound calls to our own services. Levels, `except`
  logging and the `# silent-ok` ban: `KB § PATTERNS/backend/logging.md`,
  `KB § PATTERNS/backend/logging-at-except.md`.
- **RED per route** (Rate, Errors, Duration — Tom Wilkie). The house emits one
  `req_timing method= route= status= dur_ms=` line per request with the route **template**
  (no ids or PII) and `Server-Timing: app;dur=…` (`request_timing.py:7,150,187`). `latency_report`
  computes p50/p95/count per route after every deploy. Rate and errors come from the same line
  (count, `status>=500`). There is no metrics backend yet. That is shared with devops, and backend
  owns the in-process emission contract.
- **OpenTelemetry, when adopted.** Server span name `{METHOD} {http.route}` (never the raw path),
  attributes `http.request.method`, `http.route`, `http.response.status_code`, `url.path`
  (scrubbed). Span status is Error only for 5xx on server spans; 4xx is the client's fault. The
  current log line already follows these names closely, so a future OTel exporter maps 1:1.
- **Server-Timing** leaks infrastructure detail to the browser. Send coarse metrics only (`app`,
  optionally `db`). Never send provider names or query text.
- **Never log (LGPD).** Secrets, tokens, passwords, JWTs (use `mask_secret`). Personal data as it
  appears in bodies: CPF/CNPJ, names, addresses, clinical text (Art. 11) (`logging.md:105-110`).
  Sentry events are scrubbed by key (`api/sentry_scrub.py:24-79`). Log the *fact* and the ids,
  never the diff.

**Checklist.** [ ] errors logged once, at the boundary, with correlation id · [ ] no PII or secrets
in messages or exception strings · [ ] new route visible in `latency_report` after deploy.

---

## 8 · Testing craft

- **Shape for this house: a trophy, not a pyramid.** The pyramid (Vocke/Fowler) says write many
  fast unit tests and push tests down. The trophy (Dodds) adds a static layer and weights
  integration highest. Our bugs live at **seams** (PostgREST, schema, auth deps, providers):
  postgrest-row-cap, B7 fixture-vs-real, invitation's 200-with-no-writes. So weight
  **contract/integration tests at seams** over unit tests on glue
  (`KB § PATTERNS/backend/boundary-contract-tests.md` § 2 seven named boundaries). Keep pure unit
  tests for primitives and domain math.
- **Fake vs mock vs real.**

| Double | Use when | House |
|---|---|---|
| Fake (working in-memory impl) | an IO adapter in service tests | every seed IO module ships one (`seed-fake-real-adapter.md`) |
| Mock (`MockSupabaseClient`) | asserting PostgREST call shape and writes | `seed/lib/backend/noctusai_lib/testing/mocks.py:1934`; enforces the 1 000-row cap; read `inserted_payloads` (`di-test-seam.md`) |
| `patch.object` | **external** services only | never our own modules (CLAUDE.md §1) |
| Real Postgres, in-process | migrations, SQL, RPC bodies | PGlite replay, twice (`migration-chain-replay.md`; `mcp/noctusai/tools/noctus/dev/migration_replay.py:1-9`) |
| Real Supabase | RLS policies, grants, RPC + auth together | `testing/realdb.py` — opt-in `NOCTUS_REALDB_TESTS=1` and **refuses the prod ref** (`realdb.py:24-35,75`); target a disposable branch |
| Container Postgres | an RPC/RLS suite that must run in CI without Supabase | testcontainers-python. Not adopted; propose before adding |

- **Assert the writes**, not just the status code (`KB § PATTERNS/backend/invitation-acceptance.md`
  § Why unit tests did not catch the empty implementation).
- **Property-based tests** (Hypothesis) for normalizers and parsers: `normalize_phone`, money
  rounding, data-in-the-wrong-field relocation, CPF/CNPJ. State the property, not examples:
  `normalize(normalize(x)) == normalize(x)`, `to_cents(cents_to_decimal(c)) == c`, "never
  overwrites a filled field". Not yet a dependency. Adding it is a requirements change, so do it in
  a dedicated slice.
- **Auth tests** use strict `== 401` (CLAUDE.md §1; `KB § PATTERNS/compliance/auth-boundary-false-green.md`).
- **Fixtures mirror the real schema** (B7). If the mock is more permissive than the backend, the
  test is lying (`postgrest-row-cap.md` § The root enabler).

---

## 9 · LLM-integration craft (pointers — depth in the owned LLM docs)

Call LLMs only through the seed seam (`noctusai_lib.llm` / `integrations.llm`); never import a
vendor SDK in a product (`KB § backend/05-AI-FEATURES.md`). Provider choice is one map plus a manual
switch (`KB § PATTERNS/backend/llm-provider-selection.md`). Every call is metered
(`KB § PATTERNS/backend/llm-usage.md`) and every tool call audited
(`KB § PATTERNS/backend/llm-tool-audit.md`). Craft rules that apply on top:
- Treat the LLM as an unreliable remote dependency (§ 6). Give it a timeout, one retry layer, and
  a fallback model or a graceful refusal.
- Structured output is validated by a Pydantic model (§ 3). Invalid output is a handled outcome,
  not an exception that 500s the request.
- Prompts live in the DB for agents (`backend.md` § Agent prompt text lives in the DB).
- Model outputs and user text are untrusted input to every tool (`KB § PATTERNS/security/ai-agent-threat-model.md`).
- Long or batch LLM work runs as a job (§ 6.4), never inline in a request.

---

## 10 · Python quality

- **Typing.** Use `from __future__ import annotations`, `Protocol` for seams (PEP 544), and
  `TypedDict` for PostgREST row dicts that cross a function boundary. Return types on every public
  function.
- **Static gates — recommendation, CI owner decides.** There is no mypy, pyright or ruff job in
  `.github/workflows/` (2026-11-05; TS has `seed-typecheck.yml`). The recommended path is mypy's
  documented incremental adoption: start with `noctusai_lib/primitives` and `domain/jobs`, use
  per-module config, never a global `ignore_missing_imports`, and tighten toward `--strict`. Ruff
  is the linter and formatter. This is a CI-workflow change, so it belongs to the CI owner (audit §8).
- **Bandit standards** are already enforced. Non-security hashes use `usedforsecurity=False`
  (B324) and deps pin to the fleet version (`backend.md` § Recurring CI-hygiene standards).
- **AST-first** for any code change that a parser can read (`KB § PATTERNS/common/ast.md`).

---

## 11 · Toolkit specifics (`mcp/noctusai/`)

- **Path constants are framework-level.** In MCP tool modules, `from settings import REPO_ROOT,
  PRODUCTS_DIR`. Never compute them with `Path(__file__).parents[N]`. A file move once forced every
  `parents[3]` to become `parents[5]` (`KB § PATTERNS/architect/mcp-tool-conventions.md:211-222`;
  keeper `check_mcp_path_via_settings`). *(Moved here from the backend-engineer L1 file on
  2026-11-05.)*
- **Write tools resolve the caller's root** via `workspace.resolve_caller_root(worktree_path)`
  (`mcp-tool-conventions.md:224-232`).
- New automation is a `noctus.dev.*` tool (`noctus.dev.scaffold_mcp_tool`), never a bare script
  (`KB § PATTERNS/architect/mcp-first-scripts.md`).

---

## 12 · One-page decision checklists

**New endpoint.**
1. Seed router or organ already ships it? (`noc-verify-seed`) → consume.
2. Contract first if the FE consumes it (`noc-contract-first`).
3. Auth dep from the factory and org-scoped query (OWASP API1). Admin/platform dep if privileged.
4. `StrictHttpModel` body. PATCH ⇒ `exclude_unset`. Errors via `AppException`.
5. `def`/`async def` per § 2.2. Count round trips against the budget (`noc-fast-responses`).
6. List ⇒ pagination choice (§ 4.3). A retryable POST ⇒ idempotency (§ 4.5).
7. `UploadFile` ⇒ `max_body_path_overrides` entry.
8. Tests: strict `== 401`, assert writes, contract test at the seam.

**New table.** `postgres-craft.md` § 1 checklist plus RLS, policies and indexes on policy
columns, all in the same file.

**New migration.** `postgres-craft.md` § 6.4. N-1 compatible, `lock_timeout`, `NOT VALID`→`VALIDATE`,
idempotent, runs twice on PGlite.

**New integration (outbound provider).**
1. Seed adapter exists? Else Protocol + Fake + Real + factory (`seed-fake-real-adapter.md`).
2. Credentials via the resolver. Redis via the seam (`redis-auth-seam.md`).
3. Pace with `rate_limit.acquire*`. One retry layer with jitter and `Retry-After`. Explicit timeout.
4. Inbound webhooks: verify the signature first (`webhook-signatures.md`), then `EventInbox.claim`,
   then the side effect, then release on failure.
5. A KB `INTEGRATIONS/<vendor>.md` page (owned by backend-engineer today).

**New background job.**
1. Enqueue via `make_job_repository(...)` with a `dedupe_key` derived from the business identity.
2. The handler is idempotent (it may run twice). It raises `DeadLetterError` for permanent failures
   and `RescheduleLater` for "not yet".
3. One retry layer (§ 6.2). Lease long enough, and rely on the heartbeat.
4. Observable: log `job_id` + correlation, dead letters visible via `list_dead_letters`.

---

## 13 · Worked examples (grounded in this codebase)

### A — agents/035: the index swap, done zero-downtime
**Today.** `products/agents/backend/migrations/035_julia_v2_threads_constraints.sql` swaps the
thread identity index from `(org, agent, channel, channel_ref)` to a partial UNIQUE
`(org_id, channel, channel_ref) WHERE tipo = 'thread_lead'` (:53-57). It replaces a `CHECK` (:59-64).
It refuses to run on dirty data via a `DO` block that `RAISE`s (:33-51). The file's own note
explains why it does not use `CONCURRENTLY` (:23-26): the runner sends the file as one implicit
transaction. The plain build takes a SHARE lock and blocks writes for its duration.
**Canon version.**
```sql
SET lock_timeout = '3s';                      -- fail fast, never queue ahead of traffic
-- (precondition DO-block unchanged)
-- with a runner no-transaction directive:
CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS uq_agents_threads_channel
    ON agents.conversations (org_id, channel, channel_ref) WHERE tipo = 'thread_lead';
DROP INDEX CONCURRENTLY IF EXISTS agents.uq_agents_conversations_channel_ref;
ALTER TABLE agents.conversations
    ADD CONSTRAINT conversations_thread_lead_check
    CHECK (tipo <> 'thread_lead' OR (channel IS NOT NULL AND lead_ref_id IS NOT NULL)) NOT VALID;
ALTER TABLE agents.conversations VALIDATE CONSTRAINT conversations_thread_lead_check;
```
**N-1 check.** Before applying, grep the previous image's code for `on_conflict=` on
`conversations`. An upsert whose conflict target names `(org_id, agent_…, channel, channel_ref)`
fails once the old index is dropped ("no unique constraint matching ON CONFLICT"), so a rollback
to N-1 would break inbound threads. Expand first: keep the old index for one release, then drop
it in a later migration.
**Why the partial index cannot become a constraint:** `ADD CONSTRAINT … USING INDEX` rejects
partial indexes (ALTER TABLE docs), so the partial UNIQUE index *is* the invariant.
**Gap.** The `-- noc:no-transaction` directive is a `migrate_product` change in the git/merge
redesign zone (`migrate-product-mcp-tool.md:421`). Surface it. Do not hand-apply.

### B — the seed request-idempotency primitive (generalize what exists)
**Evidence.** The durable *inbound* half exists (`EventInbox`, `message_store`). The *request*
half exists only for commerce refunds (§ 4.5). Ad-hoc keys sit in five products, which hits the
N≥3 must-formalize rule. **Do not build a second inbox.** Generalize `EventInbox` out of
`domain/payments` into a provider-neutral module. Its `(gateway, event_id)` PK is already neutral.
Add the missing request-level piece:
- Table `public.idempotency_keys(org_id, key, method, path, request_sha256, status
  text CHECK (status IN ('in_flight','done')), response_status int, response jsonb,
  locked_until timestamptz, created_at timestamptz DEFAULT now(), PRIMARY KEY (org_id, key))`,
  RLS on and service-role only. Purge rows older than 24 h (Stripe's window) with a jobs-organ cron.
- Dependency `require_idempotency(scope=…)`:
  1. No key: 400 when required, else pass through.
  2. `INSERT … ON CONFLICT DO NOTHING` as `in_flight`. If inserted, run the handler, store the
     status and body, then mark `done`.
  3. On conflict with the same hash and `done`, replay the stored response.
  4. Same hash and `in_flight` with `locked_until > now()`: 409.
  5. Different hash: 422 (IETF draft § 2.7).
  6. Handler raised: delete the row (release), which mirrors `EventInbox.release`.
- Ship Protocol + Fake + Real + factory. Pilot on 3 products (p-studio boleto, social-wiring
  automation step, community ingest) per the pilot-first rule, then fan out. The FE already sends
  the header (`api.ts:191`).
**Owner.** This is a seed change. Surface it to the architect with this design. Do not land it
inside a product slice.

### C — invitation acceptance as a named saga + RPC
**Today.** `POST /api/team/accept` (`seed/framework/backend/noctusai_seed/routers.py:397`) runs
three steps as separate calls:
(1) GoTrue identity create (`provision_invited_identity`, `:494-496`; `domain/org.py:186`),
(2) membership (`attach_user_to_org`, `:499-507`; `domain/org.py:243`),
(3) invitation flip (`accept_invitation`, `:566-568`; `domain/invitations.py:202-230`).
Step 1 has a correct compensation: delete the identity only if this call created it (`:509-540`).
Steps 2 and 3 are two PostgREST transactions on two clients (`core` and `admin`). A crash between
them leaves a member whose invitation is still `pending`, which is replayable.
**Canon decision.** Step 1 cannot share a Postgres transaction (GoTrue admin API), so it is a saga
step with its named compensation, and it stays as is. Steps 2 and 3 become **one `SECURITY
DEFINER` RPC**, `accept_invitation_membership(p_invitation_id, p_user_id, …)`. In one transaction
it locks the invitation row (`FOR UPDATE`), checks that it is `pending`, upserts the membership,
and flips the status. The RPC uses `SET search_path`, `REVOKE EXECUTE … FROM PUBLIC, anon,
authenticated`, and `RAISE` on a conflicting role (today's 409, `:548-557` — the `status_code=409` raise at `:550-551`). "Member exists ↔
invitation accepted" becomes atomic, and a concurrent double-accept serializes on the row lock.
**Caveat to verify first.** Memberships live in core's `public` schema and invitations in each
product's schema, so the function must be able to reach both schemas in the same Supabase
database. Confirm that before designing (`KB § PATTERNS/backend/database-rls.md` § Cross-schema
reach). **Test.** Assert the writes. Force a failure between steps and assert no orphan identity,
the invitation still `pending`, and no membership.

---

## Sources

- The Twelve-Factor App — https://12factor.net/ — III Config, IX Disposability (§ 1). Accessed 2026-11-05 (audit-verified).
- FastAPI — Bigger Applications — https://fastapi.tiangolo.com/tutorial/bigger-applications/ — `APIRouter` per module, `include_router` (§ 1). Accessed 2026-11-05.
- FastAPI — Sub-dependencies — https://fastapi.tiangolo.com/tutorial/dependencies/sub-dependencies/ — per-request dependency cache, `use_cache=False` (§ 2.1). Accessed 2026-11-05.
- FastAPI — Dependencies with yield — https://fastapi.tiangolo.com/tutorial/dependencies/dependencies-with-yield/ — setup/teardown, re-raise rule (§ 2.1). Accessed 2026-11-05.
- FastAPI — Concurrency and async/await — https://fastapi.tiangolo.com/async/ — `def` runs in the threadpool (§ 2.2). Accessed 2026-11-05 (audit-verified).
- FastAPI — Lifespan Events — https://fastapi.tiangolo.com/advanced/events/ — `on_event` deprecated (§ 2.3). Accessed 2026-11-05 (audit-verified).
- FastAPI — Testing Dependencies with Overrides — https://fastapi.tiangolo.com/advanced/testing-dependencies/ (§ 2.4). Accessed 2026-11-05 (audit-verified).
- FastAPI — Background Tasks — https://fastapi.tiangolo.com/tutorial/background-tasks/ — runs after the response; use a real queue for heavy work (§ 2.5). Accessed 2026-11-05.
- Pydantic — Models, extra data — https://pydantic.dev/docs/validation/latest/concepts/models/ — extra ignored by default; `forbid` (§ 3). Accessed 2026-11-05 (audit-verified).
- Pydantic — Unions — https://pydantic.dev/docs/validation/latest/concepts/unions/ — discriminated unions (§ 3). Accessed 2026-11-05.
- RFC 9457 — Problem Details for HTTP APIs — https://www.rfc-editor.org/rfc/rfc9457.html (§ 4.2). Accessed 2026-11-05 (audit-verified).
- Google AIP-158 — Pagination — https://google.aip.dev/158 — opaque page tokens (§ 4.3). Accessed 2026-11-05 (audit-verified).
- Markus Winand — We need tool support for keyset pagination (No Offset) — https://use-the-index-luke.com/no-offset — offset cost, keyset/seek method (§ 4.3). Accessed 2026-11-05.
- RFC 7396 — JSON Merge Patch — https://www.rfc-editor.org/rfc/rfc7396.html — null removes, arrays replaced (§ 4.4). Accessed 2026-11-05.
- IETF draft — The Idempotency-Key HTTP Header Field (-08) — https://datatracker.ietf.org/doc/draft-ietf-httpapi-idempotency-key-header/ — 400/422/409, fingerprint (§ 4.5, ex. B). Accessed 2026-11-05.
- Stripe — Idempotent requests — https://docs.stripe.com/api/idempotent_requests — stored response, 24 h pruning, parameter mismatch (§ 4.5, ex. B). Accessed 2026-11-05 (audit-verified).
- RFC 8594 — The Sunset HTTP Header Field — https://www.rfc-editor.org/rfc/rfc8594.html (§ 4.6). Accessed 2026-11-05.
- OWASP API Security Top 10 2023 — https://api-security.owasp.org/editions/2023/en/0x11-t10 (§ 4.7). Accessed 2026-11-05 (audit-verified).
- HTTPX — Timeouts — https://www.python-httpx.org/advanced/timeouts/ — 5 s default; connect/read/write/pool (§ 6.1). Accessed 2026-11-05.
- AWS Builders' Library — Timeouts, retries and backoff with jitter — https://builder.aws.com/content/3EumjoZascWd1oZiEgL8ORlv3qE/timeouts-retries-and-backoff-with-jitter — single-layer retries, jitter (§ 6.2). Accessed 2026-11-05 (audit-verified).
- Martin Fowler — CircuitBreaker — https://martinfowler.com/bliki/CircuitBreaker.html (§ 6.3). Accessed 2026-11-05 (audit-verified).
- Chris Richardson — Transactional outbox — https://microservices.io/patterns/data/transactional-outbox.html (§ 6.4). Accessed 2026-11-05 (audit-verified).
- Chris Richardson — Saga — https://microservices.io/patterns/data/saga.html — local transactions + compensations; orchestration vs choreography (§ 6.6, ex. C). Accessed 2026-11-05.
- Tom Wilkie (Grafana Labs) — The RED Method — https://grafana.com/blog/2018/08/02/the-red-method-how-to-instrument-your-services/ (§ 7). Accessed 2026-11-05.
- OpenTelemetry — Python — https://opentelemetry.io/docs/languages/python/ (§ 7). Accessed 2026-11-05 (audit-verified).
- OpenTelemetry — Semantic conventions for HTTP spans — https://opentelemetry.io/docs/specs/semconv/http/http-spans/ — span name, attributes, 5xx-only server error status (§ 7). Accessed 2026-11-05.
- W3C — Server Timing — https://www.w3.org/TR/server-timing/ — header syntax; privacy considerations (§ 7). Accessed 2026-11-05.
- Ham Vocke (martinfowler.com) — The Practical Test Pyramid — https://martinfowler.com/articles/practical-test-pyramid.html — pyramid, contract tests (§ 8). Accessed 2026-11-05.
- Kent C. Dodds — The Testing Trophy and Testing Classifications — https://kentcdodds.com/blog/the-testing-trophy-and-testing-classifications (§ 8). Accessed 2026-11-05.
- Hypothesis — https://hypothesis.readthedocs.io/en/latest/ — property-based testing (§ 8). Accessed 2026-11-05 (audit-verified).
- testcontainers-python — https://testcontainers-python.readthedocs.io/en/latest/ (§ 8). Accessed 2026-11-05 (audit-verified).
- mypy — Using mypy with an existing codebase — https://mypy.readthedocs.io/en/stable/existing_code.html — incremental adoption (§ 10). Accessed 2026-11-05.
- Ruff — https://docs.astral.sh/ruff/ — linter + formatter (§ 10). Accessed 2026-11-05.
- Postgres sources (locking, ALTER TABLE, CREATE INDEX, protocol, isolation, SKIP LOCKED, EXPLAIN, partial indexes, pg_stat_statements, Supabase RLS, PostgREST transactions, Parallel Change): see `KB § PATTERNS/backend/postgres-craft.md` § Sources.
