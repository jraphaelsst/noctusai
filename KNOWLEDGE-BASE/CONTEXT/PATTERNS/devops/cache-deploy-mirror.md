# cache-deploy-mirror — local SQLite → prod Postgres+pgvector snapshot

> **Scope**: `noctus.dev.cache_deploy_mirror` (`mcp/noctusai/tools/noctus/dev/cache_deploy_mirror.py`)
> — the tool that seeds prod's centralized cache from a local dev snapshot at
> deploy time, and its companion `noctus.dev.repair_embedding_cache_drift`.
> Composes with `KB § PATTERNS/common/cache-portable-architecture.md` (the
> Tier-1/Tier-2 model this mirror bridges) and `KB § PATTERNS/common/
> vectorize-embed-cache-framework.md` (the embed→cache pipeline whose output
> this mirror transports).

## Why this exists

Local dev caches live in `<git-common-dir>/noctusai/cache/*.sqlite` (Tier-1).
Prod runs the same noc against a centralized Postgres+pgvector backend
(Tier-2). At deploy time the prod cache is SEEDED from the local snapshot —
prod starts with a mirror of the architect's "blessed" state instead of
paying a full OpenAI re-embed. Vectors transfer **verbatim** (BLOB → JSON →
`list[float]` → pgvector `vector(1536)`) — this tool never calls the
embedding provider.

## The mirror contract

- **Idempotent** — TRUNCATE+INSERT per cache; re-runs are safe.
- **Atomic-per-cache** — each cache mirrors as one Postgres transaction.
  An exception rolls back; the prod cache stays at the prior consistent
  snapshot.
- **Verifies** — post-read, `rows_written` MUST equal `source_total` (what
  the mirror INTENDED to ship) or the transaction is rolled back and the
  result is `ok=False` with a named delta (`mirror-row-count-mismatch`).
  Never `ok: True` on a partial ship.
- **Bound** — a single call mirrors all 7 caches (or `only=[...]`). NOT
  incremental; every mirrored cache is a full replace.

## 🔴 2026-08-14 — cache-mirror-join-drift

### The defect

The 4 chunk-and-embedding caches (kb / code / memory / corpus-embeddings)
each store a chunk's embedding in **exactly one** of two sibling tables:

- `*_vec` — a `sqlite-vec` virtual table (fast path, binary float32 BLOBs).
- `*_embeddings_json` — a plain table (fallback, JSON-encoded `list[float]`),
  used when the refreshing process doesn't have the `sqlite-vec` extension
  loaded.

`sqlite-vec` is an **opportunistically pip-installed, UNPINNED** dependency
— present in `mcp/noctusai/.venv` (the MCP-server + pre-push venv) but
absent from every `requirements.txt` / `pyproject.toml` in this repo, so it
is also absent from a fresh CI checkout or the repo-root `venv`. The SAME
physical cache file gets refreshed by different processes over its
lifetime (the long-lived MCP server, the pre-push git hook, occasionally a
bare CLI invocation) — whichever one happens to have the extension writes
to `*_vec`; whichever doesn't writes to `*_embeddings_json`.

The refresh path's delete-before-rebuild logic branched on the **current
process's** `HAS_VEC` flag alone (`if HAS_VEC: delete vec else: delete
json`) instead of cleaning both sibling tables. So a doc/file refreshed
under environment B after previously being refreshed under environment A
had its OLD rows (in A's table) orphaned — the delete only ever reached
its own engine's table.

Measured on the live local caches before the fix (union == every chunk
had EXACTLY one embedding, split across the two tables — zero data was
actually lost, it was just partitioned):

| cache | chunks | vec-joined | json-joined | mirrored pre-fix (json-only) |
|---|---:|---:|---:|---:|
| kb | 2,937 | 1,236 | 1,701 | 1,701 (58%) |
| code | 4,240 | 1,790 | 2,450 | 2,450 (58%) |
| memory | 1,078 | 178 | 900 | 900 (83%) |
| corpus | 396 | 386 | 10 | 10 (3%) |

The mirror (`_mirror_chunks_with_json_embedding`, the pre-fix name) read
**only** `*_embeddings_json` via an `INNER JOIN` — silently dropping every
chunk whose embedding lived in `*_vec` instead — while still returning
`ok: true`. This is the higher-severity half of the bug: a **silent
shortfall reporting success**, the exact "no silent errors" class
CLAUDE.md §1 exists to prevent.

### The fix (two legs, same commit)

**Leg 1 — make a shortfall impossible to report as success.** Every
`_mirror_*` helper now returns `{rows_written, source_total, ...}` instead
of a bare int. `mirror_one_cache` generically compares the two: a mismatch
rolls back the transaction and returns `ok=False` with the named delta —
this is what the "Verifies" line in the module docstring already claimed;
the implementation never actually enforced it before this fix.

**Leg 2 — read the FULL corpus, not one engine's half.**
`_mirror_chunks_with_embedding` (renamed) reads **both** sibling tables in
Python — a vec0 virtual table can only be referenced when the sqlite-vec
extension is loaded on the reading connection, so `mirror_one_cache` opens
via `_ec.connect_cache()` (loads the extension when available) instead of
a bare `sqlite3.connect()`. Any chunk with no embedding in **either** table
is collected in `missing_embedding_sample`, never silently dropped and
never shipped as a NULL vector (a NULL vector would silently fail every
future similarity query against it — worse than dropping the row).

The root **write-side** fix lives in `_embedding_corpus.py`
(`delete_embedding_rows`, `init_schema`) and is duplicated inline in
`kb_embeddings.py` / `code_embeddings.py` (their own refresh loops predate
the N=4 consolidation and were never migrated to call the shared helper —
flagged as a follow-up):

- `init_schema` now **always** creates the plain `json_table` (zero
  extension dependency, safe to create unconditionally), in addition to
  `vec_table` when `HAS_VEC`. Previously only the CURRENT process's
  branch was created — a cache born under one engine never even had the
  other table to clean up later.
- `delete_embedding_rows(conn, *, vec_table, json_table, rowids)` deletes
  from `json_table` unconditionally and from `vec_table` when `HAS_VEC` —
  not gated on "this process's engine" alone. A row written by a DIFFERENT
  environment than the one running the delete is now still reachable
  (the json side always is; the vec side is reachable whenever the
  deleting process itself has the extension, which is the dominant case —
  pre-push + the MCP server both run under `mcp/noctusai/.venv`).

### The repair — `noctus.dev.repair_embedding_cache_drift`

LOCAL-ONLY, lossless, **zero re-embed cost**. Because every chunk in every
affected cache had exactly one valid embedding (never zero, never two —
verified empirically), the split is fully recoverable without calling the
OpenAI embedding API: `_ec.backfill_cross_engine_embeddings` copies every
json-only embedding across into the vec table (decode JSON → pack float32
→ `INSERT INTO vec_table(rowid, embedding)`, same vector, same rowid) and
prunes rows in either sibling table whose chunk no longer exists (garbage
from a since-superseded doc generation). Idempotent — safe to re-run.
Requires `sqlite-vec` loaded in the calling process (run it via the MCP
server, not a bare CLI in a venv lacking the extension); returns
`status='skipped-no-vec'` otherwise, never an error.

**Run this once, locally, before the next `cache_deploy_mirror
confirm=True`** — it repairs the SOURCE the mirror reads from, so prod
receives the full corpus in one pass instead of the join-fixed-but-still-
split local state.

```
noctus.dev.repair_embedding_cache_drift            # all 4 caches
noctus.dev.repair_embedding_cache_drift only=['kb-embeddings']
```

⚠️ A `cache_deploy_mirror confirm=True` run BEFORE this fix landed
**shrank prod** to the json-only subset (TRUNCATE+INSERT semantics — prod
now holds only what that run's mirror could see). The next correct
`confirm=True` run (after this fix + the repair above) restores the full
corpus; there is no need to separately "undo" the shrink — TRUNCATE+INSERT
is self-correcting on the next successful run.

## When to call `cache_deploy_mirror`

- At deploy time, AFTER `noctus.dev.release stage=promote` but BEFORE
  `noctus.dev.deploy_pull confirm=True` runs on the VPS.
- Manually for force-resync: `noctus.dev.cache_deploy_mirror confirm=True`.
- Always dry-run first (`confirm=False`, the default) — reports per-cache
  local row-plan without touching prod.

## What it does NOT do

- Does NOT re-embed — vectors transfer verbatim, schema-translation only.
- Does NOT create the prod database — schema must exist first
  (`noctus.dev.init_prod_cache_schema`, safe to re-run).
- Does NOT swap backends — the caller still sets
  `NOCTUS_CACHE_BACKEND=postgres` to consume the mirror.

## Composes with

`KB § PATTERNS/common/cache-portable-architecture.md` (Tier-1/Tier-2
model) · `KB § PATTERNS/common/vectorize-embed-cache-framework.md` (the
3-leg cache contract: eager pre-commit/pre-push refresh, lazy query-time
rebuild, freshness keeper) · `KB § PATTERNS/common/cache-family-index.md`.
