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

## Why never auto-delete

Worktrees can carry uncommitted work even when their branch is integrated (architect made tweaks but didn't commit). Auto-delete would silently lose work. **Surface + suggest; never act.**

## API

```python
session_end_sweep.sweep() -> dict
```

## Composes with

- `task_branch action=cleanup` — the actual cleanup primitive.
- `orphan_branch_sweeper` — the local-branch view; combined here.
- `mole` — the broader hygiene scanner.

## When to use

- End of working session.
- Before extended time-away (mark state explicit).
- Before a release tag (verify clean state).
