# scan-repetition-semantic — cross-product code repetition discovery

**What it is.** Semantic variant of `noctus.seed.scan_repetition` (which is grep-based). Walks the code-embeddings cache, finds cross-source semantic pairs above threshold, filters for absorb-to-seed candidates. Born v4.0-beta follow-up (F3).

## Why

`noctus.seed.scan_repetition` (grep-based) catches **literal** duplicates: same line, same function name, same identifiers. It MISSES the common case: two products implementing the same logic with different variable names + slightly different structure. That's where most absorb-to-seed candidates hide.

This module is the semantic variant: vector cosine catches "two functions named differently that compute the same thing."

## Filtering for absorb-to-seed

The cross-product recurrence loop (`code_recurrence_promote.scan`) finds ANY pair above threshold corpus-wide. This module is SCOPED to absorb-to-seed candidates:

| Pair type | Surfaces? | Why |
|---|---|---|
| Same product (`product:erp` ↔ `product:erp`) | No | Intra-product duplication is a different problem (seed-internal cleanup). |
| Cross-product (`product:erp` ↔ `product:therapy`) | Yes | Classic absorb candidate. |
| Seed ↔ product (`products/seed/` ↔ `product:erp`) | Yes, flagged `reimplementation_of_seed=True` | The product is reimplementing what seed already provides. Strongest absorb signal. |
| Both seed | No | Seed-internal duplication; different concern. |

## Threshold

Default **0.8** (vs. 0.7 for `code_recurrence_promote.scan`). Absorb-to-seed wants higher confidence — false absorptions are expensive to undo.

## Output

```python
{
  "ok": True,
  "threshold": 0.8,
  "total_candidates": N,
  "candidates": [
    {
      "a": {path, symbol_name, kind, path_kind},   # path_kind = 'seed' | 'product:<slug>' | 'shared'
      "b": {path, symbol_name, kind, path_kind},
      "score": float,
      "band": "strong" | "medium",
      "reimplementation_of_seed": bool,
      "cluster_id": int,                            # candidates with same path-kind pair group together
    },
    ...
  ],
  "clusters": {cluster_id: count},
  "reimplementation_count": int,
}
```

## Ordering

Reimplementation-of-seed first (highest absorb signal), then by band priority, then by score desc.

## When to use

- End of session: "what crossed the threshold this session that I should triage?"
- Before a sprint: build the absorb-to-seed backlog.
- Periodic sweep: detect drift FROM seed (products growing reimplementations).

## Composes with

- `code_recurrence_promote.scan` — same engine; this is the filtered + classified view.
- `noctus.seed.scan_repetition` — the original grep-based sibling.
- [`code-embeddings`](code-embeddings.md) — corpus + chunks.
- [`code-recurrence-baseline`](code-recurrence-baseline.md) — ratify reviewed absorb candidates so the next scan filters them out.
