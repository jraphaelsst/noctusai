# Council brief: the queue lifecycle spec (steward duties + delivering-agent standby/end)

## Subject
A methodology spec the owner wrote on 2026-11-10 to refine a decision the two stewards had just reconciled. The spec is under review BEFORE it is documented and announced to every agent. Judge whether it is sound, safe and buildable. Name where it fails, where it conflicts with existing rules, what is missing, and what must change before it goes live.

## Background: the reconciled decision it builds on
File: `project-history/assistant-chatbot/multi-steward-decision.md`. The worktree is below; read it there.
- **Into dev:** one serialized merge queue. Enqueue and landed are eventually open to any session without the steward lease. The preconditions are lease liveness keyed on boot-id and a role registry.
- **Prod** (bless, promote, prod migrations, deploy): exclusive, through a shared short-held action lock. The lock holder must be the session where the owner typed consent, verified mechanically.
- **Integration-branch owners** deliver small entries. Declared contract pairs use opt-in atomic groups.
- **Lanes are deferred.**
- **Supporting evidence:**
  - the council record: `project-history/assistant-chatbot/multi-steward-verdict-f93e1991.md`;
  - the study log: `project-history/assistant-chatbot/multi-steward-study.md`.

## The owner's spec (verbatim intent)
1. **Open enqueue** (any session may enqueue without waiting for the steward) is OK **only if it is conflict-safe**.
2. **"The steward" watches over the queue and resolves issues.**
   - First, the steward messages the agent that queued the entry, asking for clarification by running the `noc-questionnaire` skill ON that agent.
   - Then the steward **fixes it itself**. It does not give work back to agents that are done.
3. **Delivering agents stand by** until none of their work is pending. While waiting, they check the queue periodically, every 15 minutes.
4. **End and salvage.** Once an agent's work has landed and nothing remains that could trigger that agent for its dispatch purpose, the agent closes its session or ends. **Each agent salvages its own worktrees before ending.**
5. **Document and announce.** Write the spec down and announce it to the other agents when it is live, so they follow it.

## Facts to weigh (verify in the files)
- **Merge queue** (`KNOWLEDGE-BASE/CONTEXT/PATTERNS/devops/merge-queue.md`, `mcp/noctusai/tools/noctus/dev/merge_queue.py`, `task_branch.py`):
  - **The drain is serialized.** Each entry is its own `mq/<slug>--<sha7>` ref.
  - **Ejections are automatic, never auto-resolved:** a conflict, a duplicate migration number, or a failed derived-file regeneration ejects the entry.
  - **Enqueue is local:** it rebases on dev and renumbers migrations against dev only, NOT against other open queue entries. Allocating against the queue is a planned item ("item 6"), not built yet.
  - **A red batch is bisected.** One ejection costs about one CI cycle, roughly 25 min.
- **Release steward** (`KNOWLEDGE-BASE/CONTEXT/PATTERNS/devops/release-steward.md`, `.claude/skills/noc-steward/SKILL.md` — this skill exists on `dev`; read it with `git show origin/dev:.claude/skills/noc-steward/SKILL.md` if it is missing from the worktree).
- **Questionnaire skill:** `.claude/skills/noc-questionnaire/SKILL.md`. It is written for asking the OWNER; using it on another agent is new.
- **Existing agent lifecycle and teardown rules:**
  - `KNOWLEDGE-BASE/CONTEXT/PATTERNS/common/background-agent-lifecycle.md`;
  - skill `noc-archive-absorb` (absorb learnings, then salvage, before any delete);
  - `KNOWLEDGE-BASE/CONTEXT/PATTERNS/common/storage-hygiene.md`;
  - the salvage tools `noctus.dev.salvage_worktree` / `salvage_before_delete`.
  - A recorded incident: a salvage leg that commits a recovery pointer, run mid-CI, cancelled the CI the session was waiting on ("teardown goes last").
- **Sessions and subagents:**
  - Sessions are top-level interactive sessions on one 8 GB Mac. They get renamed on reboot and even mid-shift.
  - Dispatched subagents run in the background inside a session.
  - Peer messages between sessions are not durable across a reboot. The steward inbox (`release_steward request`) is durable.
  - A session cannot close another session.
- **A dispatched subagent that has finished** can be resumed by its parent with a message. Otherwise it consumes nothing.
- **Owner constraints:** "gated is not blocked" (no idle waiting), and the context budget compounds. The owner's machine-overload rule says to check load every 15 min.

## How ejected entries are fixed today (facts from the dev steward's shift and memory)
- **Written rule:**
  - The owning session fixes its entry and re-files it (merge-queue.md §4).
  - The steward only reads the verdict, re-enqueues, and replies EJECTED with the reason.
  - The current two-steward protocol says the dev steward never patches a branch steward's branch.
- **Tonight (2026-11-10):**
  - The steward diagnosed from the failed candidate's log (`gh run view --log-failed`).
  - The owning session fixed both ejections at the root (an undeclared catalog kind; a lifespan that leaked a real Redis client into a later test) and re-filed.
  - No entry from a dead agent was ejected tonight. Both ejections were fixed by the owning session within about 30 min; one is already re-enqueued. Neither needed the steward to fix anything.
- **Prior shifts:**
  - The steward fixed entries itself when the owner was away or the fix was mechanical. It did this as NEW rescue branches (a one-line keeper baseline; a path fix plus an AST rename), never by patching the original. It withdrew the bad `mq/*` ref under a standing owner permission: "steward may withdraw mq/* refs, never feat/*, dev, main".
  - Two fix routes have been used: fixing inline in the steward session, and dispatching a background rescue engineer on its own branch (`task_branch start rescue-<slug>`), which took about 5 min each tonight.
  - The steward session also holds the lease and runs prod consent actions. Local heavy work goes through `hw_admission` on the 8 GB Mac.
- **Dead requesters:** tonight 4 deliveries from sessions that died in a reboot were enqueued from the durable inbox, with `accept_unscored` and a reason. Peer messages from before the reboot were lost. LANDED replies for dead requesters go to the role's new session or to the owner.
- **Existing push signals:**
  - the off-host watchdog (`merge-queue-watchdog.yml`, every 10 min) pushes LANDED/EJECTED to the owner by WhatsApp/email;
  - `release_steward mine` gives a requester its own outcomes.
- **Teardown tooling:** `task_branch cleanup` is salvage-before-delete. Today it falsely refused landed branches 11 times because of rebased twins; a fix is queued, not landed.
- **Known collision classes for parallel enqueue today:**
  - migration numbers (allocated against dev only);
  - derived artifacts beyond KB counts (keeper baselines, lockfiles);
  - the CLAUDE.md word cap, now at exactly 2500/2500, so any concurrent new §1 line conflicts on budget;
  - hardware slots, because two local enqueues on one 8 GB Mac contend for `hw_admission`.

## Questions to challenge
- Is open enqueue actually conflict-safe today, or only safe-by-ejection? What exactly must exist first?
- Is "the steward asks the queuer via questionnaire, then fixes it itself" workable when the queuer is dead, renamed or busy, and when the fix needs the queuer's domain knowledge? What is the bounded wait?
- What does 15-minute polling by delivering agents add, and what does it cost, relative to the push signals that already exist (the off-host watchdog, commit statuses, the steward inbox)? Who is "an agent" here: a top-level session, a subagent, or both?
- "End when nothing could trigger it": who decides that, and how? How do you avoid salvaging a worktree the steward is about to fix?
- What must the documentation and the announcement contain, and where must they live so that fresh and rebooted sessions find and follow them?
