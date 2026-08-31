# seed-organs-cache — the body layer of seed absorption

> **Status:** PHASE 1 (seed pilot). W1–W4 shipped; W5 tooling shipped 2026-05-29 (e2e-per-organ leg blocked on a pre-existing FE harness gap — scoped as a follow-up). Durable learnings → `KB § PATTERNS/common/build-learn-cache-mindset.md §7a` (NOT parked here — this file is archived).
> **Slug:** `seed-organs-cache`
> **Born:** 2026-05-29.
> **Owner:** tech-lead (orchestrator).

## §0 Outcome

The platform already caches the seed's **skeleton** — methodology, infrastructure, agent fabric, shared lib re-exports — via the 8 keeper-mirror caches. This project adds the **body layer**: validated reusable components/pages/functionality, cached + embedded for query-and-reuse.

The seed-absorption discipline (`noc-absorb-product`) gains a sibling for components/pages: each validated organ is absorbed into the cache with its FE source, BE source, types, schema, tests, wiring contract, and consumer roster — queryable by intent ("I need a credentials list with multi-account selector") via vector + graph search.

**Reuse contract.** When building a new page/feature: query the cache → pick a validated organ → consume by reference. If no fit: build it, validate it end-to-end, register it. The catalog grows by USE, not by speculation.

**Validation signal (the load-bearing definition):** an organ is `validated` when its FE is 100% built with validated data flows + working functions AND its BE is 100% built, sanitized, optimized. NOT "has a test file." NOT a human verdict alone. The signal is **end-to-end working code shipped with reuse-mindset by construction**.

## §1 Scope

- Phase 1 (this project): **seed pilot** — 5 canonical seed components registered as the first organs (auth trio `LoginForm` + `ForgotPasswordPage` + `AcceptInvitePage`, plus `ResourceManager`, plus `DigestCard`). Build the tooling that makes registration + query work. Prove the loop. Each registered organ ships its **build-learn-cache knowledge bundle** alongside source + tests (see §3a).
- Phase 2 (NEXT project, not this one): **social-wiring pilot** — first product's organs cached (multi-account integrations CRUD is the obvious first; settings page is the second).
- Phase 3+ (deferred per-product): every other product's organs cached one product at a time, methodically.

Out of scope for Phase 1: BE-only organs (focus FE first), per-product overrides, manual override sidecar (start with derived-only).

## §3a Build-Learn-Cache mindset (the loop applied to organs)

Per the 2026-05-29 codification at `KB § PATTERNS/common/build-learn-cache-mindset.md`, every organ accumulates KNOWLEDGE during dev — not just at project close. The cache holds the artifact AND the journey. Each organ in this catalog carries 8 knowledge fields:

| Field | What it carries |
|---|---|
| `known_facts` | What we discovered about this organ (behaviors, invariants, constraints) |
| `errors_encountered` | Bugs hit during dev + the resolution + the patch SHA |
| `drifts_surfaced` | Pre-existing drift surfaced by this organ's work (cite auto-improvement ndjson refs) |
| `alternatives_considered` | Designs tried and abandoned + why |
| `manual_validation_log` | `[{date, validator, finding, status}]` — user-provided feedback during the build |
| `integration_test_status` | Latest run result + which integration tests cover this organ |
| `e2e_test` | `{path, status, last_run, runs_in_ci}` — every organ ships at least one e2e test |
| `bugs_fixed_during_dev` | Commit SHAs of in-flight fixes (the "we hit X and fixed it like Y" log) |

**Validation is hybrid (automated + manual).** Automated tests and CI status alone don't make an organ validated — manual validation feedback (user reports "works for case A but fails when X") gets cached too. Both signals feed the `validation_status` derivation.

**The loop runs during dev AND beyond.** Refactor, bug-fix, integration touch-up, deploy — each event APPENDS to the organ's knowledge log via `noctus.dev.organ_knowledge_append <name> <event>` (or equivalent). Knowledge never gets parked in transcripts or commit messages alone — those aren't queryable by intent.

This extends `KB § PATTERNS/common/persistent-files-absorption.md` from "absorb at project close" to "absorb continuously per artifact."

## §3b Vectorization & embedding (cache-as-agent-tool requirement — LOAD-BEARING)

The organ cache MUST be queryable by INTENT, not just by name. "Find me a reusable component for credentials list with multi-account picker" is the query shape that justifies the whole project. This requires each organ + its knowledge bundle to be EMBEDDED + INDEXED for vector-similarity search.

**Embedding write path (W4 + W5 obligation):**
- On organ registration (W4): the organ bundle (source + types + tests + the 8 knowledge fields concatenated as a structured chunk) is embedded via the existing `noctusai_lib.integrations.llm` OpenAI embedding pipeline and persisted to the `code-embeddings.sqlite` cache with `chunk_kind = "organ"` (a NEW chunk kind — extend the existing schema).
- On every `noctus.dev.organ_knowledge_append` (W5): the knowledge log appends new content → the organ chunk is re-embedded (or the new event is appended as a sibling chunk with `parent_organ = <name>`) → the search index stays current automatically.
- Cost ledger via `vector-costs.ndjson` per existing pattern.

**Embedding read path (W4 — `noctus.dev.find_reusable_component`):**
- Tool: `noctus.dev.find_reusable_component "<intent>" [--filter-status validated]`
- Embeds the query via OpenAI → cosine-top-K vector search over `code-embeddings.sqlite WHERE chunk_kind='organ'` → optionally re-ranks by validation_status → returns top-K with the `component_bundle` shape from W2.
- Falls back to graph keyword search if embedding provider is unreachable.

**Why this lives in code-embeddings, not a 9th cache.** code-embeddings is sqlite-vec (fast cosine), the right shape for this query. Adding a 9th cache would force a sync-N+1 + re-embed-everything pass; extending an existing sqlite-vec cache with a new chunk_kind is the cheap path. Aligns with the architect's "extend, don't proliferate" recommendation.

**The `organ_knowledge_append` re-embed contract**: when knowledge is appended, the embedding refresh runs INLINE (synchronous) — agents querying after a manual_validation_log entry MUST see the new content. This is the build-learn-cache loop's structural feedback closure: the cache reflects the journey AS IT HAPPENS, not at project close.

**Source SHA invariant:** the organ chunk's `source_sha` includes a hash of (source + tests + knowledge bundle) — any of the 8 fields changes → re-embed. Reuses the 3-leg mirror contract.

## §2 Phases (this project = Phase 1)

| # | Slice | Why | Files-to-modify (primary) | Status |
|---|---|---|---|---|
| W1 | Fix noc-graph re-export attribution | Honest consumer counts unblock everything downstream; the cache lies for components today because `@noctusai/lib/design-system/index.ts` re-exports break attribution. Same root-cause shape as the KB_CHAPTER extractor bug (yesterday). | `seed/lib/backend/noctusai_lib/graph/extract_code.py` (re-export resolution) · graph tests · noc-graph cache rebuild | TBD |
| W2 | `noctus.dev.component_bundle <name>` tool | The "organ-in-a-box" return: `{source, types, tests, deps[], consumers[], wiring_snippet, validation_status}` — the packaged knowledge per organ. | NEW `mcp/noctusai/tools/noctus/dev/component_bundle.py` + tests + KB doc + INDEX | TBD |
| W3 | `noctus.dev.component_list` tool + validation status derivation | Discoverability + sort by reuse. Derives `validated\|emerging\|shelfware` per component. | NEW `mcp/noctusai/tools/noctus/dev/component_list.py` + shared validation derivation in `noctusai_lib/.../validation_signal.py` + tests | TBD |
| W4 | Register first 5 seed organs + knowledge bundles | Populates the catalog with the proven canonical set + each organ ships its 8-field knowledge bundle (per §3a). Each gets an `organ.yaml` sidecar (source + tests + e2e + known_facts/errors/drifts/alternatives/manual_validation/integration). Surfaces the `shelfware: PageSkeleton/LLMSpendBadge/FakeModeBadge/ErrorBoundary` honestly. | `seed/lib/frontend/src/<each>.organ.yaml` (sidecar) + KB doc § Phase-1-canonical-set | TBD |
| W5 | E2E test automation per organ + `noctus.dev.organ_knowledge_*` tools | Every registered organ ships at least one e2e test (Playwright or vitest+RTL+MSW pair). MCP tools `organ_knowledge_append <name> <event>` (write) + `organ_knowledge_query <name>` (read) so future builders see the full journey. Manual-validation entries logged via the same tool. | NEW `mcp/noctusai/tools/noctus/dev/organ_knowledge.py` + e2e tests per organ (Phase-1 set) + KB doc | **TOOLING SHIPPED** (append/query + inline re-embed + CLI + 14 tests). **e2e leg BLOCKED** on pre-existing `seed/lib/frontend` vitest harness gap (dual-React + jest-dom matchers; `ResourceManager.test.tsx` fails 6/6) → follow-up `NOC-REMEDIATE[harness-vitest-dual-react]`. |

W1 is the prerequisite for W2-W3. W2-W3-W4-W5 run in dependency order: W1 → W2+W3 (parallel) → W4 (registers using W2+W3) → W5 (e2e + knowledge tooling).

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
- W4: 5 organ.yaml sidecars committed; KB doc lists the canonical set; each sidecar carries the 8 knowledge fields (per §3a), populated from the project's auto-improvement ndjson + commit history + manual validation log; derived + override status reconciled.
- W5: each of the 5 organs has ≥1 e2e test (path recorded in sidecar `e2e_test.path`); `noctus.dev.organ_knowledge_append` writes a new event; `noctus.dev.organ_knowledge_query <name>` returns the accumulated journey.
- Project close: a fresh agent can answer "find me a reusable component for X" via `noctus.dev.component_bundle`/`component_list` without grep AND can answer "what did we learn building Y" via `organ_knowledge_query` without reading commit logs.
- **Validation co-loop**: orchestrator + user run manual validation together; findings cached in `manual_validation_log` per organ; the build-learn-cache loop is dogfooded on this very project.

## §6 ↔ §11 self-check (proactive at every phase close)

Run at end of W1, W2, W3, W4: `--check-eight-way-sync` + `--verify-kb-sync` + the new `check_organ_catalog_coherence` (after W3) + outline-corpus baseline diff.

## Open questions

1. Should `consumes_component` be a directed edge from consumer → component, or component → consumer? Architect to decide at W1 design time.
2. Should `validation_status` be stored on the graph node or computed at query time? Likely computed (freshness — same as 8-way-sync auto-recompute).
3. Override-sidecar format: YAML sidecar next to the component OR central registry at `seed/lib/frontend/organs/<name>.yaml`? Decide at W4.

## Decision log

- 2026-05-29: project filed; Phase 1 = seed pilot; FE-first; storage = extend noc-graph; validation = derived (no manual catalog rot). Architect scout pre-read at `task aa7fcf56...` informed the decisions.
- 2026-05-29: validation signal definition pinned (end-to-end working code shipped reuse-mindset, NOT test-file-existence).
- 2026-05-29: **Build-Learn-Cache mindset absorbed into project** (user-extended mid-flight). Added §3a + W5 + extended §5 acceptance. 8 knowledge fields per organ; hybrid manual+automated validation; e2e per organ; "the loop runs during dev AND beyond" (refactor/bugfix/integration/deploy continue appending). Codified at `KB § PATTERNS/common/build-learn-cache-mindset.md`.
- 2026-05-29 (W5): **organ_knowledge_append/query tooling SHIPPED** — the loop's read/write mechanism (8-field taxonomy by mutation shape: list-append / scalar-set / object-merge; inline `register_organ(force=True)` re-embed per §3b; MCP + CLI; 14 unit tests green; dogfooded on `ResourceManager` + `DigestCard` sidecars). Documented at `KB § build-learn-cache-mindset.md §7a` (durable; survives this project's archival). **e2e-per-organ leg deferred** — a render test authored for `DigestCard` surfaced that the `seed/lib/frontend` vitest harness is broken (dual-React `null useState` + jest-dom matchers unregistered); the existing `ResourceManager.test.tsx` fails 6/6 too. The harness fix (dedupe + `react-dom/client`/`react/jsx-runtime` subpath aliases + setup matcher registration) is its own infra slice that must land before the e2e leg + the `e2e_test` sidecar field. Tracked as `NOC-REMEDIATE[harness-vitest-dual-react]`.

## Composes with

- `KB § PATTERNS/architect/noc-graph.md` — the 8th keeper-mirror this extends
- `KB § PATTERNS/common/cache-as-agent-tool.md` — the rule organs participate in
- `KB § PATTERNS/common/repetitive-task-skill-codification.md` — sibling N≥2 rule applied to procedures; this is its sibling applied to COMPONENTS
- `KB § PATTERNS/common/methodology-codification-pipeline.md` — the s1→s4 codification cadence
- `KB § PATTERNS/common/persistent-files-absorption.md` — absorption mindset extended from docs/findings to organs
- `.claude/skills/noc-absorb-product/SKILL.md` — the absorption skill this expands beyond products to components
- `feedback_seed_shape_vs_primitive_consume` — the seed-shape vs primitive-consume rule that governs how organs avoid forking the seed
