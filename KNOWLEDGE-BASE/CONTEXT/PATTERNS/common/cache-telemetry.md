# Cache telemetry — empirical "are agents using the caches?"

**What it is.** A lightweight opt-in telemetry layer for the 5 keeper-mirror caches. Caches call `cache_telemetry.record(cache, op, ...)` after each operation; entries land in `.claude/cache/cache-telemetry.ndjson` (gitignored). `summary()` aggregates. Born v4.0-beta follow-up (F6).

## Why

The 5 keeper-mirror caches (`keeper-patterns`, `agent-context`, `auto-improvement`, `kb-embeddings`, `code-embeddings`) were sized + featured for THEORETICAL demand. We don't actually know:

- Which caches are queried most?
- Which operations dominate (search vs. refresh vs. list)?
- Are there caches that get refreshed but never read?

Empirical telemetry surfaces the answer; future cost / sizing decisions become evidence-driven.

## Status — opt-in by design

Adding telemetry to a cache is a ONE-LINE addition after each operation:

```python
from . import cache_telemetry
cache_telemetry.record("kb-embeddings", "search", result_count=len(hits))
```

No contract change. Caches that don't opt in keep working. Caches that opt in pay a tiny append-to-ndjson cost.

## Ledger location

`.claude/cache/cache-telemetry.ndjson` — gitignored (high-volume, per-user noise; no value committing).

## Schema

```json
{
  "ts": "ISO-8601",
  "cache": "kb-embeddings",
  "operation": "search",
  "result_count": 5,
  "latency_ms": 12.3,
  "meta": {"top_k": 5, "query_hash": "..."}
}
```

All fields except `ts`, `cache`, `operation` are optional.

## API

```python
cache_telemetry.record(
    cache: str, operation: str,
    result_count: int | None = None,
    latency_ms: float | None = None,
    meta: dict | None = None,
) -> None    # silent on failure

cache_telemetry.summary(since=None, cache=None) -> dict
# Returns: {ok, total, by_cache, by_operation, by_cache_operation, latest_per_cache}
```

## Anti-patterns

- **DON'T** make telemetry blocking. If `record()` raises (disk full, permission denied), the cache operation MUST still succeed.
- **DON'T** add expensive fields. `latency_ms` is fine; embedding the full query / result set would blow up the ledger.
- **DON'T** commit the ledger to git. Personal-use signal, not shared methodology.

## Composes with

- All 5 keeper-mirror caches (as opt-in instrumentation point).
- `/cost-report` (vector spend) — orthogonal: cost-report tracks $; this tracks usage frequency.
- Future: `/cache-report` slash command surfacing the summary in human format.
