# Product centroid drift — quantify "is product X drifting from seed?"

**What it is.** Computes each product's code centroid (avg vector across that product's code-embeddings chunks) vs. seed centroid. Distance = `1 - cosine`. Tracked over time via `project-history/product-drift.ndjson` (committed). Born v4.0-beta follow-up (F10).

## Why

"Is product X drifting from seed?" — today, no quick answer. Grep finds replicated lines; eyeball checks of MASTER-PROMPTs miss subtle drift. This module gives ONE comparable scalar per product per snapshot.

## Output

```python
{
  "ok": True,
  "ts": "...",
  "seed_chunks": N,
  "products": [
    {"slug": "erp", "chunk_count": N, "similarity_to_seed": 0.85, "distance_from_seed": 0.15},
    ...
  ],
  "most_drifted": "social-wiring"
}
```

Snapshot rows logged to `project-history/product-drift.ndjson` — read via `history(product?)` for trend tracking.

## Interpretation

- **distance_from_seed = 0**: identical centroid (impossible in practice; means the product IS seed).
- **distance_from_seed < 0.1**: very close to seed; healthy.
- **distance_from_seed > 0.3**: substantial divergence; check what the product has added/changed.

The ABSOLUTE values are corpus-dependent; what matters is the DELTA over time (drift direction).

## API

```python
product_centroid_drift.snapshot(record_to_ledger=True) -> dict
product_centroid_drift.history(product=None, limit=30) -> dict
```

## When to use

- Periodic (monthly?) sweep: "which products drifted most this period?"
- Before a seed-level refactor: "which products will be most affected?"
- After absorbing a recurrence to seed: "did distance shrink as expected?"

## Composes with

- [`code-embeddings`](code-embeddings.md) — the vector source.
- [`scan-repetition-semantic`](scan-repetition-semantic.md) — drift signal complements; this is corpus-scalar, that is per-pair.
- `noctus.seed.audit_drift` — existing seed-internal audit; this is the product-side view.

## Anti-patterns

- **DON'T** treat distance as a quality metric. High distance might mean legitimate product-specific work; the SIGNAL is in unexpected change over time, not absolute value.
- **DON'T** use this to gate releases. Advisory only.
