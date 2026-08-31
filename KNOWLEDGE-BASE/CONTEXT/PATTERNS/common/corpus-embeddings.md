# Corpus embeddings — 7th keeper-mirror cache

> Semantic search over the heterogeneous in-repo "everything else we read
> but isn't KB or code". Shipped v4.0.

## What it indexes

Five source types, distinguished by a `source_type` column:

| `source_type` | Source path(s) | Why |
|---|---|---|
| `changelog` | `CHANGELOG.md` (when present) | "What changed in 4.x" lookups |
| `template` | `templates/**/*.md` | PROJECT-TEMPLATE / PROPOSAL-TEMPLATE / MASTER-PROMPT — agents need to find the canonical template for a situation |
| `agent` | `.claude/agents/*.md` (FULL body — L1 already in `agent-context` cache) | "Which agent does X" + "what's the full body discipline for Y" |
| `skill` | `.claude/skills/**/SKILL.md` | "Which skill auto-triggers on Z" |
| `history` | `project-history/PROJECT-HISTORY.md` | "What was decided when" — durable historical record |

Excluded by design:
- `projects/<slug>/PROJECT.md` — ephemeral; you're working on it.
- Source code — already in `code-embeddings`.
- `.claude/commands/<name>.md` — user-invoked only; low value vs. file-list grep.

Local store: `.claude/cache/corpus-embeddings.sqlite`. Prod mirror:
`noctus_cache.cache_corpus_embeddings` (with the `source_type` column).

## Why this exists

The searchable-corpus inventory before v4.0 was {KB, code}. Templates,
skills, agents (full body), changelog, and history all required grep —
which works but doesn't find conceptual matches. v4.0 closes the gap so
an agent asking "which skill auto-triggers on 'absorb a product'" gets a
real ranked answer.

## API

```python
from tools.noctus.dev import corpus_embeddings as cee

cee.refresh(force=False)                                # incremental
cee.search("absorb a product",                          # all source types
           top_k=5, min_score=0.0)
cee.search("absorb a product", source_type="skill")     # scope to skills only
cee.cache_source_sha()                                  # for freshness keeper
```

CLI:
- `--refresh-corpus-embeddings [--force]`
- `--corpus-search QUERY [--top-k N --source-type TYPE]`
- `--check-corpus-embeddings-cache-freshness`

MCP:
- `noctus.dev.refresh_corpus_embeddings`
- `noctus.dev.corpus_search` (accepts optional `source_type` kwarg)
- `openai.search.corpus` (via openai_mcp facade — also accepts `source_type`)

## Freshness boundaries

Four hooks keep the cache fresh:
1. **post-merge** — refresh when any indexed source changes after pull/merge.
2. **post-checkout** — refresh after branch switch if any indexed source changed.
3. **pre-push** — accumulated refresh before push (the user-visible batching unit).
4. **`check_corpus_embeddings_cache_freshness`** — gate keeper.

The pre-commit hook does NOT auto-refresh (per `push-time-embedding-gate`
discipline — embed at push, not commit).

## Mirror to prod

Same atomic per-cache contract. The `source_type` column travels through
the JOIN-and-splice in `cache_deploy_mirror._mirror_chunks_with_json_embedding`
(first column in the wide-row INSERT).

## Source-type scoping

`source_type` lets callers narrow the search. Useful patterns:

- `source_type="agent"` — "what's the discipline for X agent"
- `source_type="skill"` — "which skill triggers on Y"
- `source_type="template"` — "which template should I copy for Z"
- `source_type="history"` — "when did we decide W"
- `source_type="changelog"` — "what changed between 4.0 and 4.1"

No `source_type` = search across all 5.

## Composes with

- `KB § PATTERNS/common/memory-embeddings.md` — out-of-repo sibling cache.
- `KB § PATTERNS/common/kb-vector-search.md` — first vector cache; shared chunker/embedder.
- `KB § PATTERNS/common/code-embeddings.md` — code sibling.
- `KB § PATTERNS/common/push-time-embedding-gate.md` — refresh discipline.
- `KB § PATTERNS/common/agent-context-architecture.md` — the L1 extract of agents (this cache holds the FULL body).
- `KB § PATTERNS/common/cache-auto-freshness.md` — umbrella.

## Known debt

`NOC-REMEDIATE[embedding-cache-framework]`: same as memory-embeddings —
N=4 of the embedding-cache pattern, formalization owed in v4.1. — 2026-05-27
