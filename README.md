# ledgers — append-only project-history ledgers (orphan branch)

Written ONLY by git plumbing (`mcp/noctusai/tools/noctus/dev/_ledger_store.py`):
hash-object -> mktree -> commit-tree -> fast-forward push, retried on the race.
Never check this branch out, never force-push it, never delete it.

Seeded 2026-09-24 from origin/dev's `project-history/` copies. Until the dev
copies are deleted (roadmap `project-history/roadmaps/ledgers-off-dev-2026-09.md`,
deferred S4) every reader merges this branch with the dev copy.

Inspect: `noctus.dev.ledger_store action='status'` / `action='read' name=<file>`.
