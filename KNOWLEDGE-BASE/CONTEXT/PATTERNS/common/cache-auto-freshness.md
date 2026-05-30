# Cache auto-freshness — the closed loop on doc-update propagation

**What it is.** The full propagation contract for keeping the 5 keeper-mirror caches aligned with the live tree, beyond the commit boundary. Composes existing legs (pre-commit hook + 3-leg mirror contract per cache) with NEW git hooks (post-merge + post-checkout) + an orchestrated tool (`refresh_all_caches`) + a user-invocable slash command (`/refresh-caches`).

Born 2026-05-26 — closes the staleness gaps surfaced after the v4.0-beta cycle made vector caches load-bearing.

## Cache cadence — two tiers (2026-05-29)

Caches split by refresh cost, NOT all-on-every-boundary:

- **Structural caches** (keeper-patterns · agent-context · auto-improvement · **noc-graph**) — fast, local, **zero OpenAI**. Refresh on **pre-commit** (fix-on-contact) AND pre-push/post-merge/post-checkout. A methodology-surface change is reflected in these the moment it's committed. (noc-graph's semantic edges read the embedding caches via SQLite — `ingest_semantic_neighbors` makes zero OpenAI calls — so the graph rebuild is fast even though embeddings are deferred.)
- **Embedding caches** (kb · code · corpus · memory) — OpenAI-backed, slow. Refresh on **pre-push + post-merge + post-checkout ONLY**, never on pre-commit. They're advisory (semantic-search enrichment) and self-heal at the next push/merge; refreshing them per-commit taxed the inner loop for no correctness gain (the correctness gates — kb_sync · router · 8-way-sync — stay synchronous regardless). Supersedes the 2026-05-27 "every cache every boundary" rule for the embedding tier (user mandate 2026-05-29).

The 8-way-sync gate's `check_all_cache_freshness` leg checks every cache regardless of tier — so a stale cache is always surfaced; the tiering only decides WHERE it gets eagerly refreshed.

## The full coverage matrix

| Mutation source | What used to happen | What happens now |
|---|---|---|
| Edit + commit (in-session) | ⚠️ embedding refresh on every commit taxed the loop | ✅ pre-commit refreshes the **structural** caches (incl. noc-graph) only — fix-on-contact, no OpenAI |
| `git push` | ⚠️ (n/a) | ✅ **pre-push hook** refreshes ALL caches incl. the 4 embedding caches |
| `git pull` brings in remote changes | ⚠️ cache stales until next query OR next commit | ✅ **post-merge hook** refreshes all affected caches (incl. embeddings) |
| `git checkout <branch>` swap | ⚠️ cache stales for the new branch state | ✅ **post-checkout hook** refreshes all affected caches (incl. embeddings) |
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

`noctus.dev.refresh_all_caches(...)` with **4 selection modes** (mutually exclusive):

| Mode | Param | Behavior |
|---|---|---|
| **specified** (most-specified) | `only=["kb-embeddings", ...]` | Refresh ONLY listed caches; everything else skipped. Use when you KNOW what needs refresh. |
| **stale-detect** (smart default) | `only_stale=True` | Pre-check freshness keepers; refresh ONLY caches with surfaced drift. Zero work on clean caches — no cache walk overhead. |
| **skip** | `skip=["code-embeddings"]` | Refresh all except listed. Useful when offline (skip the expensive vector caches). |
| **all** | (none of the above) | Walk all 5 caches; each cache's internal source_sha guard still skips in-sync content. Lower-overhead "verify everything" pass. |

Combine any mode with `force=True` to rebuild matching caches even when source_sha matches.

Valid cache names: `keeper-patterns` / `agent-context` / `auto-improvement` / `kb-embeddings` / `code-embeddings`.

Returns:
```python
{
  "ok": bool,                          # True iff every cache succeeded
  "refreshed": {cache_name: result},   # per-cache return dict
  "failures": [cache_name, ...],
  "total_rows_written": int,
  "warnings": [str, ...],
  "skipped": [cache_name, ...],
  "selection_mode": "only" | "only-stale" | "skip" | "all"
}
```

### `detect_stale_caches()`

Sibling tool. Returns the list of cache names whose source has drifted, with NO refresh. Lightweight; powers the `only_stale=True` mode and useful for status displays.

## `/refresh-caches` slash command

User-invocable version of the same orchestrator. See `.claude/commands/refresh-caches.md` for the protocol.

## Anti-patterns

- **DON'T** loop `refresh_all_caches` on a timer — embedding refreshes are metered (OpenAI cost). Trust the 3-leg mirror + git hooks.
- **DON'T** pass `force=True` casually — re-embeds the ENTIRE corpus regardless of source_sha. Reserve for: model upgrade, schema migration, debugging.
- **DON'T** treat orphan rows as a blocker — keepers surface them as warnings; auto-purge would conflict with the "keepers surface, don't act" rule. Run `--refresh-kb-embeddings --force` if you need to clean.
- **DON'T** rely on this hook chain for cross-machine sync of `.claude/cache/*` SQLite files — those are gitignored per-user; refresh on the new machine.

## Cross-tree settle at integrate/cleanup (2026-05-30)

The structural caches (noc-graph + auto-improvement) are **Tier-1 shared** across the primary tree + every worktree (`.git/noctusai/cache/`, per `cache-portable-architecture.md`). A `noctus.dev.task_branch` **integrate**/**cleanup** is a *cross-tree handoff* — the same shared cache is written from two working trees (the worktree's pre-integrate commit + the primary's at-rest state). The stored `aggregate_source_sha` can briefly reflect a transient tree-state the at-rest primary tree doesn't match → `check_all_cache_freshness` flags noc-graph stale right after an otherwise-clean integrate.

`task_branch` closes this with `_settle_structural_caches()` at each success return: an **only-stale** (`force=False`, source-sha-guarded ⇒ no-op when coherent) + **best-effort** (a refresh failure NEVER fails the integrate/cleanup) in-process refresh of noc-graph + auto-improvement, surfaced as `cache_settle` in the result. The freshness keeper stays the net — this just settles the predictable cross-tree transient before control returns. NOT a leg-ordering bug (the pre-commit `auto_improvement.refresh()` only READS the ndjson; reordering legs is a no-op) and NOT a source-sha defect (`compute_source_sha` is deterministic). Symptom-targeted, not speculative.

## Deferred follow-ups (next session candidates)

1. **Embedding-model version stamp**: cache rows don't currently record the model name. If the seed lib upgrades `text-embedding-3-small` → `4-small`, dim mismatch errors only surface at retrieve time. A `model:` column per row + a startup check would auto-trigger force-refresh on model change.
2. **Orphan-row auto-purge tool**: a separate `noctus.dev.purge_orphan_cache_rows()` MCP tool that the keeper remediation messages point at. Keeps the "keepers surface, never act" rule clean while still offering one-command cleanup.
3. **Filesystem watcher** (heavy): daemon that watches the tracked surfaces + triggers refresh on save. OS-specific; defer until pull/checkout coverage proves insufficient.
4. **Backend portability** (Phase 1 SHIPPED 2026-05-26 evening, Phase 2+ deferred): the `CacheBackend` Protocol + default `SqliteCacheBackend` ship in `mcp/noctusai/tools/noctus/dev/cache_backend.py`. Phase 2+ (migrate the 5 cache modules to consume it; add PostgresBackend / SupabaseBackend) is on the roadmap — see `project-history/roadmaps/cache-backend-portability-2026-05.md` for triggers (T1–T5) + slice list. **The auto-freshness hooks above are sqlite-aware today; remote backends will need an equivalent-discipline section per `cache-locking-discipline.md`.**

## Composes with

- [`keeper-pattern-cache`](keeper-pattern-cache.md) — first cache; sets the 3-leg mirror contract this auto-freshness mechanism extends.
- [`kb-vector-search`](kb-vector-search.md), [`code-embeddings`](code-embeddings.md) — the two vector caches with the most expensive refreshes.
- [`agent-context-architecture`](agent-context-architecture.md), [`scoped-auto-improvement`](scoped-auto-improvement.md) — caches with high-severity freshness keepers.
- `/vector-status` — post-refresh health check.
- `/cost-report` — cost visibility for embeddings refreshes.

## History

- v4.0-beta (2026-05-26 morning): pre-commit hook leg 9b/9c/10 + per-cache freshness keepers were in place; assumed commit boundary covers freshness.
- v4.0-beta (2026-05-26 evening): user observation surfaced the gap — `git pull` + branch switch don't fire pre-commit, leaving caches stale. This pattern + the hooks codify the closure.
- 2026-05-30: user observation ("noc-graph shouldn't be stale — isn't it in the 8-way sync?") surfaced the cross-tree shared-cache transient at `task_branch` integrate/cleanup. Diagnosed (a leg-ordering hypothesis was disproven; source-sha is deterministic) → closed with the only-stale + best-effort `_settle_structural_caches()` settle leg above.
