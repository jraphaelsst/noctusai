# automation-orchestration-followup-2026-06 — extracted from the 2026-05-26 diagnostic

> **Durable record** (per `KB § PATTERNS/common/roadmap-tracking.md`).
> Continuation of `closed/automation-orchestration-2026-05.md` — covers the items the original diagnostic identified but didn't ship in the first roadmap.
> All implementations land under the **v4.0.0-beta** release scope (no version bump until rc1).

## Origin

The 2026-05-26 diagnostic (`DIAGNOSTIC-automation-opportunities.md`, now retired) surveyed automations the Phase B primitives unlock. ~50% shipped in the first roadmap; the unshipped half is captured here.

## Slices

| # | Title | Files-to-modify (primary) | Tier | Status | SHA |
|---|---|---|---|---|---|
| F1 | `engineer_output_linter` — auto-check dispatched-engineer return for mandatory `drift-found:` + `scoped-improvement:` two-leg footer | NEW `mcp/.../engineer_output_linter.py` + tests + KB doc + pre-commit hook leg | HIGH | **shipped (this commit)** | TBD |
| F2 | `unified_query` — single semantic query across kb-embeddings + auto-improvement + code-embeddings; ranked unified list | NEW `mcp/.../unified_query.py` + tests + KB doc | HIGH | **shipped (this commit)** | TBD |
| F3 | `scan_repetition_semantic` — extend grep-based `noctus.seed.scan_repetition` with semantic variant (catches similar code with different identifiers) | NEW `mcp/.../scan_repetition_semantic.py` + tests + KB doc | HIGH | **shipped (this commit)** | TBD |
| F4 | `doc_to_code_drift` — for each KB pattern naming a tool/keeper, vector-distance between doc and live code; widening distance = silent drift | NEW `mcp/.../doc_to_code_drift.py` + tests + KB doc | MEDIUM | **shipped (this commit)** | TBD |
| F5 | `orphan_branch_sweeper` — list branches diverged from origin/dev without project folders; extends `check_branch_orphan` | NEW `mcp/.../orphan_branch_sweeper.py` + tests + extends existing keeper | LOW-MED | **shipped (this commit)** | TBD |
| F6 | `cache_hitrate_telemetry` — log query frequency per cache; surfaces "are agents actually USING the caches?" | 5 small additions to cache `_connect()` functions + NEW `cache_telemetry.py` ledger module | MEDIUM | **shipped (this commit)** | TBD |
| F7 | `brief_similarity_radar` — extends `engineer_brief_compose` with last-7-day similarity check + brief-to-agent routing via owns_kb centroids | extends existing `engineer_brief_compose.py` + new functions | MEDIUM | **DEFERRED → next session** (needs lifecycle hook design + design conversation with user) | — |
| F8 | `session_end_auto_salvage` — at session-close: sweep all worktrees, salvage-and-cleanup integrated ones, append ledger | extends `noctus.dev.mole` + new orchestration logic | MEDIUM | **DEFERRED → next session** (needs harness hook research) | — |
| F9 | `pre_dispatch_cache_warmup` — inject agent's bundle + relevant auto-improvement + kb_similar into dispatch context | extends task_branch + dispatch flow | HIGH | **DEFERRED → next session** (touches dispatch shape; design conversation) | — |
| F10 | `per_product_centroid_drift` — track each product's code centroid vs seed centroid over time | NEW `mcp/.../product_drift.py` + scheduled ledger | LOW-MED | **DEFERRED → next session** | — |
| F11 | `dispatch_token_budget_telemetry` — per-dispatch token consumed; trend over time | needs dispatch lifecycle hooks (where?) | MEDIUM | **DEFERRED → next session** (where are hooks?) | — |
| F12 | Auto-author scaffolding (memory entry / KB pattern draft / keeper scaffold) | extends `scaffold_*` modules + vector match against existing | LOW | **EXPLICITLY DEFERRED** (the diagnostic itself flagged these as judgment-heavy — drafts likely need full rewrites) | — |

### Collision class

All "shipped" slices (F1-F6) are **C2 (additive on shared files)**:
- `mcp/noctusai/tools/noctus/dev/__init__.py` — registrations
- `KNOWLEDGE-BASE/INDEX.md` — entries
- `mcp/noctusai/cli.py` — flags (some slices)
- `mcp/noctusai/tools/noctus/dev/compliance.py` — allowlist (KB doc slices)

Primary scope per slice is file-disjoint (each NEW `*.py` is its own).

## Implementation approach

**Inline-empersonation** (backend-engineer lens) for all 6 shipped slices. Same pattern as W2-E3'/W2-E6/W3-E1-3 in the original roadmap — proved 3-4× faster + cheaper in tokens vs. dispatched engineers for this scope (medium-sized, methodology-internal, no specialist domain expertise needed).

**Why not full parallel dispatch**:
- This session's context budget would absorb a heavy 4-5 engineer brief-tax (~$45-60k tokens each).
- All slices touch the same SHARED files (`__init__.py`, INDEX.md) at integration; serial integration is unavoidable.
- The two-level branching dispatch flow is ALREADY proven by W2 wave — re-proving it for these slices adds no methodology evidence.

## Decision log

| Date | Decision | Why |
|---|---|---|
| 2026-05-26 | Extract unshipped diagnostic into separate follow-up roadmap | Per `KB § PATTERNS/common/roadmap-tracking.md`. Keeps the original (`closed/automation-orchestration-2026-05.md`) clean. |
| 2026-05-26 | All under v4.0.0-beta scope | User explicit: "all under the same 4.0 push." No version bump until rc1. |
| 2026-05-26 | Inline-empersonation for F1-F6 | Context hot + inline shipped clean in W2/W3; dispatched engineers had API mismatches in W1. Token cost ~3× lower inline. |
| 2026-05-26 | Defer F7-F11 to next session | Either need design conversation (F7 brief-routing, F9 dispatch-shape, F11 hook locations) or low immediate value (F10). |
| 2026-05-26 | Permanently defer F12 (auto-author scaffolding) | Original diagnostic flagged as judgment-heavy. AI drafts of KB patterns / keepers likely need full rewrites. Better as on-demand `/codify` invocation. |

## Open questions (resolve at next session if/when slice is picked up)

1. **F9 pre-dispatch cache warm-up**: where should warm-up data inject? Top of brief? Side-channel via task_branch metadata?
2. **F11 dispatch token-budget tracking**: where do dispatch lifecycle hooks exist? Need to research how Agent tool invocation can be observed for token usage.
3. **F7 brief similarity radar**: 7-day window or session-bounded? How do we name "the same engineer was dispatched for this last week"?
4. **F8 session-end auto-salvage**: does the harness expose a session-close hook we can wire to?

## Retrospective slot

To be filled at full close. Likely entries:
- How did F1-F6 inline shipments hold up?
- Did the dispatch-token-budget question resolve?
- Did F12 (auto-author) prove unnecessary or did N≥3 cases emerge?

## Composes with

- `closed/automation-orchestration-2026-05.md` — the original roadmap; this is its continuation.
- `KB § PATTERNS/common/roadmap-tracking.md` — the convention this doc instantiates.
- `KB § PATTERNS/common/versioning.md` — releases stay under v4.0.0-beta until rc1.
