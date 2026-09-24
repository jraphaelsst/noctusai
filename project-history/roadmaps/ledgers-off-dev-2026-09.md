# ledgers-off-dev-2026-09 — move the append-only ledgers off `dev` onto an orphan `ledgers` branch

> **Durable record** (per `KB § PATTERNS/common/roadmap-tracking.md`).
> Origin: 963 of 2378 `dev` commits since 2026-08-01 (41%) were ledger chores that cancelled CI, raced each other and blocked the primary checkout's sync.
> Decision: **ship S0–S3 now (orphan branch, plumbing store, dual-read, every writer flipped); defer S4 (delete the dev copies, the drains, the ledger-drain keeper) until T1 fires.**

## Origin

Owner decision on 2026-09-24, in chat ("move them off dev"; project `gate-mechanisms`). It adopted noctusai-be's proposal. On `origin/dev` since 2026-08-01, `chore(branch-pointer)` accounted for 465 commits, `chore(salvage)` for 373, `chore(ledger)` for 105, `chore(cost-log)` for 78 and `chore(ship-consent)` for 25. Every one of them moved the `dev` tip, which cancels the in-flight `test.yml` run (`cancel-in-progress`). They raced one another ("cannot lock ref"). Because they were committed on the primary checkout, they also diverged it from `origin/dev` (see `KB § PATTERNS/common/self-branching-mode.md` §12–§12d). The owner settled two sub-questions: delete `branch-tree.mirror.ndjson`, and do not hash-chain the consent rows.

## Trigger conditions (the "when")

Phase 2 (S4) kicks off when **ALL** of the following hold:

| # | Trigger | Detection signal | Why it tips the balance |
|---|---|---|---|
| T1 | **7 consecutive days with zero ledger commits on `dev` AND no dual-read divergence** | `git log origin/dev --since=<7 days ago> -- project-history/{branch-tree,worktree-salvage,auto-improvement,vector-costs,vector-signals,vector-calibration,dispatch-budget,absorptions,ship-consent}.ndjson project-history/branch-tree.mirror.ndjson` is empty; **and** for each moved ledger, every row of the `origin/dev` copy is present on `origin/ledgers` (`noctus.dev.ledger_store action='read'` counts == branch-only counts; a row only on dev = divergence) | Zero dev-side writes for a week means every peer session has restarted onto the new code. No divergence means the dev copies add nothing the dual-read still needs. |

**Today's status (2026-09-24)**: T1 has not fired. Phase 1 has just shipped, and peer sessions whose MCP servers loaded the old code keep writing the dev copies until they restart.

> **Every slice carries TWO recipes, not one.** The test recipe is the suite at
> the module boundary. The verify recipe is a live-state check.

## Phase 1 — S0–S3 (SHIPPED 2026-09-24)

| # | Title | Files | Status | Verify recipe (live-state proof, not unit tests) |
|---|---|---|---|---|
| S0 | Orphan `ledgers` branch seeded from `origin/dev`'s copies (`36c4b85c`) + GitHub ruleset `ledgers-append-only` (id 23955144: no deletion, no non-FF) | `noctus.dev.ledger_store action='bootstrap'` | **shipped** | `git ls-remote origin refs/heads/ledgers` resolves. `gh api repos/jraphaelsst/noctusai/rulesets/23955144` shows `deletion` + `non_fast_forward`. `noctus.dev.ledger_store action='status'` lists row counts for all 9 ledgers. |
| S1 | `_ledger_store`: Protocol + `GitLedgerStore` (plumbing, race retry, write-ahead spool) + `FileLedger` Fake + `open_ledger` factory. MCP tool `noctus.dev.ledger_store`. Pre-push ledgers-only fast path + refusal of delete/rewind. | `mcp/noctusai/tools/noctus/dev/_ledger_store.py` · `ledger_store.py` · `scripts/hooks/pre-push` · `tests/test_ledger_store.py` | **shipped** | Append one row from the primary (e.g. a `branch_pointer update`). `git log origin/ledgers -1` shows `ledger(branch-tree.ndjson): …`. `git status` on the primary is clean. No new commit appears on `origin/dev`. |
| S2 | Every reader dual-reads `origin/ledgers` ∪ the dev copy: auto-improvement (cache + keeper + codify + radar), vector-costs, dispatch-budget, vector-calibration, absorptions (cache + keeper), salvage idempotency and `_check_salvage_log`, branch-tree (`query`/`list`/`update`, `check_branch_tree_mirror`, `check_stale_branch_pointers`), `release._read_ledger`, `ship_consent.read_rows`, and the noc-graph history layer | per-module | **shipped** | `noctus.dev.branch_pointer action=list` shows a pointer that exists only on `origin/ledgers`. `noctus.dev.auto_improvement_query` returns a row logged after the flip. `noctus.dev.release stage=manifest` still attributes projects. |
| S3 #1 | auto-improvement writer (append + `update(transform)` rewrites) | `auto_improvement.py` · `codification_radar.py` · `codify.py` | **shipped** | `noctus.dev.auto_improvement_log …` → the row is on `origin/ledgers`, not in `project-history/auto-improvement.ndjson` |
| S3 #2 | vector-costs (the pre-commit drain goes to the store with `publish=False`; pre-commit no longer stages the ledger) + dispatch-budget + dispatch-completion + vector-signals/-calibration + absorptions | `vector_costs.py` · `scripts/hooks/pre-commit` · `dispatch_budget.py` · `dispatch_token_log.py` · `vector_calibration.py` · `absorption_tracking.py` | **shipped** | After an embedding refresh plus a commit, no `vector-costs.ndjson` change is staged. `noctus.dev.ledger_store action='status'` shows spooled cost rows, and they publish on the next pointer write. |
| S3 #3 | worktree-salvage: rows go through the store, records whose SHA is already on `origin/dev` are dropped, and `task_branch` cleanup's record + dev-push legs are removed | `_worktree_salvage.py` · `task_branch.py` · `salvage_before_delete.py` · `session_end_sweep.py` · `remote_branch_hygiene.py` | **shipped** | `task_branch action=cleanup` returns `salvage_skipped` and makes no `chore(salvage)` commit |
| S3 #4 | branch-tree writer to the store; `branch-tree.mirror.ndjson` deleted, along with the keeper's parity leg | `branch_pointer.py` · `compliance.py` · `release.py` | **shipped** | `task_branch action=start` → the pointer is on `origin/ledgers`, and `origin/dev` gains no `chore(branch-pointer)` commit |
| S3 #5 | ship-consent writer (moved last) | `ship_consent.py` | **shipped** | `ship_consent action=author` (after the user types the phrase) → the row is on `origin/ledgers`, and `release stage=manifest` shows the project approved |

**Behavior guarantee**: once a session restarts its MCP server on this code, it makes no ledger commit on `dev`. Rows written by a session still on the old code keep landing in the dev copies, and the dual-read plus the drains keep them visible and shipped. A publish that fails (offline, or a race lost 5 times) leaves its rows in `<git-common-dir>/noctusai/ledgers-pending/`, reported as `status='pending'`. They are readable locally and publish with the next write, `session_end_sweep`, a `task_branch` drain, or `noctus.dev.ledger_store action='flush'`.

**Why ship now**: each ledger chore cancelled a CI run and raced integrate. The cost is paid on every session.

## Phase 2 — S4: delete the dev copies, the drains, the ledger-drain keeper (DEFERRED — fires on T1)

| # | Title | Files | Trigger | Verify recipe (write it now, run it when it ships) |
|---|---|---|---|---|
| S4.1 | `git rm` the dev copies of the 9 moved ledgers (`project-history/ledger.ndjson` STAYS) | `project-history/*.ndjson` | T1 | `git ls-files project-history/*.ndjson` lists only `ledger.ndjson` and `orphan-remote-salvage-2026-05-30.ndjson` |
| S4.2 | Drop the dev half of every dual-read (`read_dual` → the store only), plus the `runner` `git show origin/dev:` legs in `branch_pointer`/`ship_consent`/`release` | readers listed in S2 | T1 | Each reader's test uses only the store. `noctus.dev.branch_pointer action=list` still shows the live map. |
| S4.3 | Delete the drains: `task_branch._drain_ledgers_from_primary`, `session_end_sweep.deliver_trailing_ledgers` and its `_LEDGER_PATHS`, and `_ledger_push.commit_and_ff_push_ledger` once nothing calls it. Keep `flush_pending` where the drains called it. | `task_branch.py` · `session_end_sweep.py` · `_ledger_push.py` | T1 | `grep -rn commit_and_ff_push_ledger mcp/` is empty. `task_branch integrate` still publishes spooled rows. |
| S4.4 | Delete the ledger-drain keeper (`check_ledger_drain_after_settle`), its pre-push block and its CLI flag. Remove the dead cache-exempt / benign-stash / `.gitattributes` entries for the moved paths. | `compliance.py` · `scripts/hooks/pre-push` · `cli.py` · `_benign_stash.py` · `refresh_all_caches.py` · `.gitattributes` | T1 | pre-push has no ledger-drain block. `--verify-kb-sync` is green. |
| S4.5 | Decide on the conftest ledger-path isolation: with no dev copies, the Fake could become in-memory. | `mcp/noctusai/tests/conftest.py` | T1 | the suite is green with the isolation fixture removed or simplified |

**Why not now**: peers on the old code still write the dev copies. Deleting the copies and the drains today would strand their rows in the primary checkout, which is the exact dirty-primary symptom this project removes.

## Anti-goals (explicit non-goals)

- ❌ "Move `project-history/ledger.ndjson`." It is the human, reviewed project history and belongs on `dev`.
- ❌ "Hash-chain the ship-consent rows." The owner declined. The transcript-verified `author` gate plus the server-side ruleset are the integrity story.
- ❌ "Check the `ledgers` branch out anywhere." Plumbing only. A worktree on `ledgers` would reintroduce working-tree state and porcelain commits.
- ❌ "Force-push or delete `ledgers` to clean it up." It is append-only history, guarded by the ruleset (server) and pre-push (client).

## Open questions (to revisit at trigger time)

- **Q1**: Should S4 also rewrite the `noc-graph` history input to read the store directly (dropping the materialized merged file under the cache dir)? This is cheap once the dev copy is gone.
- **Q2**: Should a periodic `noctus.dev.ledger_store action='flush'` (cron / `session_end_sweep` only) be the sole publisher for cost rows, instead of piggy-backing on the next pointer write?
- **Q3**: GitHub ruleset `ledgers-append-only` has no bypass actors. If a legitimately bad row ever needs removing, the only path is a new appended correction row. Confirm that is acceptable.

## Decision log

- **2026-09-24**: Owner approved moving the ledgers off `dev` (project `gate-mechanisms`). Delete `branch-tree.mirror.ndjson`. No hash-chaining of consent rows.
- **2026-09-24**: The Real store publishes with a push of a raw commit sha to `refs/heads/ledgers`. The old pre-push would have run the branch-tree mirror keeper against that sha and blocked, so the pre-push fast path for ledgers-only pushes shipped in S1, before any writer flipped.
- **2026-09-24**: Salvage rows for SHAs already on `origin/dev` are not written. `salvage_before_delete` (operator-invoked) still writes its row, because `delete_integrated_remote` requires one.
- **2026-09-24**: The pre-commit cost drain uses `publish=False`, so a commit never waits on the network. Rows publish with the next write of any ledger.

## Retrospective (filled at first trigger fire)

*To be filled when S4 fires.*

## Composes with

- `KB § PATTERNS/common/ledger-store.md`: the store, the dual-read, the guards.
- `KB § PATTERNS/architect/branch-tree-tracking.md`: the pointer ledger's semantics (unchanged).
- `KB § PATTERNS/common/self-branching-mode.md` §12d: the divergence loop this removes.
- `KB § PATTERNS/common/storage-hygiene.md` § 2.3: the salvage ledger.
- `KB § PATTERNS/common/vector-cost-tracking.md`: the spool and drain.

## File trail

- `mcp/noctusai/tools/noctus/dev/_ledger_store.py` (new) · `ledger_store.py` (new) · `tests/test_ledger_store.py` (new)
- `scripts/hooks/pre-push` · `scripts/hooks/pre-commit`
- writers/readers: `auto_improvement.py` · `codification_radar.py` · `codify.py` · `vector_costs.py` · `dispatch_budget.py` · `dispatch_token_log.py` · `vector_calibration.py` · `absorption_tracking.py` · `_worktree_salvage.py` · `salvage_before_delete.py` · `remote_branch_hygiene.py` · `session_end_sweep.py` · `task_branch.py` · `branch_pointer.py` · `ship_consent.py` · `release.py` · `compliance.py` · `noc_graph_cache.py` · `seed/lib/backend/noctusai_lib/graph/build.py`
- `project-history/branch-tree.mirror.ndjson` (deleted)
- KB: `common/ledger-store.md` (new) · `architect/branch-tree-tracking.md` · `common/self-branching-mode.md` · `common/storage-hygiene.md` · `common/vector-cost-tracking.md` · `common/scoped-auto-improvement.md` · `common/learn-before-archive.md` · `common/session-end-sweep.md` · `devops/ship-consent-riders.md`
- This doc.
