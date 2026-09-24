# Ledger store — append-only ledgers live on the orphan `ledgers` branch

> **Rule.** Every append-only `project-history/*.ndjson` ledger a tool writes
> automatically lives on the orphan branch `origin/ledgers`, written by git
> plumbing through `_ledger_store` — never as a commit on `dev`.
> `project-history/ledger.ndjson` (the human project history) is the one ledger
> that STAYS on `dev`.

## Why

Owner decision, 2026-09-24 (project `gate-mechanisms`). Of 2378 commits on `dev`
since 2026-08-01, 963 (41%) were ledger chores — `chore(branch-pointer)` 465,
`chore(salvage)` 373, `chore(ledger)` 105, `chore(cost-log)` 78,
`chore(ship-consent)` 25. Each one:

- moved the `dev` tip and cancelled the in-flight CI run (`test.yml` is
  `cancel-in-progress`);
- raced every other ledger push ("cannot lock ref", non-fast-forward retries);
- committed on the PRIMARY checkout, which then diverged from `origin/dev` and
  blocked its sync;
- buried real history under metadata.

A ledger row is tracking metadata. It needs durability and one shared view; it
does not need a place on the integration branch.

## What moves (and what stays)

| Ledger | Writer | Writer flipped to the store |
|---|---|---|
| `auto-improvement.ndjson` | `noctus.dev.auto_improvement_log` · `_promote` · `_reconcile` · `codify_log` | **flipped** (S3 #1). Rewrites are `update(transform)`; the cache and its keeper hash the dual-read |
| `vector-costs.ndjson` · `vector-signals.ndjson` · `vector-calibration.ndjson` · `dispatch-budget.ndjson` · `absorptions.ndjson` | the pre-commit spool drain (`publish=False`, so no network inside a commit) · `dispatch_budget` · `dispatch_token_log` · `vector_calibration` · `absorption_tracking` | **flipped** (S3 #2). Pre-commit no longer stages `vector-costs.ndjson` |
| `worktree-salvage.ndjson` | `salvage_before_delete` · `session_end_sweep` · `_worktree_salvage` (mole / cleanup sweeps) | **flipped** (S3 #3). A record whose SHA is already on `origin/dev` is not written; `task_branch` cleanup writes none (it only deletes merged branches) and its dev-push leg is gone |
| `branch-tree.ndjson` | `noctus.dev.branch_pointer` | pending (S3 #4) |
| `ship-consent.ndjson` | `noctus.dev.ship_consent` | pending (S3 #5, last) |
| `ledger.ndjson` | `noctus.dev.history_record` | **never. It stays on `dev`** |
| `branch-tree.mirror.ndjson` | — | **to be deleted with S3 #4** |

`_ledger_store.MOVED_LEDGERS` is the single list; the branch was seeded from
`origin/dev`'s copies (S0, commit `36c4b85c`).

## How (the store)

`mcp/noctusai/tools/noctus/dev/_ledger_store.py` — Protocol + Real + Fake + factory
(the seed IO-module shape, `KB § PATTERNS/backend/seed-fake-real-adapter.md`):

| Piece | What it does |
|---|---|
| `Ledger` (Protocol) | `read_text(fetch=)` · `append(lines, message=, publish=)` · `update(transform, message=)` |
| `GitLedger` / `GitLedgerStore` (Real) | `git fetch` → `cat-file` the base blob → `hash-object -w` → `mktree` → `commit-tree -p <tip>` → `git push origin <sha>:refs/heads/ledgers` (fast-forward only), retried up to 5× on the race with a fresh fetch each time |
| `FileLedger` (Fake) | the writer's legacy local file; no git, no network |
| `open_ledger(name, local_path)` (factory) | `NOCTUS_LEDGER_STORE=git` (default) or `fake` |

- **No checkout, ever.** The Real store writes objects into the shared object
  store and moves one remote ref. It never touches a working tree or an index,
  so it is safe from the primary, from any worktree, and from several processes
  at once.
- **Write-ahead spool.** `append` first lands rows in
  `<git-common-dir>/noctusai/ledgers-pending/<name>` (under `flock`), then
  publishes. If the publish fails (offline, auth, a race lost 5×) the rows stay
  spooled, the result says `status='pending'`, and the next append or
  `noctus.dev.ledger_store action='flush'` carries them. Nothing is dropped
  silently.
- **Read-your-writes.** `read_text` returns the branch blob plus this clone's
  spooled rows. A spooled row that is already on the branch is dropped when it
  is published, so a crash between push and spool-truncate cannot duplicate it.
- **`update(transform)`** rewrites a whole file (auto-improvement promote and
  reconcile). The transform runs again on every retry, against the fresh tip.

## Dual-read (until S4)

Peer sessions whose MCP server still has the old code keep appending to the
`dev` copy until they restart. So every reader merges both sources with
`_ledger_store.read_dual(ledger, dev_text)` / `merge_ndjson_text`:

- exact-duplicate lines collapse (the seed makes every pre-2026-09-24 row appear
  in both);
- auto-improvement merges by its `(ts, target, description)` key, and the
  `origin/ledgers` version wins, so a status promotion is not undone by the
  stale dev row;
- if `origin/ledgers` cannot be read, the reader falls back to the dev copy AND
  returns or logs the error. It never passes silently.

## Guards

- **GitHub ruleset** `ledgers-append-only` (id 23955144) on `refs/heads/ledgers`
  blocks deletion and non-fast-forward pushes on the server.
- **`scripts/hooks/pre-push`** refuses deleting or rewinding `ledgers` on the
  client. A push that targets only `ledgers` skips every cache refresh and
  keeper (it carries no code). Without this, each append would pay the full
  pre-push tax and hit the branch-tree mirror check for a bare sha.
- **CI** — no workflow triggers on `ledgers`.
- **Tests** — `mcp/noctusai/tests/conftest.py` pins `NOCTUS_LEDGER_STORE=fake`.
  Real-store tests build a `GitLedgerStore` on a temp bare repo
  (`tests/test_ledger_store.py`). No test can push to the real origin.

## Operate

`noctus.dev.ledger_store` — `action='status'` (tip, row counts, spooled rows) ·
`'read' name=<file> tail=N` (dual-read) · `'flush'` · `'bootstrap'` (S0; dry-run
unless `confirm=True`; refuses when the branch exists).

## Anti-patterns

- Checking out `ledgers`, or writing to it with porcelain (`git commit`). Use
  plumbing only, through the store.
- Adding a new auto-appended `project-history/*.ndjson` that commits to `dev`.
  Add it to `MOVED_LEDGERS` and write it with `open_ledger`.
- Reading only the dev copy (or only the branch) while S4 is pending. Always
  call `read_dual`.
- Force-pushing or deleting `ledgers` "to clean up". It is append-only history,
  protected on both the client and the server.

## Roadmap

`project-history/roadmaps/ledgers-off-dev-2026-09.md`: Phase 1 (S0–S3) is
in progress (the table above says which writers have flipped). S4 (delete the dev copies, the drains, and the ledger-drain keeper) is
deferred until trigger T1: 7 consecutive days with zero ledger commits on `dev`
and no dual-read divergence.

Composes with `KB § PATTERNS/architect/branch-tree-tracking.md` ·
`KB § PATTERNS/common/self-branching-mode.md` ·
`KB § PATTERNS/common/storage-hygiene.md` ·
`KB § PATTERNS/common/vector-cost-tracking.md` ·
`KB § PATTERNS/common/scoped-auto-improvement.md`.
