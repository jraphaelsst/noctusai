# noc-graph — queryable knowledge graph of the platform

**Where it lives.** Library at `seed/lib/backend/noctusai_lib/graph/`; MCP umbrella at `mcp/noctusai/tools/noctus/graph/`; CLI flag `python mcp/noctusai/cli.py --graph-build [SCOPE]`; output cache at `<repo>/.noc-graph/` (gitignored, derive-only).

**What it materializes.** The implicit relational index across (a) code (modules / classes / functions / methods / routes / MCP tools / React components / hooks) and (b) authored prose (KB patterns / KB guides / KB integrations / memory entries / projects / findings / proposals / product anchors / seed anchor). Edges include `imports` · `calls` · `inherits` · `consumes_seed` · `defined_in` · `contains` · `kb_pointer` · `memory_link` · `documents` (KB → code).

**Inspiration.** [Graphify](https://graphify.net/) — noc-native equivalent, but derived 100% from sources we already author and trust (AST + durable prose), **no LLM-inference layer**. Where Graphify mines `INFERRED` edges from comments + docs via LLM, noc's rationale is already authored prose (KB patterns, accept-with-rationale, findings.md, MEMORY frontmatter) — so our equivalent of "inferred rationale edges" is `EXTRACTED` at confidence 1.0.

## When to reach for it

| Situation | Use |
|---|---|
| Relational research turn ("what consumes the WhatsApp seam, and which products consume those MCPs?") | `noctus.graph.query` + `neighbors` instead of composing 3-5 scans |
| Architect orienting on an unfamiliar product | `noctus.graph.report focus_product=<slug>` + `graph.html` filtered to that product |
| "Which KB patterns document a given module?" | `noctus.graph.neighbors code:<path> edge_kinds=["documents"]` |
| "Shortest dependency chain from X to Y?" | `noctus.graph.path` |
| Visual orientation map for a session | open `.noc-graph/graph.html` (force-directed, click-to-expand, path mode) |

Reach for the per-tool MCP scans (`outline_*`, `refs`, `hound.scan`, `scan_cross_product_helpers`) when the question is **single-tool-shaped**. The graph is the join, not a replacement.

## MCP surface

| Tool | Input | Returns |
|---|---|---|
| `noctus.graph.build` | `scope: "repo"\|"product:<slug>"\|"seed"\|"kb"`, `output_dir?`, `memory_root?` | counts + paths |
| `noctus.graph.query` | `query`, `kinds?`, `limit=20` | ranked node matches |
| `noctus.graph.neighbors` | `node_id`, `depth=1`, `edge_kinds?` | subgraph + classified edges |
| `noctus.graph.path` | `source_id`, `target_id`, `max_depth=6` | path + via_kinds |
| `noctus.graph.explain` | `node_id` | full detail + grouped neighbors + cluster |
| `noctus.graph.report` | `focus_product?` | counts + clusters + top packages |

Run `noctus.graph.build scope="repo"` once per session (or after a non-trivial code change) before querying. End-to-end build on the current noc workspace: ~6-7s, ~20k nodes, ~32k edges.

## Schema (`graph.json`)

```json
{
  "schema_version": 1,
  "meta": {"scope": "repo", "build_seconds": 6.5, "clustering": "louvain|fallback-grouping", "node_count_by_kind": {...}},
  "nodes": [
    {"id": "code:products/social-wiring/.../routes.py:WhatsAppRouter", "label": "WhatsAppRouter",
     "kind": "class", "path": "products/...", "line": 12, "product": "social-wiring",
     "cluster": 4, "confidence": 1.0, "meta": {"docstring": "..."}}
  ],
  "edges": [
    {"source": "...", "target": "...", "kind": "consumes_seed", "confidence": 1.0, "weight": 1.0}
  ]
}
```

Node ids are **stable across rebuilds**. The `id` from a `noctus.graph.query` hit can be passed straight into `noctus.graph.neighbors`, `path`, or `explain`.

## Interactive visualization (`graph.html`)

Single-file HTML using [vis-network@9](https://visjs.github.io/vis-network/) loaded from jsdelivr CDN. No build step.

- **Layout**: force-directed (Barnes-Hut), Louvain clustering colors (or fallback product/seed/KB grouping when networkx is absent).
- **Controls**: top-bar search (live-ranked); left-rail filter chips for node kinds, products, confidence; right-side detail panel on double-click.
- **Interactions**: click → halo + 2-hop neighborhood emphasis; double-click → full panel; drag nodes; `p` toggles path mode (click source then target → animated traversal); `/` focuses search; `esc` clears; `f` future-toggles filters.
- **Effects**: animated focus/zoom, edge highlight propagation with fade on adjacent, animated path traversal, toast notifications.
- **Footer**: build timestamp + reference link to https://graphify.net/.

Open `file://.../.noc-graph/graph.html` directly (graph.json is inlined). For ~20k nodes (full repo) physics stabilization takes ~3-5s; for ~7k (single product) it's near-instant. Filter aggressively for navigability.

## Derivation discipline

- **Derive-only**: `graph.json` is never hand-maintained. Pre-commit incremental rebuild is a follow-up (`noc-graph-precommit` — see PROJECT §4).
- **No LLM-inference for v1**: every edge has a deterministic source (AST, authored doc, scanner output). Confidence = source provenance.
- **Reuse, don't replicate**: extractors call into the same primitives the MCP toolkit already exposes (`outline_*`, the same parsing discipline). If a feeder is reimplemented here, that's a recurrence-rule trip — fix it in the feeder, not in `noctusai_lib.graph`.
- **Open taxonomy**: new `NodeKind` / `EdgeKind` instances extend the enum; non-fitting instance ⇒ add the class, never force-fit.

## Deferred (destinations named)

- **L3 mined-edge layer** — consume `noctus.hound.scan` / `scan_cross_product_helpers` / `seed.scan_fusions` outputs as `MINED` edges. Destination: project `noc-graph-mined-layer`.
- **Pre-commit incremental rebuild + git merge driver for graph.json** — destination: project `noc-graph-precommit`.
- **Cross-language call graph** (Python ↔ TS via API contracts) — destination: not-yet-filed.
- **Vector-embedding semantic search** — destination: not-yet-filed.

## Related

- Project doc: [`projects/noc-graph/PROJECT.md`](../../../projects/noc-graph/PROJECT.md)
- Sibling primitives: `KB § PATTERNS/ast.md` (AST-first rule), `KB § PATTERNS/agent-reading-discipline.md` (narrow-read + Explore delegation), `KB § PATTERNS/seed-absorption.md` (`noctus.hound.scan` family — feeders for the deferred mined layer).
- External reference: https://graphify.net/ + https://github.com/safishamsi/graphify.
