# Session-end sweep — manual cleanup orchestration

**What it is.** User-invoked end-of-session orchestration that surfaces every `.claude/worktrees/*` + every local branch diverged from `origin/dev` with a classification + suggestion. Born v4.0-beta follow-up (F8).

## Why "manual"?

The Claude Code harness does NOT expose a session-close hook. Automatic auto-salvage requires harness-side support that doesn't exist. This module ships the same logic as a user-invoked tool: run `/session-end` or `noctus.dev.session_end_sweep`, get the action list, act on it.

## What it surfaces

For each worktree at `.claude/worktrees/<slug>/`:

| Classification | Predicate | Suggestion |
|---|---|---|
| `safe-to-cleanup` | branch 0 ahead of origin/dev + worktree clean | Run `task_branch action=cleanup` to remove. |
| `uncommitted-work` | worktree has uncommitted changes | Review + commit / salvage before cleanup. |
| `ahead-of-dev` | branch ahead by N commits | Finish the slice or `task_branch action=integrate`. |
| `unknown` | couldn't determine state | Investigate manually. |

Also includes `orphan_branch_sweeper.scan()` output for completeness.

## Ledger

Every sweep writes a summary entry to `project-history/worktree-salvage.ndjson`:

```json
{
  "ts": "...",
  "kind": "session-end-sweep",
  "worktree_count": N,
  "safe_to_cleanup": [...slugs],
  "uncommitted": [...slugs],
  "ahead_of_dev": [...slugs]
}
```

## Ledger auto-delivery (2026-07-03)

After the survey + summary-log, the sweep **auto-delivers any trailing append-only ledger churn** from the primary `dev` checkout to `origin/dev` — the recurring `chore(cost-log)` commit (created by the pre-push embedding refresh, which git can't fold into the same push) plus any dirty ledger row (incl. the sweep-summary row just written). This is why a session ends **`local==remote`** with nothing that looks like stale/pending work.

Safe by construction — it reuses `commit_and_ff_push_ledger` (fetch → **divergence-guard** that REFUSES if any NON-ledger commit is ahead → rebase → FF-push, never force) and runs the push with `NOCTUS_SKIP_EMBED_REFRESH=1` + `NOCTUS_SKIP_COSTLOG_COMMIT=1` so it **cannot spawn new churn** (converges in one push). Guards: only acts when the primary checkout is on `dev` (else it'd rebase/push the wrong branch); best-effort (never raises); ledgers are `_LEDGER_PATHS` (vector-costs / auto-improvement / ledger / worktree-salvage / branch-tree). Disable with `deliver_ledgers=False`. Result under `ledger_delivery: {status, pushed, detail}`.

This is the by-construction close of the "auto-ledger appends a strand on the primary" recurrence (the perpetual `chore(cost-log)` "ahead by 1" that read as stale work).

## Why never auto-delete

Worktrees can carry uncommitted work even when their branch is integrated (architect made tweaks but didn't commit). Auto-delete would silently lose work. **Surface + suggest; never act.** (Ledger *delivery* above is the exception that proves the rule — it only ever FF-pushes append-only, union-merge, cache-exempt ledger rows, never task work.)

## API

```python
session_end_sweep.sweep(deliver_ledgers=True) -> dict   # deliver_ledgers=False = survey-only
session_end_sweep.deliver_trailing_ledgers(repo_root) -> dict
```

## Composes with

- `task_branch action=cleanup` — the actual cleanup primitive.
- `orphan_branch_sweeper` — the local-branch view; combined here.
- `mole` — the broader hygiene scanner.

## When to use

- End of working session.
- Before extended time-away (mark state explicit).
- Before a release tag (verify clean state).
