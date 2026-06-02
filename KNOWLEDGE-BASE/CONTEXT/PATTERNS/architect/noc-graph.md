# noc-graph — structured graph of the whole platform (8th keeper-mirror cache)

**Where it lives.** Library at `seed/lib/backend/noctusai_lib/graph/`; MCP umbrella at `mcp/noctusai/tools/noctus/graph/`; cache module at `mcp/noctusai/tools/noctus/dev/noc_graph_cache.py`; CLI flag `python mcp/noctusai/cli.py --refresh-noc-graph`; SQLite mirror at `.claude/cache/noc-graph.sqlite` (gitignored); portable artifacts at `.noc-graph/{graph.json,graph.html,REPORT.md}` (gitignored, derived from the cache).

**What it materializes.** The implicit relational index across the WHOLE platform:

- **L0 anchors** — products (`product:<slug>`), seed (`seed:noctusai_lib`).
- **L1 code** — modules · classes · functions · methods · FastAPI ROUTES (`@router.get(...)` decorator) · MCP_TOOLs (`@server.tool(...)`) · React components · hooks · migrations.
- **L2 knowledge (authored prose)** — KB chapters / patterns / guides / integrations / backend-specs / frontend-specs · memory entries (incl. `mem:_INDEX` for `MEMORY.md`) · projects · proposals · findings.
- **L2 methodology fabric** — `.claude/agents/<name>.md` (HARNESS_AGENT) · `.claude/skills/<name>/SKILL.md` (HARNESS_SKILL) · `.claude/commands/<name>.md` (HARNESS_COMMAND) · `CLAUDE.md` + `CLAUDE/*.md` + `CONTEXTUALIZE.md` + `CHANGELOG.md` + `PROJECT-HISTORY.md` (LANDSCAPE_DOC) · KB top-level chapters re-typed as KB_CHAPTER.
- **L2 surface** — every `parser.add_argument("--flag", …)` in `mcp/noctusai/cli.py` becomes a CLI_FLAG node.
- **L2.5 history** — `project-history/auto-improvement.ndjson` events aggregated per-target: every node gains `ai_events` / `ai_last_stage` / `ai_last_ts` decorations; targets with ≥ 3 events get an AUTO_IMPROVEMENT_EVENT aggregate node.
- **L3 mined (additive, confidence < 1.0)** — `MINED_RECURRENCE` edges from `noctus.hound.scan` + `scan_cross_product_helpers` + `scan_within_product_helpers` + `seed.scan_fusions`; injection via `noctusai_lib.graph.ingest_mined_rows(graph, rows_by_scanner)` at the mcp boundary (seed lib cannot import from mcp).

**Edge taxonomy.** `imports` · `calls` · `inherits` · `decorates` · `mounts` · `consumes_seed` · `exports` · `kb_pointer` · `memory_link` · `documents` · `defined_in` · `belongs_to` · `contains` · **`auto_triggers`** · **`owns_kb`** (agent → KB) · **`invokes_skill`** · **`invokes_agent`** · **`exposes_tool`** (module → mcp_tool) · **`exposes_flag`** (cli.py → flag) · **`guarded_by`** · **`referenced_by_event`** · **`mirrors`** · **`mined_recurrence`** (L3) · **`semantic_neighbor`** (L3, planned via embedding caches) · **`consumes_component`** (consumer-module → canonical component node, resolved through barrel re-exports — see §Re-export resolution below).

**Inspiration.** [Graphify](https://graphify.net/) — noc-native equivalent, but derived 100% from sources we already author and trust (AST + durable prose), **no LLM-inference layer**. Where Graphify mines `INFERRED` edges from comments + docs via LLM, noc's rationale is already authored prose (KB patterns, accept-with-rationale, findings.md, MEMORY frontmatter, agent owns_kb, skill triggers) — so our equivalent of "inferred rationale edges" is `EXTRACTED` at confidence 1.0.

## Why this exists — the orientation problem

A fresh agent facing the platform needs to answer questions like:

- "Which skills exist? Which trigger on what?"
- "What KB does agent X own?"
- "What does this product consume from seed?"
- "Which mcp tools live in module Y?"
- "What CLI flag refreshes cache Z?"
- "What's loaded into every session by default?"

The OLD way: 5 composed scans (`outline_*` + `refs` + KB grep + memory read + `noctus.hound.scan`) per turn, ephemeral, no shared node-ID space.

The NEW way: ONE call. The graph is the **join** of every other tool the platform already ships. `/contextualize` is the fresh-agent entry point — it triggers `noctus.graph.report` + targeted `noctus.graph.query` against the harness/landscape/kb_chapter kinds. Oriented agents skip it (NO-OP) — the cost is amortized across the cache, not paid per turn.

## When to reach for it

| Situation | Use |
|---|---|
| Fresh agent boots / first turn / "I don't know this platform" | `/contextualize` (slash) → loads graph orientation + the depth set on demand |
| Relational research turn ("what consumes the WhatsApp seam, and which products consume those MCPs?") | `noctus.graph.query` + `neighbors` instead of composing 3-5 scans |
| Architect orienting on an unfamiliar product | `noctus.graph.report focus_product=<slug>` |
| "Which KB patterns does agent X own?" | `noctus.graph.neighbors agent:<name> edge_kinds=["owns_kb"]` |
| "Shortest dependency chain from X to Y?" | `noctus.graph.path` |
| "Hot drift surfaces (≥3 auto-improvement events on same target)" | `noctus.graph.query "" kinds=["auto_improvement_event"]` |
| "Which N≥3 recurrences haven't been formalized?" | filter L3 edges: `mined_recurrence` with weight ≥ 3 |

Reach for per-tool MCP scans (`outline_*`, `refs`, `hound.scan`, `scan_cross_product_helpers`) when the question is **single-tool-shaped**. The graph is the join, not a replacement.

## MCP surface

| Tool | Input | Returns |
|---|---|---|
| `noctus.graph.build` | `scope: "repo"\|"product:<slug>"\|"seed"\|"kb"\|"harness"`, `output_dir?`, `memory_root?` | counts + paths |
| `noctus.graph.query` | `query`, `kinds?`, `limit=20` | ranked node matches |
| `noctus.graph.neighbors` | `node_id`, `depth=1`, `edge_kinds?` | subgraph + classified edges |
| `noctus.graph.path` | `source_id`, `target_id`, `max_depth=6` | path + via_kinds |
| `noctus.graph.explain` | `node_id` | full detail + grouped neighbors + cluster |
| `noctus.graph.report` | `focus_product?` | counts + clusters + top packages |
| `noctus.dev.noc_graph_status` | — | cache state + node/edge breakdown by kind |
| `noctus.dev.refresh_all_caches only=["noc-graph"]` | — | refresh just this cache |

Build numbers on the current noc workspace (2026-05-27 post-refactor): **~23,800 nodes / ~38,500 edges in ~13s** (full repo). Scope `harness` produces ~80 nodes / ~150 edges in <500ms — the cheap path for `/contextualize`.

## Schema (`graph.json`)

```json
{
  "schema_version": 1,
  "meta": {
    "scope": "repo", "build_seconds": 13.5,
    "clustering": "louvain|fallback-grouping",
    "node_count_by_kind": {...}, "edge_count_by_kind": {...}
  },
  "nodes": [
    {"id": "code:products/social-wiring/.../routes.py:WhatsAppRouter",
     "label": "WhatsAppRouter", "kind": "class", "path": "products/...",
     "line": 12, "product": "social-wiring", "cluster": 4, "confidence": 1.0,
     "meta": {"docstring": "...", "ai_events": 7, "ai_last_stage": "s3"}}
  ],
  "edges": [
    {"source": "...", "target": "...", "kind": "consumes_seed",
     "confidence": 1.0, "weight": 1.0}
  ]
}
```

Node ids are **stable across rebuilds**. The `id` from a `noctus.graph.query` hit can be passed straight into `noctus.graph.neighbors`, `path`, or `explain`.

## Interactive visualization (`graph.html`)

Single-file HTML using [vis-network@9](https://visjs.github.io/vis-network/) loaded from jsdelivr CDN. No build step. Re-derived from the cache on every refresh.

- **Layout**: force-directed (Barnes-Hut), Louvain clustering colors (or fallback product/seed/KB grouping when networkx is absent).
- **Controls**: top-bar search (live-ranked); left-rail filter chips for node kinds, products, confidence; right-side detail panel on double-click.
- **Interactions**: click → halo + 2-hop neighborhood emphasis; double-click → full panel; drag nodes; `p` toggles path mode (click source then target → animated traversal); `/` focuses search; `esc` clears; `f` future-toggles filters.

For ~24k nodes (full repo) physics stabilization takes ~3-5s; filter aggressively for navigability.

## The 3-leg keeper-mirror contract (sibling of 7 other caches)

1. **Eager** — pre-commit + `post-merge` + `post-checkout` + `pre-push` hooks invoke `python mcp/noctusai/cli.py --refresh-noc-graph` whenever a graph-input file changes (code corpus / KB / `.claude/agents+skills+commands/` / `CLAUDE.md` / `CONTEXTUALIZE.md` / `CHANGELOG.md` / `project-history/*` / `mcp/noctusai/cli.py`).
2. **Lazy** — `noctus.dev.noc_graph_cache.refresh()` compares the cached `aggregate_source_sha` (sha256 over every source file's content) against the live aggregate; in-sync ⇒ no-op (~50 ms); drift ⇒ **incremental** rebuild when only cheap buckets changed (~5 s — both the AST walk and the O(N²) semantic cosine are skipped via per-bucket reuse; see *Incremental rebuild*), else a full rebuild.
3. **Loud** — `check_noc_graph_cache_freshness` keeper surfaces stale cache as a warning (advisory tier: orientation degrades, never blocks correctness). Wired into the master `check_compliance` aggregator.

## Pairings with other mechanisms

| Pairs with | How |
|---|---|
| **AST** (outline_python/typescript) | extract_code uses stdlib `ast` (mirrors `outline_python` discipline); the always-outline-able invariant guarantees lossless extraction |
| **kb-embeddings / memory-embeddings / corpus-embeddings** | (planned L3) cosine-sibling ⇒ `SEMANTIC_NEIGHBOR` MINED edges between docs that read similar but lack explicit pointers |
| **noctus.hound.scan + scan_cross_product_helpers + seed.scan_fusions** | injected into L3 mined-edge layer via `ingest_mined_rows`; each row mints `MINED_RECURRENCE` edges with the scanner's score as confidence |
| **auto-improvement ndjson** | aggregated into per-node decorations (`ai_events`, `ai_last_stage`, `ai_last_ts`) + hot-aggregate nodes for ≥ 3 events on same target |
| **keeper-pattern cache** | (planned) each keeper's `expected_path` ⇒ a `GUARDED_BY` edge from code → keeper rule |

## Derivation discipline

- **Derive-only**: `graph.json` + `graph.html` + the SQLite cache are never hand-maintained.
- **No LLM-inference for L1/L2**: every edge has a deterministic source (AST, authored doc, scanner output). Confidence = source provenance.
- **Reuse, don't replicate**: extractors call into the same primitives the MCP toolkit already exposes (`outline_*`, the same parsing discipline). If a feeder is reimplemented here, that's a recurrence-rule trip — fix it in the feeder, not in `noctusai_lib.graph`.
- **Open taxonomy**: new `NodeKind` / `EdgeKind` instances extend the enum; non-fitting instance ⇒ add the class, never force-fit.

## Incremental rebuild

The graph derives from **7 disjoint input buckets** — `code · kb · harness · landscape · memory · cli · history` — each with its own sub-sha persisted in `cache_meta` as `bucket_sha:<name>`. `refresh()` has three paths:

1. **in-sync** — aggregate `source_sha` unchanged ⇒ no-op (~50 ms).
2. **incremental** — the EXPENSIVE `code` bucket sub-sha is unchanged ⇒ reuse the persisted `code:*` nodes/edges and SKIP the AST walk; re-run the cheap knowledge tier (kb/harness/landscape/memory/cli/history) + finalization (`_assemble_incremental`).
3. **full** — `force=True`, no usable cache, or the `code` bucket changed.

**The two dominant costs, both skipped on a doc-only commit:**

- **The AST walk** (~60 s) — skipped by the `code`-bucket reuse above.
- **The O(N²) `SEMANTIC_NEIGHBOR` cosine** (~60 s) — skipped by the *semantic-reuse gate*: `semantic_neighbor_fingerprint(graph, root)` (in `tools/noctus/graph/build.py`) is a sha over `(every embedding vector loaded from the 4 caches, the resolvable node-id set)` — the **complete + only** inputs to the pair computation. When the live fingerprint equals the persisted `semantic_fingerprint`, the persisted `SEMANTIC_NEIGHBOR` edges are reused VERBATIM. `GUARDED_BY` (sub-second) always recomputes.

Measured on the live tree: a doc-only commit goes **67 s → 5.4 s (92% saved)**.

### Equivalence invariant (the correctness gate)

> A full rebuild and an incremental rebuild from the same tree state MUST produce equivalent graphs — identical node id-set AND edge id-set.

Proven by `test_noc_graph_incremental.py::TestFullVsIncrementalParity` (extractor parity) + `TestSemanticReuseEquivalence::test_reuse_path_equals_full_recompute` (semantic-edge parity), and re-verified end-to-end on the live tree.

**Cross-bucket-edge invariant chosen:** R3-derived rows are **owned by the always-re-run R3 pass, never by the reused `code` bucket.** `_compute_guarded_by_edges` *synthesizes* `code:…compliance.py::<keeper>` `keeper_rule` nodes (+ `GUARDED_BY` edges) which persist with a `code:` id; `_load_cached_code_subgraph` therefore EXCLUDES `kind='keeper_rule'` nodes and `kind IN ('guarded_by','semantic_neighbor')` edges from reuse. Without this exclusion the incremental node-set diverges from a full build pre-R3 (busting the fingerprint) and a removed keeper would leak a stale node. The `keeper_rule` nodes are re-emitted every rebuild by the always-re-run harness walk + R3, so excluding them from reuse loses nothing.

## Re-export resolution (`consumes_component` edge)

**Bug shape (fixed, project W1).** Previously the TS extractor emitted only a `consumes_seed` edge pointing at the barrel package path (e.g. `pkg:@noctusai/lib/design-system`). Named symbols like `LoginForm` consumed by 9 products had ZERO graph attribution — same root-cause shape as the KB_CHAPTER extractor's stale-path check: the resolution rule was incomplete.

**Fix: `BarrelResolver`.** Built once per graph-build, before the code-walk loop, from the `seed/lib/frontend/src/` tree. Walks every `index.ts` in the barrel whitelist; parses `export { Foo } from "./path"` lines to build a `symbol → canonical_repo_relative_path` map.

**Barrel whitelist** (more-specific first):

| Package alias | Barrel file |
|---|---|
| `@noctusai/lib/design-system/components` | `design-system/components/index.ts` |
| `@noctusai/lib/design-system/ai` | `design-system/ai/index.ts` |
| `@noctusai/lib/design-system` | `design-system/index.ts` |
| `@noctusai/lib/components` | `components/index.ts` |
| `@noctusai/lib` | `index.ts` |
| `noctusai-lib` | `index.ts` |

**Edge direction decision.** `consumer-module → component` (forward, same polarity as `IMPORTS`). Rationale: the natural query is "who uses LoginForm?" = incoming edges on the component node: `noctus.graph.neighbors component:<id> edge_kinds=["consumes_component"] incoming=True`. Reversed direction (component → consumer) would require inverting the traversal at every query site.

**Circular-attribution guard.** Files named `index.ts` or `index.tsx` under `seed/lib/frontend/src/` are detected as barrel shims (`is_barrel_shim = True`) and skipped as edge sources — preventing barrel→component cycles. Only the original consumer file (a product page/component) becomes the edge source.

**Target node ID format.** `code:<canonical_repo_relative_path>:<SymbolName>` — joins with the node already emitted by `_extract_typescript` when it processes the canonical `.tsx` file. Confidence: `EXTRACTED_LOW` (0.75) because regex-parsed import destructuring is anchored but not as strong as Python's `ast`.

**Query example.**
```
noctus.graph.neighbors component:seed/lib/frontend/src/design-system/components/LoginForm.tsx:LoginForm edge_kinds=["consumes_component"]
# → returns all 9 product Login.tsx consumer nodes
```

## Deferred (destinations named)

- **L3 SEMANTIC_NEIGHBOR layer via the 4 embedding caches** — kb/code/memory/corpus embedding centroids → similarity-mined edges. Destination: follow-up `noc-graph-semantic-neighbors`.
- **GUARDED_BY edges from keeper-pattern cache** — code → keeper rule. Destination: follow-up `noc-graph-keeper-edges`.
- **Cross-language call graph** (Python ↔ TS via API contracts). Destination: not-yet-filed.
- **Committed `graph.json` + git merge driver** — gated on cache stability signal.

## Related

- Sibling primitives: `KB § PATTERNS/common/ast.md` (AST-first rule), `KB § PATTERNS/common/agent-reading-discipline.md` (narrow-read + Explore delegation), `KB § PATTERNS/common/cache-auto-freshness.md` (the 3-leg contract every keeper-mirror cache implements), `KB § PATTERNS/common/eight-way-sync.md` (the methodology surfaces this graph indexes).
- Skill: `.claude/skills/noc-contextualize/SKILL.md` (the fresh-agent entry point).
- Command: `.claude/commands/contextualize.md` (the `/contextualize` slash command).
- External reference: https://graphify.net/ + https://github.com/safishamsi/graphify.
