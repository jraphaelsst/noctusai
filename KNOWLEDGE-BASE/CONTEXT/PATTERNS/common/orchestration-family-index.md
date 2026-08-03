# Orchestration & dispatch — family index (§1 consolidation)

> **Family-line pattern:** CLAUDE.md §1 carries ONE line for this family; the member rules live here **verbatim**. This is a lossless MOVE, not a summary — the bytes below are the bytes that were in §1. Each member keeps its own depth doc; this index is the router hop between the §1 family line and those docs. Consolidated 2026-08-03 (harness-audit re-author; §1 had reached 79 always-on rules). → `KB § PATTERNS/common/methodology-gc.md`

Git-workflow rules stay standalone in §1 — **branching**, **self-branching mode**, **`main`/`dev` model** and **prod-exposure consent** are about where code lands, not about how work is decomposed across agents.

## Members (verbatim from §1)

- **Branching-first orchestration.** Orchestrator=architect (stays with user), subagents=engineers; inline below the cutoff. → `KB § 01-PHILOSOPHY.md` · skill `noc-branch-dispatch`
- **Parallelization-first orchestration.** Real specialized-agents-in-parallel is the DEFAULT mindset (each `.claude/agents/<name>` brings its lens); serial / inline only when shared-state, single-coherent-voice, or below the inline cutoff. → `KB § PATTERNS/architect/parallelization-first-orchestration.md` · skill `noc-branch-dispatch`
- **FE↔BE contract-first dispatch — default for connected BE/FE work.** Author the endpoint contract (shapes/field-names/envelope-vs-bare/status) FIRST; both build to it. → `KB § PATTERNS/architect/fe-be-contract-first-dispatch.md`
- **Don't block on background tasks — keep working in parallel.** Idle-polling a running bash/agent burns session budget; queue independent background work + foreground docs/gates instead, consolidate on completion. → `KB § PATTERNS/common/dont-block-on-background.md`
- **Dispatch via `task_branch`, NEVER Agent `isolation: "worktree"`.** 🔴 Agent isolation forks from an arbitrary base (NOT `origin/dev`) — stale-base bug. Two-level: self-branch off `origin/dev` → `task_branch action=start` per engineer → dispatch in. → `KB § PATTERNS/architect/parallelization-first-orchestration.md`
- **Inline = empersonate; don't over-inline.** Inline-dev in the specialist's lens (discipline + owns_kb); orchestrator leverage = fan-out — serial inline bulk-build is slow + incomplete; break big modules into dispatches, 3rd inline build step ⇒ dispatch. → `KB § PATTERNS/architect/parallelization-first-orchestration.md`
- **Lenses-applied commit trailer (optional).** Inline-deved commits carry a `Lenses: <name>` trailer → auditable via `git log --grep "Lenses:"`. → `KB § PATTERNS/common/lenses-applied-trailer.md`
- **Wave-based dispatch + collision-class.** Merge cleanliness is decided at DISPATCH (C1/C2/C3), not at merge. → `KB § PATTERNS/architect/branching-and-merging.md §18/§21`
- **Dispatch with PROJECT — return with notes.** Tech-lead writes PROJECT.md §4a routing before dispatch; engineer/inline-lens returns a `delivery` note, or a `surface` note + BLOCK when re-routing mid-flight. → `KB § PATTERNS/common/dispatch-with-project-and-notes.md`

## Why a family line

These 9 rules shared one framework, and a session that needs one of them typically needs the rest — so a single router hop costs a lookup and returns 8 always-on lines of budget. The forcing function is the router keeper's rule-COUNT ceiling; the procedure is `/gc` step 5. → `KB § PATTERNS/common/claude-md-router-discipline.md`

