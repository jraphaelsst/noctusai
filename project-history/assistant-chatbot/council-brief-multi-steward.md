# Council brief: how should branches, queue and prod delivery be organized when several stewards work at once?

## The question (from the owner, verbatim intent)
The owner is studying how to coordinate multiple "steward" sessions working on multiple branches at the same time. Decide how trees and deliveries should be handled under multi-steward work. In particular: should there be **one queue mechanism that serves all stewards in parallel**, or should **one single agent be responsible for delivering to prod**? Other shapes are allowed. Give a recommended model, its failure modes, and what must be built or changed to get there.

## Definitions
- **Session**: a top-level interactive Claude Code session the owner runs on one Mac (8 GB RAM). Several run at once. Session names change on every restart.
- **Steward**: a session that owns an integration responsibility. Today there are two kinds:
  - the **release steward**, one per machine. It holds a lease and is the only session allowed to run enqueue, landed, bless, promote, deploy and prod migrations;
  - a **branch steward**: a session that owns a long-lived integration branch (e.g. `feat/assistant-chatbot`). It merges its own sub-slices into that branch and hands the branch to the release steward as a delivery.
- `dev` = integration branch; `main` = production; prod = one VPS.

## How it works today (facts)
- **Path into dev = the merge queue** (`KNOWLEDGE-BASE/CONTEXT/PATTERNS/devops/merge-queue.md`, code `mcp/noctusai/tools/noctus/dev/merge_queue.py`, `.github/workflows/merge-queue.yml`, `task_branch.py`, `task_branch_train.py`).
  - **Enqueue, local:** `task_branch enqueue` rebases, runs a migration-number collision gate and renumbers, checks doc staleness, regenerates KB counts and runs the pre-push keepers. Then it pushes `mq/<slug>--<sha7>`.
  - **The drain on GitHub Actions is serialized** in one concurrency group:
    - It takes the oldest ≤ batch_limit entries and composes them on dev as `mq-candidate/<run>-<n>`.
    - It runs the full suite, about 13–25 min per batch. Runner minutes are free.
    - Green: dev fast-forwards.
    - Red: the batch is halved (first-half bisect) and suspects are retried first. A red singleton is ejected.
    - A conflict, a duplicate migration number or a failed derived-file regeneration ejects the entry; nothing is auto-resolved.
  - One ejection costs about one CI cycle. There are no per-product lanes. Every job has a timeout, because a hung job blocks the whole queue.
  - An off-host watchdog alerts the owner (WhatsApp/email) on LANDED, EJECTED or STALL every 10 min.
- **A train** (`task_branch action=train slugs=[...]`) merges several branches `--no-ff` into one branch, which enters the queue as ONE entry.
- **The release steward** (`KNOWLEDGE-BASE/CONTEXT/PATTERNS/devops/release-steward.md`, `mcp/noctusai/tools/noctus/dev/release_steward.py`):
  - **Lease:** one per machine, in `~/.noctus/release-steward.json`, with a 7200 s TTL and a heartbeat.
  - **Hook:** a PreToolUse hook denies steward-class calls to non-holders. An override exists and is recorded.
  - **Inbox:** other sessions file `release_steward request` into it, and it drains in one pass.
  - **Origin:** it was adopted on 2026-11-05. Before the queue, parallel sessions collided on dev and one agent had to be paused. Rationale recorded at adoption (release-steward.md): the queue serialized merges, but parallel sessions could still race on bless/promote/deploy or interleave a migration with an image swap. No such race has been measured since; no counter-measurement exists either.
- **Release to prod** (`KNOWLEDGE-BASE/CONTEXT/PATTERNS/devops/ship-consent-riders.md`, `.claude/skills/noc-ship/SKILL.md`):
  - bless = fast-forward main to the newest CI-green commit in main..dev;
  - mandatory `predeploy_check`;
  - prod migrations, which need the owner's consent TYPED in the session that runs them; a relayed consent is refused by design;
  - `deploy_image` per product, which auto-rolls back on a failed health check, then smoke checks.
  - Deploys are serial on one shared VPS. There is no dev fleet, so prod is the first place a running image meets real conditions.
- **Current practice (2026-11-10):** one lease-holding release steward for queue + prod, plus one branch steward for feat/assistant-chatbot delivering stage entries into the single queue.

## Observed failure modes
1. **Split delivery.** A BE+FE pair meant to ship together went in as 2 entries. BE was ejected by an environment-dependent test and FE landed alone, so the product can't be deployed.
2. **Stale lease after a machine reboot.** Nobody owned the queue until the owner re-assigned the role by hand.
3. **Handoffs that named sessions** ("type it to noc-0") broke when names changed on restart. There is no role→session registry. Fresh sessions guessed their role.
4. **The inbox kept already-landed requests** as queued; they were reconciled by hand.
5. **A parked branch held a migration number** that blocked another session's enqueue.
6. **Merge drivers configured with absolute paths into the primary checkout** leave transient files behind, and a drift guard blamed whichever session was merging.
7. **A 50-minute bisect.** A keeper baseline missed a dev migration, and three batches went red on one entry.
8. **A red batch from a cross-entry effect** (a contract path plus a component-name clash). File-disjoint is not effect-disjoint.
9. **Derived artifacts** (KB counts, baselines, lockfiles) couple parallel entries.
10. **Consent relays** between sessions were refused by design, each costing an owner round-trip.
11. **Single point of ownership.** While the lease was stale (failure 2), and during each owner consent round-trip (failure 10), every session's delivery waited on one session's availability; deliveries were filed but nothing landed.

Note: `.claude/skills/noc-steward/SKILL.md` exists on `dev` but not in the branch worktree; read it with `git show origin/dev:.claude/skills/noc-steward/SKILL.md`.

## Shapes on the table (unordered; none is preferred)
- **A.** One queue mechanism that serves all stewards in parallel: any steward may enqueue, land and ship.
- **B.** One single agent responsible for delivering everything (queue + prod).
- **C.** Many stewards enqueue in parallel into the one serialized queue; one lease-holding prod releaser blesses, migrates and deploys.
- **D.** Per-product queue lanes (path-scoped batches and suites), with prod release single or per product.
- **E.** A branch-steward tier: integration branches aggregate sub-slices under their own steward and deliver large entries into the single queue.
- **F.** Per-steward leases scoped by product, for both queue and deploy, plus a coordination rule for cross-product changes (seed/lib, CLAUDE.md, shared schemas).
- Combinations or other shapes are welcome.

## Constraints
- The owner wants no idle waiting: "gated is not blocked".
- Consent must be typed in the acting session.
- The migration-number collision gate is per product.
- Deploys are serial on one VPS.
- The 8 GB Mac needs hardware admission for local heavy gates.
- Seed/lib changes affect every product's suite.
- The methodology rule says enforceable things ship as construction + gate + telemetry together (`KNOWLEDGE-BASE/CONTEXT/PATTERNS/common/gate-methodology-sync.md`).
- Sessions die and restart, and the model must survive that.

## Evidence to open
The files named above, plus `KNOWLEDGE-BASE/CONTEXT/PATTERNS/common/branching.md`, `KNOWLEDGE-BASE/CONTEXT/PATTERNS/common/orchestration-family-index.md` and `.claude/skills/noc-steward/SKILL.md`. The study log of the current two-steward run is at `project-history/assistant-chatbot/multi-steward-study.md`.
