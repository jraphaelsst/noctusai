---
description: Refresh all 5 keeper-mirror caches in one shot. Use after pulling many changes, switching branches, or warming up a fresh session. Composes the 3-leg mirror contract's eager + lazy legs into one explicit pass.
---

# /refresh-caches — orchestrated refresh of every keeper-mirror cache

You are running the **refresh-caches** protocol. The user invoked `/refresh-caches $ARGUMENTS`.

The 5 keeper-mirror caches (`keeper-patterns` / `agent-context` / `auto-improvement` / `kb-embeddings` / `code-embeddings`) each have their own refresh logic. This command runs all of them in one orchestrated sequence + reports per-cache outcome.

## When to use

- After `git pull` brought in many changes (post-merge hook also fires, but this is the manual equivalent).
- After a long out-of-band edit session.
- Start of a session that will lean heavily on vector search.
- After an embedding model upgrade (use `--force` to rebuild everything).
- When `--check-*-cache-freshness` keepers report drift you want to fix.

## Protocol

1. Call `noctus.dev.refresh_all_caches()` (MCP).
   - Optional `force=True` to rebuild even when source_sha matches.
   - Optional `skip=["code-embeddings"]` to omit a cache (useful when offline).

2. Report per-cache outcome:
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
