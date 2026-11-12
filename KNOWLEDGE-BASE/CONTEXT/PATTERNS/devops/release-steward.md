# Release steward — ONE elected session handles CI queueing and deploy

> **Rule.** Per machine, exactly ONE session holds the CI/deploy role: it
> enqueues to the merge queue, runs `landed`, blesses, promotes, deploys and
> applies prod migrations. Every other session files its delivery in the shared
> outbox and **keeps building** — gated is not blocked. The holder is a
> **leader** (an interactive, top-level session the owner is running), never a
> dispatched subagent. Mechanism: `noctus.dev.release_steward` + the
> `release-steward` PreToolUse hook. Adopted 2026-11-05 by owner order.

## 1 · Why

2026-11-05: the methodology was still drifting. An agent had to be paused so it
would not push to `dev` and get in another agent's way. The CI merge queue
(`KB § PATTERNS/devops/merge-queue.md`) serialises the *merges*, not the
*sessions*: N sessions could still race to enqueue, bless, promote and deploy,
interleave a migration with an image swap, or run two ships at once. A queue is
not coordination, and "be careful" is discipline, not a mechanism
(`KB § PATTERNS/common/gate-methodology-sync.md`). The fix is one owner of the
shared lane, enforced at the first expensive consequence, plus a non-blocking
way for everyone else to hand work to that owner.

## 2 · The ten specs (each is enforced or recorded as shown)

1. **One session per machine holds the role** — enqueue, `landed`, bless,
   promote, deploy, prod migrations. *Lease* `~/.noctus/release-steward.json`
   (flock + atomic replace); `claim` is refused while a live other holder exists.
2. **The holder is a leader, never a subagent.** The hook refuses a `claim`
   made from a dispatched subagent (hook payload `agent_id`); the lease records
   `child_session`. A steward's own subagents share its session id and act
   **under its lease** — they may run its shipping steps when it dispatches
   them to.
3. **On claim the holder announces itself to every peer** (`ListAgents`, then
   `SendMessage` each session) and keeps them informed: `LANDED <dev sha>` /
   `EJECTED <reason>` / `DEPLOYED` back to each requester. The `claim` result
   prints this as its `next` step.
4. **Before ANY queue/deploy action, every session checks its environment:**
   `ListAgents` + `release_steward action=status`. Not elected? See §3.
5. **The hook refuses queue/deploy/push-to-dev from non-holders and names the
   holder.** Override = `NOC_STEWARD_OVERRIDE=<reason ≥10 chars>`, recorded in
   `~/.noctus/release-steward.ndjson` (same shape as `NOC_HW_UNGATED_OK`).
   The MCP tools re-check (`status: refused_not_steward`): one decision
   function, two ends.
6. **Gated ≠ blocked.** A gated session files its delivery with
   `release_steward action=request slug=<slug>` (non-blocking, returns at
   once) and KEEPS BUILDING. Re-filing the same slug keeps the **latest
   `head_sha`**, so a session can keep adding commits and re-queue. Only a
   session with literally nothing else to do may idle — and it still never
   waits on a lane it does not own.
7. **The holder drains the whole outbox at once**: `action=inbox` lists
   pending requests grouped by requester plus the batched drain list; enqueue
   every ready request in one pass (riders batch in the merge queue), `ack` each,
   then report to each requester.
8. **Unreachable peers are covered by the gate, not by messages.**
   `SendMessage` can fail for an idle session. The outbox (what was asked and
   its outcome) and the hook (what is refused) are the record; messages are
   sugar on top.
9. **Handoff.** When the holder ends or goes idle past the TTL, the next leader
   `claim`s (a stale lease is taken over; `handoff to_session_id=…` transfers
   at once, `handoff to_name=…` offers the lane and the named session accepts
   with `claim`) and announces.
10. **Sequencing is the steward's job.** A migration that must precede an image
    (e.g. SW 323) is applied by the holder (`migrate_product confirm=True`)
    BEFORE `deploy_image`; one driver means no one else can interleave a swap
    between the two. Ordered cutovers pin `release sha=`.

## 3 · The election protocol

On session start, and before any shared-lane action:

1. `ListAgents` — who else is running? `release_steward action=status`.
2. A live steward exists → do not claim. File deliveries with `action=request`
   and keep building. Read-only calls stay open.
3. None (or `state: stale`) → the **leader session that has shipping work**
   claims: `release_steward action=claim name=<session name> reason=<why>`, then
   announces to every peer by `SendMessage`:
   `STEWARD <name> (session <id8>): queue deliveries with release_steward action=request slug=<slug>; I reply LANDED/EJECTED/DEPLOYED.`
4. A session with nothing to ship does not claim. Two leaders contending: the
   first `claim` wins (flock); the other files requests.
5. The steward ends (or will idle for long): `release` (or `handoff`) and tell
   the peers; otherwise the lease goes stale after `ttl_s` (default **7200 s**,
   `NOCTUS_STEWARD_TTL_S`; a drain + deploy is tens of minutes and every steward
   call heartbeats) or immediately when its process is gone (`claude_pid`).

## 4 · Message formats (the outbox is the record)

| Direction | Message |
|---|---|
| requester → outbox | `release_steward action=request slug=<slug> [branch=feat/… head_sha=… products=[…] migrations=true notes=…]` (the CLI/SendMessage form: `SHIP-REQUEST slug=<slug> branch=<feat/...> products=<...> migrations=<y/n> notes=<...>`) |
| steward → outbox | `release_steward action=ack slug=<slug> outcome=enqueued\|landed\|ejected\|deployed dev_sha=<sha> notes=<reason>` |
| steward → requester (SendMessage) | `LANDED <dev sha>` · `EJECTED <reason>` · `DEPLOYED` |
| requester reads | `release_steward action=mine` (or `status`) |

Status of a request: `queued_for_steward` → `enqueued` → `landed` → `deployed`
(or `ejected`). New commits after `enqueued`, or any re-request after `ejected`, put it back
to `queued_for_steward` (`requeued: true`); a same-head re-request after
`enqueued`/`landed`/`deployed` is a no-op (`unchanged: true`).

## 5 · What is steward-only, what stays open

| Steward-only (hook + tool refuse a non-holder) | Open to every session |
|---|---|
| `task_branch action=enqueue \| integrate \| landed` with `confirm=True` | `task_branch` status / start / cleanup / train; every dry-run (no `confirm`) |
| `release stage=bless \| promote \| backmerge` with `confirm=True` | `release stage=status \| manifest`, `merge_queue` list/status |
| `deploy_pull`, `deploy_image`, `migrate_product` with `confirm=True`; `record_applied_migrations`; `vps recreate` with `confirm=True` | `deploy_verify`, `vps` ps/logs/health, all read-only tools |
| Bash: `git push` to `dev`/`main`/`prod`/`prod-backup`/`mq/*` (incl. `--all`/`--mirror`), `cli.py` `--task-branch enqueue\|integrate\|landed`, `--release bless\|promote\|backmerge`, `--deploy-pull`, `--deploy-image`, `--migrate-product` each with its confirm flag | `git push origin feat/<x>` (your own branch), `git push --dry-run`, `release_steward` itself (`claim`, `request`, `status`, `mine`, `inbox`) |

## 6 · Mechanism

- **Session binding.** Claude Code starts one MCP server per session and gives
  it `CLAUDE_CODE_SESSION_ID`; the hook receives the same value as
  `session_id`. Both ends compare it to the lease. Subagents share the parent's
  id. After `/clear` the id can change: re-`claim` (a same-process lease is taken
  over via `claude_pid`).
- **Files** (`~/.noctus/`, override dir with `NOCTUS_STEWARD_DIR`):
  `release-steward.json` (lease), `release-steward.ndjson` (audit: claim, takeover,
  handoff, release, override, unattributed), `ship-requests.ndjson` (append-only
  outbox; state is folded per slug, latest wins).
- **Hook** `scripts/hooks/claude-guard-release-steward.py` →
  `tools/noctus/dev/release_steward.py::decide` (fail-closed via
  `_guard_failclosed.run_guard`, marker `[noc-guard:release-steward]`). Registered
  in `.claude/settings.json` for `Bash` and the steward-class MCP tools. The deny
  message names the steward and says: *queue it with release_steward action=request
  slug=<slug> and keep building — do not wait*; with no steward elected it says to
  run `ListAgents`, then claim (leaders) or request.
- **Backstop.** `task_branch`, `release`, `deploy_pull`, `deploy_image`,
  `migrate_product`, `record_applied_migrations`, `vps recreate` call
  `release_steward.tool_refusal` first (`ok: False, status: refused_not_steward`).
  A caller with no session identity (CI, an ops script) is allowed but audited
  `unattributed` — never silent.
- **Deliberate limits.** Token scanning of Bash, not a shell interpreter
  (`$(…)`, aliases, scripts that push internally, raw `ssh … docker compose` are
  not resolved) — CI, the pre-push keeper and `check_primary_checkout_commit`
  remain the backstops. A peer worktree forked before this landed has the old
  `.claude/settings.json` until it rebases onto `dev`, so its hook is not yet
  active (its tool-layer backstop applies after `/mcp` reconnect). Claude Code
  snapshots hooks at session start: a running session picks the hook up on
  restart or after reviewing it in `/hooks`.

## 7 · Bootstrap (first claim, and why the hook cannot lock the steward out)

`release_steward` itself is never denied, and the hook denies a steward-class
call only when no live steward is elected — so the very first step is allowed.
From any session (the Bash environment already carries the session id):

```
python mcp/noctusai/cli.py --release-steward claim --steward-name <name> --steward-reason "CI + deploy steward"
```

(or MCP `noctus.dev.release_steward action=claim name=<name> reason=…`). Then
`ListAgents` and `SendMessage` the announcement. `--steward-session-id` overrides
`$CLAUDE_CODE_SESSION_ID` for an operator acting for another session.

## 7a · Ejection flow (the branch steward fixes; not live until build 4 inbox fields; end predicate not live until builds 3+5)

Guardian spec, council 09340534 (dispositions A: the guardian is a service leaf whose authority is the lane only; B: a rejected delivery returns to its steward, not to a rescue branch; K: ejection fixes belong to the branch steward). It supersedes the rescue-branch flow of the 2026-11-10 queue-lifecycle decision (council a341e383, `project-history/assistant-chatbot/queue-lifecycle-decision.md`) and the older `merge-queue.md` §4 "the owning session fixes".

1. **Diagnose** from the failed log (`noc-steward` §3).
2. **Withdraw and tell.** The guardian withdraws the `mq/*` ref, writes `ejected{reason, conflict, url}` to the outbox, requeues the other riders, and notifies the branch steward's **ROLE** (resolved through the role registry at send time; owner fallback).
3. **Ask once, if needed.** An inbox `needs_info` record to that ROLE, one batched question, TTL about one CI cycle (~25 min). Method: `noc-questionnaire` peer mode.
4. **The branch steward fixes it** on its own branch and files `request` again (the `deliverable` preflight runs again at filing). The guardian never patches the branch, never opens a rescue branch and never dispatches an engineer for it.
5. **Two strikes.** After 2 ejections the delivery parks as `blocked_on_steward` until its steward re-files a fix the preflight accepts.
6. **Orphan.** If the steward's session is gone, or silent past the TTL, the delivery stays `blocked_on_steward`. The guardian alerts the owner, and the OWNER names a new branch steward, who adopts the branch (role registry `to_session_id=`). The guardian never adopts it itself.
7. **End predicate** (`release_steward mine`, builds 3+5): a requester may end only when its requests are LANDED (plus DEPLOYED if asked) or handed to a successor steward the owner named, it has no open `mq/*` ref, and no CI run it depends on is in flight. Teardown rules: `background-agent-lifecycle.md`.

## 8 · Reboot / multi-steward (2026-11-09/10)

After a machine reboot sessions return under NEW names, so a name is not an identity — a ROLE is.

- **Role registry** (`release_steward action=role role=<role> [name=] [op=clear] [to_session_id=]` · `action=roles`;
  `~/.noctus/release-steward-roles.json`). Any session sets its own role; setting another session's is
  steward-only. `dev-steward` is DERIVED from the lease (not settable); `branch-steward:<branch>` is the second kind
  (below); others are free (`agents`, `sw-product`, `assistant`). `status`/`roles` flag a role whose session is
  dead/stale (pid gone or no heartbeat past the lease TTL; every action refreshes the caller's roles). `claim`'s
  `next` says: announce AND re-map roles.
- **Dev steward vs branch steward.** The dev steward holds the lease and is the only one touching mq/main/VPS. A
  branch steward (e.g. `branch-steward:feat/assistant-chatbot`) merges its sub-slices into its integration branch and
  DELIVERS that branch to the dev steward with `action=request`; it never enqueues or deploys.
- **Consent is typed in the session that runs the action** (`KB § PATTERNS/devops/ship-consent-riders.md`): tell the
  owner the ROLE ("the dev steward"), never a session name that a reboot invalidates. **Consent phase
  `pre-third-users` (owner decision 2026-11-11; revisit when a 3rd user onboards):** the owner's plain deploy / go-to-prod
  ask, typed in the steward's own transcript, is the go for bless/promote/deploy AND prod migrations - no exact wording,
  no per-slice sha or migration filenames (chair ruling 59c61ef0 superseded for this phase). A relayed ask is still not
  consent. `KB § PATTERNS/devops/prod-exposure-consent.md` § Consent phase.
- **Parked branches must not hold a migration number**: renumber (`next_migration_number`) before reviving one.
- **Inbox auto-reconcile.** `inbox`/`status` judge each request against `origin/dev` (ref order: `<branch>`,
  `origin/<branch>`, `head_sha`) with three methods, recorded per outcome as `method`:
  1. `cherry` - `git cherry`: zero `+` lines (patch-ids all present) => `already_landed`.
  2. `post_image` - when cherry leaves commits unmatched (rebase with conflict resolution, squash, `--no-ff` train
     all change patch-ids): for every file the branch changes vs its merge-base, dev's blob equals the branch head's
     blob (deleted == deleted) => `already_landed`.
  3. `range_diff` - otherwise `git range-diff <mb>..<branch> <mb>..<dev>`; every branch commit marked `=` =>
     `already_landed`.
  A PARTIAL match (some files equal, some not, or range-diff `!`) lands in the NEW `uncertain` group with
  `evidence` (matched/unmatched files, range-diff marks). `uncertain` is NEVER auto-acked: `inbox.next` leads with
  `UNCERTAIN`, `reconcile` returns it, and a `reconcile_uncertain` audit row is written; the steward decides by hand.
  No match at all => pending; unresolvable ones are listed in `unresolvable`, never dropped. The fallback runs git
  with cwd = the git common dir (never the primary work tree). `action=reconcile confirm=True` (steward) acks all
  already-landed in one call.
- **Split delivery.** `request branches=[feat/a, feat/b]` (ordered): `drain` emits ONE `task_branch action=train` then
  ONE enqueue of the train. A request whose notes say "together"/"two branches"/a second `feat/` name without
  `branches=` returns a warning.
- Telemetry: `role_set|role_clear|reconcile|reconcile_uncertain|train_drain` rows in `release-steward.ndjson`.

### 8a · Withdrawal and the exchange record kinds (2026-11-10)

- **`withdrawn`.** `ack outcome=withdrawn notes=<reason>` (steward; the reason is required) or `action=withdraw slug=`
  (the requesting session or the steward; a third session gets `refused_not_requester`). A withdrawn row leaves `pending`
  and `drain`, hides from `mine` unless `include_done`, appears under inbox `include_done`, and writes a `withdraw` audit
  row. A later `request` for the slug re-opens it as a new revision (`requeued: true`), like any re-file.
- **One record type, a `kind` field**, appended to the same outbox (append-only, same lock, history never rewritten):
  `request` (default; every request row carries `kind: request`), `needs_info`, `position`, `decision`.
  - `needs_info` (`action=ask slug= question= [addressed_to=<role> deadline_min=30]`, steward-only): ONE bounded question
    with an id `ni-N`, `addressed_to` (the registered role's session, else the requester session, with a warning if the
    role is unregistered), `deadline_ts` (default now + 30 min) and `owner_fallback: true`. `mine` shows the addressee its
    open/expired items.
  - `position` (`action=position slug= notes= [ref=ni-N]`): the answer (`ref` defaults to the latest unanswered
    needs_info addressed to you) or a peer's stance. An answer after the deadline still counts.
  - `decision` (`action=decision slug= notes=`, steward-only): the final call; it does not change the request status and
    retires the slug's answered/expired threads from the inbox.
  - `inbox` lists answered/expired `needs_info` under `needs_info`; an expired one with no `position` is also under
    `escalate_to_owner` and named in `next`. Nothing is sent automatically: surfacing only.
- Telemetry: `withdraw|needs_info|position|decision|needs_info_escalate` rows in `release-steward.ndjson`.

## 8b · The guardian model (ratified 2026-11-10)

The lane holder is a **guardian**: a service leaf under the owner whose authority covers the *lane* (queue, merge into
`dev`, deploy, watch), never content or priorities. Each branch is owned end to end by its **branch steward**. The two
meet at one read-only contract, so the guardian never has to touch a branch.

### Glossary

| Term | Meaning |
|---|---|
| **guardian** | The `release_steward` lease holder (a.k.a. dev steward): queues, merges into `dev`, deploys, watches the queue. First filed, first served; the owner may override the order, and a delivery that blocks the queue jumps it. |
| **branch steward** | The session that owns ONE branch end to end: dispatches its team, makes the branch meet the delivery contract, files `request`, fixes its own ejections, and stays alive until the delivery lands. Branch-tree pointer `role=steward` marks its (long-lived) branch; role registry `branch-steward:<branch>` names the session. |
| **delivery** | One filed `request`: a branch (or an ordered train of branches), its pinned `head_sha`, `products`, `migrations`, and the `verdict_ref` for item 5. Latest head wins on re-filing. |
| **deliverable** | The verdict of the read-only `deliverable(branch)` preflight: all five contract items pass. |
| **needs_resync** | The verdict when any item fails. The delivery goes BACK to its branch steward naming the failing item(s); it is recorded (`mine` shows status `needs_resync`) and never reaches the guardian's `drain`. The guardian may also `ack outcome=needs_resync notes=<why>` when its pre-enqueue re-run fails. |

### Roles

| | Guardian | Branch steward |
|---|---|---|
| Does | queues (`enqueue` = pure push), `landed`, merges into `dev`, deploys, watches the queue, re-runs `deliverable` before every enqueue | dispatches its team; makes the branch meet the contract (merge `dev` in, renumber, regenerate derived files, run the scoped suites); `request`; fixes its own ejections; stays alive until landed |
| Post-landing tail | runs `landed` only for deliveries it owns or when asked; gets the ownership skips (`skipped_owned`) on anyone else's worktree | **owns it**: once its work is on `origin/dev` and its worktree is clean, the branch steward (requester / pointer session / worktree-claim holder) runs `task_branch landed` itself - pointer, primary FF, worktree cleanup. The guard allows exactly that and nothing else of the steward class |
| **NEVER** | edits, rebases, merges into or renumbers a delivery branch; runs a mutating git command in a worktree it does not own; writes feature code or steward tooling; arbitrates content; deploys to prod without consent the owner typed in its own session; removes a worktree/branch it does not own (`skipped_owned`) | enqueues, deploys, touches `mq/*`, `main` or the VPS, or uses the override |

### Delivery contract: `deliverable(branch)`

ONE read-only check (`release_steward action=deliverable slug=|branch=`, open to every session; code:
`release_steward.deliverable`). `request` runs it at filing; `task_branch action=enqueue` runs it again before it pushes. Read-only
by construction: its git calls pass an allowlist (no checkout/merge/rebase/commit/add/push; `worktree` only as `list`;
`status` with `--no-optional-locks`); the trial merge runs with its cwd inside the git dir (merge drivers drop scratch files
in the cwd); derived files are regenerated in a `git archive` export, never in the worktree. **G1 - what it may touch:**
the remote-tracking `origin/dev` ref (`fetch --no-write-fetch-head`; enqueue's own fetch likewise: no `FETCH_HEAD`), loose
objects from `merge-tree`, and the shared verdict store / enqueue attestation below. Never a work tree, an index, HEAD or a branch.

| # | Item | Passes when |
|---|---|---|
| 1 | `head_pushed_clean` | local head == `origin/<branch>` (`ls-remote`) AND the branch's worktree has no real dirt (known-benign refresh artifacts and untracked files are not part of the head) |
| 2 | `merge_buildable` | `origin/dev` is an ancestor of the head, OR `git --attr-source=<dev tip> merge-tree --write-tree origin/dev <head>` is clean. NOT strictly 0-behind: demanding that livelocks while `dev` moves. **Attributes (`merge=union`, the kb-counts/lgpd/gate-inventory drivers) come from DEV only** - a bare-context trial merge reads none, which made every ledger/counts touch a conflict; and never from the head, so a branch cannot declare its own conflict away. A conflict names its files |
| 3 | `migrations_free` | no migration number the branch adds is claimed by a different file in the composed tree (the head, or the merge-tree result). Reuses `task_branch._MIGRATION_NUM_RE` and the keeper's accepted-duplicates set via `migration_number_collisions` |
| 4 | `derived_current` | every derived artifact is already current AT the head: `--update-kb-counts --check`, `--render-project-history --check`, `--gen-promotions-index --check` against an export of the head (table `DERIVED_ARTIFACTS`; a missing regenerator is UNMEASURED, never green). The export must equal `git ls-tree -r <head>` (an `export-ignore` difference is UNMEASURED) and runs in the hermetic env with `PYTHONPATH` = the HEAD's seed packages (derived from its `requirements.txt` `-e` lines; EVERY top-level seed package under those paths, plus `noctusai_lib` and `noctusai_seed` when the
head ships them, must import from inside the export, else UNMEASURED), so it never judges the primary's seed lib |
| 5 | `scoped_green` | the scoped suites are green **the way CI judges them** (below) |

Not measurable is never green: an item that cannot run fails as `UNMEASURED`.

**Item 4 also carries `cli.py --help` (4b, folded in).** When the delivery's diff vs `origin/dev` includes `mcp/noctusai/cli.py`, the HEAD's
`cli.py --help` is run in the export (hermetic env, the head's seed packages; never the worktree) and a non-zero exit fails
item 4, naming the stderr tail. Why: argparse %-formats every help string, so a literal `%A` in a new `--help` text crashes the whole CLI and
every `cli.py --<flag>` gate with it (merge-loss-gate was ejected on exactly that, 2026-11-10; before this it was discipline in the
noc-steward skill). The result lists a `cli-help` artifact: `skipped: true` (and the detail says so) when the delivery does not touch
`cli.py`; when it runs, a `deliverable:cli-help` row (`pass`/`deny`) lands in the same gate-event sink as the other gates.

**Item 5 runs what CI blocks on, in the environment CI has (D1, merge-queue run 42753204233).** Two things passed locally and
failed in CI: keepers that only WARN in pre-commit but BLOCK in CI (the mcp-first-scripts manifest rows, `check_gate_triad`'s
inventory row), and a test that passed only because `CLAUDE_CODE_SESSION_ID` was set. So:

- *The CI-blocking set is derived, never listed.* From the head's own CI definition: (a) every `cli.py --check-*` step of
  `.github/workflows/test.yml` that is not `continue-on-error` and needs no CI-resolved argument (`ci_blocking_flags`);
  (b) every test in `mcp/noctusai/tests/` that asserts a `check_*` keeper returns `[]` on the live tree, found by AST
  (`ci_keeper_test_ids`: the "real tree is clean" tests that make a pre-commit warning a CI block), always; (c) the
  suites of what the diff touches DIRECTLY (`local_suites`): a `seed-backend-tests` matrix root the diff edits, and a
  `product-backend-tests` matrix product the diff edits that is awake (`deploy/fleet/active-scope.txt`). The scope is
  `ci_scope.classify` over `origin/dev...head` - the SAME module the workflow's `changes` job calls (the classifier left
  the inline bash so the two can never disagree; base selection, which depends on the GitHub event, stays in the
  workflow). Why (c): three deliveries went 5/5 and were ejected on suites the diff selected in CI
  (`test_all_products_compliant[core]` - a seeded icon; the seed suite + `test_vps_exec.py` - a seed change; a product
  FE test), 2026-11-10. **Narrowed by the owner, 2026-11-11:** running CI's FULL split locally (the toolkit shards + every
  awake product on a shared-root change) measured **2h04m** on one heavy slot versus ~15-25 min in CI's parallel jobs, so
  the toolkit split and the shared-root fan-out are judged by the merge queue only. Stated trade-off: a toolkit-only red
  (the `test_all_products_compliant[core]` shape) can still eject in the queue. The run holds ONE machine-wide heavy slot
  (`hw_admission.heavy_slot`; not admitted = `UNMEASURED`, never green). **Migration → DB-guard edge (owner, 2026-11-11):** a
  diff touching `products/<p>/backend/migrations/*.sql` also runs `test_verify_db_guards.py` + that product's PGlite
  `*replay*` tests + the generic `test_migration_*` ones (`migration_guard_suite`) - the toolkit-only red that stalled the
  queue 2h (agents 079 → `TestAgentsStudioProbes`). PGlite is linked from the source checkout only when
  `mcp/noctusai/node/package-lock.json` is byte-identical (`link_pglite`); otherwise `UNMEASURED`. **Gap, `NOC-REMEDIATE[scoped-green-fe-and-tooling]`:**
  FE vitest and the bespoke `tooling-tests` job stay CI-judged only (no `node_modules` in the export; tooling-tests renders
  a template in bash) - a branch steward touching a product FE or an MCP connector server (`mcp/<connector>/tests`) runs that suite itself before filing.
  CI's "Prime hermetic state" step is replayed first (`ci_prime_flags`).
- *The env is scrubbed the way CI's is.* `hermetic_env`: OS basics only (`HERMETIC_BASE_ENV`) plus the toolkit job's own
  `env:` plus `CI=true`. Everything else (`CLAUDE_*`, `ANTHROPIC_*`, `OPENAI_*`, `SUPABASE_*`, `NOC*` ...) is absent, because it is
  absent on a runner.
- *The verdict is a RECORD, not a string.* `run_scoped=true` (`export_ci_parity_check`) APPENDS a record to the append-only
  store `~/.noctus/deliverable-verdicts.ndjson` (DI seam; `record_verdict`): the full head sha, the head tree, the `test.yml`
  blob, the interpreter, the flags and test ids it ran, and `ok`. It returns `ci-parity:<id>`. Item 5 accepts only that ref
  (`validate_verdict_ref`): it resolves the id, requires an EXACT full-sha (and tree) match, `ok=true` and the env-scrubbed /
  CI-keeper markers the run itself set. Free-form strings, short shas, another head's record and RED records are refused.
  (A local file is not tamper-proof against an agent with shell access; it closes the typed-string forgery and the
  stale-head reuse, which is what the contract is for.) Running takes minutes, so the branch steward runs it once and files the ref.
- `release_steward action=deliverable slug=<s> run_scoped=true` (CLI `--steward-run-scoped`) RUNS the CI-parity check
  (`export_ci_parity_check`) and its result carries the `ci-parity:<id>` ref to file with the request (also for a RED run, which then
  refuses as RED).
  The check runs in a **throwaway git checkout** of the export (`_git_init_export`: `git init` + one commit in the temp dir, global/system git
  config ignored; never the requester's worktree, never the real repository): CI runs in a checkout, `--stamp-seed-version` needs git
  and the keeper-mirror caches live under the git dir (first live use: "prime step failed" with only the banner as detail). A failing
  step reports its exit code and the last ~20 MEANINGFUL lines (`meaningful_tail`: ANSI, banner and INFO lines stripped); every red keeper flag
  carries its last error line. `request run_scoped=true` is never ignored: it runs this check on the branch head, files with the `ci-parity:<id>`
  it mints (red -> `needs_resync` via item 5; an UNMEASURED run -> `needs_resync` naming the reason) and refuses what it cannot honour
  (no runner configured, a multi-branch train: one record judges ONE head).

### Enqueue, cleanup and the pre-push hook

- **`task_branch action=enqueue` is a pure push**: `git push origin <sha>:refs/heads/mq/<slug>--<sha7>`, after `deliverable` passes.
  No checkout, merge, rebase, commit, stash or file write in any worktree; a failing branch returns `status=needs_resync`
  (exit 1) naming the items. `branch=` accepts the real branch (a docs- or fix-prefixed one, not only feat-prefixed); otherwise the slug resolves among the
  conventional prefixes and an ambiguous slug refuses. `scripts/hooks/pre-push` recognises exactly this push as the queue path
  (see `merge-queue.md` § 2a). The slug is validated with the request rule (`[A-Za-z0-9._/-]+`, no `..`). Right before its push
  enqueue writes an **attestation** `<git-common-dir>/noc-enqueue/<full sha>.json` (the `deliverable()` verdict, timestamp and the ONE
  fully-qualified queue `ref` it authorises); the hook's queue path requires a fresh (< 10 min) ok attestation for exactly that sha AND
  that ref, exactly ONE mq ref per push, and a bare full sha as the local side (`HEAD:`/branch forms are refused), so typing the
  refspec by hand cannot skip the contract. A `needs_resync` re-check or a rejected push REVOKES an earlier ok attestation.
  All refs are fully qualified (`refs/remotes/<remote>/<dev>`, `refs/heads/<branch>`): a branch or tag NAMED `origin/dev` or
  `feat/<slug>` cannot make the head read as dev, redirect what is pushed, or let cleanup delete unmerged work; the request's
  head is compared in full, never by a 7-char prefix.
- **`landed` / `integrate` auto-cleanup / `cleanup` never remove what is not the caller's**: a worktree claimed by another
  session that is not dead (`harness_claim_worktree`; `unknown` counts as live), a branch whose pointer has `role=steward`, or - on
  the AUTO path - a branch whose pointer session is another live/unknown session, is reported
  `cleanup: {status: skipped_owned, owner, reason}` and the landed verdict is unaffected. A steward (or the pointer's own session)
  may clean its branch with an explicit `cleanup`; the auto path never does. The auto path **fails closed**: if the pointer store
  was not fully readable (exception, or `origin/ledgers` unreadable and answered from the dev copy), or nothing says whose the
  worktree is (no pointer carrying a session and no claim by the caller: `source: no_pointer`), it skips the deletion with owner
  unknown. A corrupt or unreadable worktree-claims file counts as OWNED (`claims_unreadable`), never as "no claims", and claim
  writes take an flock. A DIRECT `cleanup` by a session that is not the branch pointer's also leaves a live/unknown pointer
  session's worktree alone; with the pointer's own session it keeps the old behaviour, and an unreadable pointer store on a direct
  cleanup still proceeds (an explicit act - the verdict is never failed over a pointer failure). The nested cleanup receives the exact branch and the checked worktree and refuses
  (`refused_branch_mismatch`) if the worktree holds a different branch. `dead` needs the recorded pid gone AND the heartbeat older than
  the TTL; every action re-records the caller's pid (`role_touch`), a stale pid alone is not dead.
- **What is and is not protected (honest G3).** `scripts/hooks/pre-push` refuses client-side pushes to `main`/`prod` (the sanctioned
  `release` tool sets the override). Server-side, GitHub ruleset **#26931674 `dev-no-rewind-no-delete`** is active on `refs/heads/dev`
  (rules: deletion + non_fast_forward; no bypass actors; created 2026-11-10 on the owner's decision): `dev` can be neither deleted nor
  rewound, but any session with write access can still fast-forward it, and the legacy `integrate` pushes `dev` by design (the
  queue-down fallback). The queue path is guarded by the attestation above, not by the server. **Phase 2 is awaiting_owner**: a dedicated
  queue identity (a GitHub App) as the ONLY bypass/push actor for `dev`; it needs the owner's decision and the repo-admin setting. Until
  then the attestation is a guard against accidents and a typed-refspec bypass, not against a session that deliberately writes the
  attestation or fast-forwards `dev` itself.
- **Guardian tool authorship (separation of duties; owner-approved 2026-11-10).** `check_guardian_tool_authorship` refuses a commit
  staging protected tooling while the committing session holds the live guardian lease. The protected set is DERIVED
  (`derive_guardian_protected_files`, AST import walk, never hand-listed): `release_steward.py` + `task_branch.py`, every
  `tools/noctus/dev` module either imports anywhere (lazy imports included), those modules' module-level transitive imports, plus the
  anchors `scripts/hooks/pre-push`, `scripts/hooks/claude-guard-release-steward.py`, `scripts/hooks/claude-guard-session-heartbeat.py`,
  `.github/workflows/merge-queue.yml`, `prod_consent.py`, `ship_consent.py`. `compliance.py` (the keeper registry every gate edits) is
  the one deliberate exemption (residual `NOC-REMEDIATE[guardian-keeper-self-edit]`: the guardian can still neuter the keeper via
  `compliance.py`, `scripts/hooks/pre-commit` and the `cli.py` dispatch until phase 2, the queue-only GitHub App push identity plus a
  CI-side authorship check). The keeper derives from HEAD UNION the index, never the working tree. The set is pinned as a snapshot in `test_check_guardian_tool_authorship.py`, so a new import is a test
  diff in review. If derivation fails the keeper fails CLOSED for the guardian (refuses) and records an `unmeasured` row.
- **Derived/CI-parity checks are sandboxed.** Items 4/5 (`export_derived_check`, `export_ci_parity_check`) run the delivery's own
  `cli.py`/tests with a throwaway HOME, `GIT_CONFIG_NOSYSTEM=1`, `GIT_CONFIG_GLOBAL` = an empty file, and every inherited `NOCTUS_*` key the CI
  job env does not declare DROPPED (derived via `ci_job_env`, no hand-kept list), so the guardian's real `~/.noctus` is never written; a sandbox that cannot be set up is
  UNMEASURED (fails). Residual: this is environmental, not a kernel FS sandbox (macOS has no unprivileged one) - a delivery hard-coding an
  absolute path can still write it; the export-from-`git archive` isolation and the branch steward's review cover that.
- **Heartbeat from a hook.** `scripts/hooks/claude-guard-session-heartbeat.py` (SessionStart + UserPromptSubmit) calls
  `StewardStore.role_touch(session_id, claude_pid)` so a quiet but alive session does not age toward `dead`. Advisory: always exit 0,
  fail open, ~1s deadline, at most once per 60s per session, an error telemetry row only. It refreshes the caller's OWN role rows
  (heartbeat + pid together, pid = nearest `claude` ancestor, else heartbeat only); it never touches the lease or other sessions' rows,
  so it cannot make a guardian whose pid changed pass the lease check, and `dead` still needs the pid gone AND the heartbeat past the TTL.
- Failures, takeover and prod consent (ejection -> `ejected{reason, conflict, url}` and requeue, 2 ejections -> `blocked_on_steward`;
  stale-guardian takeover that may only resume or roll back; one plan hash per deploy window) are the ratified spec and are
  tracked as follow-ups; this section records what is built.

## 9 · Related

`KB § PATTERNS/devops/merge-queue.md` (the queue this role feeds; §4 session
rules) · `KB § PATTERNS/devops/hardware-admission-budget.md` (the machine-wide
flock-lease pattern this reuses) · `KB § PATTERNS/devops/ship-consent-riders.md`
§ Concurrent sessions · `KB § PATTERNS/common/self-branching-mode.md` ·
`KB § PATTERNS/common/gate-methodology-sync.md` · `KB § PATTERNS/common/orchestration-family-index.md` ·
`KB § PATTERNS/architect/orchestration-craft-canon.md` (session↔session peer protocol) ·
skills `noc-ship` · `noc-self-branch` · `noc-branch-dispatch`.
