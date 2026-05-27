# Push-time embedding-freshness gate

> Embed at the push boundary, not on every commit. Codified v4.0 (2026-05-27).

## What changed

Until v4.0, the pre-commit hook refreshed `kb-embeddings` + `code-embeddings` caches on every commit that touched a KB doc or `.py`/`.ts`/`.tsx` file. The intent was "caches always fresh", but the cost in practice was:

- Many small commits during a slice → many round-trips to OpenAI for chunks that were eventually unchanged at the FINAL push state
- Cumulative wall-clock cost per slice ≈ `N_commits × M_chunks_changed × ~150ms`
- Per-PR cost ≈ `~$0.01-0.05` of wasted embed spend that the final push state would have batched as a single call

The shape is wrong: commits are CHEAP and granular; embeds are EXPENSIVE and benefit from batching. The push boundary is the right amortization unit.

## The gate

`scripts/hooks/pre-push` now refreshes BOTH `kb-embeddings` and `code-embeddings` immediately before the branch-protection logic runs. The pre-commit hook no longer touches embeddings (the relevant blocks are commented-out with a pointer to this doc; deleted at N=3 hook touch).

Properties:

- **Soft-fail.** If `OPENAI_API_KEY` is missing OR the provider is unreachable, refresh skips with a warning — the push still proceeds. Vector search is enrichment, not load-bearing; a stale cache surfaces drift via `check_kb_vector_canonical` / `check_code_embeddings_cache_freshness` next time those run, but doesn't block development.
- **Bypass.** `NOCTUS_SKIP_EMBED_REFRESH=1 git push` skips the refresh entirely. Use for CI smoke pushes or when a `.env`-less environment intentionally skips.
- **Idempotent.** `kbe.refresh()` / `cee.refresh()` are TRUNCATE+INSERT per-chunk; running twice is safe.

## Why soft-fail (not blocking)

A hard-block would refuse to push when no OpenAI key is configured — that breaks fork-PR contributors and any env without the platform secret. The block belongs upstream (CI's `--check-kb-vector-canonical` gate, which DOES hard-fail when the prod cache is unreachable). The pre-push hook's job is "best-effort freshness on the architect's machine"; the CI gate is the production-side guarantee.

## Composes with

- `KB § PATTERNS/common/kb-vector-search.md` — the kb-embeddings cache this refreshes.
- `KB § PATTERNS/common/code-embeddings.md` — the code-embeddings cache this refreshes.
- `KB § PATTERNS/devops/ci-embedding-cache-gate.md` — the CI-side hard-fail that backstops the soft-fail here.
- `KB § PATTERNS/common/cache-auto-freshness.md` — the umbrella of cache-freshness boundaries (pre-commit / post-merge / post-checkout / pre-push).
