# Audit — `.claude/agents/backend-engineer.md` → master-level specialist

Read-only audit, 2026-11-05. Repo: `/Users/rapha/Documents/repository/NoctusAI/noctusai`.
Read: the agent file (138 lines), `KB § PATTERNS/common/agent-context-architecture.md`, all 35 owned
`PATTERNS/backend/*.md` (full or structural skim; ~7.9k lines), `backend/01..08`, and the seed code they
describe (`seed/lib/backend/noctusai_lib/**`, `seed/framework/backend/noctusai_seed/app.py`).

## 1 · Verdict

**Strong on house-specific traps, thin on general craft, and bloated in L1.** It is the best-evidenced
specialist in the repo: almost every rule is backed by an incident, a keeper and a seed fix. But:

- **Leanness (fails the house shape).** Body = 59 lines but **1,752 words** (frontend-engineer is ~1,100).
  The problem is word count, not line count: 13 rules are 50–100 words each — rules at lines 98, 102–109
  are paragraphs with incident narrative that belongs in the KB doc they already point to.
  Frontmatter carries 73 `owns_kb` lines; that's allowed, but L1 also re-lists all of them in a 135-char-
  wide prose block (line 135 is ~25 pointers on one line).
- **L0/engineer-seed duplication** (an anti-pattern named in agent-context-architecture.md §Anti-patterns):
  line 89 cache-first (CLAUDE.md §1 + engineer-seed.md:36), line 113 no-monkeypatch (§1), line 116
  AST-first (§1 + engineer-seed.md:38), line 118 heavy-run gate (engineer-seed.md:41, frontend-engineer.md:57).
- **Rule hidden in a pointer section:** line 125 (lifespan startup hook must not be fatal) and line 128
  (`request: Request = None`) are rules sitting in "Owned KB depth".
- **Craft gap:** the doc set teaches the *house* well and the *discipline* barely. Nothing on
  zero-downtime migrations, lock/statement timeouts, indexing/EXPLAIN, transaction boundaries over
  PostgREST, inbound idempotency, outbox, pagination design, error-format standards, OTel/RED metrics,
  property-based or real-DB testing, Python typing gates.
- **Domain docs are stale and point at sleeping products.** `backend/01..04,06,08` were last touched
  2026-04/05; `04-DATABASE.md` lists the 2026-04 7-schema world. The active scope
  (`deploy/fleet/active-scope.txt`) is `agents, core, monica, seed, social-wiring` — there is no
  backend domain doc for agents / social-wiring / monica.

## 2 · Strengths to keep (do not lose these in the trim)

- Seed-first composition (`create_product_app`, dep factories, late binding) — backend.md:350-420.
- Auth/tenancy by construction: `make_get_current_user_org`, no `user_metadata` authz, license gate
  with no admin bypass (tenancy-license-gate.md, no-metadata-authz.md). Maps to OWASP API1 (BOLA).
- PostgREST hazards nobody else writes down: bare table names, `client.schema()` mutating a shared
  client, the 1,000-row silent cap + `.in_()` URL length, `mode="json"` dumps.
- Event-loop discipline + shared pool + token cache (request-path-latency.md) — matches FastAPI's own
  async/def guidance.
- `StrictHttpModel extra="forbid"` (Pydantic's default is ignore, per the docs).
- Migration replay on PGlite twice, SECURITY DEFINER revoke, schema-drift + exposure in predeploy.
- Fake+Real+factory adapters, DI test seam, boundary-contract tests (B1–B7), "assert the writes".
- Outbound rate limiting with full-jitter backoff honoring `Retry-After` (rate_limit.py:399-404).
- Error envelope via `AppException` + edge-safe 502→503 rewrite (backend.md:255-320).

## 3 · Gaps, ranked (evidence)

1. **Migrations aren't checked for zero-downtime safety, though prod is first-contact and auto-rollback is the safety net.**
   `lock_timeout` / `statement_timeout` appear **0 times** in the KB and in migrations. The runner runs a
   file as one implicit transaction, so `CREATE INDEX CONCURRENTLY` is impossible. See
   `products/agents/backend/migrations/035_julia_v2_threads_constraints.sql:23-26`, which reasons it
   through by hand. No expand/contract doc exists. A further issue: `deploy_image` auto-rollback means
   the **N-1 image must run against the N schema**. So every migration has to be backward-compatible,
   and nothing says so.
2. **Inbound idempotency has no seed primitive (DRY N≥5 → must formalize).** It's ad hoc in
   adconnect `financial_service.py:357,375`, community `ingest_service.py:153` (`wa:{provider_message_id}`),
   agents `stores/transcripts.py:16`, social-wiring `automation_executor.py:21`, and p-studio
   `financeiro_service.py:153`. The FE already sends `Idempotency-Key` (`seed/lib/frontend/src/api.ts:191`),
   but no backend code reads it. The only KB mentions are passing ones (chatbot-operational-readiness.md:91,241).
3. **Transaction boundaries over PostgREST are never stated.** Each PostgREST call is its own
   transaction. Multi-row invariants need an RPC (one plpgsql transaction), and cross-system writes need a
   saga with compensation. invitation-acceptance.md:85 rediscovers the saga case without naming it, and
   `noctusai_lib/domain/invitations.py:202-230` does sequential writes.
4. **Retry/outbox/consumer reliability is fragmented.** There are two retry implementations:
   `integrations/rate_limit.py` has full jitter, `domain/jobs/retry_policy.py` has none. The
   `domain/jobs` organ (`claim_next_job`, `FOR UPDATE SKIP LOCKED`, repo.py:507) has **no owned KB
   doc**. It's mentioned only inside photo-editing / chatbot docs. The durable outbox is deferred as
   `NOC-REMEDIATE[ai-usage-durable-outbox]` (llm-usage.md:66). Circuit breakers and per-call timeout
   budgets are absent. Many `httpx.AsyncClient()` are built without an explicit timeout
   (e.g. `integrations/email/digest.py:252`, `llm/credit_probe.py:176`). The httpx 5 s default is
   implicit and not a budget.
5. **No query-performance or indexing discipline.** "Index every column a policy filters on" (Supabase RLS
   guidance) isn't a rule. EXPLAIN (ANALYZE, BUFFERS) isn't part of the workflow. The `(SELECT auth.uid())`
   rule exists (database-rls.md:17-25) but its index half is missing. `paginated_response(total, page)`
   (backend.md:248) implies offset + exact count. Keyset/opaque cursors (AIP-158) are absent.
6. **No Python static-typing or lint gate.** There's no mypy/pyright/ruff in `.github/workflows/`
   (only bandit, test.yml:1103). The TS side has `seed-typecheck.yml`. This is a CI-workflow change, so it's
   in the collision zone: recommend it, don't edit.
7. **Observability stops at logs.** Correlation id exists (`primitives/_correlation.py`) and logging.md is
   good. There's no RED metrics, tracing, or OTel. chatbot-operational-readiness.md:204-231 defers the
   metrics sink to "platform-wide". Shared with devops; backend should own the in-process instrumentation contract.
8. **Testing craft.** No property-based testing (Hypothesis) for parsers/money/phone/data-in-wrong-field
   normalizers. No real-Postgres RLS policy tests as a named practice (`testing/realdb.py` exists, but
   the KB doesn't route to it). Mock-first culture caused postgrest-row-cap.md and B7.
9. **API-design canon.** No stance on error format vs RFC 9457 (the house envelope `{"error":{code,message}}`
   is fine but should be a declared deviation). There's also no versioning/deprecation policy, and no PATCH semantics.
10. **FastAPI lifespan.** The seed takes `lifespan_startup/shutdown` callables (app.py:76-77), which is
    fine. No doc ties it to FastAPI's lifespan or forbids `@app.on_event` (deprecated). Small gap.
11. **Stale domain docs** (see §1). `01-CORE.md` "`get_current_admin` checks `noctus_users.role=='admin'`"
    should be re-verified against tenancy-license-gate's no-admin-branch rule.

**Separate DB specialist?** Not yet. DB/migration content is ~1.3k of 7.9k owned lines, and only 5
products are active. Better: a dedicated `postgres-data-craft.md` section/doc owned by backend-engineer,
plus an **Opus-escalation trigger** for any migration touching a table >~100k rows or changing a
constraint/index/column type (fits `dispatch-engineer-tuning §4·1`). Re-evaluate (roadmap trigger) if
≥2 migration-caused prod incidents land in a quarter, or DB docs exceed ~35% of owned depth.

## 4 · Proposed NEW L1 one-liners (each ≤30 words)

- **Every migration is backward-compatible with the previous image.** Auto-rollback runs N-1 against N; rename/drop/type-change = expand→migrate→contract over ≥2 deploys. → `KB § PATTERNS/backend/backend-craft-canon.md`
- **DDL sets `lock_timeout` and never rewrites a hot table in one shot.** Big-table index = no-transaction migration; validate constraints `NOT VALID`→`VALIDATE`. → `KB § PATTERNS/backend/backend-craft-canon.md`
- **One PostgREST call = one transaction.** Multi-row invariants go in an RPC; cross-system writes are a saga with named compensations. → `KB § PATTERNS/backend/backend-craft-canon.md` · `KB § PATTERNS/backend/invitation-acceptance.md`
- **Every non-idempotent POST and every inbound event dedups on a key** (seed primitive, UNIQUE(org_id,key), request-hash match). → `KB § PATTERNS/backend/backend-craft-canon.md`
- **Every outbound call has an explicit timeout, retries in exactly one layer, with jitter.** → `KB § PATTERNS/backend/backend-craft-canon.md` · `KB § PATTERNS/common/outbound-rate-limiting.md`
- **Async side effects ride the jobs organ (outbox + SKIP LOCKED), never fire-and-forget.** → `KB § PATTERNS/backend/backend-craft-canon.md`
- **A policy column is an indexed column; a new query on a growing table ships with its EXPLAIN.** → `KB § PATTERNS/backend/backend-craft-canon.md` · `KB § PATTERNS/backend/database-rls.md`
- **Lifespan hooks are side effects, never boot preconditions.** (promoted from line 125) → `KB § PATTERNS/backend/startup-hook-must-not-be-fatal.md`
- **Escalate to Opus:** migration on a large/hot table, a new invariant spanning tables, an idempotency or concurrency design. → `KB § PATTERNS/architect/dispatch-engineer-tuning.md`

## 5 · Exact L1 trim plan (lossless — every dropped sentence already lives at, or moves to, the pointer)

| Line | Action | Lands in |
|---|---|---|
| 83 | Keep the opener; add "engineer-seed covers cache-first, AST-first, heavy-run gate, worktree". | — |
| 89 cache-first | **DELETE** (dup of §1 + engineer-seed.md:36). | already in engineer-seed |
| 90–95 | Keep (already one-liners). Merge 91+92 into one "dep factories: module slots + `configure_X`, auth via `make_get_current_user_org`, no `Depends()` on `ProductDependencies.get_*`". | backend.md §Auth / §dep factories |
| 96 migrations | Collapse to "DDL applied = file committed same change; author via `scaffold_migration`; forward-safe". **Drop "numbered NNN"** (merge-flow, §8). | database-rls.md §Migrations |
| 97 | Keep. | — |
| 98 invitation | → "Side-effect endpoints are tested on their writes; mounting a standard router = a schema commitment." Move the 3-write narrative to invitation-acceptance.md (already there, lines 92-100). | invitation-acceptance.md |
| 99–101 | Trim to ≤25 words each; keeper names stay in the KB docs (no-metadata-authz.md, migration-sql-security-gates.md, migration-chain-replay.md, all of which already name them). | same |
| 102 license | → "License gate is by construction — no per-product or admin bypass; `product_slug=` only when slug≠schema." Move the core-068 detail. | tenancy-license-gate.md |
| 103+104 | Merge: "PostgREST: bare table names; never `client.schema()` on a shared client (use the pinned admin client)." | postgrest-schema-targeting.md · admin-client-schema-pinning.md |
| 105 latency | → "Never block the loop: no-await handler = `def`, else `to_thread`; reuse the pooled/cached clients." Token-cache 30 s detail moves. | request-path-latency.md (already has it) |
| 106 row cap | → "Unbounded select caps at 1,000 silently; paginate with `iter_paged_rows`, batch `.in_()` via `_batched`." Mock/keeper narrative moves. | postgrest-row-cap.md (already has it) |
| 107, 108 | One line each (~15 words). | data-in-the-wrong-field.md · document-extraction-learnings.md |
| 109 upload | → "Every `UploadFile` route needs a `max_body_path_overrides` entry (app refuses to boot otherwise)." | upload-route-body-override-derivation.md |
| 110 | Keep. | — |
| 111, 112 | Trim to "via `rate_limit` (pacing + `Retry-After` backoff)" / "via `noctusai_lib.realtime` bus (Streams, resume)". | outbound-rate-limiting.md · realtime-sse-bus.md |
| 113 monkeypatch | Collapse to "Test seams: DI · `inserted_payloads` · patch externals only" (keep the backend-specific *how*; drop the restated §1 rule). | di-test-seam.md |
| 114 | Keep. | — |
| 115 MCP paths | Move to the craft canon §Toolkit (toolkit-specific, rarely hit). | backend-craft-canon.md |
| 116 AST | **DELETE** (§1 + engineer-seed.md:38). | — |
| 118 heavy-run | **DELETE** (engineer-seed.md:41). | — |
| 120–121 commit ownership | **Replace** with "Follow the engineer-seed commit protocol" (merge-flow, §8). | engineer-seed.md |
| 125 lifespan | Promote to a rule line (§4). | — |
| 128 `request: Request = None` | Move the gotcha into audit-trail.md (verify it's there; add if not). | audit-trail.md |
| 123–135 depth | Re-flow as ~10 grouped lines of bare `KB § path` pointers (keeper needs each full path). No prose. Add the craft canon. | — |
| 137–138 | Keep, shortened. | — |

Expected result: ~50 body lines, ~900–1,000 words, plus 9 new rules at ≤30 words each.
The **same commit** must add the new doc to `owns_kb`, the body pointer, and `KB § INDEX.md` (§4 sync rule + `check_agent_kb_alignment`).

## 6 · Craft-canon doc — `KNOWLEDGE-BASE/CONTEXT/PATTERNS/backend/backend-craft-canon.md`

Outline (each section: principle → house mechanism → decision checklist → anti-patterns → sources):

0. **How to use this doc.** House-first: seed primitive > canon. Every section ends in a checklist.
1. **Service architecture.** Layers (router/service/repo/schema); DDD-tactical-lite (aggregate = consistency
   boundary = one RPC/transaction; domain services; value objects for money/phone/CPF in `primitives`);
   bigger-applications layout; 12-factor config (III) + disposability (IX) ↔ lifespan.
2. **FastAPI mastery.** Dependencies (scoping, yield-deps, caching per request), `def` vs `async def`
   decision table, lifespan (never `on_event`), `dependency_overrides` vs DI seam (when each),
   background tasks vs the jobs organ, response models + `response_model_exclude_none` traps.
3. **Pydantic v2.** Strict HTTP models, `mode="json"`, validators vs domain logic, `TypeAdapter`,
   discriminated unions for polymorphic payloads, settings models.
4. **API design.** Resource naming, status codes, error envelope (declared deviation from RFC 9457 +
   mapping table), pagination (offset vs keyset; opaque cursor per AIP-158; `count=exact` cost),
   PATCH semantics, idempotency (IETF draft + Stripe semantics), versioning/deprecation, OWASP API Top 10
   quick map (API1 BOLA ↔ org scoping; API4 resource consumption ↔ row cap/body limits; security owns depth).
5. **Data & Postgres craft** (could split to `postgres-data-craft.md` if it exceeds ~300 lines).
   Modeling (tenant key on every row, FK + `ON DELETE` policy, `CHECK` over app validation, timestamptz,
   numeric for money); indexing (policy columns, composite order, partial indexes, `pg_stat_statements`,
   EXPLAIN (ANALYZE, BUFFERS) reading guide); RLS performance; locking table (which DDL takes ACCESS
   EXCLUSIVE / SHARE); isolation levels and `SELECT … FOR UPDATE` / `SKIP LOCKED`; **zero-downtime
   migrations**: expand/contract across deploys, `lock_timeout`, `NOT VALID`→`VALIDATE`, batched
   backfills, the no-transaction migration need; transactions over PostgREST → RPC.
6. **Reliability.** Timeout budgets (connect/read/total; per provider), retry in one layer with full
   jitter, retryable-vs-not classification, circuit breaker (when the shared rate limiter isn't enough),
   transactional outbox via the jobs organ, idempotent consumers (WAHA/Meta/Stripe redelivery),
   sagas + compensations, graceful shutdown.
7. **Observability.** Structured logs + correlation id (existing), RED metrics per route, OTel HTTP span
   conventions, Server-Timing (noc-fast-responses), what never to log (LGPD).
8. **Testing craft.** Pyramid/trophy for this house (contract tests at seams > units on glue), Fake vs
   mock vs real Postgres (PGlite replay; testcontainers for RLS/RPC tests), Hypothesis for normalizers,
   assert-the-writes, strict `== 401` (CLAUDE.md §1), fixture↔real-schema (B7).
9. **LLM-integration craft.** Seam-only SDK use, budget/usage ledger, timeouts + fallbacks per
   provider, structured outputs validated by Pydantic, prompt-in-DB, tool-audit (pointers to owned docs).
10. **Python quality.** Typing (`from __future__`, Protocols, `TypedDict` for PostgREST rows), ruff/mypy
    posture (recommendation pending CI owner), bandit B324 etc. (backend.md:530).
11. **Toolkit specifics.** MCP path constants (moved from L1:115).
12. **Decision checklists** (one-page): new endpoint · new table · new migration · new integration ·
    new background job.
13. **Sources** (§9 list).

### Worked example A — the agents/035 index swap, done zero-downtime
Today (`products/agents/backend/migrations/035_julia_v2_threads_constraints.sql:15-26`) the unique index
`(org, agent, channel, channel_ref)` → `(org, channel, channel_ref)` is built non-concurrently (SHARE lock
blocks writes) because the runner wraps the file in one transaction. Canon:
`SET lock_timeout = '3s'` at the top (fail fast instead of queueing behind a long txn and blocking every
later query). For a hot table, add a runner directive (e.g. `-- noc:no-transaction`) honored by
`noctus.dev.migrate_product`, then `CREATE UNIQUE INDEX CONCURRENTLY … ; ALTER TABLE … ADD CONSTRAINT …
USING INDEX …`. Add the `CHECK` as `NOT VALID` then `VALIDATE CONSTRAINT` (SHARE UPDATE EXCLUSIVE). Verify
the N-1 image's upserts still match a unique index (auto-rollback safety). The directive itself is a
seed/toolkit change. migrate_product is backend-owned, but check its "applied record via isolated
branch" path (migrate-product-mcp-tool.md:421) with the git/merge redesign session first.

### Worked example B — the seed idempotency primitive (DRY N≥5)
Shape: `public.idempotency_keys(org_id, key, method, path, request_sha256, status, response jsonb,
locked_until, created_at)` with `UNIQUE(org_id, key)` and a TTL purge (24 h, like Stripe). Use a FastAPI dependency
`require_idempotency(scope=…)`. On first sight it inserts a row (`ON CONFLICT DO NOTHING`) and runs the handler.
On replay with the same hash, it returns the stored response. On a different hash it returns 422, and while
the first request is still in flight it returns 409, per the IETF draft. Ship it as Fake+Real+factory.
The FE `post(..., {headers: {'Idempotency-Key'}})` (`seed/lib/frontend/src/api.ts:191`) becomes the consumer.
Inbound events reuse the same table with `key = provider:event_id`, which replaces community's
`wa:{provider_message_id}`. Pilot on 3 products (p-studio Asaas boleto, social-wiring automation step,
community ingest), then fan out.

### Worked example C — invitation acceptance as a named saga + RPC
`accept_invitation` (`seed/lib/backend/noctusai_lib/domain/invitations.py:202-230`) does three writes
across GoTrue and Postgres. Canon decision: the GoTrue identity create can't share a Postgres
transaction, so it's saga step 1 with the compensation "delete the identity iff created by this call"
(invitation-acceptance.md:85). Steps 2–3 (membership insert + invitation status flip) are **one
SECURITY DEFINER RPC** (`REVOKE EXECUTE … FROM PUBLIC, anon, authenticated`, `SET search_path`). That
makes "member exists ⇔ invitation accepted" atomic. The test asserts the writes plus a forced failure
between steps (no orphan identity, invitation still `pending`).

## 7 · Frontmatter

- `model: sonnet`: keep. It's consistent with the 2026-11-04 measured A/B (commit 0a6052430,
  dispatch-engineer-tuning §4·1). Add the comment pointer that engineer-seed.md:9-14 carries, plus the
  backend escalation trigger in §4.
- `tools`: fine for an executor. Consider adding `WebFetch` so it can verify vendor API docs
  (integrations are a big share of the work), or keep source research on advisors on purpose.
- `description`: add "Postgres schema/migrations/RLS, reliability (idempotency, retries, jobs)" so routing
  catches data-layer and reliability work. Keep under ~40 words.
- `owns_kb`: add `CONTEXT/PATTERNS/backend/backend-craft-canon.md`. Consider a new owned
  `jobs-organ.md` (gap 4). Domain docs for active products (agents, social-wiring) are missing:
  `KB § PRODUCTS/social-wiring` exists but is unowned by this agent. Ask the architect for
  ownership or an `agent_owners` declaration.

## 8 · Merge-flow lines (collision zone — flag only, do not edit here)

- `.claude/agents/backend-engineer.md:120-121` "Commit ownership" (worktree off `origin/dev`, commit
  only `feat/<branch>`, tech-lead merges). Replace with a pointer to engineer-seed once the redesign settles.
- `.claude/agents/backend-engineer.md:96` "numbered `products/<p>/backend/migrations/NNN_*.sql`". In the
  new flow the number is assigned at merge, so L1 should say "author via `scaffold_migration`" and not
  promise a number.
- `database-rls.md:148` ("Next number wins…") and `:206-220` (collision safety, three-source numbering,
  `task_branch integrate` auto-renumber 2026-09-23). These need rewriting by the git/merge session.
- `migration-chain-replay.md` (pre-commit replay) and `migrate-product-mcp-tool.md:421` (applied record
  persisted through an isolated branch). Both touch branch/commit mechanics.
- Gap 6 (ruff/mypy CI job) belongs to the CI-workflow owner.

## 9 · Sources (each fetched and confirmed 2026-11-05)

- PostgreSQL — CREATE INDEX — https://www.postgresql.org/docs/current/sql-createindex.html — CONCURRENTLY can't run in a transaction block (worked example A).
- PostgreSQL — Explicit Locking — https://www.postgresql.org/docs/current/explicit-locking.html — lock modes; CREATE INDEX takes SHARE; many ALTER TABLE forms take ACCESS EXCLUSIVE.
- PostgreSQL — Client Connection Defaults — https://www.postgresql.org/docs/current/runtime-config-client.html — `lock_timeout`, `statement_timeout`.
- PostgreSQL — Using EXPLAIN — https://www.postgresql.org/docs/current/using-explain.html — EXPLAIN (ANALYZE, BUFFERS) reading.
- Supabase — Row Level Security — https://supabase.com/docs/guides/database/postgres/row-level-security — index policy columns; `(select auth.uid())`.
- Martin Fowler — Parallel Change — https://martinfowler.com/bliki/ParallelChange.html — expand/migrate/contract.
- Martin Fowler — Circuit Breaker — https://martinfowler.com/bliki/CircuitBreaker.html.
- microservices.io — Transactional outbox — https://microservices.io/patterns/data/transactional-outbox.html.
- AWS Builders' Library — Timeouts, retries and backoff with jitter — https://builder.aws.com/content/3EumjoZascWd1oZiEgL8ORlv3qE/timeouts-retries-and-backoff-with-jitter — retry at one layer; jitter (old aws.amazon.com/builders-library URL 301s here).
- RFC 9457 Problem Details for HTTP APIs — https://www.rfc-editor.org/rfc/rfc9457.html — obsoletes 7807.
- IETF draft — Idempotency-Key header (‑08) — https://datatracker.ietf.org/doc/draft-ietf-httpapi-idempotency-key-header/.
- Stripe — Idempotent requests — https://docs.stripe.com/api/idempotent_requests — stored response, 24 h pruning, param-mismatch error.
- Google AIP-158 Pagination — https://google.aip.dev/158 — opaque page tokens.
- OWASP API Security Top 10 2023 — https://api-security.owasp.org/editions/2023/en/0x11-t10 — API1 BOLA, API4 resource consumption.
- FastAPI — Lifespan events — https://fastapi.tiangolo.com/advanced/events/ — `on_event` deprecated.
- FastAPI — Concurrency and async/await — https://fastapi.tiangolo.com/async/ — `def` runs in the threadpool.
- FastAPI — Testing dependencies with overrides — https://fastapi.tiangolo.com/advanced/testing-dependencies/.
- Pydantic — Models (Extra data) — https://pydantic.dev/docs/validation/latest/concepts/models/ — extra ignored by default; `forbid` errors.
- OpenTelemetry Python — https://opentelemetry.io/docs/languages/python/ ; HTTP span semconv — https://opentelemetry.io/docs/specs/semconv/http/http-spans/.
- Hypothesis — https://hypothesis.readthedocs.io/en/latest/ — property-based testing.
- testcontainers-python — https://testcontainers-python.readthedocs.io/en/latest/.
- The Twelve-Factor App — https://12factor.net/ — III Config, IX Disposability.
