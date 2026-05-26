# Dispatch token log — manual per-dispatch budget tracking

**What it is.** A manual logging path for tracking per-dispatch token consumption + duration + outcome. The architect logs each completed dispatch; trend analysis follows. Born v4.0-beta follow-up (F11).

## Why "manual"?

Claude Code's harness does not expose dispatch lifecycle hooks. Automatic per-dispatch instrumentation requires SDK access we don't currently have. The manual path ships the data shape + analysis tools now; an automatic backend can swap in later when the harness exposes hooks.

## What gets logged

```python
{
  "ts": "...",
  "slug": "w2-e3-code-embeddings",
  "agent": "backend-engineer",
  "duration_minutes": 18.5,
  "estimated_tokens": 145000,
  "outcome": "landed" | "drift-found" | "failed" | "escalated",
  "notes": "..."
}
```

Stored at `project-history/dispatch-budget.ndjson` (committed; trend history is shared methodology signal).

## API

```python
dispatch_token_log.log_completion(
    slug, agent, duration_minutes,
    estimated_tokens=None, outcome="landed", notes=None,
) -> dict

dispatch_token_log.summary(agent=None, since=None) -> dict
```

Summary returns: `total_dispatches`, `by_outcome`, `by_agent {dispatches, avg_minutes, avg_tokens}`, `total_estimated_tokens`, `landed_rate`.

## When to log

After each dispatched-engineer return:
1. Note wall-clock duration (architect-observed).
2. Estimate tokens (sum of brief + return + any back-and-forth).
3. Classify outcome (landed / drift-found / failed / escalated).
4. Call `log_completion(...)`.

## When to read

- End-of-session retrospective: "how many tokens did dispatch cost this session?"
- Per-agent tuning: "is backend-engineer taking too long on small slices?"
- Trend: "is the landed_rate going up or down?"

## Composes with

- `dispatch_engineer_tuning` (KB pattern — tune brief shape based on observed costs).
- [`engineer-brief-compose`](#) — the upstream tool; sibling instrumentation.
- `/cost-report` — vector spend; this is dispatch labor.

## Anti-patterns

- **DON'T** skip logging because "I'll remember." You won't; the trend is the value.
- **DON'T** over-estimate tokens — best honest guess > inflated number.
- **DON'T** wait for the harness auto-hook. Manual logs starting now build the dataset.
