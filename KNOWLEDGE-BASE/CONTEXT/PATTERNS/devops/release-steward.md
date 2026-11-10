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
  owner the ROLE ("the dev steward"), never a session name that a reboot invalidates.
- **Parked branches must not hold a migration number**: renumber (`next_migration_number`) before reviving one.
- **Inbox auto-reconcile.** `inbox`/`status` run `git cherry origin/dev <branch|origin/<branch>|head_sha>`; zero `+`
  lines puts the request in `already_landed` (not `drain`); unresolvable ones are listed in `unresolvable`, never
  dropped. `action=reconcile confirm=True` (steward) acks all already-landed in one call.
- **Split delivery.** `request branches=[feat/a, feat/b]` (ordered): `drain` emits ONE `task_branch action=train` then
  ONE enqueue of the train. A request whose notes say "together"/"two branches"/a second `feat/` name without
  `branches=` returns a warning.
- Telemetry: `role_set|role_clear|reconcile|train_drain` rows in `release-steward.ndjson`.

## 9 · Related

`KB § PATTERNS/devops/merge-queue.md` (the queue this role feeds; §4 session
rules) · `KB § PATTERNS/devops/hardware-admission-budget.md` (the machine-wide
flock-lease pattern this reuses) · `KB § PATTERNS/devops/ship-consent-riders.md`
§ Concurrent sessions · `KB § PATTERNS/common/self-branching-mode.md` ·
`KB § PATTERNS/common/gate-methodology-sync.md` · `KB § PATTERNS/common/orchestration-family-index.md` ·
`KB § PATTERNS/architect/orchestration-craft-canon.md` (session↔session peer protocol) ·
skills `noc-ship` · `noc-self-branch` · `noc-branch-dispatch`.
