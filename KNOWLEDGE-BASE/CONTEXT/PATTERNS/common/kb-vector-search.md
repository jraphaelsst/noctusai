# KB vector search — markdown-canonical, vector-DB-is-enrichment

**What it is.** A semantic-search + organizational-intelligence layer over the KB, built on top of the existing markdown corpus. Fourth keeper-mirror cache (after keeper-pattern + agent-context + auto-improvement). The vector DB at `.claude/cache/kb-embeddings.sqlite` is an **enrichment index** — never a content store. Born 2026-05-26 Phase B follow-up.

**The principle (user mandate, codified).** *"Markdown stays in git as canonical … vector DB becomes a smarter index, not a replacement."* Git superpowers preserved (review, blame, diff, branch, merge) + semantic intelligence gained. Enforced by `check_kb_vector_canonical` (severity `warning` — advisory layer, never blocks correctness).

**Why both layers (the two-layer model).**

```
EMBEDDING MODEL (text → vector)        OpenAI text-embedding-3-small (1536-D)
  via `noctusai_lib.integrations.llm.generate_embedding`
  picked for: quality; same provider as ERP's embedding_service
                            ↓
VECTOR STORAGE + SEARCH                sqlite-vec (vec0 virtual table, BLOB storage)
  picked for: native KNN, ~4× smaller, future-proof to 1M+ vectors
  fallback: JSON column + pure-Python cosine if sqlite-vec absent
```

The model layer produces vectors; the storage layer searches them. **The LLM consuming results reads the chunk TEXT (markdown), never the vector** — vectors are search indices, not storage.

## What's shipped

| MCP tool | Purpose | Layer |
|---|---|---|
| `noctus.dev.kb_search(query, top_k)` | Semantic search over the KB — fuzzy-intent queries → ranked chunks | high-level (KB) |
| `noctus.dev.kb_neighbors(path, top_k)` | Top-K semantically nearest KB docs (powers auto-generated "see also") | high-level (KB) |
| `noctus.dev.kb_similar(text, top_k)` | Pre-authoring radar — find existing patterns before writing a new one | high-level (KB) |
| `noctus.dev.kb_validate_owns_kb()` | Audit per-agent `owns_kb:` claims via centroid similarity — flag mis-owned docs | high-level (KB) |
| `noctus.dev.kb_embeddings_refresh(force?, paths?)` | Re-populate the cache; per-doc source_sha guard | high-level (KB) |
| `noctus.dev.kb_embeddings_list()` | Distinct paths in the cache (verify coverage) | high-level (KB) |
| `noctus.dev.vector_embed(text)` | Embed arbitrary text — generic primitive for ad-hoc / prototyping | low-level (platform) |
| `noctus.dev.vector_status()` | Inspect: provider, model, engine, registered caches | low-level (platform) |

CLI: `--refresh-kb-embeddings [--force]` · `--kb-search <query> [--top-k N]` · `--check-kb-embeddings-cache-freshness`.

## 3-leg mirror contract

Same shape as the keeper-pattern / agent-context / auto-improvement caches:

| Leg | Mechanism |
|---|---|
| Eager pre-commit refresh | `scripts/hooks/pre-commit`: if `KNOWLEDGE-BASE/**/*.md` is staged → `cli.py --refresh-kb-embeddings` runs (reuses the existing KB-change trigger leg). |
| Lazy query-time refresh | Per-doc source_sha guard in `refresh()`; mismatched → rebuilds before answering. |
| Loud freshness gate | `check_kb_vector_canonical` (severity `warning`) — fails as warning at `validate` when stale or orphan rows present. |

**Why warning, not high.** Vector search is **advisory** — a stale cache returns slightly outdated rankings; everything else still works. The agent can always fall back to grep / owns_kb / INDEX.md. Don't block commits over a degraded discovery layer.

## Schema

```sql
-- Always present (chunk metadata, both engines).
CREATE TABLE kb_chunks (
  rowid_alias  INTEGER PRIMARY KEY AUTOINCREMENT,
  path         TEXT NOT NULL,        -- e.g. 'CONTEXT/PATTERNS/common/foo.md'
  chunk_idx    INTEGER NOT NULL,
  chunk_text   TEXT NOT NULL,        -- the literal chunk (LLM reads THIS)
  source_sha   TEXT NOT NULL,
  cached_at    TEXT NOT NULL
);

-- Fast path: sqlite-vec virtual table (rowid joined to kb_chunks).
CREATE VIRTUAL TABLE kb_vec USING vec0(embedding float[1536]);

-- Fallback path: JSON column (when sqlite-vec absent).
CREATE TABLE kb_embeddings_json (
  chunk_rowid  INTEGER PRIMARY KEY,
  embedding    TEXT NOT NULL  -- JSON-serialized list[float]
);
```

## Chunking strategy

Per-H2 with paragraph windows + char cap (1800 chars ≈ 450 tokens, well under the 8191-token embedding model limit). Each chunk preserves the H1 title as a prefix → standalone retrievable without losing doc context. Tuned for noc's well-structured KB pattern docs.

## Use cases beyond search (the enrichment layer)

The vector DB powers more than `kb_search`. These are deferred next-slices, sketched here so future-us doesn't lose the thread:

| Tool | Status | What it does |
|---|---|---|
| `kb_neighbors` | **SHIPPED** | Top-K semantic neighbors per doc (auto-generated "see also") |
| `kb_similar` | **SHIPPED** | Pre-authoring radar — find existing patterns before writing a new one |
| `kb_validate_owns_kb` | **SHIPPED** | Audit ownership claims — flag mis-owned docs via centroid distance |
| `kb_cluster` | DEFERRED | k-means/DBSCAN topic clustering — reveals natural taxonomy, challenges/validates manual subfolders |
| `kb_recurrence_radar` | DEFERRED | New auto-improvement entry → vector-compare to existing s1/s2 → flag near-dups → speed up N=3 promotion |
| `code_embeddings_*` | DEFERRED | Cross-product code similarity (different chunking pipeline — embed Python AST nodes / TS modules) |

Each is a thin module on top of this cache + `noctus.dev.vector_*` primitives.

## Named triggers — when to revisit / extend

- **OpenAI dependency**: noc already uses OpenAI for chat + embeddings (ERP). If we want fully airgapped: swap the model to `sentence-transformers` (BGE/mxbai). Same interface; only the provider changes. (A future LLM-integrations KB doc would catalog the swap.)
- **Corpus growth past 5,000 chunks**: pure-Python cosine starts to lag; sqlite-vec scales easily. We already use sqlite-vec when available — this trigger just means "monitor query latency."
- **Cross-product code semantics**: would call for a separate cache (`code-embeddings.sqlite`) keyed by `(product, path, symbol)` rather than `(kb_path, chunk_idx)`.
- **Vector DB stops being advisory**: if downstream tools START to require the vector cache to function (vs. degrade gracefully), promote the freshness keeper from `warning` to `high`.

## Anti-patterns (the principle, restated)

- **Move KB content INTO the vector DB.** Markdown is canonical. The DB never holds authoritative content; it holds vectors that POINT BACK to markdown. Loss of markdown = loss of git superpowers (review/blame/diff/branch/merge) for a search optimization we don't need.
- **Read vector content as authoritative.** The LLM consumes `chunk_text` (markdown), not the vector. Vectors are search indices, not storage.
- **Block commits on vector-cache freshness.** The cache is advisory. Severity stays `warning`. If you want to block, you have a different requirement (probably an SLO on discovery quality) that doesn't belong here.
- **Skip the existing routing in favor of vector search.** Vector search is great for fuzzy intent ("find patterns about cross-product state management") but inferior to grep / owns_kb / INDEX.md for tight-named-concepts ("the `_HARNESS_ADVISOR_AGENTS` set-membership"). Use both; vector is ADDITIVE.

## Composes with

[[keeper-pattern-cache]] (first cache; same 3-leg contract) · [[agent-context-architecture]] (second cache + `owns_kb:` declarations this layer can audit) · [[scoped-auto-improvement]] (third cache + future semantic-recurrence-radar) · [[methodology-codification-pipeline]] (s3-kb stage gets a sensor: cluster-detection of s1/s2 entries) · [[keeper-check-before-docing]] (the discipline this extends — query the cache BEFORE editing) · [[claude-md-router-discipline]] (markdown-as-canonical sibling principle).
