# automation-orchestration-2026-05 — Hardening via automation built on Phase B primitives

> **Durable record** (per `KB § PATTERNS/common/roadmap-tracking.md`).
> Lives in `project-history/roadmaps/` because:
> - `projects/<slug>/` is ephemeral (archived on close)
> - `KNOWLEDGE-BASE/` is for methodology, not project state
> - This is multi-session, mutable, structured — none of the existing
>   ndjson ledgers fit.
> On close: absorb lessons → KB/memory, move to `closed/` subdir (optional).

## Goal

Use the Phase B primitives (4 keeper-mirror caches: keeper-patterns + agent-context + auto-improvement + kb-embeddings; generic `vector_*` primitives; `owns_kb` declarations + 6 keepers; drift-fix-on-contact + scoped-auto-improvement + role-split) to **harden noc's platform, tools, and methodology** with low-cost automations that reduce session-time friction and amplify the codification pipeline.

Specifically: ship the **Tier-1 automations** identified in the 2026-05-26 diagnostic that converge on three named outcomes:

1. **Eliminate recurring drift classes** that wasted session time multiple times this run (task_branch cleanup hazards = N=4 by end of session — direct fix).
2. **Convert the codification pipeline from manual to sensor-driven** (auto-improvement ledger cluster detection → s1→s4 promotion candidates surface automatically).
3. **Reduce engineer-brief composition friction** (the biggest dispatch wall-clock bottleneck) by composing briefs from the existing caches.

## Slices

| # | Title | Files-to-modify (primary) | Agent | Status | Wave | SHA |
|---|---|---|---|---|---|---|
| E1 | `task_branch cleanup` gitignored-fix + worktree-ledger-fix | `mcp/noctusai/tools/noctus/dev/task_branch.py` + colocated test | backend-engineer | **shipped** | W1 | `f43b75da` |
| E2 | `engineer_brief_compose` (auto-author tool) | NEW `mcp/.../engineer_brief_compose.py` + `__init__.py` + cli.py + test | backend-engineer | **shipped (this commit)** | W1 | TBD |
| E3 | `code-embeddings.sqlite` (5th keeper-mirror cache) | NEW `mcp/.../code_embeddings.py` + keeper + KB doc + test | backend-engineer | **DEFERRED → W2-E3'** (stale-base fork; engineer still running but expected to need re-dispatch) | W2 | — |
| E4 | `auto_improvement_cluster` + `codification_radar` | NEW `mcp/.../codification_radar.py` + KB doc + test | backend-engineer | **DEFERRED → W2-E4'** (E4 re-created `auto_improvement.py` + `vectorize.py` from scratch with incompatible APIs; needs porting to the REAL modules) | W2 | — |
| E5 | Vector cost tracking (OpenAI embed token / $) | NEW `mcp/.../vector_costs.py` + `__init__.py` + small instrumentation in `kb_embeddings.py` + `project-history/vector-costs.ndjson` + KB doc + test | backend-engineer | **shipped (this commit)** | W1 | TBD |
| W2-E3' | Re-dispatch code-embeddings via two-level branching | (same as E3, correct flow) | backend-engineer | pending | W2 | — |
| W2-E4' | Port codification_radar to real auto_improvement/vectorize APIs | Rewrite `codification_radar.py` using `auto_improvement.query()` + `vectorize.embed_text()` dict-return shape | backend-engineer / inline-empersonation | pending | W2 | — |
| W2-E6 | Vector approval-canonical layer (ratified baseline) | NEW `kb_baseline.py` + keeper + KB pattern + working-cache integration + `project-history/kb-baselines/` + tests | backend-engineer | pending | W2 | — |
| W2-E7 | **Vector autocalibration + auto-improvement** | NEW `vector_calibration.py` — observes vector signals (similarity scores, cluster sizes, hit-rate); reasons about WHY signals look right/wrong vs canonical truth; surfaces calibration recommendations (NOT auto-applies); ledger of past calibration decisions; KB pattern doc + test. **Critical**: the architect REASONS, doesn't blindly accept numbers. Tool surfaces signals; tech-lead evaluates source + makes the call. | backend-engineer (impl) + architect (calibration calls) | pending | W2 | — |

### Wave-1 collision-class

All five slices touch `mcp/noctusai/tools/noctus/dev/__init__.py` to register their new modules (additive — 2 lines each). E3 also adds to the bottom of `compliance.py` (additive). E5 also lightly modifies `kb_embeddings.py` to add cost-logging hooks (additive — ~5 lines inserted before return statements).

- **Collision class:** C2 (additive-only on shared files).
- **File-disjoint primary scope** per slice — no two engineers write the same NEW file.
- **Integration order** (sequential, primary-tree clean between each):
  1. E1 first (lowest risk, fully isolated, unblocks cleanup tooling).
  2. E3 next (creates code-embeddings — no consumers yet).
  3. E5 next (cost-tracking infra — must land before E2/E4 if they want to use it; safe regardless).
  4. E2 + E4 last (both READ from existing caches; no inter-dependency).
- After each integrate: `git pull --ff-only origin dev` on the primary.

### Rollback story

Each engineer's branch is independent. If any single slice breaks integration:
- Skip that slice's integrate. Other 4 land fine.
- The broken engineer's worktree is preserved; tech-lead investigates separately.
- No cascading failures because slices don't depend on each other's outputs.

## Decision log

| Date | Decision | Why |
|---|---|---|
| 2026-05-26 | Use `project-history/roadmaps/<slug>.md` as the durable home for project plans | Existing locations don't fit: KB is for methodology (not project state), MEMORY for behavioral rules, ndjson ledgers for events, `projects/` is ephemeral. New convention codified in `KB § PATTERNS/common/roadmap-tracking.md`. |
| 2026-05-26 | Dispatch all 5 slices in ONE wave (Wave-1), C2 collision-class | First true test of parallelization-first orchestration. User explicit: "test the new parallelism methodology … learn from drifts, errors and more and auto-improve on learnings and findings." All 5 are file-disjoint on primary scope; C2 additive shared files. |
| 2026-05-26 | Add E5 (vector cost tracking) after user request | OpenAI API has metered cost; user wants visibility. Generic platform tool — future cache modules opt in. Lives in `project-history/vector-costs.ndjson` for audit durability. |
| 2026-05-26 | Defer auto-improvement.ndjson schema migration | Existing schema works for current use cases; cluster tool (E4) reads as-is. Migration if shape proves cramped. |

## Open questions (resolve as work progresses)

1. **Cost-tracking provider scope**: log only embeddings (kb + code), or also chat completions? Embeddings first; broaden if pattern emerges.
2. **Engineer-brief auto-author output format**: full markdown brief vs. dict for programmatic dispatch? Start with markdown; add dict variant if dispatch wrappers want it.
3. **Codification radar thresholds**: similarity threshold for "this is the same surface" cluster? Start at 0.75 (conservative); tune from real data.
4. **Code-embeddings chunking**: by function (AST-level) vs. by file? Start with AST-level for Python (libcst available); files for TS (simpler).

## Retrospective (Wave-1 partial close — 2026-05-26)

### Surprise wins
- E1 forked correctly from current dev → clean integration → ~6.5 min wall-clock to ship.
- E2 + E5 NEW files were sound despite stale-base forks (engineers used lazy imports + graceful-degrade, which masked the stale-base issue at compose time and made integration possible after surgical placement of the additive changes).
- **The auto-improvement ledger + surface discipline worked AS DESIGNED**: every engineer's `drift-found:` / `scoped-improvement:` footer surfaced real problems the architect then routed to next-slice work. The methodology's own immune system caught its biggest gap.

### Critical drift surfaces (the lessons)

**1. Agent `isolation: "worktree"` does NOT honor `noc-self-branch`** (N=4)
- Wave-1 dispatched 5 agents via the harness Agent tool with `isolation: "worktree"`.
- 4 of 5 forked from `7c2a778e` (a commit weeks old, pre-Phase-B). Only E1 forked from current `origin/dev`.
- Result: engineers wrote code against a pre-Phase-B world. E4 RE-CREATED `auto_improvement.py` + `vectorize.py` from scratch (those didn't exist in its base) — incompatible APIs vs. the real modules.
- **Codification**: CLAUDE.md §1 new bullet + KB pattern doc anti-pattern + new "Two-level branching" section. Future dispatches MUST use `noctus.dev.task_branch action=start` (which forks from architect's branch, which forks from `origin/dev`) — NEVER the Agent tool's built-in worktree isolation.

**2. Two-level branching for collision insurance** (user mandate, codified)
- Architect first self-branches off `origin/dev` (the integration sandbox).
- Each engineer's worktree forks off architect's branch (NOT off `dev`).
- Architect collects + reconciles commits at architect-branch level BEFORE pushing to `dev`.
- `dev` only sees the architect's reconciled merge, never partial waves.

**3. Inline = empersonate the specialist** (user mandate, codified)
- Inline-deving without empersonation drifts into generalist mode. Each task domain has a specialist; the architect routes by domain even when inline.
- Switch lens at task boundaries (not within a task); apply specialist's discipline + owns_kb until the task's commit.

### Costs vs. estimates
- Wave-1 wall-clock budget: ~30 min (max(slice)) — actual: ~10-15 min before lessons surfaced, then ~1-2 hours of unplanned integration + codification work.
- ROI on the lesson: HIGH. The N=4 drift class is now codified; future dispatches won't re-pay.

### What parallel dispatch actually taught us
- **C2 collision-class analysis was correct** — the actual collisions on `__init__.py` were additive and harmless.
- **The unexpected collision class** was stale-base — file presence/absence at fork time. Not in our existing C1/C2/C3 taxonomy. **Added to the anti-patterns list.**
- **The two-level branching extra-insurance idea (user)** is the structural fix: even if engineers fork stale, the architect's branch acts as a reconciliation buffer before anything touches `dev`.

### What's NOT done from Wave-1 (now W2)
- E3 (code-embeddings) — engineer still running; will likely need re-dispatch.
- E4 (codification_radar) — needs porting to real `auto_improvement.query()` + `vectorize.embed_text()` APIs.
- Both rolled into W2-E3' / W2-E4'.

### New W2 slices added from this retrospective
- W2-E3': re-dispatch code-embeddings via correct flow.
- W2-E4': port codification_radar.
- W2-E6: vector approval-canonical layer (ratified baseline).
- W2-E7: vector autocalibration (user mandate — REASON about signals, not blindly accept).

### Lessons preview (running) — to be absorbed at full close
- "Stale-base fork from Agent isolation" is a new collision class.
- Two-level branching is the structural fix.
- Inline-specialist-empersonation is the inline counterpart to dispatch routing.
- Engineer's two-leg footer discipline (`drift-found:` / `scoped-improvement:`) is the system's auto-immune response — IT WORKED.
- Vector autocalibration must be reasoning-driven, not threshold-blind.

## Composes with

- `KB § PATTERNS/common/agent-context-architecture.md` (the L1-index pattern these caches operate over)
- `KB § PATTERNS/common/scoped-auto-improvement.md` (the ledger E4 reads from)
- `KB § PATTERNS/common/kb-vector-search.md` (the cache E3 mirrors + E5 instruments)
- `KB § PATTERNS/common/drift-fix-on-contact.md` (the rule that surfaces drift to auto-improvement.ndjson)
- `KB § PATTERNS/architect/parallelization-first-orchestration.md` (the orchestration model we're testing)
- `KB § PATTERNS/architect/branching-dispatch.md` (10-step runbook for the Wave-1 dispatch)
- `KB § PATTERNS/common/roadmap-tracking.md` (the convention this doc instantiates)
