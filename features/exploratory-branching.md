# Feature — exploratory-branching

> **What this is.** A "skill" the user invokes via natural language ("branch 2 things and compare", "merge them upfront", "let's try both", "A or B", "spike", "experiment"). Documents two exploratory-branching patterns that build on top of the existing branching methodology (`KB § PATTERNS/branching-and-merging.md`). Filed as a feature per the new "branch this → file → implement" trigger order.

- **Created:** 2026-05-03
- **Owner / stakeholder:** rapha
- **Branch:** `exploratory-branching`
- **Trigger phrase:** user said "lets doc something as if they were a new skill. (lol) when we come to crossroads or just simply experimentating or simply comparision, when i ask you to branch 2 things and compare results or merge them upfront, you already know what to do, right?"

---

## Scope

Two exploratory-branching patterns:

1. **Branch-and-compare (parallel experimentation).** When the user asks to compare alternatives — "branch 2 things and compare results", "let's try both A and B", "spike", "experiment" — each approach gets its own branch from `origin/main`. Both are implemented in isolation. Comparison happens after both ship. User picks winner (or asks for hybrid).
2. **Branch-and-merge-upfront (synthesis).** When the user asks to combine ideas — "merge them upfront", "what if we did both", "hybrid" — both approaches go on a single branch as the union. Compared against `origin/main` baseline, not against alternatives. Shipped if the union holds.

Both patterns sit on top of the existing branching methodology (branch-from-origin/main, push semantics, orchestrator merge). They're new entry points / triggers, not new mechanics.

## Why

The existing branching methodology covers when you KNOW what you're building (branch when work needs isolation, push when ready, etc.). It doesn't explicitly cover the **decision-making cases**: when comparing alternatives or combining them. These cases happen frequently in design conversations — "should we do X or Y?" / "which approach is cleaner?" / "what if we tried both?". Without explicit methodology, the agent might:
- Pick one arbitrarily and ship it (loses comparison value).
- Ask too many clarifying questions instead of branching to find out.
- Combine the approaches inline on main (no isolation; no rollback).

Naming the patterns + their triggers gives the agent a clear recipe.

## Decisions

- **Two patterns, not three.** Considered a "branch one alternative, mainline the other" pattern but it collapses to "branch-and-compare with one branch already shipped." Not distinct enough.
- **Lives on top of branching methodology, not as a separate doc.** New §15 in `KB § PATTERNS/branching-and-merging.md`. Same doc; new entry points.
- **Trigger phrases are descriptive, not exhaustive.** The agent recognizes intent ("compare", "both", "hybrid", "spike", "experiment") rather than matching exact strings. Two-word minimum + extended phrasing both count.

## Sub-tasks

- [x] Branch `exploratory-branching` created from origin/main.
- [x] This feature file filed at `features/exploratory-branching.md`.
- [x] `KB § PATTERNS/branching-and-merging.md` extended with §15 — three subsections (15.1 branch-and-compare, 15.2 merge-upfront, 15.3 choosing between).
- [x] `CLAUDE/projects.md` updated with one bullet pointing to §15.
- [x] Memory entry `feedback_exploratory_branching.md` filed; `MEMORY.md` index line added.
- [x] **Master-tree branching adaptation** — landed as §11.1 in branching-and-merging.md (hierarchical branching: master from origin/main; children from master, NOT origin/main; children land on master; master lands on origin/main). Plus §7.1 cross-reference subsection added to master-tree-parallel-batches.md. Memory entry feedback_master_tree_parallel_batches.md extended with branching adaptation paragraph. CLAUDE/projects.md branch-per-project bullet amended to mention §11.1.
- [x] Verify-kb-sync + update-kb-counts both green.
- [x] Commit on branch.
- [x] Push branch.
- [ ] Orchestrator fresh-eyes pass.
- [ ] Fast-forward push branch tip to main.
- [ ] Delete this feature file as part of the close commit (apply-inline-then-delete pattern).

## Improvements

(Captured live during implementation per `KB § PATTERNS/project-execution.md § 2.6`.)

- **applied:** drive-by fix on §14 — caught a leftover "(§10 TBD)" reference that should have been retired in merging-methodology Phase 7. Updated to "(§10)". Surfaced live while reading §14 for context before adding §15.
- **applied:** added §15.3 "Choosing between the two patterns" decision table. Wasn't in the original feature plan but emerged because the trigger-phrase recognition + scenario fit made a 6-row table the right shape for ambiguity resolution. **Default-when-ambiguous: ask.**
- **applied:** anti-pattern "forcing synthesis when A and B genuinely conflict" with the `if approach_a:` toggle smell — emerged from thinking through what bad merge-upfront looks like in practice. Real failure mode worth naming.

## Closure

Single-session feature. On close: final commit + folder-less delete (just remove this .md), orchestrator fast-forward push to main.
