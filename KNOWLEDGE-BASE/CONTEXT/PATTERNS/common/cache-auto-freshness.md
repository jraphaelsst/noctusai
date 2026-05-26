# Cache auto-freshness — the closed loop on doc-update propagation

**What it is.** The full propagation contract for keeping the 5 keeper-mirror caches aligned with the live tree, beyond the commit boundary. Composes existing legs (pre-commit hook + 3-leg mirror contract per cache) with NEW git hooks (post-merge + post-checkout) + an orchestrated tool (`refresh_all_caches`) + a user-invocable slash command (`/refresh-caches`).

Born 2026-05-26 — closes the staleness gaps surfaced after the v4.0-beta cycle made vector caches load-bearing.

## The full coverage matrix

| Mutation source | What used to happen | What happens now |
|---|---|---|
| Edit + commit (in-session) | ✅ pre-commit hook leg fires per affected cache | ✅ unchanged |
| `git pull` brings in remote changes | ⚠️ cache stales until next query OR next commit | ✅ **post-merge hook** refreshes affected caches |
| `git checkout <branch>` swap | ⚠️ cache stales for the new branch state | ✅ **post-checkout hook** refreshes affected caches |
| Fresh clone | ✅ first query bootstraps (cache file missing → refresh) | ✅ unchanged |
| Embedding provider fails | ✅ graceful-degrade; cache stays at previous state | ✅ unchanged |
| Doc deleted (orphan row remains) | ⚠️ `check_*_canonical` keeper surfaces warning; not purged | ⚠️ same — see anti-pattern below |
| Many concurrent edits across surfaces | ⚠️ each cache refreshes only its own surface | ✅ **`refresh_all_caches`** + `/refresh-caches` for explicit full sync |
| Embedding model upgrade | ⚠️ dim mismatch errors at retrieve time | ⚠️ same — see deferred follow-up below |

## The hooks

### `scripts/hooks/post-merge`

Fires after `git pull` OR `git merge`. Computes `git diff --name-only HEAD@{1} HEAD` to find what changed; refreshes affected caches:
- `KNOWLEDGE-BASE/**/*.md` changed → `--refresh-kb-embeddings` (advisory)
- `(mcp|noctusai_lib|products/seed)/**/*.{py,ts,tsx}` changed → `--refresh-code-embeddings` (advisory)
- `project-history/auto-improvement.ndjson` changed → `--refresh-auto-improvement-cache` (blocking)
- `.claude/agents/**/*.md` OR `KNOWLEDGE-BASE/**` changed → `--refresh-agent-context-cache` (advisory)
- `compliance.py` changed → `--refresh-keeper-cache` (blocking)

Symlinked from `.git/hooks/post-merge` via `install-hooks.sh`.

### `scripts/hooks/post-checkout`

Fires after branch switch (git passes `flag=1` for branch checkouts, `0` for file-level — we only act on branch switches). Same trigger matrix as post-merge.

Notable behavior:
- Skips file-level checkouts (no working-tree state change worth re-embedding).
- Skips no-op checkouts where `prev == new`.
- Fast-exits when no cache-relevant files changed in the diff.

## `refresh_all_caches` orchestrator

`noctus.dev.refresh_all_caches(force=False, skip=None)` runs all 5 cache refreshes in sequence:

```
1. keeper-patterns       (mirrors compliance.py)
2. agent-context         (mirrors .claude/agents/<name>.md ∪ owned_kb)
3. auto-improvement      (mirrors project-history/auto-improvement.ndjson)
4. kb-embeddings         (vector cache over KNOWLEDGE-BASE/**/*.md)
5. code-embeddings       (vector cache over code corpus)
```

Returns:
```python
{
  "ok": bool,                          # True iff every cache succeeded
  "refreshed": {cache_name: result},   # per-cache return dict
  "failures": [cache_name, ...],
  "total_rows_written": int,
  "warnings": [str, ...],
  "skipped": [cache_name, ...]
}
```

## `/refresh-caches` slash command

User-invocable version of the same orchestrator. See `.claude/commands/refresh-caches.md` for the protocol.

## Anti-patterns

- **DON'T** loop `refresh_all_caches` on a timer — embedding refreshes are metered (OpenAI cost). Trust the 3-leg mirror + git hooks.
- **DON'T** pass `force=True` casually — re-embeds the ENTIRE corpus regardless of source_sha. Reserve for: model upgrade, schema migration, debugging.
- **DON'T** treat orphan rows as a blocker — keepers surface them as warnings; auto-purge would conflict with the "keepers surface, don't act" rule. Run `--refresh-kb-embeddings --force` if you need to clean.
- **DON'T** rely on this hook chain for cross-machine sync of `.claude/cache/*` SQLite files — those are gitignored per-user; refresh on the new machine.

## Deferred follow-ups (next session candidates)

1. **Embedding-model version stamp**: cache rows don't currently record the model name. If the seed lib upgrades `text-embedding-3-small` → `4-small`, dim mismatch errors only surface at retrieve time. A `model:` column per row + a startup check would auto-trigger force-refresh on model change.
2. **Orphan-row auto-purge tool**: a separate `noctus.dev.purge_orphan_cache_rows()` MCP tool that the keeper remediation messages point at. Keeps the "keepers surface, never act" rule clean while still offering one-command cleanup.
3. **Filesystem watcher** (heavy): daemon that watches the tracked surfaces + triggers refresh on save. OS-specific; defer until pull/checkout coverage proves insufficient.

## Composes with

- [`keeper-pattern-cache`](keeper-pattern-cache.md) — first cache; sets the 3-leg mirror contract this auto-freshness mechanism extends.
- [`kb-vector-search`](kb-vector-search.md), [`code-embeddings`](code-embeddings.md) — the two vector caches with the most expensive refreshes.
- [`agent-context-architecture`](agent-context-architecture.md), [`scoped-auto-improvement`](scoped-auto-improvement.md) — caches with high-severity freshness keepers.
- `/vector-status` — post-refresh health check.
- `/cost-report` — cost visibility for embeddings refreshes.

## History

- v4.0-beta (2026-05-26 morning): pre-commit hook leg 9b/9c/10 + per-cache freshness keepers were in place; assumed commit boundary covers freshness.
- v4.0-beta (2026-05-26 evening): user observation surfaced the gap — `git pull` + branch switch don't fire pre-commit, leaving caches stale. This pattern + the hooks codify the closure.
