# Autonomous Operator via Subagent — Option D

> **What this is.** A pattern for keeping a single Claude session **autonomously responsive** to a dispatch / cherry-pick / archive queue between user turns, without polluting the architect's user-facing context. A `ScheduleWakeup` tick fires → the architect spawns an `orchestrator-operator` **subagent** (defined at `.claude/agents/orchestrator-operator.md`) → the subagent drains the `## Pending` section of `.claude/dispatcher.md` in **its own isolated context** → returns a summary → the architect's main context stays clean.
>
> **What this is NOT.** A multi-session orchestrator (that's Option B / `/loop`). A replacement for the architect (Option A — direct in-session orchestration). A separate Claude process (Option C — full specialized subagent per task). Option D is the **fusion** of B + C: single session, autonomous polling, specialized subagent drains inbox per tick.
>
> **When to apply.** Mid-project, dispatch-heavy phases where the architect would otherwise spend every other user turn doing `git fetch / cherry-pick / push / archive` mechanics instead of ideating with the user. Threshold: ≥3 mechanical operations queueable between user turns.
>
> **Cross-references.** `KB § PATTERNS/branching-and-merging.md § 16` (worktree-per-engineer), `§ 18` (wave-based dispatch + pause-on-dependency), `KB § PATTERNS/master-tree-parallel-batches.md` (the multi-product orchestrator this composes with), `feedback_autonomous_operator_via_subagent.md` (working agreement).

---

## 1. The four options

A vs B vs C vs D — same goal (autonomous orchestration between user turns), four shapes:

| Option | Shape | Architect context | Setup cost | Best for |
|---|---|---|---|---|
| **A — Direct in-session** | Architect dispatches + cherry-picks + pushes inline between user turns | **Drains fast** — every mechanical op consumes user-facing budget | Zero | Tiny projects (<5 mechanical ops total) |
| **B — `/loop` autonomous polling** | Separate `/loop` command polls inbox on a cadence; runs in its own process | **Untouched** | Setup `/loop` cadence + inbox plumbing | Long-running orchestrators that survive session restarts |
| **C — Specialized subagent per task** | Each mechanical op spawns a fresh subagent inline; architect prompts it each time | Architect prompts cost some budget; **subagent context is fresh per task** | Per-task brief overhead | High-variance task types where each needs a custom brief |
| **D — Single session, ScheduleWakeup → subagent drains inbox** | `ScheduleWakeup` tick fires → architect spawns ONE `orchestrator-operator` subagent → subagent drains entire inbox in isolated context → returns summary → architect resumes user-conversation mode | **Stays clean** — only the summary lands; subagent eats the per-tick context | Define the agent once at `.claude/agents/orchestrator-operator.md` + inbox/outbox plumbing | **Dispatch-heavy projects where the architect needs to stay with the user** |

**Decision rule.** Default to A for small projects, B if you need cross-session continuity, C if every task needs custom briefing. Option D is the right choice when **dispatch-heavy + user-thinks-with-architect** are both true at the same time.

---

## 2. The 8-step flow

```
USER TURN → ARCHITECT REPLY → INBOX-QUEUE-IF-NEEDED → WAKEUP-SCHEDULED
            ↑                                              ↓
            │                              ScheduleWakeup fires (15min default)
            │                                              ↓
            │                              Architect reads .claude/dispatcher.md ## Pending
            │                                              ↓
            │                              IF pending → spawn orchestrator-operator subagent
            │                                              ↓
            │                              Subagent drains inbox in ISOLATED context
            │                              (dispatches engineers / validates worktrees /
            │                               cherry-picks + pushes / archives)
            │                                              ↓
            │                              Subagent returns summary text
            │                                              ↓
            └──── Architect re-reads outbox, updates project state, returns to user-conversation mode
                                                           ↓
                                              Next ScheduleWakeup queued (15min default; 5min if dispatch-heavy)
```

Step-by-step:

1. **User turn.** User asks the architect something. Architect responds.
2. **Inbox queue.** If the response implies mechanical work (engineer dispatch / cherry-pick / archive), the architect appends a task to `.claude/dispatcher.md` `## Pending` rather than executing inline.
3. **ScheduleWakeup queued.** Architect schedules a wakeup (15min default; 5min during dispatch-heavy phases).
4. **Wakeup fires.** Architect reads `.claude/dispatcher.md` `## Pending` to check for pending tasks.
5. **IF pending → spawn subagent.** Architect invokes `Agent(subagent_type="orchestrator-operator", prompt="Drain .claude/dispatcher.md ## Pending.")`.
6. **Subagent works in isolated context.** Per-task playbook lives in `.claude/agents/orchestrator-operator.md`. Subagent reads `## Pending`, executes each task, mutates state (`pending` → `in-progress` → `done` / `failed`), appends to the `## Outbox` section.
7. **Subagent returns summary text.** Single concise text block — drained count, per-task verdict, architect-followup queue, suggested next cadence.
8. **Architect re-reads outbox + resumes user mode.** Re-schedules next wakeup. Loop continues.

---

## 3. The inbox / outbox contract

### Inbox — `.claude/dispatcher.md` `## Pending`

The unified gitignored file (created from `templates/dispatcher.md`). One task per heading inside `## Pending`. *(This playbook + `orchestrator-operator.md` use `## <task-id>` headings; the `check_dispatcher_staleness` detector + `two-session-architect-operator.md` use `### YYYY-MM-DDTHH:MM — NAME` — pre-existing format divergence, tracked for a future `dispatcher-format-unify` follow-up.)*

```markdown
## Pending

## 2026-05-11-1430-cherrypick-engineer-D
- **Kind:** cherry-pick-and-push
- **State:** pending
- **Args:**
  - from-worktree: .claude/worktrees/agent-a159f24dad63cf02a
  - target-branch: autonomous-operator-via-subagent-doc-2026-05-11
  - cherry-pick-range: origin/main..HEAD
  - allowlist-authors: claude
- **Queued by:** architect 2026-05-11 14:30 UTC
- **Brief:** Engineer D shipped 6 files for Option D rollout; cherry-pick to target branch and push.

## 2026-05-11-1445-archive-project
- **Kind:** archive-project
- **State:** pending
- **Args:**
  - project-path: projects/autonomous-operator-pattern
- **Queued by:** architect 2026-05-11 14:45 UTC
```

### Outbox — `.claude/dispatcher.md` `## Outbox`

Append-only audit section (after `## Completed`). One entry per completed task. Shape defined in `.claude/agents/orchestrator-operator.md § Outbox convention`. Architect reads to verify, prune, or re-queue.

### State mutation rules

- `pending` → `in-progress` when subagent starts a task.
- `in-progress` → `done` or `failed` when subagent finishes.
- **Never delete** — only flip state. Architect prunes during the next user turn (or via a `prune-inbox` housekeeping task).
- Two ticks can't process the same task — `in-progress` blocks re-consumption.

---

## 4. ScheduleWakeup cadence

| Phase | Cadence | Rationale |
|---|---|---|
| Idle / planning | None (don't schedule) | No mechanical work pending |
| Single-engineer dispatch in flight | 15min | One engineer → one batch at end |
| Wave-based parallel dispatch (3+ engineers) | 5min | Engineers complete asynchronously; tighter polling catches the first finisher faster |
| Cherry-pick + push backlog (3+ branches) | 5min | Same — high throughput justifies tighter polling |
| Post-merge / archival | 15min | One-shot archives, no urgency |

**Anti-pattern.** Always-on 1min polling — wastes context on no-op ticks. Always schedule with intent; cancel when idle.

**Override.** User can prompt "drain inbox now" — architect spawns the subagent immediately, no wakeup wait.

---

## 5. When to use D

- **YES** — multi-product master-tree with 3+ wave-based parallel batches. Architect needs to stay with the user to think through the next batch design while engineers from the previous batch trickle in.
- **YES** — long dispatch-heavy phases (cherry-pick 5+ engineer branches sequentially) where each push has independent prep work.
- **YES** — user explicitly says "keep working while we talk about X." The architect interprets this as "queue operator tasks; keep user-conversation primary."
- **NO** — single-engineer project, single push at close. Inline execution wins on simplicity.
- **NO** — exploratory ideation phase where there's no mechanical work to queue. Option D adds inbox plumbing overhead for no payoff.
- **NO** — user wants synchronous feedback ("does the push succeed? tell me before we move on"). The asynchronous shape defeats the purpose.

---

## 6. Setup recipe

1. **Define the operator agent** (one-time per repo).
   - File: `.claude/agents/orchestrator-operator.md` with YAML frontmatter (`name`, `description`, `tools: Bash, Read, Write, Edit, Agent, mcp__noctusai__noctus_dev_archive`).
   - Body: per-task playbook (dispatch-engineer / validate-worktree / cherry-pick-and-push / archive-project), outbox convention, git ownership rules, failure handling.
   - Reference implementation: `.claude/agents/orchestrator-operator.md` shipped 2026-05-11.

2. **Plumb the dispatcher file.** `mkdir -p .claude && cp templates/dispatcher.md .claude/dispatcher.md` (the live file is **gitignored** — transient coordination state, not history; `.gitignore` already carries `.claude/dispatcher.md`, enforced by `check_gitignore_drift`).

3. **Wire ScheduleWakeup into the architect's natural rhythm.** When the architect queues an inbox task, schedule a wakeup with the appropriate cadence. The architect ALWAYS schedules a wakeup when an inbox task is queued — silent skip = orphan task.

4. **Drain protocol per tick.** Architect reads `.claude/dispatcher.md` `## Pending` first; if pending tasks exist, spawn the operator subagent with prompt `"Drain .claude/dispatcher.md ## Pending. Report when done."`; on subagent return, read the `## Outbox` tail, surface architect-followup queue, re-schedule next wakeup.

5. **Project close.** FF-merge-to-main is **always the architect's job**, never the operator's (per `KB § PATTERNS/project-execution.md § Commit + push at project close`). The operator may cherry-pick to a branch and push the branch, but the branch→main FF is the architect's final act.

---

## 7. Anti-patterns

- **Operator dispatches a second operator.** Cross-context recursion. One operator per tick. Caught by `.claude/agents/orchestrator-operator.md § Scope guards`.
- **Operator pushes main without brief authorization.** Push-to-main requires the architect's `Args:` block to carry an explicit `push-main: yes` flag — calibrated from pilot tick 1, which surfaced the contradiction between "brief authorizes push" and "agent definition forbids push". Default-safe is still no-push-main; the flag is the override.
- **Operator dispatches engineers with overlapping files.** Two `dispatch-engineer` tasks in one tick targeting the same file = race condition; operator must STOP + outbox `failed — overlap detected`. Same-product carries higher overlap risk; same-shared-lib (`seed/`, `noctusai_lib/`, `mcp/`) is the highest. Cross-product is default-safe. Architect's `overlap-acknowledged:` flag is the explicit override. Mirrors the architect-side rule in `KB § PATTERNS/branching-and-merging.md § 17.6`.
- **Operator presumes architect-brief facts without verifying.** Briefs sometimes carry stale claims ("branch already renamed" / "worktree already pushed"). Operator runs `git branch --list` + `git log ..HEAD` + `git status` to confirm; adapts inline if reality diverges; outboxes the divergence.
- **Operator aborts on phase-state-hook block.** The pre-commit hook reads the canonical noc home regardless of worktree; unrelated drift can block a clean cherry-pick. Operator applies the inline patch recipe (`**Improvements:**` block + `[DEFERRED-<reason>]` ticks) on first hit; aborts only on second-different-file recurrence. Outbox notes the side-effect either way.
- **Architect skips wakeup scheduling.** Inbox task lands but no tick is queued — orphan task waits indefinitely. Always schedule with intent.
- **Inbox without outbox.** Audit log gaps make failure triage impossible. Operator always appends outbox; if outbox write fails, operator aborts the tick (cardinal rule: silent failure forbidden).
- **Operator extends scope mid-tick.** Engineer reports a Wave 2 dispatch need → operator dispatches Wave 2 inline. Wrong. Operator outboxes `engineer requests Wave 2 dispatch`; architect decides on next user turn.
- **Conversational operator.** Operator should never converse with the architect across multiple turns — single return text per tick. Caught by `§ Anti-patterns` in the agent definition.
- **Stale ScheduleWakeup chain.** Architect leaves wakeups queued after project close. Cancel wakeups when the inbox drains to empty + no near-term tasks expected.

---

## 8. Relationship to other patterns

- **`KB § PATTERNS/branching-and-merging.md § 16 Git worktree for true parallel agents`** — Option D presumes worktree-per-engineer. The operator's `cherry-pick-and-push` playbook works against engineer-isolated worktrees.
- **`KB § PATTERNS/branching-and-merging.md § 18 Wave-based dispatch`** — Option D is the wave-dispatch enabler. Without Option D, the architect manually polls each wave's branches; with Option D, the operator drains the wave's branches per tick.
- **`KB § PATTERNS/master-tree-parallel-batches.md`** — Option D composes naturally with master-trees. The master orchestrator schedules wakeups; the operator drains each batch's mechanical tail.
- **`KB § PATTERNS/project-execution.md § FF-to-main at project close`** — Option D preserves the architect-owned project-close gate. The operator never touches main.
- **`feedback_orchestrator_role.md` (memory)** — Option D is the architect-vs-engineer role split applied **temporally**: architect stays with user, operator drains the mechanical tail between turns.

---

## 9. Open questions (active 2026-05-11)

1. **Tick budget.** What's the right ceiling on tasks-per-tick before splitting into two ticks? Conjecture: 5 cherry-picks OR 1 engineer dispatch (engineer briefs are long; cherry-picks are short). Calibrate from first 3 real uses.
2. **Cross-tick state.** If a wakeup fires while the previous operator subagent is still running, what happens? Conjecture: the architect's tick handler compares the `## Outbox` tail against the `## Pending` state in `.claude/dispatcher.md` (the file is gitignored — no `git log`; use content/mtime, not VCS history) — if the previous tick is incomplete, defer the new tick. Confirm during first parallel-wave dispatch.
3. **Project-folder lifecycle.** When does the inbox/outbox file pair get archived? Conjecture: at project close, the architect's archival step moves them into `projects/<slug>/archive/` alongside the project doc. Confirm via the first archival.
