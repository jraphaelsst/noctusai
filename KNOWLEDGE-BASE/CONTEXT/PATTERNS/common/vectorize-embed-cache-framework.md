# Vectorize → embed → cache — the unified pipeline (META-RULE)

> **Stage:** s3-codified (2026-05-29). The META-RULE that unifies the three operations the platform does together — **vectorize**, **embed**, **cache** — into a single canonical pipeline. Whenever an agent is asked to "vectorize" / "embed" / "cache" an artifact, they follow the SAME 3-leg shape. The 6+ existing instantiations are not coincidence — they're all this pipeline.

## The 3-leg pipeline

```
┌────────────────────────────┐    ┌────────────────────────┐    ┌──────────────────────────┐
│  1. CACHING ARCHITECTURE   │ →  │  2. EMBED / VECTORIZE  │ →  │  3. CACHE PERSISTENCE    │
│  (decision FIRST,          │    │  (transform via the    │    │  (3-leg mirror contract  │
│   before any embed call)   │    │   seed pipeline only)  │    │   + source_sha invariant)│
└────────────────────────────┘    └────────────────────────┘    └──────────────────────────┘
```

### Leg 1 — Caching-architecture decision (FIRST)

**Before any embedding work**, decide WHERE this artifact lives in the cache landscape:

- **Reuse an existing keeper-mirror cache** when the SQLite shape fits — extend with a new `chunk_kind` column value or a new row category.
- **Do NOT spawn a 9th sibling cache** without crossing the recurrence + promotion ritual (see § The promotion ritual below).
- Storage path resolves through `cache_backend.cache_path(<name>)` per [[cache-portable-architecture]] (Tier-1 local at `<git-common-dir>/noctusai/cache/*.sqlite` shared by ALL worktrees + Tier-2 prod pgvector via `cache_deploy_mirror` / `cache_pull`).
- SQLite opens in WAL mode per [[cache-locking-discipline]] (readers never block writers).

**The decision is load-bearing.** Skipping it is how the platform ends up with N caches that store the same shape under different names. The promotion ritual catches this; running it FIRST avoids the rework.

### Leg 2 — Embed / vectorize (via the seed pipeline ONLY)

- **Transform via `noctusai_lib.integrations.llm.generate_embedding`** (`seed/lib/backend/noctusai_lib/integrations/llm/embeddings.py`). The seed's OpenAI-via-provider-registry pipeline owns key resolution + provider dispatch + cost capture. Single-text — the right call for a ONE-OFF embed (query time, `register_organ`).
- **A REFRESH LOOP (many chunks) MUST batch, never call `generate_embedding` per chunk.** OpenAI's `/embeddings` endpoint accepts an array `input`; a per-chunk loop turns N chunks into N independently-paced-and-retried HTTP requests, which self-inflicts 429s even when the provider is healthy (508 chunks → 507 retries observed, 2026-08 pre-push retry-storm — `models.list()` succeeded and a direct single embed always returned immediately throughout). Use `_embedding_corpus.embed_batch_sync(texts)` (→ `generate_embeddings_batch`) + `_embedding_corpus.iter_batches(items)` to slice the pending chunk list; a batch failure fails that whole slice together (preserve the existing per-doc/per-file all-or-nothing rollback at batch, not chunk, granularity). Default batch size 64, tunable via `NOCTUS_EMBED_BATCH_SIZE`.
- **NEVER inline OpenAI client calls** anywhere outside `noctusai_lib.integrations.llm` — embedding is IO; IO modules ship Protocol+Fake+Real+factory per [[seed-fake-real-adapter]].
- **Cost-log to `project-history/vector-costs.ndjson`** via `noctus.dev.vector_costs_log_batch` (or the equivalent direct append for the host CLI surface). Every embed call is auditable. Never silent.
- **Deterministic chunk shape.** The text being embedded must be derivable from a stable `source_sha = sha256(canonical_chunk_text)` — re-embed of the same content is a no-op (idempotency). Stale entries are pruned/refreshed only when `source_sha` changes.

### Leg 3 — Cache persistence (3-leg mirror contract + source_sha invariant)

Persist into the chosen sqlite (or sqlite-vec) cache with the canonical mirror contract from [[keeper-pattern-cache]]:

1. **Eager refresh** — pre-commit hook refreshes the cache when the upstream source is staged.
2. **Lazy rebuild** — query-time `lookup()` compares `cache_meta.source_sha` vs live source; rebuilds on mismatch.
3. **Loud freshness gate** — `check_<cache>_cache_freshness` keeper fails in `validate` when the cache is missing / stale / unreadable.

Auto-refresh wiring extends per [[cache-auto-freshness]]: pre-commit + `post-merge` + `post-checkout` + `pre-push` git hooks call `refresh_all_caches(only_stale=True)`. Per-file `source_sha` short-circuits bound the cost.

## Canonical code shape

```python
# noctusai_lib (or mcp/noctusai/cache_backend) — the seed-side helper

from noctusai_lib.integrations.llm import generate_embedding
from mcp.noctusai.cache_backend import cache_path, acquire_refresh_lock

def embed_and_cache(
    artifact: Artifact,        # has .canonical_text(): str + .stable_id(): str
    *,
    kind: str,                 # "kb-pattern" | "code-symbol" | "memory-doc" | "organ" | ...
    cache_name: str,           # the keeper-mirror cache file (chosen in Leg 1)
) -> CacheRow:
    # Leg 1 — cache landed: caller resolved via cache_path(cache_name)
    db_path = cache_path(cache_name)

    # Idempotency: source_sha gates the embed call
    text = artifact.canonical_text()
    source_sha = sha256(text.encode()).hexdigest()
    existing = lookup(db_path, artifact.stable_id(), source_sha)
    if existing is not None:
        return existing  # no-op re-embed

    # Leg 2 — embed via the seed pipeline only (never inline OpenAI)
    vector = await generate_embedding(text, model=EMBEDDING_MODEL)
    log_vector_cost(namespace=cache_name, tokens=count_tokens(text), model=EMBEDDING_MODEL)

    # Leg 3 — persist with the 3-leg mirror contract (eager + lazy + freshness keeper)
    with acquire_refresh_lock(cache_name):
        return upsert_row(
            db_path,
            stable_id=artifact.stable_id(),
            chunk_kind=kind,
            source_sha=source_sha,
            vector=vector,
        )
```

The shape repeats for every consumer; only the chunk extraction (Leg 1's "what's the canonical text") varies.

## The 6+ existing instantiations (proof this IS the pipeline)

Each row below is the same pipeline with a different `kind` + `cache_name`:

| Instantiation | Cache | Chunk kind | Source SHA over | Keeper |
|---|---|---|---|---|
| **kb-embeddings** | `kb-embeddings.sqlite` (sqlite-vec) | KB markdown pattern | doc body | `check_kb_vector_canonical` (advisory) |
| **code-embeddings** | `code-embeddings.sqlite` (sqlite-vec) | AST symbol (`function` / `class` / `file`) | symbol body | `check_code_embeddings_freshness` |
| **memory-embeddings** | `memory-embeddings.sqlite` (sqlite-vec) | memory doc (`feedback_*` / `reference_*` / `project_*`) | doc body | `check_memory_embeddings_freshness` |
| **corpus-embeddings** | `corpus-embeddings.sqlite` (sqlite-vec) | router/topic/orientation/command/agent/skill/template/changelog/history | source-file body | `check_corpus_embeddings_freshness` |
| **organ chunk** (seed-organs-cache W4) | reuses an existing cache by `chunk_kind="organ"` | organ definition + knowledge bundle | canonical organ text | covered by chosen host's freshness keeper |
| **build-learn-cache re-embed** (knowledge-on-append) | the organ row's cache | re-embed on append to `known_facts` / `errors_encountered` / etc | concatenated bundle text | same as host cache |

Plus the foundational primitives all 4 vector caches share:
- Storage path → `cache_backend.cache_path()` (one resolution helper) [[cache-portable-architecture]]
- Embed call → `noctusai_lib.integrations.llm.generate_embedding`
- Cost log → `project-history/vector-costs.ndjson` (via `vector_costs_log_batch`)
- Locking → `acquire_refresh_lock(<cache>)` + WAL mode [[cache-locking-discipline]]
- Refresh boundaries → pre-commit + `post-merge` + `post-checkout` + `pre-push` [[cache-auto-freshness]]

**N=6+ instantiations make this a CLEAR-cut DRY recurrence formalization** per the recurrence rule (N=2 → triage; N=3+ MUST formalize). Codifying after the 6th instance is overdue, not premature.

## The promotion ritual — when to spawn a NEW cache vs extend

| Same SQLite schema? | Same `chunk_kind` table layout? | Decision |
|---|---|---|
| YES | YES (just a new row category) | **EXTEND** the existing cache with a new `chunk_kind` value. Re-use the existing eager/lazy/freshness legs. |
| YES | NO (a new column / row dimension) | **EXTEND** via schema migration — bump cache's source_sha trigger to force a rebuild. |
| NO (e.g. need sqlite-vec but host is plain sqlite, or vice-versa) | n/a | **SPAWN a new keeper-mirror cache** following the full 3-leg mirror contract template. |

**Default = EXTEND.** Spawning a new cache is methodology surgery (new keeper, new freshness gate, new pre-commit hook leg, new INDEX.md row, new memory note); requires the recurrence-rule receipts (N≥3 same-shape consumers) + a one-line rationale at promotion time.

## Cost discipline (non-negotiable)

- Every embed call MUST log to `project-history/vector-costs.ndjson` via `noctus.dev.vector_costs_log_batch`. Silent embeds break the cost-tracking surface ([[vector-cost-tracking]]).
- The cost log feeds the `/cost-report` slash command + the `dispatch-budget` sibling pattern.
- A re-embed that hits the source_sha cache should NOT log a cost (it didn't happen). Cost-log only on actual API roundtrip.

## Idempotency (non-negotiable)

- `source_sha = sha256(canonical_chunk_text)`. **Canonical** means deterministic: same input → same hash regardless of whitespace normalization / ordering / formatting choices. Pin the canonicalization once per cache.
- Re-embed of the same `(stable_id, source_sha)` is a no-op. The cache returns the existing row; no API call.
- Source change ⇒ `source_sha` changes ⇒ the lazy rebuild leg fires next query (OR the eager pre-commit leg refreshes immediately if the source file is staged).

## Anti-patterns

- **Inline OpenAI client calls outside `noctusai_lib.integrations.llm`** — breaks Protocol+Fake+Real+factory contract; tests can't swap to Fake; cost-log bypassed. Cite: the seed-Fake-Real-adapter rule.
- **Silent freshness gaps** — embed without registering the cache in the pre-commit / post-merge / post-checkout / pre-push refresh chain. Cite: [[cache-auto-freshness]]. The chain firing IS the methodology working; gaps = silent staleness.
- **Embed-without-caching (one-shot embed)** — wasted work. If the embedding has any future query value, persist it via Leg 3. If it doesn't, you don't need to embed at all.
- **Cache-without-re-embed-on-source-change** — stale entries silently misroute queries. The 4 cache-path bugs caught 2026-05-28 were variants of this. The `source_sha` invariant + the freshness keeper close the loop.
- **Spawn a 9th sibling cache without the promotion ritual** — duplicates the keeper surface, fragments query attention (which cache do I search?), bloats the 4-hook refresh chain. The recurrence-rule receipts MUST land first.
- **Skip Leg 1 ("just add the embed call")** — by the time you discover the existing cache that already houses this `chunk_kind`, you've shipped a fork. Leg 1 is cheaper than the rework.

## Composes with

- [[cache-portable-architecture]] — Leg 1's storage-path resolution
- [[cache-locking-discipline]] — Leg 3's WAL mode + `acquire_refresh_lock`
- [[cache-auto-freshness]] — Leg 3's 4-boundary refresh chain
- [[keeper-pattern-cache]] — the 3-leg mirror contract template
- [[cache-as-agent-tool]] — the consumption rule (caches as search engines; the read side of this pipeline)
- [[seed-fake-real-adapter]] — Leg 2's IO Protocol shape (embedding is IO)
- [[vector-cost-tracking]] — Leg 2's cost-log destination
- [[methodology-codification-pipeline]] — the s1→s2→s3→s4 stages this rule itself just traversed
- [[kb-vector-search]] / [[code-embeddings]] / [[memory-embeddings]] / [[corpus-embeddings]] — the 4 vector-cache instantiations

## Sibling docs (the build-learn-cache mindset is named but not codified)

The build-learn-cache mindset (knowledge-on-append re-embed contract) was named in commit `f4aa96aa` (2026-05-29) — implementation via `noctus.dev.organ_knowledge_{append,query}` tools in seed-organs-cache W5, but the standalone KB doc was deferred. This META-RULE incorporates that mindset directly: any append to an organ's knowledge bundle triggers a re-embed via Leg 2 + a Leg-3 upsert. When the standalone `build-learn-cache-mindset.md` lands, it will compose with this one (this is the foundational pipeline; that is the loop-of-learning that runs on top).

## Why codify this NOW

Codification trigger (2026-05-29): user-surfaced META-RULE — "whenever i ask future agents to vectorize or embbed, or cache, all 3 should follow the same fw of caching -> embbed/vectorize, then cache." The 6 existing instantiations (4 vector caches + organ chunk + build-learn re-embed) are the recurrence-rule receipts. Shipping the 7th instance without this codification = shipping the forbidden 4th instance of the recurrence rule.
