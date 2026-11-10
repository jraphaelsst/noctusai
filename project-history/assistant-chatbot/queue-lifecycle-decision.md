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
_(pending)_

## Reconciled decision
_(pending)_
