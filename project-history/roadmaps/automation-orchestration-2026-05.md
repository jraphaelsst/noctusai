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
| E1 | `task_branch cleanup` gitignored-fix + worktree-ledger-fix | `mcp/noctusai/tools/noctus/dev/task_branch.py` + colocated test | backend-engineer | pending | W1 | — |
| E2 | `engineer_brief_compose` (auto-author tool) | NEW `mcp/.../engineer_brief_compose.py` + `__init__.py` (additive) + test + brief KB doc | backend-engineer | pending | W1 | — |
| E3 | `code-embeddings.sqlite` (5th keeper-mirror cache) | NEW `mcp/.../code_embeddings.py` + `__init__.py` (additive) + new keeper in `compliance.py` (additive, bottom) + KB doc + test | backend-engineer | pending | W1 | — |
| E4 | `auto_improvement_cluster` + `codification_radar` | NEW `mcp/.../codification_radar.py` + `__init__.py` (additive) + KB doc + test | backend-engineer | pending | W1 | — |
| E5 | Vector cost tracking (OpenAI embed token / $) | NEW `mcp/.../vector_costs.py` + `__init__.py` (additive) + small additive instrumentation in `kb_embeddings.py` + new `project-history/vector-costs.ndjson` schema + KB doc + test | backend-engineer | pending | W1 | — |

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

## Retrospective (filled at close)

_To be filled when all slices ship — capture: surprise wins, drift surfaces, methodology improvements, costs vs. estimates, what parallel dispatch taught us about C2 collision discipline._

**Lessons preview (running):**
- _captured as slices land_

## Composes with

- `KB § PATTERNS/common/agent-context-architecture.md` (the L1-index pattern these caches operate over)
- `KB § PATTERNS/common/scoped-auto-improvement.md` (the ledger E4 reads from)
- `KB § PATTERNS/common/kb-vector-search.md` (the cache E3 mirrors + E5 instruments)
- `KB § PATTERNS/common/drift-fix-on-contact.md` (the rule that surfaces drift to auto-improvement.ndjson)
- `KB § PATTERNS/architect/parallelization-first-orchestration.md` (the orchestration model we're testing)
- `KB § PATTERNS/architect/branching-dispatch.md` (10-step runbook for the Wave-1 dispatch)
- `KB § PATTERNS/common/roadmap-tracking.md` (the convention this doc instantiates)
