# Feature — branching-first-orchestration

> **What this is.** A foundational principle elevating branching+parallelization from a tactical tool to the orchestrator's strategic default. The orchestrator's first question on any incoming work: "can this be chunked into parallel branches?" Sequential is the carve-out, not the default.

- **Created:** 2026-05-03
- **Owner:** rapha
- **Branch:** `branching-first-orchestration`
- **Trigger:** user directive 2026-05-03 — *"and let's add another point to our methodology. The dev methodology should be BRANCHING-first. The orchestrator should always branch (batch lol) progressive work into chunks and execute them in parallel. Im pretty sure that's how you operate, i just want that registered in my commits :) ... Parallelization. always look for blocks and branch in blocks that dont collide, preferably."*

## Scope

Add ONE foundational principle in three layers (KB depth + CLAUDE auto-loaded + memory):

- **`KB § 01-PHILOSOPHY.md` — new section:** "Branching-first orchestration — parallelize by default; serial only when chunks collide."
- **`CLAUDE.md` §1:** new universal-rule bullet pointing to KB.
- **Agent memory:** `feedback_branching_first_orchestration.md` + MEMORY.md index line.

## Why

The branching + merging methodology shipped today (`KB § PATTERNS/branching-and-merging.md`) ships the **mechanics** of branching, merging, multi-branch convergence, role separation, etc. But the methodology was implicitly defaulting to "branch when needed" rather than "always branch + parallelize when possible." The orchestrator's strategic stance was undefined.

User's directive elevates the stance: **branching-first** = the orchestrator looks for parallelization opportunities by default, not as an exception. Every incoming work request triggers chunk-identification + parallel dispatch consideration BEFORE serial execution is considered.

This is foundational because it changes the orchestrator's mental model from "do this work" to "how can I chunk + parallelize this work?" — different cognitive starting point with downstream effects on how every project / feature / multi-piece task gets scoped.

## Sub-tasks

- [x] Branch `branching-first-orchestration` created from origin/main.
- [x] This feature file filed.
- [x] Add new section to `KB § 01-PHILOSOPHY.md`: "Branching-first orchestration."
- [x] Add new bullet to `CLAUDE.md` §1.
- [x] Add memory entry `feedback_branching_first_orchestration.md`.
- [x] Update `MEMORY.md` index (Foundational principles cluster).
- [x] **BONUS: Features-are-durable-callable-utilities concept refinement** — per user mid-flight directive: removed archive-on-close from features (KB §11.1, KB §11.2 archive table, CLAUDE/projects.md features bullet + archive bullet, memory feedback_features_methodology.md, memory feedback_archive_system.md). Features stay in `features/` permanently; explicit "delete X" still deletes; explicit `noctus.dev.archive(mode="feature")` still works on user request. **applied inline.**
- [x] verify-kb-sync.sh + update-kb-counts.py --check both green.
- [x] Commit on branch.
- [x] Push branch to branch.
- [x] Orchestrator fresh-eyes pass.
- [x] Fast-forward push branch tip to main.
- [x] **NEW: Feature .md STAYS at its location post-close** (per the bonus refinement above) — NOT auto-archived.

## Improvements

(Captured live during implementation per `KB § PATTERNS/project-execution.md § 2.6`.)

- **applied (mid-flight):** user refined features methodology to "durable callable utilities" — removed archive-on-close everywhere. This bundles cleanly with the branching-first principle since both are foundational orchestration framings. Single commit covers both.

## Closure

Single-session feature. **Stays at `features/branching-first-orchestration.md` post-close** (per the new features-are-durable rule that this feature itself ships). Future agents reference it as a callable utility entry.
