---
description: Show the state of the entire vector platform — 5 keeper-mirror caches + cost ledger + last refresh times. One-shot health overview.
---

# /vector-status — vector platform health

You are running the **vector-status** protocol. The user invoked `/vector-status $ARGUMENTS`.

The vector platform spans 5 keeper-mirror caches (`keeper-patterns`, `agent-context`, `auto-improvement`, `kb-embeddings`, `code-embeddings`) plus 2 derived ledgers (`vector-costs`, `vector-signals`, `vector-calibration`, `kb-baselines/`, `code-baselines/`). One command, one mental model of the whole stack.

## Protocol

1. **Embedding stack** — call `noctus.dev.vector_status()` (MCP). Report:
   - provider + model (`openai / text-embedding-3-small`)
   - storage engine (`sqlite-vec` vs `pure-python`)
   - registered caches + row counts

2. **Per-cache freshness** — for each of the 5 mirror caches, run its freshness keeper:
   - `--check-keeper-cache-freshness` (severity high — gates the gate)
   - `--check-agent-context-cache-freshness` (severity high)
   - `--check-auto-improvement-cache-freshness` (severity high)
   - `--check-kb-embeddings-cache-freshness` (severity warning)
   - `--check-code-embeddings-cache-freshness` (severity warning)

3. **Cost ledger snapshot** — via `noctus.dev.vector_costs_total` (it reads the tracked
   `project-history/vector-costs.ndjson` **plus** the not-yet-folded-in spool
   `project-history/.vector-costs-spool.ndjson`; reading the ndjson alone misses every row
   written since the last commit):
   - Total rows, lifetime spend, last refresh per namespace.
   - If `--detail` argument, list each namespace's last entry.

4. **Baselines** — `project-history/kb-baselines/` + `project-history/code-baselines/`:
   - Most-recent ratification timestamp + reason per surface.
   - `kb_baseline_diff()` / `code_baseline_diff()` summary if argument `--diff`.

5. **Calibration log** — `project-history/vector-calibration.ndjson`:
   - Last N=5 decisions (parameter + old→new + reasoning).

## Output shape

```
┌─ Vector platform ─────────────────────────────────────┐
│ Provider: openai · Model: text-embedding-3-small      │
│ Engine:   sqlite-vec (fast path)                      │
└───────────────────────────────────────────────────────┘

Caches:
  keeper-patterns      <rows>   sha=<src_sha:12>   ✓ fresh
  agent-context        <rows>   <agents>           ✓ fresh
  auto-improvement     <rows>   <entries>          ✓ fresh
  kb-embeddings        <rows>   <docs>             ✓ fresh
  code-embeddings      <rows>   <files>            ✓ fresh

Cost ledger:
  Total entries: <N>     Lifetime spend: $<X.XXXX>
  kb-embeddings:   last $<X> on <date>
  code-embeddings: last $<X> on <date>
  ...

Baselines:
  kb-baselines/:    <N> ratified, latest <id> on <date>
  code-baselines/:  <N> ratified, latest <id> on <date>

Recent calibration decisions: <last 5 rows>
```

## When to use

- Before a vector-heavy operation (`kb_search`, `code_search`, `kb_validate_owns_kb`) — confirm caches are fresh.
- After a long offline period — see what's stale before deciding to refresh.
- Cost-audit at end of session / week.
- Onboarding: shows the whole vector platform in one glance.

## Anti-patterns

- DON'T blindly trigger refresh on every stale signal — refresh is metered. Reason about cost first (see `KB § CONTEXT/PATTERNS/common/vector-calibration.md`).
- DON'T treat warning-severity freshness as a blocker — vector search is advisory.
