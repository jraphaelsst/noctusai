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

## Slice scores — per-agent / per-model quality history

`log_completion(..., score={...}, engineer_return="...")` also appends a row to `slice-scores.ndjson` (append-only, on `origin/ledgers` like the other ledgers) so the trend of each (agent, model) pair is readable over time.

**Rubric `RUBRIC_V1`** (each criterion scored 0-4; `q_weighted = sum(weight*q)`, null if any criterion is null): Q1 correctness .25 · Q2 design .20 · Q3 tests .15 · Q4 maintainability .15 · Q5 security .10 · Q6 methodology .05 · Q7 integration-rework .10. A weight change ships as `RUBRIC_V2`; rows keep their `rubric_version`, never compare across versions.

**Row**: `ts, slug, branch, sha, agent, model, planner_model, rubric_version, q{Q1..Q7}, q_weighted, tokens, tool_uses, wall_s_measured, wall_s_self_reported, first_pass, rework_commits, rework_severity{blocker,major,minor}, scope_changes, drifts[], improvements[] ({text,target,ai_ts}), notes`.
- `wall_s_measured` is ONLY the harness FINAL-notification `duration_ms`; an interim notification is not a duration. `wall_s_self_reported` is the engineer's own claim (kept to measure its error).
- `scope_changes` = owner changes mid-flight; they are NOT rework and never lower Q7.
- Validation: q within 0-4 or null, agent and model non-empty, no PII in any field.

**Superseding**: the ledger is append-only; to correct a row append a new one with the same slug+sha (note `supersedes`) — `agent_metrics` keeps the latest per slug+sha. `publish=False` spools without pushing.

**`engineer_return=`**: linted with `engineer_output_linter.lint_return`; a missing footer returns `{ok: False, refused: "missing-footer"}` and writes nothing. Each `drift-found:` / `scoped-improvement:` bullet becomes one `auto_improvement.log_entry` (agent, kind drift|improvement, `resolve_when="manual:engineer-footer triage"`); the returned ts is stored in `ai_ts` so a score row links to its triage entries.

**Reading the trend**: `noctus.team.agent_metrics` (`name='*'` for all, `by_week=True` to bucket) groups by (agent, model): `n`, `mean_q_weighted`, `first_pass_yield`, `rework_rate` (blocker 3 / major 2 / minor 1, per slice), `tokens_per_accepted_slice`, `cost_usd_est`, `self_estimate_error_ratio` (self-reported / measured; >1 = overstates), `top_drifts`. Cost is an ESTIMATE: tokens are stored as one total, so a 90/10 in/out split is assumed (Opus 5.5 $4/$20, Sonnet 5.5 $2/$10 per MTok, `PRICES`). Read the trend over weeks, not single rows: n<5 per group is anecdote.

**Dashboard**: `noctus.team.dashboard` composes this rollup (read-only) as `slice_scores` — the all-agents groups (with `cost_note`) plus `by_week` (the weekly-bucketed groups); a failing slice lands in `errors[]`, never raises.

**Integrate gate (measured slices only)**: `noctus.dev.task_branch action=integrate` REFUSES (`status=blocked`, `refused="slice_unscored"`) a `feat/<slug>` whose branch-tree pointer names a dispatched engineer (any pointer `agent` other than `self-branch`/`tech-lead`/`orchestrator`) and that has no row in `slice-scores.ndjson` (read via `_ledger_store`, matched on `slug` or `branch`). The result carries `unscored[]` and the exact `log_completion_calls` to make. A train checks EACH rider, not just the train branch. A missing pointer is NOT an exemption (unknown author = engineer); an unreadable ledger blocks (`slice_scores_unreadable`); only an injected test runner (no pointer store) skips. Tech-lead inline work is exempt via the pointer agent, no extra ceremony. Escape: `accept_unscored="<reason>"` (>=10 chars; CLI `--task-branch-accept-unscored`), recorded as `accepted_unscored`. (Distinct from `accept_unmeasured`, which waives timed-out merged-tip gates.) Backstop keeper `check_engineer_slice_scored` (`--check-engineer-slice-scored`): landed engineer pointers (claimed >= 2026-11-04) with no score row; blocks only the owning session, warns for peers. Sibling keeper `check_guard_hooks_registered`: every `scripts/hooks/claude-guard-*.py` must be named by a hook `command` in `.claude/settings.json` (an unregistered guard is a silent no-op).
