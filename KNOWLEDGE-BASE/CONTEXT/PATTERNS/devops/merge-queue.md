# Merge queue — the one path into `dev`

> **Rule.** Code reaches `dev` only through the CI merge queue. A session
> *enqueues* a small, rebased slice. GitHub runners test it on top of `dev`
> plus whatever is queued ahead of it, and the queue lands it only when that
> combined code is green. Developer machines run fast, local checks only.
> Adopted 2026-11-05 by owner order, after the julia-line integrate storm.

## 1 · Why: what the old flow cost (measured 2026-11-04/05)

Under the old flow, `task_branch integrate` rebased onto `dev`, ran the full
merged-tip gate set **on the owner's laptop**, then fast-forward pushed. About
six sessions shared two hardware slots.

| Cause class | Share of blocking events | What it looked like |
|---|---|---|
| Parallel work | ~70% | Rebase conflicts; two branches both taking SW migration 320; other sessions' reds blocking through an "inconclusive" baseline; 14 slices whose bugs only appeared once combined |
| Machine overload | ~25% (most of the wall-clock) | A 2h20m queue for a slot; toolkit tests timing out; restarts when the slot gate was toggled |
| Tooling | ~5% | `rebase` flattened a train's merge commits and lost their conflict resolutions |

The two compound each other. A local verdict takes about an hour, and in that
hour peers push to `dev`, so the verdict goes stale and the branch rebases and
re-runs. Overload stretches the window, and parallel pushes fill it.

The industry has solved this the same way for years. Bors's "not rocket science
rule", GitHub/GitLab merge queues and merge trains, and Uber's SubmitQueue all
test a change against the state the trunk *will* have, on CI, and serialize
the landing. DORA's trunk-based guidance adds small batches and short-lived
branches. Teams running parallel AI agents report the same lessons: a merge
gate on tests, one supervisor owning the merge order, about 3–5 concurrent
writers, and claiming a task before writing. Sources are in §9.

## 2 · Shape

```
session (laptop)                     GitHub Actions (merge-queue.yml, serialized)
────────────────                     ─────────────────────────────────────────────
task_branch action=enqueue           drain: oldest mq/* entries (≤ batch_limit)
  rebase on origin/dev                 compose onto dev in a scratch worktree
  migration renumber (vs dev)            ff | rebase | --no-ff merge (for trains)
  doc-staleness, KB counts               eject: conflict · duplicate migration nr
  pre-push keepers                     push mq-candidate/<run>-<n>
  push → refs/heads/mq/<slug>--<sha7>  dispatch Tests & Build (full suite) on it
                                       green → FF dev to the candidate
task_branch action=landed            red   → re-run failed jobs once (flake)
  reads the `merge-queue` status         still red → halve the batch (bisect);
  landed → pointer, primary FF,                       a red single entry is ejected
           worktree cleanup          verdict → commit status `merge-queue` on the
  ejected → fix, enqueue again                  ENQUEUED sha (landed as <dev sha> | why)
```

Code lives in:

- `mcp/noctusai/tools/noctus/dev/merge_queue.py`: the driver. It is stdlib-only
  and runs on a bare runner. Its tests are `tests/test_merge_queue.py`, which use
  real git against a local bare remote, with only `gh` faked.
- `.github/workflows/merge-queue.yml`: the triggers are a push to `mq/**`, a
  manual dispatch, and a sweeper every 20 minutes. `concurrency:
  merge-queue`, never cancelled.
- `task_branch action=enqueue|landed`, in `task_branch.py`, tested by
  `tests/test_task_branch_queue.py`.
- `noctus.dev.merge_queue` / `cli.py --merge-queue list|status`: the read-only
  queue view.

## 3 · Invariants

1. **`dev` only moves to a green sha.** A queue landing is a fast-forward to a
   candidate whose `Tests & Build` run is green. The one exception: when `dev`
   advanced meanwhile by `project-history/**/*.ndjson` ledger rows only, the
   candidate is replayed over them without a re-test. That is the same
   predicate `test.yml`'s `paths-ignore` uses. Any code advance of `dev` forces
   a re-test. "Dev is green" is therefore true by construction, and a red `dev`
   tip stops being something every branch inherits.
2. **Every entry gets a verdict on the sha that was enqueued.** The verdict is a
   `merge-queue` commit status: `pending` (in a batch under test), `success`
   (landed as `<dev sha>`), or `failure` (ejected, with the reason). Silence is
   never a pass. `landed` reports `queued` until a verdict exists.
3. **A batch is judged as one tree.** File-disjoint is not effect-disjoint
   (`methodology-execution-discipline.md`). The queue tests exactly the tree
   that `dev` will become.
4. **The queue never edits an entry.** A conflict or a duplicate migration
   number ejects the entry; it is never auto-resolved on CI. The owning session
   fixes the branch and enqueues it again. Local renumbering against `dev`
   still happens at enqueue time (`_attempt_migration_renumber`).
5. **The driver comes from `dev`.** The workflow checks out `dev` and runs
   *that* `merge_queue.py`, never the entry's copy.

## 4 · How to work under the queue (the session rules)

- **Small slices, enqueued as soon as they are green.** One branch is one
  concern. Do not build a long-lived multi-slice branch. jl-ship carried 14
  slices plus a train, and that is how 40% of the blocks were our own bugs
  surfacing only when everything met.
- **Check locally before enqueueing, scoped to what you touched.** Run your
  product's own suite, plus the repo-wide toolkit gates *if you touched*
  `mcp/`, migrations, KB or compliance surfaces: `test_compliance.py`,
  `test_verify_db_guards.py`, `test_migrations.py`. Use
  `noctus.dev.gate_sweep`, which derives the set from the diff. The queue
  catches the rest, but an ejection costs a CI cycle, about 25 minutes.
- **Never push code to `dev` directly.** Ledger rows (branch pointers,
  salvage, `project-history/*.ndjson`) still drain straight to `dev`; the
  queue rebases over them.
- **Enqueue → `landed`.** After enqueueing, keep working on something else and
  check with `task_branch action=landed slug=<slug>`. Pass `confirm=True` once
  it says landed, so the pointer, primary FF and cleanup run. If ejected, read
  the reason (it links the CI run), fix it on the branch, and enqueue again.
- **About 3–4 sessions writing code at once.** More only adds queue time and
  conflict odds; the codebase's ability to absorb parallel change is the limit,
  not the session count. The figure is not arbitrary:
  - Claude Code's agent-teams guidance recommends 3–5 teammates.
  - Brooks' law: communication paths grow as n(n−1)/2, so 4 writers have 6 paths and 8 have 28.
  - Conway (1968) makes the same observation.
  Sources are in `orchestration-craft-canon.md` § Sources. Each session publishes its branch-pointer `paths`
  before the first edit (`branch-tree-tracking.md`); that is the claim.
- **Migration numbers.** Take the next free number against `origin/dev` *and*
  the queue (`noctus.dev.merge_queue` lists what is waiting). On a collision
  the later entry is ejected with the number to change.
- **Trains still work.** A branch carrying `--no-ff` merge commits is merged,
  not rebased, so its conflict resolutions survive. The queue already batches,
  so prefer enqueueing slices individually. The local half matches since
  2026-11-05: `enqueue` merges `origin/dev` into any branch carrying a merge
  commit and rebases it with `--rebase-merges` (it used to do that only for
  `train-*` slugs, so feat/julia-golive was flattened and re-hit the conflicts
  its merge had already resolved).

## 5 · Fallback: `task_branch action=integrate`

The legacy path still exists: local merged-tip gates, hardware slots, then a
direct fast-forward push. Use it **only** when the queue itself is down
(GitHub Actions outage) and say so in the report. While a queue batch is
running, a direct code push to `dev` forces that batch to re-test (invariant 1).
That is correct but wastes about 25 minutes of CI.

## 6 · Bless and ship are unchanged

`release stage=bless` looks CI runs up by commit sha (`gh run list --commit`),
so it finds the candidate's dispatch run on the exact sha `dev` fast-forwarded
to. A ledger-replayed landing has no run of its own; R1 walks back to its
qualifying ancestor, which is normal steady state. Path-scoped workflows that
fire on a push to `dev` are dispatched by the queue after landing when the
landed diff touches their paths (`POST_LAND_DISPATCH`, today
`agents-secc-ci.yml`), because a `GITHUB_TOKEN` push deliberately triggers no
workflows.

## 7 · Limits and options

- **Why not GitHub's native merge queue?** It needs an organization-owned
  repository, and `jraphaelsst/noctusai` is user-owned. Moving the repo to a
  (free) organization would unlock it, along with PR-based required checks.
  That is the owner's decision, so it is recorded here as an option, not done.
- **No scope lanes yet.** Every batch runs the full suite (a `workflow_dispatch`
  run is never scoped down, by `test.yml` design). That costs about 25 minutes
  per batch, but runner minutes are free for a public repository and batching
  amortizes it. Per-product lanes are the next step if queue time becomes the
  bottleneck.
- **Range keepers judge exactly the batch (2026-11-05).** The drain dispatches
  `test.yml` with `-f base=<dev sha the candidate was composed on>`; the
  commit-range keepers use `base..candidate`. Before this, a dispatched run had
  no `event.before` and fell back to `SHA~50..SHA`, re-judging 50 commits
  already on dev.
- **Local pre-push doc-staleness covers `mq/*` (2026-11-05).** The leg matched
  only pushes to `dev`, so it never fired once code took the queue; an `mq/*`
  push is judged against its merge-base with `origin/dev`.
- **Bisection is "first half", not speculative.** A red batch of N retries its
  first ⌈N/2⌉. That is enough at our volume; Uber-style speculation is not
  warranted.
- **The suspects stay isolated until the culprit is out (2026-11-05).** The
  entries of a red batch are *suspects*. While any of them are still queued,
  batches are drawn only from them:
  - a green half clears its entries, and the rest are tested alone;
  - a red singleton is ejected;
  - only after that do fresh entries join a batch.

  Before this, a green half reset the limit to a full batch, so the culprit
  was re-composed with innocent entries and turned their batch red too. That
  happened live: -6 red, -7 green, then -8 was the culprit plus 3 innocent
  entries. Covered by
  `test_a_green_half_does_not_reset_bisection_onto_fresh_entries`. The suspect
  set lives for one drain run only. A new run starts clean and re-bisects if
  needed.

## 8 · Related

`KB § PATTERNS/common/self-branching-mode.md` (the worktree lifecycle around
it) · `KB § PATTERNS/architect/branching-dispatch.md` (dispatch and trains) ·
`KB § PATTERNS/devops/dev-main-ci-gates.md` (what CI gates) ·
`KB § PATTERNS/devops/hardware-admission-budget.md` (the local slot gate, which
now covers local checks only) · `KB § PATTERNS/common/methodology-execution-discipline.md`
(per-branch green ≠ integration green).

## 9 · Sources

- Graphite, *What is a merge queue*: https://graphite.dev/blog/what-is-a-merge-queue
- Mergify, *Merge queue in a monorepo*: https://mergify.com/learn/monorepo/merge-queue
- matklad, *GitHub Merge Queue* (the "not rocket science rule"): https://matklad.github.io/2023/06/18/GitHub-merge-queue.html
- Uber, *CI at Scale: Lean, Green, and Fast* (SubmitQueue): https://arxiv.org/html/2501.03440v1 · https://github.com/uber/submitqueue/
- DORA, *Trunk-based development*: https://dora.dev/capabilities/trunk-based-development/
- Bytebase, *Migration guidelines* (timestamps vs sequence): https://docs.bytebase.com/gitops/best-practices/migration-guidelines.md
- GitLab, *Parallel branch migrations deploy out of order*: https://gitlab.com/gitlab-org/container-registry/-/work_items/2099
- *5 Lessons from Running AI Coding Agents in Parallel*: https://dev.to/battyterm/5-lessons-from-running-ai-coding-agents-in-parallel-53on
- Augment, *Multi-agent coding workspace*: https://www.augmentcode.com/guides/how-to-run-a-multi-agent-coding-workspace
- GitHub Docs, *Triggering a workflow* (why `GITHUB_TOKEN` pushes start no runs): https://docs.github.com/en/actions/using-workflows/triggering-a-workflow
