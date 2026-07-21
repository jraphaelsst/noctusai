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

## Branch-pointer auto-heal (the flip-before-merge backstop)

The discipline is: an engineer flips their branch-tree pointer `on_going → shipped` **before** merging ([[branch-tree-tracking]]). When they forget, the global branch map keeps showing phantom in-flight work that mis-routes a peer's collision decision. The sweep is the **backstop**: it flips any `on_going` pointer whose branch is already integrated into `origin/dev` → `shipped`.

"Already integrated" = the branch still exists AND is merged (SHA-ancestry ∨ every commit cherry-picked/squashed in — the shared `_worktree_staleness.is_merged` predicate), OR the branch is gone (cleaned up post-integrate) AND its recorded commit is an ancestor of `origin/dev`. A branch that's gone with an *unreachable* commit is left `on_going` — never a silent false-heal (we can't prove it landed). Each flip is written `push_dev=False`; the existing ledger-delivery leg pushes them in **one** FF commit (the mirror ledger is in `_LEDGER_PATHS` so canonical+mirror ship together — never a half-committed mirror). Runs by default; `heal_pointers=False` disables it. This is the discipline↔backstop pair: the engineer flip is compliance-by-construction, the auto-heal is the safety net, and `is_merged` is the shared predicate both `cleanup_stale_worktrees` and this pass read.

## API

```python
session_end_sweep.sweep(deliver_ledgers=True, heal_pointers=True) -> dict   # both False = survey-only
session_end_sweep.deliver_trailing_ledgers(repo_root) -> dict
session_end_sweep._autoheal_branch_pointers(repo_root) -> dict  # {healed, skipped_unproven, errors}
```

## Composes with

- `task_branch action=cleanup` — the actual cleanup primitive.
- `orphan_branch_sweeper` — the local-branch view; combined here.
- `mole` — the broader hygiene scanner.

## When to use

- End of working session.
- Before extended time-away (mark state explicit).
- Before a release tag (verify clean state).
