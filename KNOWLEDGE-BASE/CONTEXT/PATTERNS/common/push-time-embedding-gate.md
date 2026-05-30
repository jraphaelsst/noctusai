# Cache-refresh universality — every boundary refreshes every cache whose source changed

> **v4.1 rule (2026-05-30 — refines v4.0):** every cache-freshness boundary
> (pre-commit / post-merge / post-checkout / pre-push) refreshes every cache
> **whose source files actually changed in that boundary's scope**. Coverage is
> universal (no boundary is skipped); *work* is gated by relevance. A delete-only
> or no-source push refreshes nothing. Correctness is backstopped by
> `check_all_cache_freshness` (8-way-sync, pre-commit) — any residual staleness
> surfaces on the next commit, so "no stale cache at any moment" still holds.
>
> **Why v4.1 (cost ≠ time):** v4.0 made pre-push refresh ALL caches
> *unconditionally* — the lone outlier (pre-commit / post-merge / post-checkout
> already gated on changed sources). v4.0's defence was "cost is near-zero
> because `source_sha` skips unchanged chunks" — TRUE for OpenAI **$**, but the
> refresh still **enumerated + hashed every source file and rebuilt noc-graph
> (~5s) on every push**, so a delete-only or hook-only push paid a 30-60s
> WALL-CLOCK tax for zero content change. v4.1 closes that by gating pre-push on
> the pushed range's changed files — same shape as the other three boundaries.
> A cache only skips when ITS sources didn't change, so it can't go stale from
> that push; the keeper catches anything missed.

This file's old title was "Push-time embedding-freshness gate." It documented
a mid-day decision to move kb/code embedding refresh from per-commit to
per-push only (to amortize the OpenAI cost across many small commits). That
decision was REVERSED later the same day after the memory-embeddings + corpus-
embeddings caches landed. New rule: every cache refreshes at every boundary.

## The reasoning behind the reversal

**Why the push-only rule felt right at first:**
- Embedding every commit re-embeds chunks that may end up unchanged at the
  final push state — wasteful round-trips, ~$0.01-0.05 per PR.
- Push is the natural batching unit.

**Why it turned out wrong:**
- A stale cache at ANY moment is a real correctness gap for the methodology
  layer. An agent that runs `noctus.dev.kb_search` between commits and gets a
  stale answer makes a decision on stale information. The waste was real but
  smaller than that risk.
- The 7th cache (memory) lives OUT of repo. There's no commit boundary for
  it at all — it must refresh on something else. If pre-commit doesn't fire
  for any of the 4 vector caches, memory has no other natural anchor either.
- Cost is not actually high in steady state — `kb-embeddings` and friends
  use per-file `source_sha` guards; only CHANGED docs re-embed. The "many
  commits re-embed unchanged chunks" worry doesn't bite because unchanged
  chunks skip.

## The current rule

Every boundary refreshes every cache:

| Boundary | What it refreshes |
|---|---|
| **pre-commit** | All 4 vector caches IF their source surface was staged + memory-embeddings always-attempt (out-of-repo) + 3 row caches IF their source was staged |
| **post-merge** | All 4 vector caches IF a source file changed in the merge + memory-embeddings always-attempt + 3 row caches IF their source changed |
| **post-checkout** | Same as post-merge (branch switch is structurally similar) |
| **pre-push** | Each cache IF its source changed in the pushed range (`remote_oid..local_oid` across all non-delete refs): kb/corpus ← `*.md`, code ← `*.py`, keeper ← `compliance.py`, agent-context ← `.claude/agents/`, auto-improvement ← `auto-improvement.ndjson`, noc-graph ← code/KB/`.claude`. **Delete-only / no-source push → skip all.** memory (out-of-repo) only under `NOCTUS_FORCE_EMBED_REFRESH=1` (it anchors on post-merge/post-checkout). |

Per-file `source_sha` skip bounds the **cost** (unchanged files don't re-embed);
the v4.1 changed-files gate bounds the **time** (a push that touches none of a
cache's sources doesn't even enumerate/hash them or rebuild noc-graph).

## Bypass / override

- `NOCTUS_SKIP_EMBED_REFRESH=1 git push` — skip the pre-push refresh entirely
  (CI smoke / `.env`-less env).
- `NOCTUS_FORCE_EMBED_REFRESH=1 git push` — force the full v4.0
  belt-and-suspenders pass (refresh all 8 regardless of changed files) — the
  escape hatch if you ever suspect a missed source signal.
- The pre-commit / post-merge / post-checkout refreshes fire on their source
  signal as before (mechanical + fast; no env bypass).

## Properties

- **Soft-fail** on missing API key / unreachable provider — vector search is
  enrichment, not load-bearing. The refresh logs the skip + the boundary
  proceeds. Hard-block belongs upstream in CI (`--check-kb-vector-canonical`).
- **Idempotent.** Per-file `source_sha` guard makes every refresh a no-op for
  unchanged content. Running 3 times in a row costs ~0ms per cache.
- **Cost-bounded.** Steady state has near-zero embed spend — only changed
  chunks re-embed.

## Composes with

- `KB § PATTERNS/common/cache-auto-freshness.md` — the umbrella.
- `KB § PATTERNS/common/kb-vector-search.md` / `code-embeddings.md` /
  `memory-embeddings.md` / `corpus-embeddings.md` — the 4 vector caches.
- `KB § PATTERNS/common/keeper-pattern-cache.md` / `agent-context-architecture.md` /
  `scoped-auto-improvement.md` — the 3 row caches.
- `KB § PATTERNS/devops/ci-embedding-cache-gate.md` — CI-side hard-fail backstop.

## History note

This doc was originally `push-time-embedding-gate.md` (codified earlier
2026-05-27). The push-only rule held for a few hours before being reversed
when the memory + corpus caches landed and the always-fresh-everywhere shape
proved cleaner. Title kept for INDEX continuity; content rewritten to
reflect current rule. The reversal itself is a methodology learning —
documented at `feedback_universal-cache-refresh.md` in memory.
