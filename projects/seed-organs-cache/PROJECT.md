# seed-organs-cache — the body layer of seed absorption

> **Status:** PHASE 1 (seed pilot). Active.
> **Slug:** `seed-organs-cache`
> **Born:** 2026-05-29.
> **Owner:** tech-lead (orchestrator).

## §0 Outcome

The platform already caches the seed's **skeleton** — methodology, infrastructure, agent fabric, shared lib re-exports — via the 8 keeper-mirror caches. This project adds the **body layer**: validated reusable components/pages/functionality, cached + embedded for query-and-reuse.

The seed-absorption discipline (`noc-absorb-product`) gains a sibling for components/pages: each validated organ is absorbed into the cache with its FE source, BE source, types, schema, tests, wiring contract, and consumer roster — queryable by intent ("I need a credentials list with multi-account selector") via vector + graph search.

**Reuse contract.** When building a new page/feature: query the cache → pick a validated organ → consume by reference. If no fit: build it, validate it end-to-end, register it. The catalog grows by USE, not by speculation.

**Validation signal (the load-bearing definition):** an organ is `validated` when its FE is 100% built with validated data flows + working functions AND its BE is 100% built, sanitized, optimized. NOT "has a test file." NOT a human verdict alone. The signal is **end-to-end working code shipped with reuse-mindset by construction**.

## §1 Scope

- Phase 1 (this project): **seed pilot** — 5 canonical seed components registered as the first organs (auth trio `LoginForm` + `ForgotPasswordPage` + `AcceptInvitePage`, plus `ResourceManager`, plus `DigestCard`). Build the tooling that makes registration + query work. Prove the loop.
- Phase 2 (NEXT project, not this one): **social-wiring pilot** — first product's organs cached (multi-account integrations CRUD is the obvious first; settings page is the second).
- Phase 3+ (deferred per-product): every other product's organs cached one product at a time, methodically.

Out of scope for Phase 1: BE-only organs (focus FE first), per-product overrides, manual override sidecar (start with derived-only).

## §2 Phases (this project = Phase 1)

| # | Slice | Why | Files-to-modify (primary) | Status |
|---|---|---|---|---|
| W1 | Fix noc-graph re-export attribution | Honest consumer counts unblock everything downstream; the cache lies for components today because `@noctusai/lib/design-system/index.ts` re-exports break attribution. Same root-cause shape as the KB_CHAPTER extractor bug (yesterday). | `seed/lib/backend/noctusai_lib/graph/extract_code.py` (re-export resolution) · graph tests · noc-graph cache rebuild | TBD |
| W2 | `noctus.dev.component_bundle <name>` tool | The "organ-in-a-box" return: `{source, types, tests, deps[], consumers[], wiring_snippet, validation_status}` — the packaged knowledge per organ. | NEW `mcp/noctusai/tools/noctus/dev/component_bundle.py` + tests + KB doc + INDEX | TBD |
| W3 | `noctus.dev.component_list` tool + validation status derivation | Discoverability + sort by reuse. Derives `validated\|emerging\|shelfware` per component. | NEW `mcp/noctusai/tools/noctus/dev/component_list.py` + shared validation derivation in `noctusai_lib/.../validation_signal.py` + tests | TBD |
| W4 | Register first 5 seed organs | Populates the catalog with the proven canonical set. Each gets a `validation_override.yaml` sidecar where derived signal isn't enough. Surfaces the `shelfware: PageSkeleton/LLMSpendBadge/FakeModeBadge/ErrorBoundary` honestly. | `seed/lib/frontend/src/<each>.organ.yaml` (sidecar) + KB doc § Phase-1-canonical-set | TBD |

W1 is the prerequisite for W2-W4. W2-W3-W4 are file-disjoint and run in parallel after W1 lands.

## §3 Seed-first analysis

- **Does the seed already ship this?** No. The seed ships components (the bodies) but not the cache/tool layer that classifies + packages them by reuse. This project ADDS that layer.
- **Storage decision:** extend `noc-graph` (NOT a 9th cache). Add a `component_meta` table + new `consumes_component` edge kind resolved through re-exports + `validation_status` derived field. Reuses the 7-keeper-mirror freshness machinery for free; no sync-N+1.
- **Validation derivation:** `validated = ALL OF (consumers ≥ 3 ∧ has_test ∧ test_passes_in_CI ∧ no NOC-REMEDIATE markers in source ∧ no recent bug-fix commits in 14 days)`. `shelfware = consumers == 0`. `emerging = otherwise`.
- **Naming:** `organ` is the cache-side name; `component` remains the code-side name. The catalog maps `organ ⇔ component(s)`.

## §4a Dispatch routing

Tech-lead writes per `feedback_dispatch_with_project_and_notes`.

| Slice | Lens | Codification expectations | Routes not taken | Notes |
|---|---|---|---|---|
| W1 (re-export fix) | backend-engineer | s1: extractor patch + tests. s2: scoped-improvement if a recurring pattern. s3: KB pattern doc IF re-export gotcha generalizes. s4: keeper IF derivable. | Skipped: rewriting all extractors (out of scope; fix-on-contact). | The fix is the same shape as the KB_CHAPTER extractor bug — namedly `walk_kb_chapters` had a stale path check. This bug is the re-export-edge-resolution miss in `extract_code.py`. |
| W2 (`component_bundle`) | backend-engineer | s1: tool + tests. s2: memory if MCP-tool-shape pattern emerges. s3: KB pattern `component-bundle-tool.md`. s4: optional keeper. | Skipped: BE bundles (FE-only Phase 1). | Returns `{source, types, tests, deps[], consumers[], wiring_snippet, validation_status}`. AST-extracts; never regex. |
| W3 (`component_list` + validation derivation) | backend-engineer | s1: tool + tests. s2/s3: KB doc on the derived validation signal. s4: `check_organ_catalog_coherence` keeper. | Skipped: manual override sidecar (Phase 2). | Validation signal lives at `noctusai_lib/.../validation_signal.py` so reuse cross-product is possible at Phase 2. |
| W4 (register first 5 seed organs) | architect (advisor) + tech-lead inline | s1: organ.yaml sidecars + KB doc § Phase-1-canonical-set. s3: KB pattern `seed-organ-canonical-set.md`. | Skipped: registering Phase-2 social-wiring organs. | The first 5: `LoginForm` (9 consumers — top), `ForgotPasswordPage` (8), `AcceptInvitePage` (8), `ResourceManager` (3, has tests), `DigestCard` (3). Plus surface the 4 shelfware components honestly. |

## §5 Acceptance criteria

- W1: `noctus.graph.neighbors component:LoginForm edge_kinds=["consumes_component"]` returns ≥9 product nodes.
- W2: `noctus.dev.component_bundle ResourceManager` returns the structured bundle in ≤1s.
- W3: `noctus.dev.component_list sort=consumers_desc` lists the first 5 + correctly tags `shelfware` for the 4 zero-consumer components.
- W4: 5 organ.yaml sidecars committed; KB doc lists the canonical set with derived + override status.
- Project close: a fresh agent can answer "find me a reusable component for X" via `noctus.dev.component_bundle`/`component_list` without grep.

## §6 ↔ §11 self-check (proactive at every phase close)

Run at end of W1, W2, W3, W4: `--check-eight-way-sync` + `--verify-kb-sync` + the new `check_organ_catalog_coherence` (after W3) + outline-corpus baseline diff.

## Open questions

1. Should `consumes_component` be a directed edge from consumer → component, or component → consumer? Architect to decide at W1 design time.
2. Should `validation_status` be stored on the graph node or computed at query time? Likely computed (freshness — same as 8-way-sync auto-recompute).
3. Override-sidecar format: YAML sidecar next to the component OR central registry at `seed/lib/frontend/organs/<name>.yaml`? Decide at W4.

## Decision log

- 2026-05-29: project filed; Phase 1 = seed pilot; FE-first; storage = extend noc-graph; validation = derived (no manual catalog rot). Architect scout pre-read at `task aa7fcf56...` informed the decisions.
- 2026-05-29: validation signal definition pinned (end-to-end working code shipped reuse-mindset, NOT test-file-existence).

## Composes with

- `KB § PATTERNS/architect/noc-graph.md` — the 8th keeper-mirror this extends
- `KB § PATTERNS/common/cache-as-agent-tool.md` — the rule organs participate in
- `KB § PATTERNS/common/repetitive-task-skill-codification.md` — sibling N≥2 rule applied to procedures; this is its sibling applied to COMPONENTS
- `KB § PATTERNS/common/methodology-codification-pipeline.md` — the s1→s4 codification cadence
- `KB § PATTERNS/common/persistent-files-absorption.md` — absorption mindset extended from docs/findings to organs
- `.claude/skills/noc-absorb-product/SKILL.md` — the absorption skill this expands beyond products to components
- `feedback_seed_shape_vs_primitive_consume` — the seed-shape vs primitive-consume rule that governs how organs avoid forking the seed
