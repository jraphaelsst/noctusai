---
description: Analyze project-history/vector-costs.ndjson — total spend, per-namespace breakdown, recent activity. Use before/after large refresh ops.
---

# /cost-report — vector platform spend analysis

You are running the **cost-report** protocol. The user invoked `/cost-report $ARGUMENTS`.

The `project-history/vector-costs.ndjson` ledger records every refresh-batch that consumed OpenAI API tokens. This command surfaces total spend + per-namespace breakdown + recent activity so the architect can reason about cost-vs-value.

## Protocol

1. **Read the ledger** — `project-history/vector-costs.ndjson`. Each row:
   ```
   {ts, namespace, model, provider, doc_count, chunk_count,
    estimated_tokens, estimated_cost_usd, source_ref}
   ```

2. **Compute aggregates**:
   - **Lifetime total**: sum `estimated_cost_usd` across all rows.
   - **Per-namespace**: sum + last-refresh-ts per namespace.
   - **Per-day**: sum per `ts[:10]` (calendar day) for the last 7 days.

3. **Surface findings**:
   - Largest single batch (often a full corpus refresh; expected on cold start).
   - Smallest non-trivial batch (often the opt-in `embed_text(namespace=...)` callers — kb_recurrence_radar, codification_radar).
   - Any namespace not seen in N days (suggests it's been static or unused).

4. **Compare to estimates** — if the user has a budget target, compare against it. The empirical rule from the 2026-05-26 verify pass: estimates can be 6× lower than reality due to chunking expansion. Report the empirical chunks-per-doc ratio:
   ```
   kb-embeddings:    ~14 chunks/doc  (empirical)
   code-embeddings:  ~7 chunks/file  (empirical)
   ```

## Output shape

```
┌─ Vector cost report ──────────────────────────────────┐
│  Lifetime spend: $<X.XXX>                              │
│  Total batches:  <N>                                   │
│  Tokens consumed: <N,NNN,NNN>                          │
└───────────────────────────────────────────────────────┘

Per-namespace:
  kb-embeddings        $<X.XXX>   last refresh <date>   <N> batches
  code-embeddings      $<X.XXX>   last refresh <date>   <N> batches
  kb_recurrence_radar  $<X.XXXX>  last embed   <date>   <N> calls
  codification_radar   $<X.XXXX>  last embed   <date>   <N> calls

Largest batch: <namespace> on <date>, $<X>, <N> chunks
Most recent:   <namespace> on <date>, $<X>

Per-day (last 7):
  <date>: $<X.XXX>
  ...

Estimate calibration:
  kb-embeddings:   <empirical ratio>  vs theoretical <ratio>
  code-embeddings: <empirical ratio>  vs theoretical <ratio>
```

## When to use

- End of session: how much did I spend?
- Before a planned refresh: estimate vs. ledger empirical ratio = more honest forecast.
- When deciding whether to add opt-in cost-attribution to a new caller (`vectorize.embed_text(namespace=...)`).
- Audit / billing reconciliation.

## Anti-patterns

- DON'T treat cost as the only metric — `vector_status` covers freshness + health.
- DON'T commit a cost-attribution change to `vectorize.embed_text` without verifying via `/cost-report` that the new namespace shows up in the ledger.

## Composes with

- `KB § CONTEXT/PATTERNS/common/vector-cost-tracking.md`
- `/vector-status` (broader health view; this is the spend slice)
- `KB § CONTEXT/PATTERNS/common/vector-calibration.md` (reasoning-driven calibration may suggest threshold changes to reduce cost)
