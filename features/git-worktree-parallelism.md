# Feature — git-worktree-parallelism + knowledge-tracking

> **What this is.** Two related methodology additions:
> 1. **Git worktree for true parallel agents** — solves the single-worktree contention bug discovered today (subagents on different branches stomp each other's checkout state). `git worktree add` per subagent gives each its own filesystem worktree on its own branch.
> 2. **Knowledge tracking** — orchestrator maintains a durable `findings.md` capturing slips / errors / mistakes / lessons / interesting discoveries during work, both branching-orchestrated and not.

- **Created:** 2026-05-04
- **Owner:** rapha
- **Branch:** `worktree-and-knowledge-tracking`
- **Trigger:** user directive — *"for now, let's go with the doc git worktree, i had already asked for you to doc that for future use. stop the execution and doc it and use it. ... Please, as their orchestrator, i need you to keep track of their work and their findings, gather pieces of knowledge throught the process and give me a file with them. I want interesting findings annotations and piece of knowledge gathered from errors, mistakes, slips, lessons and stuff."*

## Scope

Two related additions, single feature commit:

**1. Git worktree (`KB § PATTERNS/branching-and-merging.md § 16`):**
- New section: "Git worktree for true parallel agents."
- Recipe: `git worktree add ../noctusai-worktrees/<branch-name> <branch-or-commit>` per subagent.
- When required: dispatching 2+ subagents on different branches in single Task turn.
- When not needed: single subagent or sequential subagent dispatch (worktree contention doesn't trigger).
- Cleanup: `git worktree remove` after branches merge to main.
- Anti-patterns: dispatching N subagents into same worktree (race-prone); leaving worktrees lingering after close.

**2. Knowledge tracking — two layers:**
- **Foundational principle (`KB § 01-PHILOSOPHY.md`):** any non-trivial work maintains a durable `findings.md` (or equivalent) capturing slips / errors / mistakes / lessons / interesting discoveries. Default-on for projects + master-trees + any orchestrated work; optional for trivial features.
- **Orchestration-specific (`KB § PATTERNS/branching-and-merging.md § 17`):** when orchestrator dispatches subagents, the findings.md aggregates each subagent's interesting discoveries. Orchestrator appends as reports come in. At project close, file becomes the orchestration's knowledge artifact.
- Distinct from `phase_learnings` SQLite (per-phase, structured atomic learnings) and `live-patterns-log.md` (master-tree's per-batch findings). `findings.md` is the **meta-record** — what happened across the work, especially the unexpected stuff.
- Contributes to the `feedback_safety_nets_become_learnings.md` evolution loop — durable findings → recurrence rule → methodology amendment.

## Why

**Worktrees:** today's first-parallel-execution attempt hit single-worktree contention (subagent's `git checkout -b` switched orchestrator's worktree state mid-flight, stashing uncommitted Phase 0 work). The branching-first methodology assumes parallel-safe; in practice with single git worktree, parallel agents racing checkout state is a real failure mode. `git worktree add` gives each subagent its own filesystem isolation — true parallelism.

**Knowledge tracking:** today produced multiple methodology slips (worktree contention, orchestration delegation) AND multiple interesting findings (cards-from-SQLite insight, branch-tip-to-main fast-forward push semantics, file-type heuristics for conflict resolution). Without a durable file collecting these, they live only in conversation memory + commit messages. The user explicitly wants a file ("give me a file with them") + future agents picking up the work read it for context.

## Sub-tasks

- [x] Branch `worktree-and-knowledge-tracking` created from origin/main.
- [x] This feature file filed.
- [x] Add `KB § PATTERNS/branching-and-merging.md § 16` "Git worktree for true parallel agents."
- [x] Add `KB § PATTERNS/branching-and-merging.md § 17` "Knowledge tracking during orchestration."
- [x] Add `KB § 01-PHILOSOPHY.md` foundational principle "Knowledge tracking — durable findings file."
- [x] Update `KB § 01-PHILOSOPHY.md § Branching-first orchestration` orchestrator's full responsibilities list — added knowledge tracking + worktree setup.
- [x] Update `CLAUDE.md` branching-first bullet — added worktree + findings + new knowledge-tracking bullet.
- [x] Add memory entry `feedback_knowledge_tracking.md`.
- [x] Update memory `feedback_branching_first_orchestration.md` with worktree + findings clauses + 6-step responsibilities list.
- [x] Update `MEMORY.md` index — branching-first entry expanded; new knowledge-tracking entry added.
- [x] verify-kb-sync.sh + update-kb-counts.py --check both green.
- [x] Commit on branch.
- [x] Push branch.
- [x] Orchestrator fresh-eyes pass.
- [x] Fast-forward push to main.
- [x] Feature stays at its location (per features-are-durable rule shipped today).

## Closure

Feature stays at `features/git-worktree-parallelism.md` post-close. Future agents reference it as the canonical entry on worktree-based parallelism.
