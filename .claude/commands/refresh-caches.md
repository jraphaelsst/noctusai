---
description: Refresh all 5 keeper-mirror caches in one shot. Use after pulling many changes, switching branches, or warming up a fresh session. Composes the 3-leg mirror contract's eager + lazy legs into one explicit pass.
---

# /refresh-caches — orchestrated refresh of every keeper-mirror cache

You are running the **refresh-caches** protocol. The user invoked `/refresh-caches $ARGUMENTS`.

The 5 keeper-mirror caches (`keeper-patterns` / `agent-context` / `auto-improvement` / `kb-embeddings` / `code-embeddings`) each have their own refresh logic. This command runs all of them in one orchestrated sequence + reports per-cache outcome.

## When to use which mode

| Scenario | Recommended mode |
|---|---|
| Start of session, want fresh state | `only_stale=True` (default; touches nothing if clean) |
| Just pulled / branch-switched (hooks should've fired, but verify) | `only_stale=True` |
| Specific drift surfaced by keeper | `only=["<name>"]` |
| Offline / no OpenAI key | `skip=["kb-embeddings","code-embeddings"]` |
| Model upgrade / schema migration | `only=["<name>"], force=True` |
| Audit "are all 5 actually in-sync?" | `only_stale=True` first; if empty, you're clean |

## Protocol

1. **Default — refresh only what's stale**: call `noctus.dev.refresh_all_caches(only_stale=True)`. This pre-checks freshness keepers and refreshes ONLY caches whose source has drifted. Zero work on clean caches.
2. **Specified**: `noctus.dev.refresh_all_caches(only=["kb-embeddings"])` — refresh ONLY the listed caches. Most explicit; use when you know which caches need attention.
3. **Skip-mode**: `noctus.dev.refresh_all_caches(skip=["code-embeddings"])` — refresh all except listed (useful when offline; code corpus is the heaviest).
4. **Full**: `noctus.dev.refresh_all_caches()` — refresh all 5; each cache's source_sha guard still skips in-sync content, so this is a "walk to verify" pass.
5. **Force**: pair any of the above with `force=True` to rebuild even when source_sha matches. RESERVED for: model upgrade, schema migration, debug.

Report per-cache outcome:
   ```
   keeper-patterns:   ✓ rebuilt / in-sync
   agent-context:     ✓ rebuilt / in-sync
   auto-improvement:  ✓ rebuilt / in-sync
   kb-embeddings:     ✓ rebuilt N chunks / in-sync
   code-embeddings:   ✓ rebuilt N chunks / in-sync
   ```

3. If failures list is non-empty, surface each with the error string + the suggested remediation (usually `--refresh-<cache>` standalone with `--force`).

4. If `total_rows_written > 0` AND `OPENAI_API_KEY` was used, mention the cost via `/cost-report` for visibility.

## What this does NOT do

- Does NOT call OpenAI when no API key is configured — embeddings caches degrade silently (per their own contract).
- Does NOT promote `warning`-severity issues to errors — all 5 caches are advisory.
- Does NOT purge orphan rows beyond what each cache does internally; orphan rows surface via `check_kb_vector_canonical` / `check_code_embeddings_cache_freshness`.

## Composes with

- `KB § CONTEXT/PATTERNS/common/cache-auto-freshness.md` (this command's umbrella pattern)
- Pre-commit hook legs 9b/9c/10 (per-cache auto-refresh on staged changes)
- `post-merge` + `post-checkout` git hooks (automatic refresh after pull / branch switch)
- `/vector-status` (post-refresh sanity check)
- `/cost-report` (cost visibility for the refresh batch)

## Anti-patterns

- DON'T loop this command on a timer. Refreshes are metered (OpenAI cost on embeddings caches). Trust the 3-leg mirror contract.
- DON'T pass `force=True` casually. Force re-embeds EVERYTHING — significant cost on the embeddings caches.
