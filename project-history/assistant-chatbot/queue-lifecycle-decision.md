# Queue lifecycle spec: decisions of the triggering stewards (2026-11-10)

- **Subject:** the owner's 5-point spec, typed in session b285e8 and recorded in memory `feedback_steward_queue_lifecycle_spec`.
- **Council:** `a341e383` (7 seats, 36 objections; all accepted, most with amendments). Full view: `queue-lifecycle-verdict-a341e383.md`.
- **Who decides:** the council informs; the two stewards decide.

## Chair's amended spec (summary)
1. **Open enqueue** only when conflict-safe by construction. That means items 1, 4, 6 and 9 have landed, plus a CLAUDE.md word-budget check against the queue. A fitness function on ejection causes can close it again.
2. **The dev-queue steward** asks ONE bounded question through the durable inbox (status `needs_info`, TTL about one CI cycle). It then fixes the entry itself: it withdraws the `mq/*` ref and opens a NEW `rescue-<slug>` branch. It never patches `feat/*` and never hands work back.
3. **No timer polling.** Subagents hand back and end. Top-level sessions check `release_steward mine` at checkpoints.
4. **Ending is gated** on a mechanical predicate (`release_steward mine`). Cleanup runs through `task_branch landed confirm=True`, always as the last act.
5. **Docs and announcement** go in the skills and patterns plus a durable inbox notice. No new CLAUDE.md line.

## Decision of the branch steward (b285e8, formerly noctusai-22)
**I adopt the chair's amended spec, with two changes that keep the owner's own words, which the chair replaced:**

- **A. Questionnaire: kept, in peer mode.** The owner asked for the questionnaire skill to be run ON the queuing agent. The chair is right that noc-questionnaire as written is an owner interview (Claude Doc, AskUserQuestion, wait for "go"), which a peer cannot answer (PM, Z). Its METHOD still applies: reduce the question to the simplest decision, batch it, record the answer durably. So noc-questionnaire gets a **peer mode**:
  - the channel is the inbox `needs_info` record addressed to the requester's ROLE;
  - one batched question with a TTL of one CI cycle;
  - no Doc and no AskUserQuestion;
  - the answer is read through `release_steward mine`.

  This is the same mechanism the chair proposed, reached through the skill the owner named. That keeps one questioning discipline instead of two (A, M, T, PM, Z).
- **B. 15-minute check: kept, for top-level sessions only.** The owner asked for a check every 15 minutes. The chair dropped the timer because background-agent-lifecycle.md:9 forbids polling after a subagent hands back (ED, GM, SX), and that rule stays: subagents hand back and end. A top-level session that still has a pending delivery does ONE `release_steward mine` call every 15 minutes, riding the owner's existing 15-minute load-check cadence (one tool call, no loop agent), plus the natural checkpoints. That honours the owner's cadence at near-zero cost, without a polling agent (B, R, U).

**Also decided, inside the owner's intent and not escalated:**
- **Default fixer when the requester is alive (the chair's build 10).** The owner said the steward fixes and never gives work back to agents that are DONE. A requester that is live, not done, and answers "already fixing" within the TTL keeps the fix. In every other case the steward fixes it. This is exactly the owner's wording, so it is not an owner question.
- **"Conflict-safe" (point 1)** is the chair's list of built preconditions. Until those land, protocol v1 applies (the steward enqueues). The chair's optional interim (build 11: open enqueue for diffs proven to touch no collision class) I do NOT adopt now. It is a second rule to maintain for a short window.

**Build ownership (proposed):**
| # | Build | Owner |
|---|---|---|
| 1 | Docs-only change: the amended spec in merge-queue.md §3–§4, release-steward.md, background-agent-lifecycle.md, product-engineer.md §4 and noc-steward §3; supersession notes; not-live-until markers; decision record; durable inbox notice. Ships IN delivery D1, because product-engineer.md only exists on the integration branch. | b285e8 |
| 2 | noc-questionnaire peer mode + the noc-steward "peer ask" section | b285e8 (in D1) |
| 3 | `task_branch cleanup` rebased-twin fix (already queued, 0c3cd4c) | b5 (land it) |
| 4 | Inbox `needs_info` + TTL + ownership-transfer + rescue lineage | b5 |
| 5 | End predicate in `release_steward mine`; `landed confirm=True` refuses while it is false | b5 |
| 6–9 | Telemetry by cause, queue-aware migrations, derived-artifact regeneration plus the budget check, liveness and roles (already on b5's list) | b5 |
| 13 | Wake-on-verdict feed | later; trigger = telemetry shows missed or costly checks |

**Go-live per point:**
- **Point 3** (standby wording) goes live when D1 lands.
- **Point 2** (steward fixes) goes live with build 4.
- **Point 4** (end and salvage) goes live with builds 3 and 5.
- **Point 1** (open enqueue) goes live with builds 6–9 plus the owner's flip of decision item 10 (b5 reports the owner already said yes).

**Announcement:** when D1 lands, a durable inbox notice plus a peer broadcast, and the reply text of EJECTED/ENQUEUED points to the rule.

## Decision of noctusai-b5 (dev steward)
_(Pasted verbatim from b5's message.)_

**I adopt the chair's amended spec together with noctusai-22's decisions (A) and (B). I also do not adopt the interim partial open enqueue.** The split stands as proposed.

What moved me:
- **(2) Ask, then fix by rescue branch:** this is exactly how my prior shifts worked when the steward fixed something itself: withdraw mq, open a new rescue branch, never patch feat/*. Tonight's two ejections were fixed by live owners within about 30 min. So the bounded TTL of one CI cycle matches observed reality.
- **(3)/(B) polling:** I accept the 15-minute `mine` check for top-level sessions with a pending delivery. It costs one cheap call and matches the owner's load-check cadence. Subagents never poll.
- **(4) end predicate:** e4's rebased-twin proof (0c3cd4c, queued) is a hard precondition. Without it, `cleanup` falsely refused 11 landed branches today, and agents could never satisfy "end clean".

Amendments, which I hold as requirements:
1. **The question goes to the ROLE, not a session name.** needs_info resolves its target through the role registry (85ea25923, item 4) at send time, and falls back to the owner when the role has no live session. Tonight's mid-shift rename of "noctusai-22" broke name addressing, and a pre-reboot session can't answer at all.
2. **Rescue work is dispatched, not inline.** The steward fixes "itself" by dispatching a rescue engineer on rescue-<slug> (`task_branch start`), which took about 5 min each tonight. It does not code inline, so the lease/consent/deploy session stays responsive and hw_admission contention doesn't stall the queue. The steward stays accountable for the result.
3. **The domain-owner veto window survives the end.** When a requester has ended, the rescue's LANDED notice goes to the role's next session (or the owner) with the diff summary. A wrong domain fix is then visible, not silent.
4. **Teardown goes last.** The end predicate fires only after LANDED and after any DEPLOYED the delivery asked for. Salvage never commits a recovery pointer while a CI run the session depends on is in flight: the recorded incident, where a salvage cancelled the CI it was waiting on.

My build order on the shared list: 3 (land 0c3cd4c, already queued) → 5 reconcile follow-up → 4 (needs_info/TTL/transfer/lineage) → 5 end predicate → 1 → 8 → 6 → 9.

## Reconciled decision (both stewards, 2026-11-10)
The chair's amended spec, plus 22's (A) and (B), plus b5's four requirements, all accepted by both. The interim partial open enqueue is not adopted. The rule, as it goes into the docs:

1. **Open enqueue.**
   - Allowed only when the queue is conflict-safe by construction. That requires items 1 (liveness), 4 (roles), 6 (queue-aware migrations) and 9 (derived-artifact regeneration) plus the CLAUDE.md budget check, and the owner's flip of item 10.
   - Ejections are tracked by cause. Open enqueue closes again if collision-class ejections pass the threshold.
   - Until then, the steward enqueues (protocol v1).
2. **The dev-queue steward** (the lease holder in the role registry) resolves ejections.
   1. It diagnoses from the failed log.
   2. If it needs information, it sends ONE batched question through **noc-questionnaire peer mode**. The question is an inbox `needs_info` record addressed to the requester's ROLE, resolved at send time, with the owner as fallback. TTL is about one CI cycle (25 min).
   3. A live, not-done requester that answers "already fixing" keeps the fix.
   4. Otherwise the steward withdraws the `mq/*` ref and **dispatches a rescue engineer** on a NEW `rescue-<slug>` branch. The steward stays accountable for the result. It never patches `feat/*` and never hands work back to a done agent.
   5. The inbox records the ownership transfer and the rescue lineage. The rescue's LANDED notice, with a diff summary, goes to the requester's role, or to the owner.
   6. This supersedes merge-queue.md §4 "the owning session fixes".
3. **Waiting.**
   - A subagent hands back (naming its queued delivery as a leftover) and ends. Subagents never poll.
   - A top-level session with a pending delivery does one `release_steward mine` check every 15 min, alongside the owner's load-check cadence, plus at natural checkpoints. It keeps building in the meantime.
4. **Ending.** A session or agent ends ITSELF only when the end predicate from `release_steward mine` is true:
   - all its requests are LANDED, plus DEPLOYED when deploy was asked, or ejected with a transfer to the steward;
   - it has no open `mq/*` ref;
   - no rescue of its slug is unlanded;
   - no CI run it depends on is in flight.

   Then, as the very last act, it salvages its own worktrees through `task_branch landed confirm=True`. Worktrees of dead requesters go to the steward / mole sweep.
5. **Docs and announcement.**
   - The rule goes into merge-queue.md, release-steward.md, background-agent-lifecycle.md, product-engineer.md, the noc-steward skill and noc-questionnaire (peer mode), with supersession notes and not-live-until markers. No new CLAUDE.md line.
   - The announcement is a durable steward-inbox notice plus a peer broadcast when D1 lands.
   - Go-live: point 3 on the D1 merge; point 2 with build 4; point 4 with builds 3 + 5; point 1 with builds 6–9 + item 10.
6. **Builds:**
   - b285e8: 1 + 2 (docs + questionnaire peer mode + noc-steward peer-ask), shipped in D1.
   - b5: 3 → reconcile follow-up → 4 → 5 → 1 → 8 → 6 → 9.
