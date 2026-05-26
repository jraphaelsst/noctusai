# Parallelization-first orchestration — the default mindset

**The shift.** The tech-lead's default is **specialized agents in parallel**, not a single generalist working serially. The existing machinery already pointed here ([[branching-first-orchestration]], [[wave-based dispatch]], [[self-branching-mode]], [[dispatch-engineer-tuning]]) — this rule names it as the **mindset** at the top of the orchestration stack: *who* is the specialist roster; *when/how* is parallelization-first. Born 2026-05-25 explicitly after the peer's P2 harness-agents-skills landed the specialist roster — making "real specialized agents orchestration" the actual lived default, not aspiration.

## Why parallel + specialized beats serial + generalist (for fitting tasks)
- **Specialization** — each `.claude/agents/<name>.md` carries domain prompts + scoped tools + the right model (advisors=opus / executors=sonnet) so the dispatched persona is *better at its slice* than a generalist context-juggling all of them.
- **Parallelism** — wall-clock = `max(branch_i)` not `sum(branch_i)` when slices are file-disjoint.
- **Context hygiene** — each subagent has its own context budget; the tech-lead's context stays focused on orchestration + integration, not implementation noise.
- **Isolation** — `worktree` per branch is collision-safe ([[self-branching-mode]] §0); shared `dev` HEAD stays idle.

## Where it fits best (use as default)
| ✅ Fits | Why |
|---|---|
| **File-disjoint multi-file work** | C1 collision-class (per [[branching-and-merging]] §18) → parallel-clean by construction |
| **Multi-specialist work** (design + backend + frontend + devops + security) | Each persona contributes its lens; the tech-lead synthesizes |
| **Same-shape across N products** (master-tree-parallel-batches) | Same procedure, N targets → batch dispatch |
| **Decomposable judgment** (architect first, executors after) | Wave-based: design → impl wave gated on design merge |

## Where it does NOT fit (justify the carve-out + log it)
| ❌ Does not fit | Why |
|---|---|
| **<inline cutoff** (`<100 LoC ∧ <3 files ∧ single-phase`) | Dispatch tax (~45–60k contextualization tokens) > work amortizes; tech-lead does it inline ([[branching-and-merging]] §18.2.1) |
| **Shared-state mutations** of the same lines | C3 substantive-overlap; re-scope to a parallel-clean sibling file OR sequence |
| **A single coherent voice** (one design doc, one synthesis) | One agent's continuity > N voices; the tech-lead writes / one advisor returns |
| **The agent isn't loaded** (newly-added `.claude/agents/*.md` need a fresh session — known harness behavior) | Surface the drift; use what IS loaded as proxy (engineer-default / Plan / Explore) OR defer the dispatch to the next session |

## The flow (tech-lead view)
1. **Decompose** the task into slices. Ask: how many specialists? Are slices file-disjoint? Is judgment decomposable into design-then-impl?
2. **Pick the roster** for each slice — read `KB § 06-AGENTS.md` + the live `.claude/agents/` files; prefer the most-specialized advisor/executor that fits the slice's domain.
3. **Brief tight** (the `engineer-default` minimum-viable-brief: goal + reference + scope + acceptance — see `.claude/agents/engineer-default.md` §11). Tight briefs are the real speed lever, not the model.
4. **Dispatch in one turn** when parallel-clean; one turn per wave when wave-gated (Wave N+1 dispatches only after Wave N FF-merges, per [[branching-and-merging]] §18).
5. **Architect-side certify** each return on its own clean worktree before commit (per the worktree-sensitivity corollary in [[branching]]).
6. **Integrate** (FF rebase-then-push); the tech-lead is the sole git owner.

## Composes with
- [[branching]] (the unified primitive — worktree off `origin/dev` → integrate clean → never switch shared HEAD).
- [[branching-dispatch]] (the 10-step parallel-engineer runbook; semantic-duplicate collision detection; honest reconciliation commit).
- [[branching-and-merging]] §18/§21 (wave-based + collision-class C1/C2/C3).
- [[self-branching-mode]] (the absolute "never work on `dev`" primitive — the substrate parallelization rides on).
- [[dispatch-engineer-tuning]] (the per-engine efficiency layer; the dispatch tax this rule reasons about).
- [[master-tree-parallel-batches]] (the multi-product orchestrator).
- `.claude/agents/` (the actual specialist roster — architect/security/compliance-reviewer/backend-engineer/frontend-engineer/devops-engineer/engineer-default/skill-scout/orchestrator-operator).

## Anti-patterns
- **Generalist-by-default** — the tech-lead handling everything inline because "it's just code." Specialist dispatch + the small dispatch tax pay back on wall-clock + quality for any non-trivial work.
- **Serial-by-default** — running engineers one-at-a-time when slices are file-disjoint. C1 work belongs in parallel.
- **Skip-the-architect** — dispatching executors without an advisor's design pass on judgment-heavy work; the design seat (opus) catches recurrence, seam mismatches, and "is this a bone or an organ?" before the implementation ships.
- **Dispatch what you should inline** — a 50-LoC patch in one file does NOT amortize the dispatch tax; inline cutoff applies.
