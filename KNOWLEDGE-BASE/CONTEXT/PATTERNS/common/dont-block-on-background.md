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

## The `ScheduleWakeup` fallback heartbeat

A `<task-notification>` arrives when a background bash/agent completes (success OR failure). That covers the common case. **But there are silent-stall modes**: the task hangs on a network call, the process gets stuck in a syscall, the OS swaps it out, etc. Then no notification ever fires.

The escape hatch: schedule a **fallback heartbeat** via `ScheduleWakeup` when you spawn a long-running background task. If the task notification arrives first, the wakeup is moot (no extra action). If the task stalls silently, the wakeup re-invokes the session — diagnose, kill if needed, retry.

```python
# Spawn long-running background task.
Bash(... run_in_background=True)  # → task ID, will notify on completion

# Schedule fallback heartbeat — IGNORED if task notifies first.
ScheduleWakeup(
    delaySeconds=600,                 # generous; tune per expected task duration
    reason="B4 code-embeddings refresh; fallback if no completion in 10 min",
    prompt="Continue from where I left off — check status of <task_id>; "
           "if still running and not progressing for two checks, kill + diagnose.",
)
```

**Picking `delaySeconds`** (per the runtime guidance on cache windows):
- **60-270s**: stay in prompt cache; for actively polling fast-moving external state.
- **300-3600s**: pay one cache miss; for genuinely idle waits or fallback heartbeats on minute-scale tasks.
- **Default for fallback**: ~1200s (20 min). Long enough that natural notification wins for normal runs; short enough to recover from a silent stall.

**The prompt you pass back to yourself is literal** — the next session-invocation reads it as if the user typed it. Write it as a complete instruction (with task IDs, the expected check, the action on stall). The session has no memory of "I scheduled this" except via the prompt content.

### Symmetric to `<task-notification>`

| Trigger | Fires when | What you do |
|---|---|---|
| `<task-notification>` | Background task completes (success / failure) | Read output, integrate |
| `ScheduleWakeup` fallback | Time elapsed AND no task notification overrode it | Diagnose stall, kill + retry if needed |

The two together form the **complete escape from idle-polling**: notifications cover completion, wakeups cover stalls.

### Naming

Internally, this pattern composes with [`autonomous-operator-via-subagent`](../architect/autonomous-operator-via-subagent.md), which uses `ScheduleWakeup` for a different purpose (autonomous dispatch queue drain). Don't conflate the two:
- **Autonomous operator**: long-cadence (15min default) wakeup → spawn subagent → drain inbox.
- **Fallback heartbeat**: short fallback (10-20 min) wakeup → only acts if background task stalled.

Both use the same harness primitive (`ScheduleWakeup`), different intent.

## Composes with

- [`parallelization-first-orchestration`](../architect/parallelization-first-orchestration.md) — same principle at the agent-dispatch layer.
- [`branching-dispatch`](../architect/branching-dispatch.md) — multi-engineer wave pattern; this rule extends the same logic to mixed bash + foreground work.

## Anti-pattern catalog

- `TaskOutput(block=True, timeout=600000)` immediately after spawn, with no other foreground work queued.
- Polling with `Bash(sleep 30; check_status)` loops.
- Spawning ONE long background task when the workload could fan out across 3 independent shorter tasks.
