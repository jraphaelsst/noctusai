# Vector Cost Tracking

## Summary

Generic platform tool that records OpenAI embedding API usage — tokens +
estimated USD — to a durable NDJSON ledger. Cache modules opt in by calling
`log_refresh_batch(...)` at the end of each refresh run. Provides MCP tools
and CLI flags so users can audit cumulative spend without logging into the
OpenAI dashboard.

## Why it exists

Every embedding API call has a cost. Without instrumentation, cost is invisible:
no per-namespace breakdown, no trend, no budget gate. This pattern provides:
- A committed ledger (`project-history/vector-costs.ndjson`) that survives
  context resets and session changes.
- Per-namespace reporting so "kb-embeddings" vs "code-embeddings" costs are
  attributed separately.
- A lightweight module that any cache layer can opt into with ~5 lines.

## Ledger schema

One NDJSON line per refresh batch:

```json
{
  "ts":                   "2026-05-26T14:32:00.123456+00:00",
  "namespace":            "kb-embeddings",
  "model":                "text-embedding-3-small",
  "provider":             "openai",
  "doc_count":            12,
  "chunk_count":          48,
  "estimated_tokens":     21600,
  "estimated_cost_usd":   0.000432,
  "source_ref":           "session:2026-05-26"
}
```

`source_ref` is free-form — typically `"session:YYYY-MM-DD"` or a project slug.

## Cost table (USD / 1M tokens)

| Model | Rate | Source |
|---|---|---|
| text-embedding-3-small | $0.02 | OpenAI pricing 2026-05-26 |
| text-embedding-3-large | $0.13 | OpenAI pricing 2026-05-26 |
| text-embedding-ada-002 | $0.10 | OpenAI pricing 2026-05-26 |

**Update cadence**: when OpenAI reprices, update `COST_PER_MILLION_TOKENS` in
`mcp/noctusai/tools/noctus/dev/vector_costs.py` AND this table in the same
commit (doc-code coherence rule).

## Token estimation

`estimate_tokens(text, model)` prefers `tiktoken` (cl100k_base encoding,
exact BPE count). Falls back to `len(text) // 4` when tiktoken is absent.
Both paths record the same schema; the fallback is accurate to ±20% for
English prose.

## API

Module: `mcp/noctusai/tools/noctus/dev/vector_costs.py`

### `log_refresh_batch(...)`

```python
log_refresh_batch(
    namespace="kb-embeddings",  # or "code-embeddings", etc.
    model="text-embedding-3-small",
    doc_count=len(refreshed),
    chunk_count=total_rows,
    estimated_tokens=estimated,
    # cost_estimate_usd=None → computed from cost table
    provider="openai",
    source_ref="session:2026-05-26",
)
```

Returns `{ok, path, row}`. Failures are logged as warnings, never raised
(cost tracking is advisory — never blocks a successful refresh).

### `estimate_tokens(text, model) -> int`

Tiktoken-first, `len // 4` fallback.

### `estimate_cost(tokens, model) -> float`

Table lookup × tokens / 1_000_000. Returns 0.0 for unknown models (warning
logged).

### `report(namespace?, since?, group_by?) -> list[dict]`

Aggregates the ledger by "day" | "week" | "month". Each bucket:
`{period, namespace, doc_count, chunk_count, estimated_tokens,
estimated_cost_usd, batch_count}`.

### `total(namespace?, since?) -> dict`

Quick sum: `{namespace, since, doc_count, chunk_count, estimated_tokens,
estimated_cost_usd, batch_count, first_ts, last_ts}`.

## MCP tools

| Tool | Purpose |
|---|---|
| `noctus.dev.vector_costs_log_batch` | Append a row (called by cache modules) |
| `noctus.dev.vector_costs_report` | Aggregate by period |
| `noctus.dev.vector_costs_total` | Quick total |

## CLI flags

```
python mcp/noctusai/cli.py --vector-costs-report [--namespace kb-embeddings] [--since 2026-05-01] [--group-by day]
python mcp/noctusai/cli.py --vector-costs-total [--namespace kb-embeddings] [--since 2026-05-01]
```

## Opting in (instrumentation recipe)

At the end of a `refresh()` function, AFTER all DB commits:

```python
if chunks_embedded > 0:
    try:
        from tools.noctus.dev import vector_costs as _vc
        _vc.log_refresh_batch(
            namespace="my-embeddings",
            model="text-embedding-3-small",
            doc_count=len(refreshed),
            chunk_count=chunks_embedded,
            estimated_tokens=chunks_embedded * (MAX_CHUNK_CHARS // 4),
            source_ref=f"session:{today}",
        )
    except Exception as _exc:
        logger.warning("vector_costs instrumentation failed: %s", _exc)
```

The try/except wrapper ensures cost tracking never propagates failures back
to the caller. Keep it additive — do not modify the existing refresh logic.

## Opt-in cost attribution from `vectorize.embed_text` (2026-05-26)

The original cost-ledger path required wrapping the `refresh()` call in
each cache module. That covered the BATCH refreshes (kb-embeddings,
code-embeddings) but missed direct `vectorize.embed_text()` callers
(kb_recurrence_radar, codification_radar) — they consumed OpenAI silently.

The fix (codified after the 2026-05-26 verify pass surfaced the gap):
`vectorize.embed_text` now accepts an OPTIONAL `namespace=` kwarg. When
provided, the successful embed logs to `vector-costs.ndjson` via
`log_refresh_batch(namespace, chunk_count=1)`:

```python
# vectorize.py
def embed_text(text: str, namespace: str | None = None) -> dict:
    ...  # do the embed
    if namespace:
        try:
            from . import vector_costs as _vc
            _vc.log_refresh_batch(
                namespace=namespace,                       # caller's attribution
                model=cfg.default_embedding_model,
                doc_count=1,
                chunk_count=1,
                estimated_tokens=max(1, len(text) // 4),
                provider=cfg.default_provider,
                source_ref=None,
            )
        except Exception:  # never block embed on logging failure
            pass
    return result
```

**Caller pattern**:
```python
# kb_recurrence_radar.py
result = vectorize.embed_text(text, namespace="kb_recurrence_radar")

# codification_radar.py
result = embed_text(description, namespace="codification_radar")
```

**Design choices**:
- **Opt-in, not opt-out**: generic callers (prototyping, debugging) don't
  spam the ledger. They get an unlabeled embed; the cost just doesn't show.
- **Per-call, not per-batch**: each `embed_text` produces ONE row. For
  high-volume callers, prefer a batch refresh pattern with one summary row.
- **Failure-tolerant**: logging errors never propagate to the embed result.

## Universality

This is a `common/` pattern — owned by no single agent; every agent inherits
via the `_AGENT_KB_UNOWNED_ALLOWLIST` in `compliance.py`. Any future cache
module (code-embeddings, conversation-embeddings, etc.) opts in with the
same recipe.

## Constraints

- The ledger is append-only; rows are never deleted or modified.
- The ledger is committed to the repo (not gitignored) so spend history
  persists across clones and session resets.
- Cost estimates are advisory (±20% on the fallback path). Real billing
  remains in the OpenAI dashboard.
