# In-Flight Execution Rollout — Master-Tree Implementation Roadmap

> **What this project is.** A master-tree implementation roadmap that
> orchestrates the **16 in-flight projects** surfaced by the 2026-05-03
> `projects/`-cleanup pass. It does NOT elaborate any individual child's
> phases; each child already owns its own `PROJECT.md`. This master groups
> the 16 into **parallel batches** based on file-overlap analysis +
> dependency analysis, so the orchestrator can dispatch batches of branch
> subagents in single tool-use turns per the branching-first methodology.
>
> **Why a roadmap, not a batch coordinator like `absorbed-projects-batch`.**
> Coordinators (`absorbed-projects-batch`, `main-core-migrations-batch`,
> the archived `products-wiring-rollout`) sequence work *within one
> domain*. This rollout is **cross-domain meta-orchestration** — it
> sequences the *coordinators themselves* alongside standalone children,
> resolves cross-batch dependencies (e.g. `send-message-consolidation`
> gates on `whatsapp-seed-absorption` which lives inside
> `absorbed-projects-batch`), and maximizes parallel branches.
>
> **Run-by.** Designed for a fresh-session orchestrator agent. §1 inlines
> context, §2 quotes the user verbatim, §5 names every child + the batch
> shape, §10 commands are copy-paste ready for dispatching subagents.
> Children are read-only references — this master never edits child
> PROJECT.md files.

- **Created:** 2026-05-03
- **Last updated:** 2026-05-03
- **Status:** 📋 **FILED — Phase 0 ✅ (this file).** Phases 1+ are orchestrator-driven (batch dispatch + sync-gates).
- **Owner / stakeholders:** Raphael (joaoraphaelsst@gmail.com)
- **Project slug:** `in-flight-execution-rollout` (subject=in-flight-execution, intent=rollout — orchestrator-of-orchestrators)
- **Project location:** `projects/in-flight-execution-rollout/` (cross-product / platform-coordinator — drives 16 in-flight children across root + products)
- **Branch:** `in-flight-execution-rollout` (per branching-first methodology — branched from `origin/main`, never pushed to `main`; orchestrator merges per `KB § PATTERNS/branching-and-merging.md`)
- **Related docs:**
  - `KB § 01-PHILOSOPHY.md § Branching-first orchestration` — default mental model: parallelize via Task subagents in single tool-use turn; serial requires justification
  - `KB § PATTERNS/branching-and-merging.md` — branch from `origin/main`, push branch-to-branch only, orchestrator merges
  - `KB § PATTERNS/master-tree-parallel-batches.md` — same-shape children execute as synchronized batches; live cross-pollination via shared scratchpad; sync-gates pre/mid/post
  - `KB § PATTERNS/project-execution.md` — canonical execution workflow each child runs through (incl. § 11.2 archive-on-close)
  - Each child's `PROJECT.md` — the real work specs (16 paths in §5)

---

## 1. Context & Purpose

The 2026-05-03 `projects/`-cleanup pass surfaced **16 legitimately
in-flight projects** (active, parked, deferred-by-design, or scaffolded).
Without coordination they sit unparallelized — agents picking up one at a
time, paying full context-switching cost, missing the parallelization
budget the new branching-first methodology unlocks.

The user's intent: **execute the 16 in parallel branches batched by
file disjointness + dependency analysis**, mirroring the master-tree
parallel-batches model that proved out via the (now-archived)
`products-wiring-rollout` (PF + ERP wiring sweeps in lockstep).

This roadmap is the single high-level plan that:

1. Names every in-flight project and its current execution state (active /
   parked / deferred / orchestrated-by-existing-coordinator).
2. Groups them into **parallel-safe batches** by file-overlap analysis.
3. Calls out **serial dependency chains** that can't parallelize.
4. Carves out **deferred-by-design** projects (3 future-direction drafts)
   so the orchestrator skips them by default.
5. Defers to existing coordinators (`absorbed-projects-batch`,
   `main-core-migrations-batch`) for projects already inside their
   tier-ordered execution plans — this master references them as
   single execution units, not re-orchestrates their children.

The win: the orchestrator opens this file, reads §5 (Architecture /
Roadmap structure), and dispatches Batch 1 subagents in one Task
tool-use turn. When the batch sync-gate closes (§9 success criteria),
the orchestrator dispatches Batch 2. And so on. Total wall-clock to
"all 16 either shipped or explicitly deferred" collapses from N × single-agent
session-time to ⌈N / batch-width⌉ × batch-time.

---

## 2. Confirmed constraints

User directive 2026-05-03 (verbatim):

> *"branch another agent to deal with in-flight skipped projects, please?
> ask him to elaborate a master project tree single file containing the
> whole path to implementing all of the projects. It doesnt need to
> elaborate each individual project yet, it should create a plan of
> implementation, and the other agents are gonna branch and batch work
> on in. Got it? the idea of this is parallelizing a few branches so we
> can tackle many places at once."*

Implications:

- **Single high-level plan, not per-child elaboration.** Each child's
  `PROJECT.md` already owns its phases; this file orchestrates the path
  to *executing* them in parallel batches. Child PROJECT.md files are
  READ-ONLY from this master.
- **Branching-first by default.** Every batch dispatches children on
  their own branches per `KB § PATTERNS/branching-and-merging.md`.
  Subagents branch from `origin/main` (or from the master's branch when
  the master ships infrastructure that the children must build on),
  push branch-to-branch only, orchestrator merges. **Never** push to
  `main` from a child branch.
- **Parallelize via Task subagents in a single tool-use turn.** Per
  `KB § 01-PHILOSOPHY.md § Branching-first orchestration`. Serial
  execution requires explicit justification (file overlap, hard
  dependency, single-resource constraint).
- **Defer to existing coordinators.** `absorbed-projects-batch` and
  `main-core-migrations-batch` already orchestrate subsets of the 16.
  This master references them as monolithic execution units (one
  subagent per coordinator, NOT one subagent per coordinator's child).
  The coordinator agent runs its own internal tier sequencing.
- **Deferred-by-design stays deferred.** The 3 future-direction drafts
  (`agno-dev-team-future-direction`,
  `dev-observability-bot-future-direction`,
  `user-context-bot-future-direction`) are explicitly preserved-only;
  the master excludes them from active execution unless the user lifts
  the deferral.
- **Scope** — only the 16 listed in §5. New projects filed during
  execution surface in §11 + §8 dependencies but do NOT join active
  batches without an explicit user signal.

---

## 3. Design principles

How the orchestrator chunks + sequences + parallelizes:

1. **File disjointness drives batch grouping.** Two projects in the same
   batch MUST NOT touch the same file paths (excluding shared infra
   like `KB`, `CLAUDE.md`, memory). When file paths overlap, the
   projects go in *different* batches so their branches merge cleanly
   without conflict resolution overhead.
2. **Dependency edges drive batch ORDERING.** If A's deliverable is B's
   precondition (e.g. `send-message-consolidation` consumes
   `whatsapp-seed-absorption` Phase 1), B is in a strictly-earlier
   batch than A. Batches are topological generations of the dependency
   DAG.
3. **Coordinators count as one node.** `absorbed-projects-batch`
   contains 8 children; `main-core-migrations-batch` contains 7. Each
   counts as **one master-tree node** here — its internal sequencing is
   its own concern. Splitting them would re-orchestrate already-
   orchestrated work (a slip — the coordinator already encodes the
   right tier order).
4. **Resume-blocked children execute first within a batch.** When a
   child has Phase 0 done and is awaiting "continue", picking it up is
   cheaper than starting a fresh project. Inside its batch, dispatch it
   as the highest-priority subagent.
5. **Deferred-by-design = skip, don't dispatch.** The 3
   future-direction children are documented preservation; they enter
   active execution only if the user explicitly promotes them. The
   master's job is to make the skip *explicit*, not to re-evaluate the
   deferral every cycle.
6. **Live cross-pollination via shared scratchpad.** Per
   `KB § PATTERNS/master-tree-parallel-batches.md`, batches share a
   live patterns log + cross-pollination catalog under
   `projects/in-flight-execution-rollout/`. When subagent A surfaces a
   pattern subagent B would benefit from, it lands in the scratchpad
   mid-batch (not waiting for batch close).
7. **Sync-gates pre/mid/post each batch.** Pre-batch (orchestrator
   dispatches), mid-batch (any subagent surfacing a blocker pings
   master), post-batch (master verifies all branches green + merged
   before opening next batch).

---

## 3a. Seed-first analysis (REQUIRED — the seed is every product's skeleton)

This is a **methodology orchestration** project — its only deliverable is
sequencing, batch dispatch, sync-gate cadence, and rollup. It produces
no production code. Each child runs its own §3a where applicable.

Six-question checklist:

1. **Is the contract identical for every product?** N/A — this master
   ships no product-touching code.
2. **Is the data source product-specific?** N/A.
3. **Is the placement product-specific?** N/A.
4. **Is the visibility / permission rule the same?** N/A.
5. **Does the seam already exist in seed?** N/A.
6. **Default-on or opt-in?** N/A (orchestration cadence, not a product
   surface).

**Litmus — per-product code count this design requires:** [x] **0 lines**
in any `products/<x>/` tree, in any `seed/`, in any `noctusai_lib/`. All
master-tree work lives entirely under
`projects/in-flight-execution-rollout/` (this PROJECT.md + scratchpads +
optional proposals). Per-product / per-seed code lands inside each
child project, where its own §3a governs placement.

**Phase plan implications:** §6 phases work in
`projects/in-flight-execution-rollout/` only. **No phase walks through
products as a primitive.**

---

## 4. Scope

**In scope:**

- The roadmap itself (§5 batch grouping + ordering).
- Orchestrator dispatch recipes (§10 copy-paste).
- Cross-batch dependency tracking (§8).
- Sync-gate cadence + success criteria (§9).
- Rollup retrospective at close (§6 final phase).
- Live shared scratchpad files (created on first batch dispatch):
  - `projects/in-flight-execution-rollout/live-patterns-log.md`
  - `projects/in-flight-execution-rollout/cross-pollination-catalog.md`
  - `projects/in-flight-execution-rollout/batch-status.md`

**Out of scope:**

- Elaborating individual child phases (each child's PROJECT.md owns
  this; the master never edits children).
- Re-evaluating any child's design decisions (children's §7 + §11
  remain canonical; this master only orchestrates EXECUTION).
- Re-orchestrating the internal tiers of `absorbed-projects-batch` or
  `main-core-migrations-batch` (those coordinators own their children;
  this master treats each coordinator as one node).
- Promoting any of the 3 deferred-by-design future-direction children
  into active execution (that requires explicit user signal — see §7).
- Touching any code outside this project folder.

---

## 5. Architecture / Roadmap structure

### 5.1 The 16 in-flight projects (inventory)

| # | Slug | Location | Status | Files-touched scope | Coordinator? |
|---|---|---|---|---|---|
| 1 | `absorbed-projects-batch` | `projects/` | ⏳ EXECUTING (Tier 1 in progress, Tier 2 ✅, Tier 4 deferred) | `noctusai_lib/integrations/whatsapp/`, `noctusai_lib/domain/{scheduling,chatbot,ai}/`, `mcp/noctusai/tools/**`, KB § PATTERNS/* | **YES** (8 children inside) |
| 2 | `adconnect-migration` | `projects/` | Scaffolded, in-flight | `adconnect/**` (whole product) — own JWT auth, isolated | NO |
| 3 | `agno-dev-team-future-direction` | `projects/` | Deferred — design captured | (preserved doc only) | NO |
| 4 | `dev-observability-bot-future-direction` | `projects/` | Deferred — design preserved | (preserved doc only) | NO |
| 5 | `erp-schema-drift-deep-audit` | `projects/` | ⏳ EXECUTING (Phase 1 ✅, Phase 2+ pending §7) | `products/erp-imobiliario/backend/{migrations,app/routers,app/services}/**`, RLS policies | NO |
| 6 | `imobi-scheduling-bot-creation` | `projects/` | Design captured → Phase 0 ready | `products/imobi-scheduling/**` (NEW product, doesn't exist yet) | NO |
| 7 | `main-core-migrations-batch` | `projects/` | ⏳ EXECUTING (Phase 1+, child `therapy-platform-wiring` Phase 1 ✅) | Owns 7 heterogeneous children incl. `repo-state-consolidation` (deleted), `strict-mode-migration`, `vista-api-mcp` (concept), `methodology-mirror-and-workspaces` (concept), `project-history-ledger` (concept), `adconnect-migration`, `therapy-platform-wiring` | **YES** (7 children inside, but several listed standalone in this table — see §5.2 disambiguation) |
| 8 | `progressive-refinement-archive` | `projects/` (on `progressive-refinement-archive` branch — not yet on main) | Phase 0 ✅ → Phases 1-5 ready | `mcp/noctusai/tools/noctus/dev/archive_phase.py` (NEW), `mcp/noctusai/data/phase_learnings.db` (existing), `KB § PATTERNS/project-execution.md`, `CLAUDE.md`, memory | NO |
| 9 | `project-history-ledger` | `projects/` | Concept — interrogation pending | (will surface during Phase 0; concept-stage) | NO |
| 10 | `send-message-consolidation` | `projects/` | 🅿️ PARKED (gated on `whatsapp-seed-absorption` Phase 1) | `products/erp-imobiliario/backend/app/services/whatsapp_service.py`, `products/therapy-platform/backend/app/services/whatsapp_therapy_service.py` | NO |
| 11 | `session-review-baseline` | `projects/` | Reactivated — execution in progress | `mcp/noctusai/{cli.py,session_loader.py,tools/noctus/dev/session_review.py}` | NO |
| 12 | `strict-mode-migration` | `projects/` | 📋 READY FOR EXECUTION (Phase 0 ✅) | `seed/lib/frontend/tsconfig.json`, `seed/framework/frontend/tsconfig.json`, `.github/workflows/*.yml` | NO |
| 13 | `user-context-bot-future-direction` | `projects/` | Deferred — design preserved | (preserved doc only) | NO |
| 14 | `personal-finance-wiring` | `products/personal-finance/projects/` | Phase 0 ✅; awaiting B1 sync-gate sign-off | `products/personal-finance/{backend,frontend}/**` (whole product) | NO (was a child of archived `products-wiring-rollout`) |
| 15 | `therapy-platform-wiring` | `products/therapy-platform/projects/` | ⏳ Phase 0 ✅ + Phase 1 ✅; awaiting Phase 2 continue | `products/therapy-platform/{backend,frontend}/**` (whole product) | NO (currently a child of `main-core-migrations-batch` Tier 3) |
| 16 | `therapy-scheduling-pilot-rollout` | `products/therapy-platform/projects/` | 🅿️ PARKED — awaiting user reactivation | `products/therapy-platform/frontend/{src/App.tsx,src/components/Nav,src/pages/therapist/Scheduling.tsx}`, `KB § GUIDES/` (NEW runbook), env config | NO |

### 5.2 Disambiguation: children that appear inside coordinators

`main-core-migrations-batch` (#7) lists these as its tier-ordered children:

- `strict-mode-migration` (#12) — Tier 2.b deliverable
- `adconnect-migration` (#2) — Tier 4
- `project-history-ledger` (#9) — Tier 4 concept
- `therapy-platform-wiring` (#15) — Tier 3
- `methodology-mirror-and-workspaces` (NOT in the 16; concept-deferred)
- `vista-api-mcp` (NOT in the 16; concept-deferred)
- `repo-state-consolidation` (DELETED by user this session; not in the 16)

**Roadmap rule:** when the orchestrator dispatches the
`main-core-migrations-batch` subagent, that subagent runs the
coordinator's *own* tier sequence — picking up children #2, #9, #12,
#15 inside its loop. **Do NOT also dispatch standalone subagents for
those four children**; the coordinator handles them.

`absorbed-projects-batch` (#1) similarly owns 8 children
(`whatsapp-seed-absorption`, `scheduling-engine-seed`,
`llm-tool-call-audit`, `mcp-server-expansion`, `imobi-scheduling-bot-creation`,
plus the 3 deferred-by-design future-direction drafts). Children #3,
#4, #6, #13 in the inventory are inside this coordinator. **Do NOT
also dispatch standalone subagents for them.**

After applying the disambiguation, the **standalone projects** the
master must dispatch directly are:

- #5 `erp-schema-drift-deep-audit`
- #8 `progressive-refinement-archive` (lives on its own branch — must
  be merged or rebased onto `origin/main` first)
- #10 `send-message-consolidation` (PARKED — see §8 dependency)
- #11 `session-review-baseline`
- #14 `personal-finance-wiring`
- #16 `therapy-scheduling-pilot-rollout` (PARKED — awaiting user)

…plus the **2 coordinators** (#1, #7) dispatched as monolithic units.

That's **8 master-tree dispatch nodes** for active execution + 3
preserved-only future-direction skips.

### 5.3 Batch grouping (file-overlap analysis)

**File-overlap collisions identified:**

- #5 `erp-schema-drift-deep-audit` touches `products/erp-imobiliario/backend/**`. The archived `products-wiring-rollout` also touched ERP backend (B1 absorbed factory there). With ERP wiring archived, no live ERP collision remains. **#5 is parallel-safe** vs. all other standalone nodes.
- #14 `personal-finance-wiring` touches `products/personal-finance/**`. **No collisions** — PF is its own product surface; nothing else in the 16 touches it.
- #15 `therapy-platform-wiring` (inside coordinator #7) and #16 `therapy-scheduling-pilot-rollout` BOTH touch `products/therapy-platform/frontend/`. **Collision** — `therapy-scheduling-pilot-rollout` adds `App.tsx` route + nav entry; `therapy-platform-wiring` Phase 2+ touches admin pages + nav. Forced **serial**: #15 (inside coordinator #7) lands first, then #16 reactivates with a clean route table.
- #11 `session-review-baseline` touches `mcp/noctusai/`. Coordinator #1 (`absorbed-projects-batch`) Tier 2 (`mcp-server-expansion`) is ✅ closed but its children may still touch `mcp/noctusai/tools/`. **Soft collision** — different files in same directory tree. Manageable via branch-to-branch merges, no hard serial gate required.
- #8 `progressive-refinement-archive` touches `mcp/noctusai/tools/noctus/dev/archive_phase.py` (NEW), `KB § PATTERNS/project-execution.md`, `CLAUDE.md`, memory. **Soft collision** with #11 in `mcp/noctusai/tools/noctus/dev/` (different files); **soft collision** with everything in KB/CLAUDE.md (every project may touch these). Manageable via branch-merge ordering.
- #10 `send-message-consolidation` touches the WhatsApp service files in ERP + therapy backends. **Hard dependency** on coordinator #1 Tier 1.d (`whatsapp-seed-absorption` Phase 1) — see §8.
- #1, #7 coordinators may collide with each other if both touch shared seed paths (`noctusai_lib/`). The two coordinators were *designed* to run in parallel (they're sibling batches per their own §1's). Their internal §11 + scratchpads coordinate; **parallel-safe** in this master's view.

### 5.4 The execution batches

**Batch 1 (parallel; 5 nodes; safe-to-dispatch in one Task turn):**

1. **#1 `absorbed-projects-batch`** — coordinator runs its own Tier 1.c (`scheduling-engine-seed`), Tier 1.d (`whatsapp-seed-absorption`), Tier 3 (`imobi-scheduling-bot-creation`). Branch: `absorbed-projects-batch` (or coordinator picks).
2. **#7 `main-core-migrations-batch`** — coordinator runs Tier 3 child Phase 2 (`therapy-platform-wiring` admin Tier A regressions), then Tier 4 (concept-stage children + `adconnect-migration` + `strict-mode-migration` Phase 1+). Branch: `main-core-migrations-batch`.
3. **#5 `erp-schema-drift-deep-audit`** — Phase 2+ (wider 11-table org_id audit) starts after user §7 sign-off; if user has signed off, dispatch directly. Branch: `erp-schema-drift-deep-audit`.
4. **#11 `session-review-baseline`** — execution in progress; pick up next phase. Branch: `session-review-baseline`.
5. **#14 `personal-finance-wiring`** — Phase 1+ (B1 sync-gate sign-off was the gate; if PF can proceed standalone post-rollout-archive, dispatch). Branch: `personal-finance-wiring`.

**Batch 2 (parallel; 1 node; gated on Batch 1 partial closure):**

6. **#8 `progressive-refinement-archive`** — lives on its own branch already (`progressive-refinement-archive`) with Phase 0 ✅ committed. Orchestrator MUST first either merge that branch to `main` or rebase the master's branch on top of it before dispatching, to avoid double-history. **Parallel-safe vs. Batch 1** *in principle* (touches `mcp/noctusai/tools/noctus/dev/archive_phase.py` NEW + `KB § PATTERNS/project-execution.md` edits), but moved to Batch 2 as a hygiene step — let the in-flight branches stabilize first to avoid compound-merge complexity.

**Batch 3 (serial after #1 Tier 1.d; 1 node):**

7. **#10 `send-message-consolidation`** — PARKED gated on `whatsapp-seed-absorption` (inside coordinator #1) Phase 1 shipping `noctusai_lib.integrations.whatsapp.send_text()`. Once #1 surfaces that lib via batch-status update, dispatch this child. Branch: `send-message-consolidation`.

**Batch 4 (serial after #15 closes; 1 node; user-gated):**

8. **#16 `therapy-scheduling-pilot-rollout`** — PARKED awaiting user reactivation. Even when the user lifts the park, it must land **after** `therapy-platform-wiring` Phase 2+ (inside coordinator #7) closes, to avoid colliding on `App.tsx` route table + therapist nav. Branch: `therapy-scheduling-pilot-rollout`.

**Skipped by design (3 nodes; do NOT dispatch unless user promotes):**

- #3 `agno-dev-team-future-direction`
- #4 `dev-observability-bot-future-direction`
- #13 `user-context-bot-future-direction`

### 5.5 Orchestrator's final decisions (2026-05-04)

User resolved §7 questions on 2026-05-04. Orchestrator's overlay on the subagent's plan:

- **Q1 resolved → PROMOTE `agno-dev-team-future-direction` (#3) Deferred → Active.** User: *"q1 yes, the dev team is just the project scaffold."* Status flipped in its own PROJECT.md. **NOT a dispatch target** — agno Python doesn't exist on disk yet (sibling `automations/` repo's Phase 7 is the implementation gate). Active means scheduled, not in execution. Stays out of Batch 1.
- **Q2 resolved → DELETE `erp-schema-drift-deep-audit` (#5) + file replacement `erp-org-scoping-completion`.** User: *"delete this project, its old and i dont remember what it does. If it was something important, please file another project to solve its issue, but uptodate."* Phase 1 (security fix) shipped 2026-05-03 and is durable in git history; replacement focuses on Phase 2+ (11-table org_id audit + design decision). Replacement is filed but **NOT in Batch 1A** — still gated on user §7 design-decision (option-a per-table column vs option-b rewire-via-join).
- **Q3 resolved → `personal-finance-wiring` (#14) PROCEEDS STANDALONE.** Parent `products-wiring-rollout` is archived; PF's scope is product-internal. Confirmed in user: *"q3 a git worktree, then we develop our own based on the git worktree work, yea?"* (the git-worktree shape becomes the dispatch mechanism for PF itself in this batch). PF goes into Batch 1A.
- **Worktree mechanism → `git worktree add` per subagent** per `KB § PATTERNS/branching-and-merging.md § 16` (shipped 2026-05-04). Solves single-worktree contention.
- **Batch size for first dispatch → 2-3 (user directive).** *"batch size 2-3 for now, evaluate their performance and tell me what you think."*

**Batch 1A definition (orchestrator's first parallel dispatch — 2 nodes, validated for file disjointness):**

| Node | Subagent scope | Worktree path | Disjoint from sibling? |
|---|---|---|---|
| `session-review-baseline` (#11) | `mcp/noctusai/cli.py` + new detector module under `mcp/noctusai/tools/noctus/dev/` + `mcp/noctusai/tests/test_session_review.py` (Phase 2+ AST-first detector + Phase 3+ narrow-read detector) | `../noctusai-worktrees/session-review-baseline` | YES — entire scope under `mcp/noctusai/` |
| `personal-finance-wiring` (#14) | `products/personal-finance/backend/{routers,services,migrations}/**` + `products/personal-finance/frontend/src/{hooks,pages,types}/**` (Phase 1 — Pattern absorption + known-pattern fixes from Phase 0 gap inventory) | `../noctusai-worktrees/personal-finance-wiring` | YES — entire scope under `products/personal-finance/` |

Zero file overlap between the two — clean parallel.

**After Batch 1A closes (orchestrator review + merge), Batch 1B will define remaining nodes.** Coordinator master-trees (#1 + #7) and gated nodes (`erp-org-scoping-completion`, `progressive-refinement-archive`) become Batch 1B+ candidates after we validate the parallel-dispatch mechanics + worktree workflow at smaller scale.

**Findings tracking:** Orchestrator initializes `projects/in-flight-execution-rollout/findings.md` per `KB § 01-PHILOSOPHY.md § Knowledge tracking — durable findings file` + `KB § PATTERNS/branching-and-merging.md § 17`. Subagent reports → orchestrator extracts slips/errors/lessons/surprises → appends to findings.md. Synthesized at orchestration close.

---

## 6. Implementation phases

> Each phase below is the **master's** phase, not a child's. Children
> run their own internal phases inside their coordinators or standalone.

- **Phase 0 — File this roadmap.** ✅ (this commit). Inventory + batch
  grouping + dependency analysis captured. Branch
  `in-flight-execution-rollout` pushed branch-to-branch to origin.
- **Phase 1 — Pre-Batch-1 sync-gate (orchestrator).** Before
  dispatching, orchestrator confirms:
  - User §7 sign-off on `erp-schema-drift-deep-audit` Phase 2 model
    decision (org-scoping per-table column vs. JWT-only) — if absent,
    drop #5 from Batch 1 (defer to Batch 1.5 or surface §7 to user
    upfront).
  - User §7 sign-off on `personal-finance-wiring` B1 — if absent, drop
    #14 from Batch 1.
  - Branch `progressive-refinement-archive` either merged to `main` or
    its work merged into a parent that includes it (so Batch 2 can
    dispatch from clean origin/main).
- **Phase 2 — Dispatch Batch 1 (orchestrator).** ONE Task tool-use turn
  with N subagent invocations (N = surviving Batch 1 size after
  Phase 1 gate, ≤ 5). See §10 for the dispatch recipe.
- **Phase 3 — Batch 1 mid-batch sync (live).** Subagents update
  `projects/in-flight-execution-rollout/batch-status.md` on each phase
  close. When coordinator #1 closes Tier 1.d (`whatsapp-seed-absorption`
  Phase 1), batch-status flips a flag → orchestrator dispatches #10
  (Batch 3) without waiting for #1's full close. Cross-pollination
  patterns surface in `live-patterns-log.md`.
- **Phase 4 — Batch 1 close + sync-gate.** Orchestrator merges all
  Batch 1 branches (via the merging methodology). Verifies all
  branches green (each subagent's session-end verification per
  `feedback_finish_session`).
- **Phase 5 — Dispatch Batch 2 (orchestrator).** #8
  `progressive-refinement-archive` Phase 1+ (the rendering tooling).
- **Phase 6 — Dispatch Batch 3 (orchestrator).** #10
  `send-message-consolidation` (after #1 Tier 1.d ships the
  `send_text` lib).
- **Phase 7 — Dispatch Batch 4 (orchestrator; user-gated).** #16
  `therapy-scheduling-pilot-rollout` after user lifts park AND #15
  closes.
- **Phase 8 — Rollup retrospective + close.** Master's §11 records:
  which children shipped, which deferred, which surfaced new follow-up
  projects, total wall-clock saved by parallelization vs. serial
  baseline. Master archives per `KB § PATTERNS/project-execution.md
  § 11.2` (auto-archive to `archive/projects/<today>/<NN>-in-flight-execution-rollout/`).

---

## 7. Open questions

Pair every question with an evidence-backed recommendation per
`feedback_zero_context_project`.

- **Q1: Should the 3 deferred-by-design future-direction children
  (#3, #4, #13) be promoted into active execution?** *Recommendation:
  NO.* Each child's own §2 + §1 documents an explicit user-deferral
  decision; promotion requires a fresh user signal. Master skips them
  by default. If the user wants them in, file a sub-amendment to this
  roadmap.
- **Q2: Has the user signed off on `erp-schema-drift-deep-audit`
  Phase 2 org-scoping model?** *Recommendation:* Phase 1
  pre-dispatch gate — orchestrator MUST check the child's §7 status.
  If unanswered, surface the §7 question to the user BEFORE dispatch
  (not after) so #5 can join Batch 1 cleanly.
- **Q3: Has `personal-finance-wiring` B1 sync-gate cleared post-
  rollout-archive?** *Recommendation:* the parent `products-wiring-rollout`
  is archived. PF can either (a) proceed standalone (safe — its own
  scope is product-internal), or (b) await re-confirmation from user.
  Default to (a) unless the user signals otherwise. Surface in Phase 1
  pre-dispatch gate.
- **Q4: When `therapy-scheduling-pilot-rollout` reactivates, does
  `App.tsx` + nav layout land via #15 first or as part of #16?**
  *Recommendation:* #15 owns nav table state; #16 adds ONE entry. Wait
  for #15 to close, then #16 inserts. (Already encoded as Batch 4
  serial gate.)
- **Q5: Should the master itself land its scratchpad files
  (`live-patterns-log.md`, `cross-pollination-catalog.md`,
  `batch-status.md`) at filing time, or lazily on first batch
  dispatch?** *Recommendation:* lazily — keep this Phase 0 commit
  scoped to the roadmap doc. Scratchpads are operational artifacts
  that emerge with execution; pre-creating empty files adds noise
  without value.

---

## 8. Dependencies & blockers

**Cross-batch dependencies (drives serial gates):**

- **#10 `send-message-consolidation` ← #1 `absorbed-projects-batch`
  Tier 1.d (`whatsapp-seed-absorption`) Phase 1.** #10 Phase 1 is
  gated on `noctusai_lib.integrations.whatsapp.send_text()` being
  importable. **Dispatch order:** #10 is in Batch 3, opens only after
  Tier 1.d closes inside coordinator #1.
- **#16 `therapy-scheduling-pilot-rollout` ← #15 `therapy-platform-wiring`
  Phase 2+** (inside coordinator #7). Both touch
  `products/therapy-platform/frontend/src/App.tsx` route table + nav
  config. **Dispatch order:** #16 is in Batch 4, opens only after
  coordinator #7 closes Tier 3 (`therapy-platform-wiring`).

**Active master-tree integration:**

- Coordinators #1 + #7 ARE master-trees themselves. Their existing tier
  sequences are authoritative — this master treats each as a single
  execution node and does NOT re-orchestrate their internal tiers.
  When they finish, their own §11 + close-gate fires per their own
  workflow; their `apply-inline-then-delete` (or `archive-on-close`
  per `KB § PATTERNS/project-execution.md § 11.2`) trigger
  independently.
- The (now-archived) `products-wiring-rollout` previously orchestrated
  PF + ERP wiring + therapy-platform-wiring as parallel batches. With
  it archived, its surviving children (#14 PF, #15 therapy) execute
  here — #14 standalone in Batch 1, #15 inside coordinator #7.

**External / human blockers:**

- #16 user reactivation signal (manual).
- #5 user §7 sign-off on org-scoping model.
- #14 user re-confirmation of B1 sync-gate (post-rollout-archive).
- #3, #4, #13 user promotion signal (default NO).

---

## 9. Success criteria

The master closes when ALL of these hold:

- [ ] **Batch 1 closed** — coordinators #1 + #7 each at their own §11
      "closed" state OR explicitly paused with documented reason; #5,
      #11, #14 each at their own close OR explicit pause.
- [ ] **Batch 2 closed** — #8 `progressive-refinement-archive` at its
      own §11 closed state; archive-phase tooling shipped + KB updated.
- [ ] **Batch 3 closed** — #10 `send-message-consolidation` at its own
      §11 closed; accept-with-rationale catalog row flipped from
      `accept` → `formalize`.
- [ ] **Batch 4 closed OR explicitly user-deferred** — #16 either
      executed (user reactivated + #15 done) OR confirmed parked with
      no reactivation signal received during this rollout window.
- [ ] **Deferred-by-design count = 3** — #3, #4, #13 untouched (their
      preservation files unchanged).
- [ ] **All branches merged to `main`** via the merging methodology
      (no dangling child branches).
- [ ] **No new in-flight projects accumulated** — projects filed
      *during* execution are either merged (and §11 cites them) or
      explicitly carried to the next rollout cycle.
- [ ] **Rollup retrospective written** in this master's §11 (Phase 8).
- [ ] **Master archived** per `KB § PATTERNS/project-execution.md
      § 11.2`.

---

## 10. How to use this plan

### 10.1 Orchestrator dispatch recipe — Batch 1

Open ONE Task tool-use turn with N subagent invocations (one per
surviving Batch 1 node after Phase 1 gate). Template per subagent:

```
Branch off origin/main as <child-slug>. Your task: execute the
in-flight project at <child-PROJECT.md path> per its own §6 phases
and `KB § PATTERNS/project-execution.md § 0` workflow. Inherit:
- Branch + commit per phase (no push to main); push branch-to-branch.
- Live-update `projects/in-flight-execution-rollout/batch-status.md`
  on every phase close.
- Surface cross-pollination patterns to
  `projects/in-flight-execution-rollout/live-patterns-log.md` when
  another in-flight project would benefit.
- Run end-of-session verification per `feedback_finish_session` before
  returning.
- On full child close, fold into child's §11 + trigger archive per
  `KB § PATTERNS/project-execution.md § 11.2` (do NOT delete the
  folder — `noctus.dev.archive` does the move).
- Report: which phases closed this session, what's deferred, branch +
  HEAD commit pushed.
```

Per-node specifics:

| Node | Child PROJECT path |
|---|---|
| #1 coordinator | `projects/absorbed-projects-batch/PROJECT.md` |
| #7 coordinator | `projects/main-core-migrations-batch/PROJECT.md` |
| #5 standalone | `projects/erp-schema-drift-deep-audit/PROJECT.md` |
| #11 standalone | `projects/session-review-baseline/PROJECT.md` |
| #14 standalone | `products/personal-finance/projects/personal-finance-wiring/PROJECT.md` |

### 10.2 Mid-batch sync — Batch 3 trigger

Watch `projects/in-flight-execution-rollout/batch-status.md` for entry:

```
[YYYY-MM-DD HH:MM] coordinator absorbed-projects-batch:
Tier 1.d whatsapp-seed-absorption Phase 1 ✅ —
noctusai_lib.integrations.whatsapp.send_text() shipped + 12 tests green
```

When that entry appears, dispatch Batch 3:

```
Branch off origin/main (or off the branch that landed
whatsapp-seed-absorption Phase 1) as send-message-consolidation. Your
task: execute projects/send-message-consolidation/PROJECT.md per its
§6 phases. Inherit standard rules from §10.1.
```

### 10.3 Pre-Batch-2 hygiene

Before dispatching Batch 2:

```bash
git fetch origin
git checkout main
git merge --ff-only origin/progressive-refinement-archive  # if fast-forwardable
# OR rebase the in-flight-execution-rollout branch onto progressive-refinement-archive's HEAD
```

Then dispatch:

```
Branch off the freshly-updated origin/main (or the rebased master) as
progressive-refinement-archive-phase1. Your task: execute
projects/progressive-refinement-archive/PROJECT.md Phase 1+ per its §6.
Inherit standard rules from §10.1.
```

### 10.4 User-gated Batch 4

When the user signals reactivation of #16, AND coordinator #7 has
closed Tier 3 (`therapy-platform-wiring`), dispatch:

```
Branch off origin/main as therapy-scheduling-pilot-rollout. Your task:
execute products/therapy-platform/projects/therapy-scheduling-pilot-rollout/PROJECT.md
per its §6 phases. Inherit standard rules from §10.1. Coordinate
nav-table changes with the now-closed therapy-platform-wiring's final
nav state (read-only reference).
```

---

## 11. Change log

- **2026-05-03 — Phase 0 ✅ — master roadmap filed.** This commit
  introduces the master-tree implementation roadmap for the 16
  in-flight projects surfaced by the 2026-05-03 cleanup pass. Inventory
  in §5.1, file-overlap analysis in §5.3, batch grouping in §5.4
  (Batch 1: 5 parallel nodes; Batch 2: 1 node; Batch 3: 1 serial node
  gated on coordinator #1 Tier 1.d; Batch 4: 1 user-gated node;
  3 deferred-by-design skipped). Master treats coordinators
  `absorbed-projects-batch` (#1) + `main-core-migrations-batch` (#7)
  as monolithic dispatch units (their internal tiers stay authoritative).
  Branch `in-flight-execution-rollout` pushed branch-to-branch from
  `origin/main` per `KB § PATTERNS/branching-and-merging.md`.

  **Improvements:** none — Phase 0 is filing only.

---

## 12. No-leftovers

This master archives per `KB § PATTERNS/project-execution.md § 11.2`
on close (Phase 8). The PROJECT.md + scratchpad files
(`live-patterns-log.md`, `cross-pollination-catalog.md`,
`batch-status.md`) move to
`archive/projects/<close-date>/NN-in-flight-execution-rollout/` via
`noctus.dev.archive` (auto-`git mv`, content + git history preserved).
The `proposals/` folder (currently empty `.gitkeep`) goes with it.

References to the 16 children are scoped to this PROJECT.md's §5; they
survive in the archived doc as a reading anchor for future similar
rollouts. Children themselves run their own §12 No-leftovers per their
own PROJECT.md.

No CLAUDE.md / KB / memory edits result from this master — it's an
operational orchestration doc, not a methodology change. (If the
orchestration cadence proves valuable enough to formalize, that's a
follow-up methodology project, not part of this rollout.)
