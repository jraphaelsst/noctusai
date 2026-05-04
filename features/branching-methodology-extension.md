# Feature — branching-methodology-extension

> **What this is.** A lightweight methodology extension to the branching workflow shipped earlier today (`KB § PATTERNS/branching-and-merging.md`). This is filed as a **feature** (single .md, simpler than a project) — the canonical first feature to demonstrate the pattern.

- **Created:** 2026-05-03
- **Owner / stakeholder:** rapha
- **Trigger phrase:** user said "let's add something more here to the branching methodology"
- **Branch:** `branching-methodology-extension` (this feature dogfoods the new "branch first → file feature → implement" order)

---

## Scope

Extends the branching methodology with four additions and introduces the **feature** concept.

1. **Branch-per-project workflow.** Phase commits go to the project's branch, not main. Final commit + push happens on the branch at deliverable. Main is the integration target, not the active workspace.
2. **Orchestrator vs working-agent role split.** The CLI agent (orchestrator — me, in the user's conversation) does the final merge to main. Subagents (spawned via Task) commit and push to the branch, but never to main. Separation of concerns: working agent has narrow task context; orchestrator has session-wide context — different vantage points spot different integration concerns.
3. **Branch-creation as project/feature trigger.** When the user says "branch this" / "branch X" / extended phrase: agent creates branch FIRST, then files project (`PROJECT.md` + folder) or feature (`<slug>.md`), then implements. Branch first is a hard ordering: it forces clean isolation before any code is written.
4. **Pre-work fetch protocol.** Before any agent starts substantive work on a scope, run `git fetch` and check for active branches touching the same files. If a parallel agent is already working: this agent works on next steps, waits for the parallel agent to commit first, then merges. Same recursion if next steps also collide. Solves same-file-collision PROACTIVELY (before editing) rather than reactively (after committing).
5. **Features concept (NEW).** Lightweight project variant: single `.md` file, no folder, no §1-§12 ceremony, no §3a seed-first analysis required. For low-hanging fruit, quick wins, methodology tweaks, simple fixes. Locations mirror projects: `features/<slug>.md` (cross-cutting), `products/<x>/features/<slug>.md` (single-product), `core/features/<slug>.md` (core). Promotion path: if a feature grows beyond simple scope, promote to a project folder.

## Why

- Branch-per-project = isolation. Phase commits don't touch main; main only sees integrated, reviewed work.
- Orchestrator-merges = a fresh-eyes review pass. Working agents rationalize their design as they implement; orchestrator's session context catches integration issues the working agent missed.
- Branch-first trigger = forces clean methodology entry. No "started typing then realized I should branch" mid-stream.
- Pre-work fetch = collision avoidance, not collision recovery. Cheaper and safer.
- Features = methodology that scales down. Not every change earns project ceremony; the previous "everything is a project or it's nothing" pressure was producing two slip patterns: (a) skipping methodology entirely for small work, (b) over-engineering small work as a project.

## Decisions

- **Discriminator project vs feature:** Complexity-driven. ≤2 sub-tasks AND ≤1-2 files touched AND no multi-phase plan → feature. Otherwise → project. Borderline cases: prefer feature (cheaper to promote up than to demote down).
- **Branch threshold:** Branch when filing a project OR feature. One-line direct fixes (typo, broken link) can still go straight to main without branching — they don't earn filing either.
- **Orchestrator role when there's no subagent:** Same agent, but mode-switching. After the implementation phase commits, take a literal pause + separate turn, then review the branch with fresh eyes before the merge to main. Less rigorous than separate-session, more rigorous than "merge on autopilot."

## Sub-tasks

- [x] Branch `branching-methodology-extension` created from origin/main.
- [x] This feature file filed at `features/branching-methodology-extension.md`.
- [x] `KB § PATTERNS/branching-and-merging.md` extended with §11 (branch-per-project), §12 (orchestrator role with structural-rationale + GitHub-PR-analogy + survives-model-shifts framing), §13 (branch-naming triggers), §14 (pre-work fetch protocol). §10 (merging TBD) also strengthened with the "why merging matters as the second-class problem" paragraph.
- [x] `KB § PATTERNS/project-execution.md` extended with §11.1 (features — lightweight project variant).
- [x] `KB § INDEX.md` checked — no new top-level pattern doc added (features section is in existing project-execution.md).
- [x] `CLAUDE/projects.md` updated with 4 new bullets: branch-per-project + orchestrator-merges, branch-creation triggers, pre-work fetch protocol, features.
- [x] Memory updates: extended `feedback_branching_methodology.md`; added `feedback_orchestrator_role.md` + `feedback_features_methodology.md`; `MEMORY.md` index updated.
- [x] Verify-kb-sync + update-kb-counts both green.
- [ ] Commit on branch.
- [ ] Push branch to branch (`git push -u origin branching-methodology-extension`).
- [ ] Orchestrator fresh-eyes pass.
- [ ] Fast-forward push branch tip to main.
- [ ] Delete this feature file as part of the close commit (apply-inline-then-delete pattern, mirroring projects).

## Improvements

(Captured live during implementation per `KB § PATTERNS/project-execution.md § 2.6`. Filed inline as `applied: <change>` or `deferred → <destination>: <change>`.)

- **applied:** strengthened §12 with explicit "structural mechanism, not model-dependent" framing per user mid-flight directive — locks in the rationale so the rule survives future Claude version changes.
- **applied:** added GitHub-PR-model analogy + "if no GitHub, you'd still need an integrator" framing to §12 per user mid-flight directive.
- **applied:** added §10 "why merging matters" paragraph clarifying that branching solves authorship-violation pushing, while merging solves same-line content overwriting — distinct failure modes.
- **deferred → `wish_develop_merging_methodology.md`:** the merging methodology itself remains the wish; this feature only wires the branching half deeper.

## Phase enrichment-loop

This feature only has one logical phase (the implementation). At commit time, log ≥1 learning to the SQLite tracker per `KB § PATTERNS/project-execution.md § 2.11`.

## Closure

Single-session feature. On close: final commit + folder-less delete (just remove this .md), orchestrator fast-forward push to main, branch optionally deleted on remote.
