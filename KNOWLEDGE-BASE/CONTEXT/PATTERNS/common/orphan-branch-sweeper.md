# Orphan branch sweeper — classify + curate local branches

**What it is.** A read-only sweep of every local branch that classifies each by integration state + artifact presence, surfacing actionable suggestions (safe-to-delete / has-worktree / has-roadmap / unknown). Born v4.0-beta follow-up (F5).

## Why

Long-running sessions accumulate branches. Many are integrated + pushed to dev but the local branch lingers. Some are abandoned (engineer killed mid-flight). There's no curated view of "which branches are safe to clean up?"

## Classification

For each local branch (excluding `main` and `dev`):

| Classification | Predicate | Suggestion |
|---|---|---|
| `current` | branch is currently checked out | "don't delete from this session" |
| `integrated` | 0 commits ahead of `origin/dev` | "safe to delete" |
| `active-worktree` | live worktree exists at `.claude/worktrees/<leaf>/` | "finish work or use task_branch cleanup" |
| `stale-with-roadmap` | ahead of dev, no worktree, matching `project-history/roadmaps/<slug>*.md` | "resume work or close roadmap" |
| `stale-no-artifacts` | ahead of dev, no worktree, no roadmap | "review before deleting" |
| `unknown` | couldn't determine relationship to origin/dev | "investigate" |

## API

```python
orphan_branch_sweeper.scan(repo_root=None) -> dict
```

Returns:

```python
{
  "ok": True,
  "current_branch": str,
  "branches": [
    {
      "name": str,
      "ahead": int | None,
      "behind": int | None,
      "has_worktree": bool,
      "roadmap_path": str | None,
      "classification": <see above>,
      "suggestion": str,
    },
    ...
  ],
}
```

## Optional `delete_integrated`

```python
orphan_branch_sweeper.delete_integrated(dry_run=True) -> dict
```

Defaults to dry-run. Only deletes branches classified `integrated`. NEVER touches active-worktree / stale-with-roadmap / unknown.

## When to use

- End of session — "what can I clean up locally?"
- After a long-running feature branch ships — confirm all the feat/* are gone.
- Before tagging a release — clean local branch list = clean session state.

## Composes with

- `check_branch_orphan` (existing keeper) — same intent, less detailed classification. This is the read-only sweep + suggestion layer.
- `noctus.dev.task_branch cleanup` — handles active worktrees; this surfaces what's left after cleanup.
- [`roadmap-tracking`](roadmap-tracking.md) — `stale-with-roadmap` classification keys off the convention.
