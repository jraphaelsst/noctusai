# Memory embeddings — 6th keeper-mirror cache

> Semantic search over the agent's OUT-OF-REPO memory dir. Sibling of
> `kb-embeddings` / `code-embeddings`; closes the "have we seen this
> pattern before" gap. Shipped v4.0.

## What it indexes

`~/.claude/projects/<workspace>/memory/`:
- `MEMORY.md` — the auto-loaded index.
- Every `feedback_*.md` — workflow / deployment / architecture / etc.
- Every `reference_*.md` — pointers to external systems.
- Every `project_*.md` — durable project notes.

Out-of-repo by Claude Code design (per-project workspace store). The cache
discovers the dir via:
1. `NOCTUS_AGENT_MEMORY_DIR` env override.
2. Path-slug derivation against the **primary** git worktree (linked
   worktrees share memory) — `<primary-path-with-/-as->` under
   `~/.claude/projects/`.
3. Loose-match scan as fallback.

Local store: `.claude/cache/memory-embeddings.sqlite` (same WAL + sqlite-vec
shape as kb-embeddings). Prod mirror: `noctus_cache.cache_memory_embeddings`
via `cache_deploy_mirror`.

## Why this exists

Memory grows continuously. Today: ~50 feedback files, ~5000 prose words +
codified rules. A pure-grep workflow doesn't find conceptual matches —
"we hit this last month under a different name" went un-served. Semantic
search closes that gap with the same shape kb-embeddings was built for.

## API

```python
from tools.noctus.dev import memory_embeddings as mee

mee.refresh(force=False)                    # incremental (per-file sha)
mee.search("worktree salvage decisions")    # returns top-K chunks
mee.cache_source_sha()                      # aggregate sha for freshness keeper
```

CLI:
- `--refresh-memory-embeddings [--force]`
- `--memory-search QUERY [--top-k N]`
- `--check-memory-embeddings-cache-freshness`

MCP:
- `noctus.dev.refresh_memory_embeddings`
- `noctus.dev.memory_search`
- `openai.search.memory` (via openai_mcp facade)

## Freshness

Three boundaries keep it fresh:
1. **Pre-push hook** — refreshes on `git push` (the user-visible batching unit).
2. **Operator on-demand** — `noctus.dev.refresh_memory_embeddings(force=True)` from any session.
3. **`check_memory_embeddings_cache_freshness`** — gate that compares `cache_meta.source_sha` to live aggregate sha.

Memory has no git-hook signal (out of repo). The pre-push run is the
mechanical refresh; manual triggers cover ad-hoc refresh.

## Mirror to prod

Same contract as the other 6 keeper-mirror caches:
- Per-cache TRUNCATE+INSERT in `cache_deploy_mirror`.
- JOIN local `memory_chunks` + `memory_embeddings_json` to populate the prod
  `vector(1536)` column.
- Atomic per-cache; idempotent re-run safe.

## Composes with

- `KB § PATTERNS/common/kb-vector-search.md` — sibling cache + shared chunker / embedder.
- `KB § PATTERNS/common/code-embeddings.md` — sibling cache.
- `KB § PATTERNS/common/corpus-embeddings.md` — 7th sibling cache.
- `KB § PATTERNS/common/push-time-embedding-gate.md` — the refresh boundary.
- `KB § PATTERNS/common/cache-auto-freshness.md` — umbrella.

## Known debt

`NOC-REMEDIATE[embedding-cache-framework]`: with kb + code + memory +
corpus at N=4, the embedding-cache infrastructure is in DRY violation.
v4.1 should extract `noctusai_lib.cache.embedding_cache` framework + thin
per-corpus modules. For now, the 4 modules reuse helpers via import
(`from .kb_embeddings import _embed_sync, _cosine, ...`). — 2026-05-27
