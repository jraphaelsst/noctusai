# Feature — architect-engineer-roles

> **What this is.** Adds explicit role-language to the branching-first orchestration methodology: **the orchestrator IS the architect** (plans, dispatches, evaluates). **Subagents ARE engineers** (or teams of engineers) who build per the architect's plan. The roles were already structurally defined; this feature names them explicitly so the language reinforces the architectural pattern.

- **Created:** 2026-05-04
- **Owner:** rapha
- **Branch:** `architect-engineer-roles`
- **Trigger:** user directive 2026-05-04 — *"when i ask you to branch, you plan and dispatch agents that report back to you. keep the lernings and findings concepts. But you literally is gonna be the orchestrator that architects and dispatches and evaluates other agents work. please doc that. new detail to the dev branching methodology. branching still dispatches parallelism when good scenario for it, single agents when not. but the orchestrator is really the orchestrator. he plans like and architect, then dispatches for engineers or teams of engineers to build. keep the architect and engineer/team concepts doc'd as well."*

## Scope

Add the architect/engineer role-language across the three layers + reinforce parallelism-when-good vs. single-agent-when-not framing:

- **`KB § 01-PHILOSOPHY.md § Branching-first orchestration`** — add a new sub-section "Roles: Architect (orchestrator) + Engineers (subagents)" anchoring the language. Update the orchestrator-responsibilities list to say "Architect's responsibilities."
- **`KB § PATTERNS/branching-and-merging.md § 12 Orchestrator vs working-agent role split`** — add architect/engineer language to existing section. Working agent → engineer; orchestrator → architect.
- **`CLAUDE.md` §1 branching-first bullet** — add architect/engineer one-liner.
- **Memory:** extend `feedback_branching_first_orchestration.md` + `feedback_orchestrator_role.md` with the language.

## Why

User directive: durable language that reinforces the role. The structural separation (orchestrator broad-context vs subagent narrow-context) was already documented; the architect/engineer naming gives it a memorable, intuitive shape that future agents can hold.

The pattern is industry-standard: an architect designs the system, engineers (or teams of engineers) build the components, the architect reviews + integrates. Adopting this language doesn't change behavior — it makes the existing behavior unmistakable.

## Sub-tasks

- [x] Branch `architect-engineer-roles` created from origin/main.
- [x] This feature file filed.
- [x] Add "Roles: Architect + Engineers" sub-section to `KB § 01-PHILOSOPHY.md § Branching-first orchestration` — including the **conversational dimension** (architect stays available for user-facing ideation while engineers work, per user 2026-05-04 mid-flight clarification).
- [x] Architect's responsibilities (7 items) + Engineer's responsibilities (6 items) lists added.
- [x] Update `CLAUDE.md` §1 branching-first bullet with architect/engineer language + conversational dimension.
- [x] Update memory entries (`feedback_branching_first_orchestration.md` + `feedback_orchestrator_role.md` + MEMORY.md index).
- [x] verify-kb-sync.sh green.
- [x] Commit on branch.
- [x] Push branch.
- [x] FF push to main.
- [x] Feature stays at its location (per features-are-durable rule).

## Closure

Feature stays at `features/architect-engineer-roles.md`. Future agents reference it as the canonical entry on the role naming.
