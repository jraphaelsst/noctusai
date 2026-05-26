# Unified query — single semantic search across multiple keeper-mirror caches

**What it is.** A composition tool: one query, fanned out across `kb-embeddings` + `code-embeddings` + `auto-improvement` (via `kb_recurrence_radar`), results merged + normalized + ranked into a single list with `source` labeled per hit. Born v4.0-beta follow-up (F2).

## Why

Architects asking "what do we know about X?" currently fan out across 3 separate tools:
- `noctus.dev.kb_search` — docs corpus
- `noctus.dev.code_search` — code corpus
- `noctus.dev.kb_recurrence_radar` — open auto-improvement entries

Then mentally merge + re-rank. This module mechanizes the merge so the caller sees ONE list.

## Why not just three separate calls

Each cache returns its own score distribution. A naive top-K-from-each pass returns 3K results which the caller still has to merge. `unified_query`:
1. Calls each requested cache with `per_source_k` (default 5).
2. Normalizes scores onto a comparable [0, 1] scale.
3. Merges + sorts by normalized score desc.
4. Dedupes identical summaries.
5. Returns top_k (default 10) with `source` labeled.

## API

```python
unified_query.query(
    text: str,
    top_k: int = 10,
    sources: list[str] | None = None,    # subset of {kb-embeddings, code-embeddings, auto-improvement}
    per_source_k: int = 5,
    min_score: float = 0.0,
) -> dict
```

Returns:

```python
{
  "ok": bool,
  "query": str,
  "hits": [
    {
      "source": "kb-embeddings" | "code-embeddings" | "auto-improvement",
      "score": float,          # normalized [0,1]
      "raw_score": float,
      "summary": str,          # short label (path / target / etc)
      "ref": dict,             # source's full row
    },
    ...
  ],
  "by_source": {source: hit_count},
  "warnings": [str],           # graceful-degrade record per failed source
}
```

## Graceful degradation

A source that errors out (provider unreachable, cache missing) gets logged in `warnings:` and skipped. Other sources still return — partial result better than no result for a meta-query.

## When to use

- Onboarding: "what does noc know about <surface>?" — one call, three perspectives.
- Pre-authoring: "before I write a new module, what exists semantically near this surface?"
- Triage: an issue surfaced — pull docs + code + open improvement entries in one go.

## When NOT to use

- Direct named lookup → use the source-specific tool (`kb_search` / `code_search` / `auto_improvement.query`).
- Cost-sensitive batch queries → 3× the per-source-k cost; don't loop.

## Composes with

- `kb_embeddings.search`, `code_embeddings.search`, `kb_recurrence_radar.consult` — the three feeders.
- [`kb-vector-search`](kb-vector-search.md), [`code-embeddings`](code-embeddings.md), [`kb-recurrence-radar`](kb-recurrence-radar.md) — the patterns each feeder ships under.
- `/cost-report` — every fan-out is a small embed call; track via `vectorize.embed_text(namespace="unified_query")` if instrumented (future).
