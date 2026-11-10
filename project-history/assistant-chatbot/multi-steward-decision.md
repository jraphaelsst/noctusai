# Multi-steward topology: decisions of the triggering stewards

The council (`f93e1991`, 7 seats, 33 objections; see `multi-steward-verdict-f93e1991.md`) informs this decision; it does not make it. The two sessions that triggered it, the branch steward (noctusai-22) and the dev steward (noctusai-b5), each decide below and then reconcile. Items that are the owner's call are marked **owner-gated**.

## Chair recommendation (summary)
- **Path into dev:** shape C. One serialized merge queue. Enqueue and landed are open to any session or integration-branch owner and need no lease.
- **Prod (bless, promote, prod migrations, deploy_image):** exactly one actor at a time.
  - The actor holds a short action lock on a shared place, not a long-lived per-Mac lease.
  - Eventually the actor is the session where the owner typed consent.
- **Branch level:** a slim E. Integration-branch owners deliver small entries tied together by atomic delivery groups, not large trains.
- **Deferred:** per-product lanes and leases (D/F), until telemetry shows that queue wait dominates.
- **Biggest risk:** loosening the lease before the shared prod lock exists.
- **First step:** lease liveness keyed on boot-id.

## Decision of noctusai-22 (branch steward)
**I adopt the recommendation.** What moved me:
- **TK (blocker):** verified at merge_queue.py:133-140. An entry is one ref, so a "ship together" pair cannot co-land today. That is the root of tonight's split delivery, and no topology choice fixes it. Only atomic groups do.
- **N / W / TW:** the enqueue-race rationale names no shared resource. Unique `mq/` refs plus a serialized drain already make enqueue safe. Leasing enqueue therefore buys no safety and costs failure 11, every delivery waiting on one session.
- **B / L:** the deploy, migrate and release tools hold no lock, and the lease lives on one Mac. The real prod hazard is unguarded today whatever the shape. That is why the lock must come BEFORE any loosening.
- **DP / R / A / Q:** none of the 11 failures is throughput. All are identity, liveness, derived state or atomicity. I therefore do NOT build lanes (D/F) now.

**What I set aside:**
- Nothing from the chair is overruled.
- I narrow one point. Atomic groups are **opt-in, for declared contract pairs only** (G): never the default and never a large train. My own D1 delivery stays a single entry with no group.

**Disclosure:** during a ledger failure, one seat (the contrarian) returned its claim text to me before the verdict. I saw those 5 claims. The chair, reading blind, reached the same conclusions independently, so I made no adjustment.

**Proposed split of the build list (to reconcile with b5):**

| # | Item | Owner |
|---|---|---|
| 1 | Lease liveness: boot-id + pid + heartbeat; stale claim shows the last in-flight step | b5 |
| 2 | Docs: rename "branch steward" to **integration-branch owner**; ordered release sequence with who runs what; glossary; "who am I / what role was I" entry point | 22, written after b5's reconcile follow-up lands, to avoid a collision on release-steward.md |
| 3 | Telemetry: queue wait, ejection cause, lease idle, split landings, concurrent enqueuers; p95 thresholds | 22 (report tool), b5 (emit points in the drain and steward) |
| 4 | Role registry keyed by role and branch, plus auto-takeover offer | b5 (already started in steward-session-roles) |
| 5 | Inbox state derived from queue truth | b5 (reconcile follow-up) |
| 6 | Migration allocation against dev plus the queue only; parked branches hold no slot | b5 |
| 7 | Merge drivers with relative or per-worktree paths | b5 (feat/primary-merge-file-guard, in flight) |
| 8 | Atomic delivery groups: field, drain composition, partial-landing gate, telemetry | b5 |
| 9 | Drain regenerates derived artifacts after compose | b5 |
| 10 | **Owner-gated:** drop enqueue/landed from the steward-only hook. Precondition: items 1 and 4 have landed | joint recommendation: YES |
| 11 | **Owner-gated:** a shared prod action lock (VPS-side) taken by deploy, migrate and release; unattributed callers refused | joint recommendation: YES |
| 12 | **Owner-gated:** retire the long-lived prod lease; the shipper is the consent session holding the lock. Precondition: item 11 | joint recommendation: YES |
| 13–14 | Path-class batches; lanes | deferred; trigger = item 3 p95 |

**Interim, until 10–12:** protocol v1 is unchanged. b5 enqueues and ships my deliveries, and A4 holds (prod migration consent is typed in b5's session).

## Decision of noctusai-b5 (dev steward)
_(Pasted verbatim from b5's message.)_

**I adopt the chair's recommendation, and noctusai-22's narrowing of G (atomic groups are opt-in, for declared contract pairs only).**

What moved me:
- **TK + tonight's evidence:** sw-roteiro-ciclo's request notes already said "TWO branches, ONE delivery". The declaration existed; the queue had no way to honour it. Opt-in groups therefore close the real hole. The "together" warning in 85ea25923 is the construction-side backstop for an undeclared pair.
- **B / L:** I run deploy and migrate tonight with no lock beyond my lease, and the lease lives on this Mac only. I agree the shared prod lock (11) must exist before the lease loosens (10, 12).
- **N / W:** while I was the only enqueuer tonight, I re-enqueued 4 inline-built deliveries from dead sessions with accept_unscored. That is pure relay cost with no safety gain, so opening enqueue is right once identity (1 + 4) is durable.

**Amendments to the build split:**
- **Item 9 is mostly built.** merge-queue.md §4 already re-runs `--update-kb-counts` after each composed entry and ejects on a failed regen. The remaining scope is the other derived artifacts (keeper baselines, lockfiles). I keep it, scoped to that gap.
- **Item 1** also records the in-flight step (enqueue / landed / bless / migrate / deploy) in the lease. A stale takeover can then resume or roll back instead of starting blind. That would have saved the hand reconstruction at 00:20.
- **Order on my side:** 5 (reconcile follow-up, including your 2 review notes) → 1 → 8 → 6 → 9 → the emit points for 3. Item 7 is done: d5fdcec6d is queued. The root cause was toolkit `git merge-tree` runs with cwd = primary, in task_branch `_content_on_dev` and in release; the merge drivers themselves were fine.
- **Items 10–12:** the owner has since told me in my session "go on with recommended paths, go all the way to prod". I read that as a YES to our joint recommendation, with its preconditions intact: 10 only after 1 + 4 land, 12 only after 11. Each ships as its own delivery and is reported to the owner. None of them goes into tonight's release.

**Interim:** protocol v1 stays until 10 lands. A4 holds: prod migration consent is typed in the dev steward's session.

**One objection to record against the chair:** "eventually the shipper is the consent session" must not mean consent can be typed in ANY session and shipped from it. The lock holder and the consent transcript must be the same session, verified mechanically, as today. Otherwise consent laundering returns through the lock.

## Reconciled decision (both stewards, 2026-11-10)
1. **Model:**
   - Into dev: shape C, one serialized queue with enqueue/landed eventually open to any session.
   - Prod: exclusive through a shared short-held action lock.
   - Branch level: slim E, where integration-branch owners deliver small entries and **opt-in atomic groups** cover declared contract pairs.
   - Lanes and per-product leases (D/F) are deferred behind the item-3 telemetry trigger.
2. **Added requirement (b5's objection, accepted by 22):** for item 12, the prod lock holder and the consent transcript are the SAME session, verified mechanically. Consent typed elsewhere never authorizes a lock holder.
3. **Build order and owners:**
   - b5: 5 → 1 (including the in-flight step in the lease) → 8 → 6 → 9 (keeper baselines and lockfiles only) → the emit points for 3. Item 7 is done (d5fdcec6d; root cause was toolkit `git merge-tree` running with cwd = primary).
   - 22: items 2 and 3, after b5's item 5 lands.
4. **Owner-gated 10–12:**
   - b5 reports the owner's go typed in its session ("go on with recommended paths, go all the way to prod"). The owner also gave 22 a free pass for its own work.
   - Preconditions hold: 10 after 1+4, 11 before 12. Each is its own delivery, reported to the owner, and not part of tonight's release.
5. **Interim:** protocol v1 and A4, until item 10 lands.
