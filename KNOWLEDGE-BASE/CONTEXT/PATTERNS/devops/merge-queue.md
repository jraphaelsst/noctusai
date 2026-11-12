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
  deliverable(branch) read-only        compose onto dev in a scratch worktree
  PURE PUSH <sha> →                      ff | rebase | --no-ff merge (for trains)
   refs/heads/mq/<slug>--<sha7>          eject: conflict · duplicate migration nr
  (no checkout/merge/rebase/commit)    push mq-candidate/<run>-<n>
                                       dispatch Tests & Build (full suite) on it
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
  `tests/test_guardian_pure_push_enqueue.py` (enqueue, real git),
  `tests/test_task_branch_queue.py` (landed) and
  `tests/test_task_branch_cleanup_ownership.py` (landed never cleans what is not the caller's).
- `noctus.dev.merge_queue` / `cli.py --merge-queue list|status`: the read-only
  queue view.

## 2a · Enqueue is a pure push (2026-11-10)

`task_branch action=enqueue` does exactly this, from the guardian's own checkout (HEAD may be `dev`):

1. `deliverable(branch)`: the read-only delivery contract (`release-steward.md` § 8b): head pushed + tree clean, merge-buildable
   (contains `origin/dev` OR `git merge-tree` is clean), migration numbers free, derived files current at the head, scoped
   keepers/tests green the way CI judges them. Any failing item: `status=needs_resync`, exit 1, nothing pushed, nothing touched.
2. `git push origin <sha>:refs/heads/mq/<slug>--<sha7>`.

No checkout, merge, rebase, commit, stash or file write happens in any worktree (proved on real git in
`tests/test_guardian_pure_push_enqueue.py`: file hashes, refs, HEAD, index and `.git/rebase-*` state are byte-identical
before and after). Derived-file regeneration for composition is the queue's job (compose re-derives kb-counts, see § 4), never
enqueue's. Legacy `integrate` is unchanged.

**The pre-push hook knows this push, and only for `enqueue`.** `scripts/hooks/pre-push` recognises the queue path: a push whose ONLY
remote refs are `refs/heads/mq/<slug>--<sha7>`, with `<sha7>` a prefix of the pushed local sha, AND a fresh attestation: right before its
push enqueue writes `<git-common-dir>/noc-enqueue/<full sha>.json` (the `deliverable()` verdict, ok, matching sha, written < 10 min ago).
The attestation names the one fully-qualified queue ref it authorises; the hook also requires exactly ONE mq ref per push and a bare full sha
as the local side. A needs_resync re-check or a rejected push revokes it. Without it the hook REFUSES and names `task_branch action=enqueue` as the remedy (a hand-typed exact-sha push would otherwise skip the
whole delivery contract). Its local ref is a bare sha, which used to make the
branch-tree mirror keeper look for a branch named after the sha and block the push (reported only as the generic "main is
sacred" banner). Now: a bare-sha push to an exact mq ref skips that per-branch check; an mq ref that does not name its sha is
refused; an mq ref combined with ANY other ref (`dev`, `main`, `prod`...) is refused; and a push to `main`/`prod` is still gated.
Tests: `tests/test_pre_push_queue_path.py` (the real hook in a temp repo; red against the previous hook).

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
   The steward may REBASE an entry before landing it (new shas, same content),
   so once landed, `task_branch` decides "merged" by CONTENT, not ancestry:
   every branch commit's patch-id is on `origin/dev` (`git cherry`), or a trial
   merge of the branch into dev yields dev's own tree. Equivalent ⇒ pointer,
   primary FF, worktree + branch teardown (the branch is then force-deleted,
   safe because the content is proven on dev). Not equivalent ⇒ refused with
   `missing_commits`, worktree untouched (it is never rebased or half-applied).
3. **A batch is judged as one tree.** File-disjoint is not effect-disjoint
   (`methodology-execution-discipline.md`). The queue tests exactly the tree
   that `dev` will become.
4. **The queue never edits an entry.** A conflict or a duplicate migration
   number ejects the entry; it is never auto-resolved on CI. The ejection is
   resolved per §4 "Ejections" (decision 2026-11-10,
   `project-history/assistant-chatbot/queue-lifecycle-decision.md`); the fix lands
   on the branch steward's branch and is filed again. Nothing edits the branch
   before the queue either: enqueue is a pure push (§ 2a), so a stale number is
   caught by the `deliverable` preflight (`migrations_free`, as `needs_resync`)
   and renumbered by the branch steward, not at enqueue time.
   **One carve-out — registered derived ledgers (2026-11-07).** A conflict that
   lies wholly inside ONE set in `merge_queue.DERIVED_SETS` (today: the
   access-tiers `FINDINGS.md` / `findings.ndjson` / `metrics.ndjson`) is not a
   content conflict — each slice regenerated the same derived artifact. Compose
   takes the head copy, finishes applying the entry, re-runs the set's regen on
   the merged tree and commits only that set (`chore(<set>): re-derive conflicted
   ledger at compose [auto]`, drain log `[mq-derived-regen]`). A mixed conflict
   still ejects as `conflict`; a failed regen ejects as `derived_regen`. Adding a
   set is one data row — never hand-resolve a derived file. Born when two slices
   ejected on these files in one batch (s1 `merge-queue/derived-ledger-coupling`).
5. **The driver comes from `dev`.** The workflow checks out `dev` and runs
   *that* `merge_queue.py`, never the entry's copy.

## 4 · How to work under the queue (the session rules)

- **One elected steward runs the queue; everyone else files and keeps
  building.** Before any queue/deploy action check your environment
  (`ListAgents` + `release_steward action=status`). Only the steward enqueues,
  runs `landed`, blesses, promotes and deploys; the `release-steward` hook
  refuses everyone else and names the steward. A gated session does **not**
  stop: it files `release_steward action=request slug=<slug>` (re-filing keeps
  the latest `head_sha`) and continues building; the steward drains the whole
  outbox in one pass so riders batch in the queue, then replies `LANDED <dev
  sha>` / `EJECTED <reason>` / `DEPLOYED`. The steps below that say "enqueue" or
  "`landed`" are the steward's; a non-steward session's equivalent is the
  request. → `KB § PATTERNS/devops/release-steward.md`
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
  the reason (it links the CI run); the steward resolves it (see "Ejections").
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
  so prefer enqueueing slices individually. Since 2026-11-10 the local half
  does nothing to the branch at all: `enqueue` no longer merges `origin/dev`
  into a merge-carrying branch or runs `rebase --rebase-merges` (that ran in the
  requester's worktree and left rebase state behind on a conflict, the D1 stuck
  rebase). A merge-built branch that is behind `dev` is accepted when
  `git merge-tree` against `dev` is clean; otherwise it comes back `needs_resync`.
- **The drain registers the repo's custom merge drivers first** (`scripts/hooks/register-merge-drivers.sh`, after installing toolkit deps). `.gitattributes` only names a driver; unregistered on the runner, derived kb-counts blocks text-merge and eject parallel entries (2026-11-05). Keeper `check_merge_drivers_registered_in_ci`. Merge drivers run before git writes the merged tree (ort), so they re-derive counts against the pre-merge tree: after every composed entry the drain therefore re-runs `cli.py --update-kb-counts` in its worktree and commits changed derived paths as `chore(kb-counts): regenerate derived counts at compose [auto]`; a failing regen ejects the entry (`kb_counts_regen`), never continues silently. → `KB § PATTERNS/common/auto-generated-merge-drivers.md`
- **Open enqueue (not live until items 1, 4, 6, 9 land, the CLAUDE.md word-budget check
  against the queue exists, and the owner flips decision item 10).** Any session may
  enqueue only when the queue is conflict-safe by construction: liveness (1), role
  registry (4), queue-aware migration numbers (6), derived-artifact regeneration (9).
  Fitness function: ejections are tracked by cause; if collision-class ejections pass
  the threshold, open enqueue closes again. Until then the steward enqueues (protocol v1).
- **Ejections (the branch steward fixes; council 09340534 dispositions A, B, K).** The
  guardian (lease holder) is a service leaf: on a red it withdraws the `mq/*` ref, writes
  `ejected{reason, conflict, url}` to the outbox, requeues the other riders and notifies the
  branch steward's ROLE (one batched `needs_info` question if it needs information,
  `noc-questionnaire` peer mode, TTL ~25 min). The branch steward fixes the ejection on its
  own branch and files `request` again. After 2 ejections the delivery parks as
  `blocked_on_steward`. The guardian never patches the branch and never opens a rescue
  branch. **Orphan** (the steward's session is gone or silent past the TTL): the delivery
  stays `blocked_on_steward`, the guardian alerts the owner, and the OWNER names a new
  branch steward, who adopts the branch; the guardian never adopts it. Flow:
  `release-steward.md` §7a.

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

## 6a · Job timeouts — a hung job without one blocks the whole queue

2026-11-05: batch run `42057027002` (`mq-candidate/42047199280-3`) hung in the
`Install system build deps` apt step of `Tooling Tests (pytest)` for 1.5h+.
The job had no `timeout-minutes`, so GitHub's 360-min default applied; the
drain job waits on the batch's `Tests & Build`, so all 13 queued entries
stalled behind one apt call.

**Rule.** Every workflow job (no `uses:`) declares `timeout-minutes` <= 120
(drain: 360); every step running apt / `playwright --with-deps` carries a
step `timeout-minutes` (10) and apt gets `-o Acquire::Retries=3 -o
Acquire::http::Timeout=30`. Keeper `check_workflow_job_timeouts`
(`--check-workflow-job-timeouts`; pre-commit when a workflow is staged, and in
the compliance sweep).

**Values are measured, not guessed** — p95/max of the last ~40 green runs per
workflow (2026-11-05), set at roughly max(2 x p95, p95 + 10), floor 5, rounded
up (max >= p95 headroom for cold caches):

| Job | p95 / max (min) | Set |
|---|---|---|
| changes | 0.5 / 0.5 | 5 |
| product-backend-tests | 2.1 / 16.0 | 30 |
| seed-backend-tests | 6.5 / 12.9 | 25 |
| product-frontend-tests | 1.7 / 9.2 | 20 |
| seed-frontend-tests | 2.3 / 2.7 | 15 |
| core/erp/pf frontend builds | 0.8 / 1.0 (erp, pf no data) | 10 |
| core-e2e / erp-e2e (no data) | 8.3 / 10.6 | 25 |
| sw-e2e-tests | 3.0 / 3.0 | 15 |
| docker-compose-validate, trivy, bandit, gitleaks, harness-mod | <= 2.0 | 10 |
| commit-range-keepers | 1.6 / 1.6 | 15 |
| tooling-tests | 3.0 / 6.2 | 20 |
| mcp-toolkit-tests | 14.3 / 16.8 | 35 |
| mcp-toolkit-tests-coverage | 0.2 / 0.2 | 5 |
| build-and-push build-push | 10.6 / 10.9 | 30 |
| build-transcriber build-push | 9.7 / 9.7 | 30 |
| cache-cleanup | 0.6 / 0.6 | 5 |
| deploy-prod deploy (SSH ff-only pull) | 0.1 / 0.1 | 15 |
| embedding-cache-validate (no data) | - | 20 |
| seed-typecheck (lib, framework) | 1.4 / 1.4 | 10 |

`deploy-prod` is generous on purpose: the §2a pull backs up, then
fast-forwards, and cancelling mid-FF is the one unsafe cut, so the budget is
~150x the observed runtime. Re-measure when a job's p95 drifts toward half its
timeout.

**Mirror outage (2026-11-11 ~14:16Z).** `azure.archive.ubuntu.com` answered `Ign:` for every package and every
apt step hung to its 10-min timeout. About 12 red jobs per batch (candidates -9/-10, runs `43036758510`/`43043398036`), and
the drain bisected an infra red. **Rule:** every apt use goes through `.github/actions/apt-install`. It drops the Google
source, sets apt-wide retries and timeouts (`/etc/apt/apt.conf.d/99noc-resilient`, inherited by playwright's own
`apt-get`), probes the mirror under a hard cap, and walks `archive.ubuntu.com` → `mirrors.ubuntu.com/mirrors.txt` on a
hang, `Ign:` or `Err:`. It fails loudly naming the mirror. Playwright jobs run it with no `packages` before
`--with-deps` / `install-deps`. The fix rides in the candidate's own `test.yml`, so the batch that carries it already
gets past the broken mirror.

## 6b · Watchdog — the queue tells the owner, with or without a steward

**Rule.** The queue reports itself off-host. A watcher that lives in a session
dies with it, so it cannot be the only alarm.

**Why.** Four failures reached nobody:
- **2026-11-05:** the drain crashed on every run for about 1.5 h. The verdicts never changed, so the in-session watcher printed nothing.
- **2026-11-06:** a second crash loop.
- **2026-11-07:** 9 entries were EJECTED while a dev-text watcher waited for hours.
- **2026-11-08:** one entry with a stale keeper baseline failed three candidate batches of about 50 min each. The steward session had ended, so nothing landed for 3.5 h and no one knew.

**How.** `.github/workflows/merge-queue-watchdog.yml` runs every 10 min.
- **Command:** `python -m tools.noctus.dev.mq_watchdog --state … --send`. It uses only the standard library and keeps its state in the actions cache, the same shape as `prod-watchdog.yml`.
- **Channels:** the same as prod-watchdog (WAHA WhatsApp, Resend email).
- **Per run:** at most one message.

The message reports:

| Line | When |
|---|---|
| `✅ LANDED` / `❌ EJECTED` | an entry left the queue, with its verdict (dev sha / reason + url) |
| `🟠 BATCH-RED` | a `mq-candidate/*` CI run failed. The bisect has begun, so act now, not after it ends |
| `🔴 DRAIN-FAIL` | a drain run ended failure / timed_out / startup_failure (cancelled is normal) |
| `⏸️ STALL` | the queue is non-empty and nothing has left it for `MQW_STALL_MIN` (90), or a drain is in progress over `MQW_DRAIN_LONG_MIN` (150). It reminds every `MQW_REMIND_MIN` (120), then `🟢 RECOVERED` |
| `👁️ BLIND` | the queue was unreadable `MQW_BLIND_RUNS` (3) runs in a row |

**Delivery.**
- **Routing:** failures go to every channel; a success-only digest goes to WhatsApp (else email).
- **The first run** only records a baseline.
- **An undelivered failure** exits 1, which turns the workflow red, so GitHub's failure email is the backstop. State is not advanced, and the next run retries.

**Local use:** run `noctus.dev.mq_watchdog` (dry by default), or `cli.py --mq-watchdog`. The in-session `cli.py --merge-queue watch` stays the steward's live feed; the watchdog does not replace it.

**In-session feed reports batches too (2026-11-09).** `cli.py --merge-queue watch` also prints `MQ-BATCH <candidate> -> success|failure|cancelled <url>` once per finished candidate batch (the first poll is a silent baseline; a failed read prints `MQ-WATCH-ERROR batches …`). Before this an entry-only watch stayed silent through a whole bisect, because nothing leaves the list while suspects are retried. One Monitor on `^MQ-LEFT|^MQ-BATCH|^MQ-WATCH-ERROR` is the whole live loop; the procedure is skill `noc-steward`.

## 6c · Priority lane and parallel product-disjoint candidates (2026-11-11)

**Priority lane.** An entry whose diff vs dev touches `.github/`, or whose tip commit carries a
`MQ-Priority: <why>` trailer, composes FIRST and ALONE, ahead of oldest-first order and ahead of
an open bisection (a priority run never moves the bisection state). Why: on 2026-11-11 the
apt-mirror CI fix waited behind FIFO and the first candidate went infra-red without it. The
trailer is the flag because it rides the commit through enqueue's rebase untouched: no enqueue
change. (`.github/workflows/*` still needs the push token, as before.)

**Parallel candidates (K=2, `PARALLEL_CANDIDATES`).** When the leading entries of the next batch
are all product-only (every changed path under `products/<slug>/`, other than the shared
`products/seed/`) and fall into 2+ disjoint product groups, each group is composed on the SAME dev
base and pushed as its own candidate (`mq-candidate/<run>-<n>p<i>`); their CI runs overlap, which
is the gain. Entries sharing a product merge into one group. A red candidate ejects (or
attributes/bisects) on its own and never touches the others.

**What never runs in parallel.** Anything outside `products/<slug>/` (seed, mcp, `.github`, KB,
scripts, ledgers, an unreadable diff) is ONE shared area that conflicts with everything: a shared
entry is never a second candidate, an open bisection never forms a wave, a priority entry is
always alone. With a shared entry first in line the queue behaves exactly as before.

**Land rule.** The first green lands as today. A later green is re-composed on the new dev tip
(re-running the kb-counts/derived regen on the COMBINED tree) and lands WITHOUT a CI re-run only
when the result is provably the exact union of the two tested trees: the two diffs vs base share
no file, the re-composed tree differs from the tested candidate only in the peer's files, and it
differs from the tip in exactly the candidate's own files. Any miss (shared derived file such as
counts moved, dev moved beyond the wave, re-compose not clean) leaves the entries queued and the
next round re-tests them on the combined tree, so a miss costs time, never correctness.
**Residual risk, stated:** file-disjoint is not effect-disjoint (per-branch green is not
integration green); restricting the skip to product-only entries with no shared file is what
keeps that risk small, not zero. Path areas come from the queue's own map (`entry_areas`), to be
derived from `ci_scope.classify` once that lands (`NOC-REMEDIATE[mq-area-map-dedup]`).

## 6d · Toolkit shards are balanced by measured time (2026-11-11)

The slowest `MCP Toolkit Tests` shard gates every batch. Round-robin by file count gave 933s / 206s / 357s / 665s
(run `43029073315`). The split is now longest-processing-time bin packing over per-file seconds
(`mcp/noctusai/tools/noctus/dev/ci_shards.py`, table `scripts/ci/mcp-test-durations.json`; an unknown file weighs
the median). Predicted 540s per shard. `test_compliance.py` stays isolated. Refresh the table from a run's shard
logs (recipe in the module docstring) when a shard drifts more than ~2x from the others. The coverage-proof job
uses the same splitter, so a file can never be dropped or run twice. Owner-approved speedup 5.

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
- **A red batch is attributed before it is bisected (2026-11-11).** Each
  bisect step is a ~50-minute CI run, and a 2-hour stall happened. So on a red
  batch the drain first reads the failing tests (`gh run view --log-failed`,
  `FAILED path::Class::test`), maps each to an area, and compares that with each
  entry's diff against the batch base (`attribute_culprit`, a pure function):
  - `products/<p>/...` test -> that product + `seed/`; `seed/...` -> `seed/`;
    `mcp/...` -> `mcp/`; no readable test id -> only a scoped job name
    (`Product Backend Tests (pytest) (<p>)`, `Seed ...`, `MCP Toolkit Tests`);
  - the migration edge: `verify_db_guards`, `*_on_replay*` and migration-replay
    tests map to entries whose diff adds `products/<p>/.../migrations/*.sql`
    (the product `<p>` when the test names it, e.g. `TestAgentsStudioProbes` ->
    agents; otherwise any migration).
  EXACTLY ONE matching entry is ejected as `ci_red_attributed`, the reason
  naming the failing test and the matching path (it rides the `merge-queue`
  status, so the `MQ-LEFT` line carries it), and the rest go to a fresh
  candidate. Zero or several matches, or an unreadable failure, bisect exactly as
  before; the log line says `ATTRIBUTED` or `bisecting (<reason>)` and each
  round record carries `attribution: {path: attributed|bisect, reason}`. It
  never guesses. Covered by the `culprit attribution` tests in
  `test_merge_queue.py`.

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

- **Workflow-file entries cannot ride the queue (2026-11-05).** The drain
  pushes `mq-candidate/*` with `github.token`, and GitHub refuses any pushed
  *new* commit object that changes `.github/workflows/*` unless the token has
  the `workflows` permission, which `GITHUB_TOKEN` can never have. A rebased or
  merged entry that touches a workflow file was unpushable, and the drain
  raised on the push, wedging the whole queue (17 entries `queued` for ~1.5h).
  Now:
  - compose ejects such an entry up front with kind `needs_workflow_token`
    ("changes .github/workflows/* - the queue's token cannot push workflow
    edits; land via the steward's workflow-file path") and continues;
  - a fast-forward entry reuses its already-pushed commit, so it is not
    pre-ejected;
  - any rejected candidate push is caught, never raised: a "without `workflows`
    permission" rejection ejects the workflow-touching entries with the same
    reason; any other rejection ejects a lone entry (`push_rejected`, with the
    stderr tail) or bisects a batch;
  - the seam is the env var `MQ_PUSH_TOKEN` (see below); with it unset the
    pre-eject above applies unchanged.

  **The token path (2026-11-05).** The owner created a fine-grained PAT
  (contents + workflows write), stored as the environment secret
  `MQ_PUSH_TOKEN` of the GitHub environment `merge-queue`. When it is set the
  queue is workflow-capable: the pre-eject is off, and for a batch whose
  composed diff against dev touches `.github/workflows/` the candidate push and
  the dev fast-forward go to `https://x-access-token:<tok>@github.com/<repo>.git`.
  Every other batch pushes through the plain remote with `github.token`. Why
  only workflow batches: a push made with a PAT triggers push workflows
  (`test.yml`, seed-typecheck, agents-secc-ci fire on a push to dev) while a
  `github.token` push does not, so using the PAT everywhere would double-run CI
  on every landing. The token is redacted from every error, stderr tail and
  status the drain surfaces (`redact()`).

  **Why a dev-only environment and a kick job.** The environment's
  deployment-branch policy allows only `dev`, so only a run whose workflow file
  comes from dev can read the secret; a queued branch could otherwise edit
  `merge-queue.yml` to print it. A run triggered by the `mq/**` push has the
  queue branch as its ref, so `merge-queue.yml` is split: `kick` (push only, no
  secrets, no environment) dispatches the workflow on dev, and `drain` (only on
  `refs/heads/dev`, `environment: merge-queue`) does the work. The concurrency
  group is on the drain job so a kick never waits behind a running drain.

  Covered by `test_workflow_touching_entry_is_pre_ejected_and_the_rest_land`,
  `test_workflow_token_seam_switches_the_pre_eject_off`,
  `test_rejected_candidate_push_ejects_instead_of_raising`,
  `test_workflow_permission_rejection_maps_to_the_workflow_reason`,
  `test_workflow_batch_pushes_candidate_and_dev_via_the_token_url_and_lands`,
  `test_non_workflow_batch_with_token_still_pushes_via_the_plain_remote`,
  `test_token_never_surfaces_in_errors_statuses_or_verdicts`,
  `test_merge_queue_workflow_splits_kick_from_the_dev_only_drain`.

## 8 · Related

`KB § PATTERNS/common/self-branching-mode.md` (the worktree lifecycle around
it) · `KB § PATTERNS/architect/branching-dispatch.md` (dispatch and trains) ·
`KB § PATTERNS/devops/dev-main-ci-gates.md` (what CI gates) ·
`KB § PATTERNS/devops/release-steward.md` (who runs the queue: one elected
session) · `KB § PATTERNS/devops/hardware-admission-budget.md` (the local slot gate, which
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
