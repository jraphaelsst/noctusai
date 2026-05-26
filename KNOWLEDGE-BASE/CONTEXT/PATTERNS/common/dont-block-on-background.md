# Don't block on background tasks — keep working in parallel

**The rule.** When a background bash / agent / remote session is processing, the conversational session does NOT idle-poll. Queue more independent work, write docs, evaluate already-completed results, prep follow-ups. Composes with [`parallelization-first-orchestration`](../architect/parallelization-first-orchestration.md): same principle (max(branch_i) not sum) applied at the bash-task layer instead of the agent-dispatch layer.

## Why this exists

Wall-clock budget is real. Idle polling burns session budget for nothing. A 5-minute kb-embeddings refresh running in background while the foreground does NOTHING is a 5-minute hole in the session. The same 5 minutes can fit: more parallel tasks queued, doc authoring, evaluation of previously-completed work, fix-on-contact for drift surfaced earlier.

## The anti-pattern

```
1. Spawn background task X (will take 5 min).
2. Call TaskOutput(block=True, timeout=600000) immediately.
3. Produce no other output for 5 minutes.
4. Task notifies completion.
5. Continue.
```

Total session output across those 5 min: zero. Cache savings: zero. Other work that COULD have happened: lost.

## The right pattern

```
1. Spawn background task X (will take 5 min).
2. Spawn independent background task Y (parallel — also 3 min).
3. Foreground work that doesn't depend on X or Y:
   - Author the report document.
   - Run gates / sanity checks.
   - Prep follow-up code changes.
4. Background task notifications fire as they complete.
5. For each completion: evaluate output → integrate → queue follow-up if needed.
6. Consolidate when all complete.
```

Total session output across those 5 min: report drafted, gates run, follow-ups identified. Wall-clock: max(X, Y) instead of X + Y + idle.

## When blocking IS correct

- The ONLY useful next step genuinely depends on the running task's output (no parallelizable foreground work exists, no independent background work to queue).
- The task is so short (< 30s) that the overhead of context-switching to another task exceeds the wait.

For long-running tasks (> 60s), there's almost always parallel work available — at minimum, drafting the next-step document or running independent gates.

## Composes with

- [`parallelization-first-orchestration`](../architect/parallelization-first-orchestration.md) — same principle at the agent-dispatch layer.
- [`branching-dispatch`](../architect/branching-dispatch.md) — multi-engineer wave pattern; this rule extends the same logic to mixed bash + foreground work.

## Anti-pattern catalog

- `TaskOutput(block=True, timeout=600000)` immediately after spawn, with no other foreground work queued.
- Polling with `Bash(sleep 30; check_status)` loops.
- Spawning ONE long background task when the workload could fan out across 3 independent shorter tasks.
