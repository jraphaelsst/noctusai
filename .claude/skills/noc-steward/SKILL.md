---
name: noc-steward
description: Use when this session is (or is asked to become) the release steward that guards the CI merge queue — triggers "you are the steward", "be the steward", "finish the shipment", "plan the merge queue", "ship everything", "watch the queue", "guard the queue", "drain the inbox", "is the queue moving?", "how's the queue going?", "batch red", "entry ejected", or any peer request (`release_steward action=request`) arriving in your inbox. The live loop: claim, enqueue, watch with ONE feed, act on every red within minutes, land and reply, then ship.
version: 1.0.0
---

# noc-steward — guard the merge queue, then ship

The steward is the ONE session that enqueues, runs `landed`, withdraws, blesses, promotes, deploys and applies prod migrations (`KB § PATTERNS/devops/release-steward.md`). Every other session files `release_steward action=request` and keeps building. The queue is the only path into `dev` (`KB § PATTERNS/devops/merge-queue.md`).

**Why this skill exists.** Twice the queue stalled with nobody knowing: 2026-11-08, a bad keeper baseline failed three ~50-min bisect batches (3.5 h silent); 2026-11-09, the owner saw batch 9 red before the steward did. An entry-only watch is silent through a bisect, because nothing leaves the list. Silence is not a pass.

## 1 · Take the role

1. `ListAgents` + `noctus.dev.release_steward action=status`. Stale or no holder ⇒ `claim`, announce to every peer (`SendMessage`).
2. `release_steward action=inbox`: drain it in ONE batched enqueue pass (`task_branch action=enqueue slug=… confirm=True`), `ack` each.
3. Write the shift into a memory file `project_ci_steward_<date>_<name>.md`: the plan, the holds, the consents (verbatim, with where they were typed), and a log line per event. It is what survives a compaction.

## 2 · Watch — one feed, every terminal state

Arm ONE Monitor (30-min max; **re-arm on every expiry**, never let it lapse):

```
cd mcp/noctusai && .venv/bin/python cli.py --merge-queue watch --merge-queue-interval 60 2>&1 \
  | grep -E --line-buffered "^MQ-LEFT|^MQ-BATCH|^MQ-WATCH-ERROR|Traceback"
```

- `MQ-BATCH <candidate> -> success|failure|cancelled <url>`: one line per finished candidate batch (since 2026-11-09). `cancelled` usually means a job hit its timeout: a hang, not a green.
- `MQ-LEFT <slug> <sha> -> landed <dev> | ejected <why> | unknown`: `unknown` after a withdrawal is expected.
- Off-host backstop: `.github/workflows/merge-queue-watchdog.yml` (every 10 min) alerts the owner on WhatsApp/email with or without a session (`noctus.dev.mq_watchdog`).
- **Owner rule (2026-11-09):** if a drift goes unnoticed again, add a 20-minute timer (`ScheduleWakeup`/`CronCreate`) that checks the queue even when no event arrives.

## 3 · A red or cancelled batch — act within minutes

1. Read the failure: `gh run view <id> --log-failed` (or `gh api …/actions/jobs/<job>/logs`; a re-run hides attempt 1, so read `runs/<id>/attempts/1/jobs`). Name the test, the file:line, the error.
2. List the batch: `git fetch origin <candidate>` + `git log --oneline origin/dev..FETCH_HEAD`. Match the failure to the entry whose diff touches it.
3. **Withdraw the culprit** to save the ~50-min bisect: `git push origin --delete mq/<slug>--<sha7>` (owner standing permission: `mq/*` refs only; never `feat/*`, `dev`, `main`). The drain keeps bisecting the suspects it already holds; a withdrawal only takes effect in the NEXT drain run.
4. Hand it back: send the branch steward's role the run URL, file:line and cause (outbox `ejected{reason, conflict, url}`). The branch steward fixes it on its own branch and re-files; you never patch it (council 09340534 B, K).
5. Cannot reproduce locally (e.g. real-Postgres proofs with no `pg_ctl`)? Park it with a named destination in the memory file; never re-queue blind.

### Ejection procedure (the branch steward fixes; not live until build 4 inbox fields, interim in brackets)

Rule: `KB § PATTERNS/devops/release-steward.md` § 7a (guardian spec, council 09340534 dispositions A, B, K).
1. Diagnose (steps 1-2 above). Withdraw the `mq/*` ref, write `ejected{reason, conflict, url}` to the outbox, requeue the other riders.
2. Notify the branch steward's ROLE. Needs information? Ask ONE batched question via `noc-questionnaire` PEER MODE: `needs_info`, TTL ~25 min. [Interim: `SendMessage` to the role's current session + the inbox notes field, labelled interim.]
3. The branch steward fixes it on its own branch and re-files `request`. You never patch the branch, never open a rescue branch, never dispatch an engineer for it.
4. After 2 ejections, park the delivery as `blocked_on_steward`. Orphan (steward gone or silent past the TTL): keep it parked, alert the owner; the OWNER names a new branch steward, who adopts the branch. You never adopt it.

## 4 · On every landing

`task_branch action=landed slug=… confirm=True`, then reply `LANDED <dev sha>` / `EJECTED <reason>` to the requester. `no_pointer` on a subagent worktree is benign. `missing_commits` on derived `chore(kb-counts) … [auto]` commits is the tool, not lost work: confirm with `git log --oneline` that the content is on dev.

## 5 · Consent — what the steward may decide

- The owner's ask to ship IS the permission for bless/promote/deploy (`noc-ship` 1b). Do not invent approval phrases.
- **Prod migrations need the owner's go typed in YOUR transcript.** Consent phase `pre-third-users` (owner decision 2026-11-11; revisit when a 3rd user onboards): the owner's plain deploy / go-to-prod ask IS that go - no exact wording, no per-slice sha or filenames. An owner answer relayed by a peer is recorded as RELAYED and confirmed directly before acting. `KB § PATTERNS/devops/prod-exposure-consent.md` § Consent phase.
- Deleting remote branches and closing PRs needs the owner, always.
- A deploy hold (missing secret, migration-before-image) is written into the memory file the moment it is known, with the dev SHA to cut at.

## 6 · Ship

After the queue drains: follow `noc-ship` (status → manifest → `predeploy_check` per active product, pinned tree → bless → promote). Apply each authorized migration BEFORE the image that needs it, then `deploy_image`, then reply `DEPLOYED`. A fleet-wide FE change needs one page per product opened by eye.

## 7 · Primary-checkout care — the steward keeps the shared tree working

**Why (owner, 2026-11-13).** The primary sat 108 commits behind `origin/dev` for a day, with a stale `index.lock` from the night before, a `FINDINGS.md` render byte-identical to dev's and an unpushed ledger commit whose rows had already landed. Every "run the primary's cli.py" path, every hook (they are symlinks into the primary) and `landed` ran stale code, and the steward only reported it. The owner's ask: the steward checks the tree and fixes it whenever no other session is free to.

**When.** At claim, after every `landed`, and at every Monitor re-arm (so at least every 30 min while the shift runs).

**How.**
1. `python3 mcp/noctusai/primary_ff.py` (from any worktree; it resolves the primary itself). It fast-forwards to `origin/dev` and, since 2026-11-13, heals three states without losing anything:
   - an `index.lock` older than 15 min: removed (a younger one answers `skipped_locked`; wait, never race it);
   - unstaged edits whose bytes already equal dev's blob: restored, then fast-forwarded;
   - local-only commits whose every added line is already on dev and every removed line is gone from it: HEAD is parked under `refs/noc/primary-landed/<sha>`, then `reset --keep` onto dev.
2. Any other `skipped_*` (a real edit, staged work, a commit dev lacks, a non-`dev` branch) holds someone's work. Do NOT force it, and do not route around `primary_write_guard`. Find the owner of the change (`git log -1 --format=%an%n%B`, the `Noc-Branch:` trailer, ListAgents), hand it to that session; if none is alive, salvage it onto a self-branch off `origin/dev` (`noc-self-branch`) and enqueue it, then rerun step 1. Only what needs a human (a decision on unrecognised work) goes to the owner, as ONE copy-paste line.
3. Your own worktrees: remove each one the moment its job ends (deploy pins, record branches after `landed`). Leave peers' worktrees to the SessionStart sweep.
4. Log the result line in the shift memory file. "Reported but not fixed" is not a finished state (fix-on-contact).

## Lessons that recur (append; each cost an hour once)

- argparse %-formats help text: a literal `%` in a new `--help` string crashes `cli.py --help` (write `%%`).
- A hanging test burns its whole job timeout and reports `cancelled` with no test name.
- `landed` reads the PRIMARY checkout's toolkit; a dirty primary skips its fast-forward, so a landed tool fix is not live until the primary can FF. Run §7 after every landing.
- A tool run that hangs keeps its hw-admission slot (2026-11-13: a migrate stuck on a dead socket held slot-1 for 80 min and starved every scoped run). Check `lsof ~/.noctus/hw-slots/*.lock` when admission waits with no visible heavy job.
- The steward lease lasts 2 h. Run `--release-steward heartbeat` on a ~25-min loop for the whole shift, or `enqueue` starts refusing you as a stale steward.
- The auto-mode classifier blocks `gh run cancel` on drains and force-pushes; ask the owner, never work around it.
