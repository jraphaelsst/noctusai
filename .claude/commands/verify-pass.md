---
description: Scaffold a verify-pass for any new infra slice — Pass-A (free, no LLM) recipe builder + Pass-B (live OpenAI) cost estimator + result-aggregation template.
---

# /verify-pass — verify-pending pass scaffolding

You are running the **verify-pass** protocol. The user invoked `/verify-pass $ARGUMENTS`.

Tests-green ≠ verified-in-production. This command scaffolds the **verification phase** for any new infra slice: per-slice recipes (Pass A free / Pass B OpenAI), cost estimation BEFORE running, result aggregation as the runs complete. Born from the 2026-05-26 automation-orchestration roadmap close.

## Protocol

1. **Identify slices** to verify. Inputs:
   - `--from-roadmap <slug>` — read `project-history/roadmaps/closed/<slug>.md` (or active), extract slices marked `VERIFY-PENDING`.
   - `--from-commits <N>` — read last N commit footers for `s4-keeper` entries.
   - `--manual <module>...` — explicit module list.

2. **Classify each slice** into Pass A or Pass B:
   - **Pass A (free)**: pure-python / pure-ledger; no LLM call required.
     Examples: `vector_calibration`, `kb_baseline`, `code_recurrence_promote` (after the cache exists), `code_baseline`.
   - **Pass B (OpenAI $)**: requires `OPENAI_API_KEY` configured + embed calls.
     Examples: `kb_embeddings.refresh`, `code_embeddings.refresh`, `codification_radar.cluster` (embeds open entries), `kb_recurrence_radar.consult`.

3. **Estimate Pass B cost** — use `/cost-report` empirical chunks/doc ratios:
   ```
   kb-embeddings:   docs × 14 chunks × ~450 tokens × $0.02/M = $<X>
   code-embeddings: files × 7 chunks × ~1500 tokens × $0.02/M = $<X>
   radar/consult:   entries × ~500 tokens × $0.02/M = $<X>
   ```
   Surface to user for go/no-go.

4. **Pass A — author per-slice scripts** under `/tmp/verify_<slice>.py`. Each:
   - Imports the module
   - Monkey-patches `LEDGER_PATH` / `BASELINE_DIR` / `_load_*` to tmp
   - Runs the slice's MCP-tool entrypoint
   - Asserts return contract (`{ok: True, ...}` + specific shape)
   - Prints PASS / FAIL with key numbers

5. **Pass B — author per-slice scripts** that:
   - Load `.env` via `python-dotenv`
   - Call `configure_llm(LLMConfig(key_provider=...))`
   - Run the live refresh / cluster / consult
   - Assert: rows landed in cache OR new line in `vector-costs.ndjson` OR ranked hits returned

6. **Spawn in parallel** via `run_in_background=True` Bash calls. Don't idle-poll (per `KB § PATTERNS/common/dont-block-on-background.md`). Schedule a `ScheduleWakeup` fallback heartbeat (1200s) in case a task stalls silently.

7. **Aggregate results** as notifications fire. Append to a verify-log table in the relevant closed-roadmap doc or as a sibling `verify-log-YYYY-MM-DD.md`.

8. **Commit + push** with the verify-log update + any cost-ledger rows that landed.

## Output shape

```
┌─ /verify-pass — automation-orchestration-2026-05 ─────┐
│ Pass A (free, N=4):                                    │
│   ✅ W2-E7 vector_calibration   <recipe ref>           │
│   ✅ W2-E6 kb_baseline          <recipe ref>           │
│   ✅ W3-E1 code_recurrence      <recipe ref>           │
│   ✅ W3-E2 code_baseline        <recipe ref>           │
│                                                         │
│ Pass B (OpenAI, N=4, est $0.04):                       │
│   ⏳ E5      vector_costs        <recipe ref>          │
│   ⏳ W2-E3'  kb_embeddings       <recipe ref>          │
│   ⏳ W2-E3'  code_embeddings     <recipe ref>          │
│   ⏳ W2-E4'  codification_radar  <recipe ref>          │
└────────────────────────────────────────────────────────┘
```

## When to use

- At the end of a roadmap close (the "VERIFY-PENDING" handoff).
- After shipping a new keeper-mirror cache.
- Before a deploy / pre-release smoke.

## Anti-patterns

- DON'T skip Pass A because "the tests passed." Tests are at the module level; verify exercises the MCP tool + the side effects.
- DON'T run Pass B without checking `vector-costs.ndjson` BEFORE and AFTER — that's the E5 cost-ledger gate.
- DON'T spawn all Pass B in serial — parallel via background tasks, per the dont-block rule.

## Composes with

- `KB § CONTEXT/PATTERNS/common/dont-block-on-background.md` (run pattern)
- `KB § CONTEXT/PATTERNS/common/roadmap-tracking.md` (verify-pending column)
- `/cost-report` (estimation calibration)
- `/vector-status` (pre-flight health)
