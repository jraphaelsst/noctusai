# cache-backend-portability-2026-05 — local SQLite today, swap-ready for tomorrow

> **Durable record** (per `KB § PATTERNS/common/roadmap-tracking.md`).
> Origin: 2026-05-26 architectural question — "should we containerize the cache DB and/or migrate to Supabase storage?"
> Decision: **don't migrate now; ship the abstraction layer to make migration cheap when the trigger fires.**

## Origin

The 5 keeper-mirror caches (`keeper-patterns`, `agent-context`, `auto-improvement`, `kb-embeddings`, `code-embeddings`) all live in `.claude/cache/*.sqlite` — gitignored per-user, regenerable from source. Total disk footprint: ~135MB (kb-embeddings ~49MB + code-embeddings ~86MB; the other three are <1MB combined).

The user surfaced the natural next question: should this be containerized + future-migrated to Supabase pgvector for centralized/shared cache access?

**Honest analysis** (see chat 2026-05-26 evening):

- **Today (N=1 architect, local-only)**: local SQLite is correct. Microsecond access, no auth setup, no network dependency, no cost. The 3-leg mirror contract + auto-freshness hooks already handle drift.
- **Future (N≥2 architects OR hosted-noc tier OR CI-shared embeddings)**: centralized cache pays back. The natural target is Postgres + pgvector (NOT "SQLite in a container" — that's worst-of-both-worlds; NOT "Supabase storage buckets" — wrong shape for tabular cache data).

The migration itself is bounded scope IF the abstraction layer is in place. This roadmap captures both halves: the **abstraction shipped today** (Phase 1) + the **migration plan for when the trigger fires** (Phase 2+).

## Trigger conditions (the "when")

Migration kicks off when **ANY** of the following fires:

| # | Trigger | Detection signal | Why it tips the balance |
|---|---|---|---|
| T1 | N≥2 architects working noc concurrently | observed: ≥2 dev `feat/*` branches per week across distinct authors | shared cache stops being "nice" and starts saving real $ + wall-clock |
| T2 | Hosted noc deployment (SaaS / shared instance) | strategic decision (not auto-detectable) | mandatory — remote agents can't hit a local SQLite file |
| T3 | CI runs embedding-using gates | observed: CI green/red depends on a `kb_*` / `code_*` vector call | local-per-runner cache = wasted minutes + cost on every CI run |
| T4 | Embedding corpus crosses 1M chunks | observed: code-embeddings rows >1M | sqlite-vec KNN starts struggling; pgvector with HNSW handles it |
| T5 | Multi-machine same-architect (laptop + desktop + VPS) | user-reported friction: "I keep regenerating the same 49MB on each machine" | shared cache eliminates the redundant rebuild |

**Today's status**: none of T1-T5 fired. Default remains local SQLite.

## Phase 1 — Abstraction layer (SHIPPED this roadmap)

| # | Title | Files | Status |
|---|---|---|---|
| P1.1 | `cache_backend.py` — `CacheBackend` Protocol + `SqliteCacheBackend` default + `get_backend()` factory + `cache_path()` catalog | NEW `mcp/noctusai/tools/noctus/dev/cache_backend.py` | **shipped** |
| P1.2 | Contract test suite — 18 tests locking Protocol shape + sqlite behavior + factory env-var resolution | NEW `mcp/noctusai/tests/test_cache_backend.py` | **shipped** |
| P1.3 | Roadmap (this doc) | NEW `project-history/roadmaps/cache-backend-portability-2026-05.md` | **shipped** |
| P1.4 | Back-references from `cache-auto-freshness.md` + `keeper-pattern-cache.md` | EDIT existing KB docs (deferred follow-up #4) | **shipped** |

**Behavior guarantee**: Phase 1 is **zero-cost at runtime**. The 5 existing cache modules continue using direct `sqlite3.connect()` calls — no consumer is migrated yet. The abstraction EXISTS for when needed.

**Why ship now if no consumer uses it**: option value. The hard work of the migration is the abstraction shape, NOT the swap. Building the Protocol while we have the design context is 10× cheaper than retrofitting it under pressure.

## Phase 2 — Incremental consumer migration (DEFERRED — fires per-cache as triggers warrant)

When the abstraction has real consumers, the 5 cache modules each migrate their `_connect()` to consume `get_backend().connect(<name>)`. Each module is independent — partial migration is supported.

| # | Cache | Migration shape | Effort estimate |
|---|---|---|---|
| P2.1 | `keeper-patterns` | swap `_connect()` to `get_backend().connect("keeper-patterns")` | 30min |
| P2.2 | `agent-context` | same | 30min |
| P2.3 | `auto-improvement` | same | 30min |
| P2.4 | `kb-embeddings` | same + sqlite-vec extension load needs backend-aware adapter | 1h |
| P2.5 | `code-embeddings` | same + sqlite-vec extension load needs backend-aware adapter | 1h |

**Trigger**: do P2.x when the next-write to that module is needed for something else anyway (fix-on-contact opportunity), OR when Phase 3 needs the consumer migrated.

**Why not big-bang now**: zero current benefit + 5h of churn + test surface. Lazy migration is correct.

## Phase 3 — PostgresCacheBackend (DEFERRED — fires when T1/T2/T3 trigger)

| # | Title | Files | Trigger |
|---|---|---|---|
| P3.1 | `PostgresCacheBackend` impl — psycopg2 / asyncpg wrapper conforming to the Protocol | NEW `mcp/noctusai/tools/noctus/dev/cache_backend_postgres.py` | **shipped** |
| P3.2 | Per-cache parameter-style audit — replace `?` placeholders with cursor.execute-style adaptation OR keep sqlite-style + paramstyle adapter | edits across the 5 cache modules' SQL | with P3.1 |
| P3.3 | Migration tool — `noctus.dev.cache_migrate(from='sqlite', to='postgres')` — pure dump+reload (NOT data migration; just refresh against the new backend) | NEW migration tool OR document `force=True` refresh on the new backend | with P3.1 |
| P3.4 | Per-cache backend selection env var — `NOCTUS_CACHE_BACKEND_<NAME>` for gradual rollout (e.g., vector caches go remote, methodology caches stay local) | extend `get_backend()` in `cache_backend.py` | with P3.1 |

**Why Postgres before Supabase**: Postgres is the lowest-cost real backend (self-host, or cheap managed). Supabase is the natural HOSTED variant once we want managed.

**Why NOT containerize SQLite**: SQLite is file-based. Wrapping it in a container with volume mount = same as local SQLite + container overhead. Network-serving SQLite (rqlite/dqlite) = exotic dependency; the natural network DB is Postgres.

## Phase 4 — SupabaseCacheBackend + pgvector (DEFERRED — fires when T2 triggers OR Postgres provisioning becomes a chore)

| # | Title | Files | Trigger |
|---|---|---|---|
| P4.1 | `SupabaseCacheBackend` impl — Supabase HTTP client wrapping pgvector tables | NEW `mcp/noctusai/tools/noctus/dev/cache_backend_supabase.py` | T2 |
| P4.2 | Schema-to-Supabase migration script | NEW one-shot script | with P4.1 |
| P4.3 | RLS policies for multi-architect access | Supabase config (manual via Supabase MCP) | with P4.1 |
| P4.4 | Vector ops parity — sqlite-vec KNN ↔ pgvector cosine; result-shape parity tests | extend embedding cache modules | with P4.1 |
| P4.5 | Cost tracking — extend `vector-costs.ndjson` ledger with Supabase egress + storage rows | extend `cost_evaluation.py` | with P4.1 |

**Why Supabase-specific**: noc already uses Supabase for app data. Reusing the same project = single auth surface + single billing surface + RLS pattern already in muscle memory.

**Cost shape change to plan for**:
- Today: $0.10 OpenAI embedding refresh, free SQLite storage.
- Phase 4: $0.10 OpenAI + Supabase storage ($0.021/GB-month → ~$0.003/month for 135MB) + Supabase egress ($0.09/GB → variable based on query volume). Marginal at our scale; matters if cache hits >100K/month.

## Phase 5 — Containerization (DEFERRED — likely never)

The original question included "containerize the SQLite cache." Phase 5 captures why this is generally the WRONG move:

- **Container around SQLite + volume mount** = same as local SQLite, plus container overhead. Zero benefit.
- **Container running a SQLite network server (rqlite/dqlite/litestream)** = exotic dependency, eventually-consistent semantics, ops complexity. The natural network DB is Postgres → see Phase 3/4.
- **Container around Postgres for self-hosting** = fine, but that's Phase 3, not "containerize the cache."

**Only viable Phase 5 use case**: bundle the cache files into the noc Docker image for fresh-container warmup (CI runners, dev sandbox). That's an artifact-bundle (read-only seed), NOT a stateful service. Will revisit if T3 fires + we want fast CI warmup.

## Anti-goals (explicit non-goals)

- ❌ "Migrate now because cloud is shinier." We have ZERO trigger; migrating burns weeks of attention for no benefit.
- ❌ "Containerize SQLite as a stepping stone." Stepping stone to what? Skip the bad shape; go direct to Postgres when the trigger fires.
- ❌ "Centralize all 5 caches in one shot." Vector caches benefit FIRST (largest, most expensive); methodology caches (keeper-patterns, agent-context) are tiny + per-user-fast — they may NEVER need migration.
- ❌ "Add Supabase storage buckets for cache blobs." Wrong shape — caches are tabular + indexed, not blob-shaped. pgvector tables are the fit.
- ❌ "Force-migrate via big-bang refactor." Each Phase 2 slice is per-cache, independent. Lazy + on-contact.

## Open questions (to revisit at trigger time)

- **Q1**: Does the per-cache override (`NOCTUS_CACHE_BACKEND_<NAME>`) belong in `get_backend()` or in each consumer? Defer until first remote backend ships.
- **Q2**: What's the right shape for the `vector_*` operations in `CacheBackend`? Today the Protocol is row-store-shaped; KNN is bypassed via direct sqlite-vec calls. Phase 3/4 may need a `VectorCacheBackend(CacheBackend)` extension Protocol.
- **Q3**: Backup/restore semantics — do we WANT cross-machine sync of the .sqlite files via a sync service (rclone / Syncthing) as a cheaper alternative to remote-backend migration? Defer; might be the right answer for the T5 trigger only.
- **Q4**: Per-cache TTL vs always-fresh — when caches are remote, stale reads matter more. Need to think about read-after-write consistency at Phase 3 design time.

## Decision log

- **2026-05-26**: User question + analysis → decision to **ship abstraction, defer migration**. Trigger conditions T1-T5 documented. Phase 1 shipped.
- **2026-05-26 evening**: T2 trigger fired (hosted noc deployment); `PostgresCacheBackend` implemented as Phase 3.1. psycopg2 present in venv; `pgvector` Python package missing (DRIFT — surfaced to architect). 22 new tests; existing 18 updated (1 test updated: `test_get_backend_unknown_raises_ValueError` was using `"postgres"` as its "unknown" value — now uses `"supabase"`).

## Retrospective (filled at first trigger)

*To be filled when Phase 2 or later fires. Capture:*
- *Which trigger actually fired (T1/T2/T3/T4/T5)?*
- *Was the Phase 1 abstraction sufficient, or did we discover gaps?*
- *Time-to-migration vs estimate.*
- *Lessons absorbed back to KB / MEMORY.md.*

## Composes with

- `KB § CONTEXT/PATTERNS/common/cache-auto-freshness.md` — the closed-loop propagation umbrella; will need extension for remote backends (the post-merge/post-checkout hooks need to know whether to skip when backend is remote).
- `KB § CONTEXT/PATTERNS/common/keeper-pattern-cache.md` — the 3-leg mirror contract; Phase 2 migrations preserve all 3 legs by construction.
- `KB § CONTEXT/PATTERNS/common/cache-locking-discipline.md` — WAL mode is sqlite-specific; Postgres has its own MVCC story; Supabase has its own. Phase 3 design needs an equivalent-discipline section.
- `KB § PATTERNS/common/roadmap-tracking.md` — this doc's shape contract.

## File trail

- `mcp/noctusai/tools/noctus/dev/cache_backend.py` — the abstraction (Phase 1).
- `mcp/noctusai/tests/test_cache_backend.py` — 18 contract tests.
- This doc — the migration plan.
