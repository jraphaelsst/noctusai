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
| **The agent isn't loaded** (newly-added `.claude/agents/*.md` need a fresh session — known harness behavior) | Surface the drift; use what IS loaded as proxy (engineer-seed / Plan / Explore) OR defer the dispatch to the next session |

## The flow (tech-lead view)
1. **Decompose** the task into slices. Ask: how many specialists? Are slices file-disjoint? Is judgment decomposable into design-then-impl?
2. **Pick the roster** for each slice — read `KB § 06-AGENTS.md` + the live `.claude/agents/` files; prefer the most-specialized advisor/executor that fits the slice's domain.
3. **Brief tight** (the `engineer-seed` minimum-viable-brief: goal + reference + scope + acceptance — see `.claude/agents/engineer-seed.md` §11). Tight briefs are the real speed lever, not the model.
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
- `.claude/agents/` (the actual specialist roster — architect/security/compliance-reviewer/backend-engineer/frontend-engineer/devops-engineer/engineer-seed/skill-scout/orchestrator-operator).

## Anti-patterns
- **Generalist-by-default** — the tech-lead handling everything inline because "it's just code." Specialist dispatch + the small dispatch tax pay back on wall-clock + quality for any non-trivial work.
- **Serial-by-default** — running engineers one-at-a-time when slices are file-disjoint. C1 work belongs in parallel.
- **Skip-the-architect** — dispatching executors without an advisor's design pass on judgment-heavy work; the design seat (opus) catches recurrence, seam mismatches, and "is this a bone or an organ?" before the implementation ships.
- **Dispatch what you should inline** — a 50-LoC patch in one file does NOT amortize the dispatch tax; inline cutoff applies.
- **🔴 Agent `isolation: "worktree"` for noc dispatches** — Wave-1 (2026-05-26) surfaced N=4 stale-base recurrence: 4 of 5 agents dispatched via the harness `Agent` tool with `isolation: "worktree"` forked from `7c2a778e` (weeks old, pre-Phase-B) instead of `origin/dev`. Code referenced modules that didn't exist in the worktree base; one engineer (E4) RE-CREATED `auto_improvement.py` + `vectorize.py` from scratch, generating conflicts. The harness's built-in isolation does NOT honor noc-self-branch's fork-from-`origin/dev` rule. **The correct flow** is in the next section.

## Two-level branching (the dispatch flow — codified 2026-05-26 N=4)

**Why two levels:** the architect's branch is the integration sandbox; engineer branches fork off the architect's branch (not `dev` directly) so the architect can collect commits + manage merging before the work touches `dev`. Extra insurance layer against engineer-vs-engineer collisions AND a deliberate place to reconcile semantic surprises before they land in `dev`.

```
origin/dev
   │
   ↓ (1) architect self-branches off origin/dev → architect-branch (e.g. feat/wave-X)
   │
   ├──→ (2) noctus.dev.task_branch action=start slug=E1 ─→ wt-E1 (forks off architect-branch)
   ├──→ (2) noctus.dev.task_branch action=start slug=E2 ─→ wt-E2 (forks off architect-branch)
   ├──→ (2) noctus.dev.task_branch action=start slug=E3 ─→ wt-E3 (forks off architect-branch)
   │
   ↓ (3) DISPATCH each agent INTO its pre-created worktree
   │     (NOT via Agent tool's isolation: "worktree" param)
   │     each agent works in its wt-E<X>, stages files, returns
   │
   ↓ (4) Architect collects commits from each wt-E<X>, evaluates, merges to architect-branch
   │     Surprises / collisions reconciled HERE, before dev sees anything
   │
   ↓ (5) Architect pushes architect-branch → origin/dev (FF) when ALL slices integrated cleanly
```

**Mechanism:**
1. **Self-branch off `origin/dev`** (architect's branch — e.g. `noctus.dev.task_branch action=start slug=wave-X-arch`).
2. **For each engineer**: call `noctus.dev.task_branch action=start slug=E<X>` from the ARCHITECT'S branch. This forks the engineer's worktree off architect-branch (per `noc-self-branch` workflow), NOT off `dev`.
3. **Dispatch the agent INTO that worktree** — pass the worktree path in the brief as the engineer's cwd. Do NOT use the Agent tool's `isolation: "worktree"` parameter (the harness's built-in isolation forks from an arbitrary base; we have N=4 evidence it doesn't honor `origin/dev`).
4. **Collect + reconcile** at architect-branch level. Architect cherry-picks / merges each engineer's commits. Semantic conflicts (E4 re-creating shared modules) get caught HERE, before `dev`.
5. **Push architect-branch → `dev`** (FF) when the wave is clean.

**The collision-insurance properties:**
- Even if two engineers semantically collide, the architect catches it at step 4 (their work is on architect-branch sibling branches, not dev).
- If one engineer's work is unsalvageable, the others ship without it; the architect just doesn't merge that branch.
- `dev` never sees a partial / half-integrated wave; it only sees the architect's reconciled merge.

## Inline-deving — empersonate the specialist (codified 2026-05-26)

When the work is **below the inline cutoff** OR the architect chooses inline for a specific reason (e.g., methodology work that needs a single coherent voice across sub-domains), the architect MUST still ROUTE BY DOMAIN. Inline ≠ "use generic architect mode for everything."

**The rule:** at each task boundary during inline work, ask the same question as at dispatch — "which specialist would I dispatch for this?" — and EMPERSONATE that specialist until the task's commit. Then switch lens for the next task. Apply each specialist's discipline + owns_kb + behavioral specifics from their `.claude/agents/<name>.md` body.

**Practical empersonation matrix:**

| Task domain | Empersonate | Apply (per `.claude/agents/<name>.md`) |
|---|---|---|
| FastAPI routers / services / Pydantic schemas / RLS / migrations / integrations | backend-engineer | seed-first via `create_product_app`, FastAPI dep factory, `StrictHttpModel`, AST-first libcst, MCP path constants, no monkey-patch our own |
| React / TanStack Query / vite / hooks-in-dedicated-files / SSO callback | frontend-engineer | createProductApp factory, page-scoped CRUD, env.CORE_URL (no hand-roll), AST-first ts-morph, status_pagina gating |
| Containers / CI / deploy / dev↔prod parity / base-image / sanitization / VPS ops | devops-engineer | single-container-per-product, container-first dev loop, deploy-config contract, source-of-truth chain, secrets discipline |
| Webhook signatures / LGPD / LLM-bot defense / auth bypass / input validation | security (advisor lens) | threat-model first, verify-before-side-effect, no `VITE_` secrets, RLS per-org, keeper-runs |
| Regression baseline / wiring audit / DRY recurrence / eight-way sync verify | compliance-reviewer (advisor lens) | regression semantics, route-exists ≠ wired, replication-to-seed symmetry, `scan_*` sextet |
| Seed architecture / orchestration / branching / dispatch / project shape / MCP toolkit | architect (self) | Phase-0 audit, 4-question practical decision test, replication-to-seed-symmetry at LANGUAGE time, parallelization-first |

**Switch lens at task boundaries**, not within a task. A single backend task doesn't half-empersonate two specialists; it's wholly the backend-engineer's lens until commit. Then the next task may switch to compliance-reviewer for the verify pass, then to devops-engineer for the deploy wiring.

**Why this matters:** inline-without-empersonation drifts into generalist mode — all the same patterns get applied uniformly regardless of domain, missing the domain-specific discipline each specialist owns. Empersonation preserves the specialist value during inline work.

The rule mirrors dispatch decisions; only difference is empersonation vs. delegation. Same routing logic. Same `owns_kb` boundaries.

---

## The over-inlining anti-pattern (don't revert to solo-builder)

The failure mode this whole pattern exists to prevent: the tech-lead dispatches one wave, then **does the entire long tail inline itself** — deploy, migrations, conflict resolution, follow-up fixes, the FE — serially, over hours. It is slow (O(1 worker) when O(N engineers) was available) **and** it ships incomplete (a solo serial builder runs out of session before the work is done; N parallel engineers each finish their slice). Observed 2026-06-03 (orbity absorption→prod): 2 backend engineers dispatched, then everything else hand-built inline, FE left raw.

**The orchestrator's leverage is fan-out, not throughput-of-one.** What the tech-lead inlines is *only* the genuinely orchestrator-owned work: git/merge/promote/deploy, cross-engineer conflict resolution, the single-owner live mutations (DB/DNS), and verification. **Not** the bulk page/service/test build — that is always a dispatch.

**Triggers (halt-and-dispatch):**
- **3rd consecutive inline build step** ⇒ stop, ask "why isn't this a dispatched engineer?", dispatch. The default answer is "it is."
- **"This is taking me a long time inline"** ⇒ that *is* the signal to break the task into engineer slices and fan out, not to grind.
- **A big module / multi-file feature** ⇒ break it down and dispatch per-slice; never build it solo because "I'm already in the file."
- **Connected BE↔FE** ⇒ author the contract, dispatch BOTH sides in parallel from the start (see `fe-be-contract-first-dispatch.md`) — never BE-now / FE-someday.

**Keep a fleet running:** when a wave lands, the next wave's engineers should already be dispatched. Idle orchestrator time = under-utilization. Pair builders with auditors (wiring-audit / compliance) so built ≠ wired is caught (`KB § PATTERNS/common/...` dispatch-review-wiring-audit).

Under-parallelizing is a *form of under-building* — you shipped less because you didn't fan out — so this composes with the realism rule (build maximally; realism governs the claim, not the ambition).
