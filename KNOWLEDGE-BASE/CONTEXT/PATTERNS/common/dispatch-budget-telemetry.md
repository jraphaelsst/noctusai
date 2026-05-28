# Dispatch-budget telemetry

Per-dispatch token-consumed audit ledger — manual log path (auto-capture deferred).

## Why it exists

Every engineer dispatch burns tokens (input prompt + output). Without instrumentation cost
is invisible: no per-agent breakdown, no trend over time, no budget gate.
This pattern ships the **manual log path** (F11, roadmap `automation-orchestration-followup-2026-06.md`).
Auto-capture is deferred until the harness exposes dispatch lifecycle hooks.

## Architecture

- Durable source-of-truth: `project-history/dispatch-budget.ndjson` (committed, sibling of
  `auto-improvement.ndjson` + `vector-costs.ndjson`).
- One NDJSON line per engineer dispatch.
- `report()` + `summary()` aggregate on-the-fly (no secondary cache — ledger is small).
- MCP tools: `noctus.dev.dispatch_budget_log` / `dispatch_budget_report` / `dispatch_budget_summary`.
- CLI flags: `--dispatch-budget-log` / `--dispatch-budget-report` / `--dispatch-budget-summary`.
- Implementation: `mcp/noctusai/tools/noctus/dev/dispatch_budget.py`.

## NDJSON schema (one row per dispatch)

```json
{
  "ts":             "ISO-8601 UTC",
  "agent":          "backend-engineer | frontend-engineer | ...",
  "slug":           "feat/<branch-or-task-slug>",
  "input_tokens":   12345,
  "output_tokens":  3456,
  "total_tokens":   15801,
  "model":          "claude-sonnet-4-6 | claude-opus-4-7 | ...",
  "source_ref":     "session:2026-05-28 | null"
}
```

`total_tokens` is always derived as `input_tokens + output_tokens` at write time.

## Manual log path — when to call

The orchestrator calls `noctus.dev.dispatch_budget_log` **after** each engineer dispatch
completes, reading token counts from the engineer's task JSONL `usage` block
(visible in the agent's first-message `usage` response or the harness task log).

Typical call (MCP):
```
noctus.dev.dispatch_budget_log(
    agent="backend-engineer",
    slug="feat/r1-f11-dispatch-budget-telemetry",
    input_tokens=12345,
    output_tokens=3456,
    model="claude-sonnet-4-6",
    source_ref="session:2026-05-28",
)
```

CLI equivalent:
```
python mcp/noctusai/cli.py --dispatch-budget-log \
  --agent backend-engineer \
  --slug feat/r1-f11 \
  --input-tokens 12345 \
  --output-tokens 3456 \
  --model claude-sonnet-4-6 \
  --source-ref session:2026-05-28
```

## Report aggregation shape

`dispatch_budget_report(window_days=7)` → groups by `(agent, model)`:

```json
[
  {
    "agent": "backend-engineer",
    "model": "claude-sonnet-4-6",
    "dispatch_count": 4,
    "input_tokens_sum": 48000,
    "output_tokens_sum": 12000,
    "total_tokens_sum": 60000,
    "total_tokens_avg": 15000.0,
    "total_tokens_p95": 19200,
    "first_ts": "2026-05-27T10:00:00+00:00",
    "last_ts": "2026-05-28T09:30:00+00:00"
  }
]
```

`dispatch_budget_summary()` → same fields, no grouping, one aggregate dict.

## Auto-capture (deferred — F11 open question)

Auto-capture requires the harness to expose pre/post-dispatch lifecycle hooks that fire
with the task's token `usage` struct. Until those hooks land:

- Orchestrator MANUALLY calls `dispatch_budget_log` after each dispatch.
- Token counts are read from the engineer's task JSONL / first-message `usage` block.
- The roadmap records this as the F11 open question; the manual path ships today so
  telemetry accumulates from session start rather than waiting for automation.

When auto-capture lands, the NDJSON schema and MCP tools remain unchanged —
only the call site moves from orchestrator → harness hook.

## Composes with

- `vector-costs.ndjson` sibling pattern (`KB § PATTERNS/common/vector-cost-tracking.md`) —
  same NDJSON append shape, same ledger directory, orthogonal concern.
- `dispatch-engineer-tuning.md` (`KB § PATTERNS/architect/dispatch-engineer-tuning.md`) —
  the token-consumption data from this ledger feeds the tuning levers (L2 model choice,
  L5 tight briefs, L4 scoped verification).
- `auto-improvement.ndjson` (`KB § PATTERNS/common/scoped-auto-improvement.md`) —
  same commit-sibling durable surface pattern.
