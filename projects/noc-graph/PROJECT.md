# noc-graph — Queryable knowledge graph of the noc platform

> Living document. Symbol-first. Phase status icons (`✅ ⏳ ❌ 🔒`); triage `[F]/[R]/[A]`; recurrence `N=2`⇒triage / `N≥3`⇒MUST formalize.

- **Created:** 2026-05-20
- **Last updated:** 2026-05-20
- **Status:** Design locked → Phase 1 in progress
- **Owner / stakeholders:** USER (joaoraphaelsst) · Architect (this session)
- **Related docs:** `CLAUDE.md` § AST-first · `KB § PATTERNS/agent-reading-discipline.md` · `KB § PATTERNS/ast.md` · `KB § PATTERNS/seed-absorption.md` · `KB § PATTERNS/mcp-first-scripts.md` · graphify reference: https://graphify.net/ + https://github.com/safishamsi/graphify
- **Project slug:** `noc-graph` — root project (cross-cutting platform infrastructure: every product + seed + KB + memory is an input). Location: `projects/noc-graph/`.

---

## 1. Context & Purpose

Research-heavy turns on noc currently compose 3-5 different MCP scans (`noctus.dev.outline`, `refs`, `scan_cross_product_helpers`, `noctus.hound.scan`, grep) plus manual reads of KB / MEMORY / MASTER-PROMPT to answer relational questions like *"which products consume the WhatsApp seam and through which MCPs"*. Each scan is on-demand, each answer is ephemeral, none share a node-ID space. The implicit graph is reconstructed from scratch every turn.

External reference Graphify (https://graphify.net/) reports ~71× token-reduction on a 52-file mixed corpus by materializing the index once and querying it cheaply. The user evaluated and asked us to build a noc-native equivalent: same shape (materialized AST + authored-rationale graph; vis-network HTML; MCP query surface; pre-commit incremental rebuild) but **derived 100% from sources we already own and trust** — no LLM-inference layer, since noc's rationale is authored prose (KB patterns, accept-with-rationale, findings.md, MEMORY frontmatter), not LLM-mined.

The win: a single MCP call (`noctus.graph.query "what consumes the WhatsApp seam"`) replaces a multi-tool research pipeline; an interactive `graph.html` gives architects a clickable orientation map of an unfamiliar product; the artifact is regenerable from inputs (never drifts, only stales).

---

## 2. Confirmed constraints

- **No external feature** — user explicitly does NOT want to consume Graphify; build our own. *(Drives implementation as a noc-native MCP + seed library, not a wrapper.)*
- **No LLM-inference for relationships** — every edge has a deterministic source (AST, authored doc, existing scanner). *(Drives confidence-tagging directly from source provenance; no Anthropic/OpenAI calls in the build pipeline.)*
- **Visualization must be interactive with effects** — easily navigable, expandable, clickable, animated. *(Drives choice of vis-network with custom CSS/transitions; explicit reference to graphify's UI shape.)*
- **MCP-first** — every capability exposed as `noctus.graph.*` per `KB § PATTERNS/mcp-first-scripts.md`. *(No bare `scripts/build-graph.sh`; CLI flag on `mcp/noctusai/cli.py` only.)*
- **AST-first** — code-side extraction reuses `outline_python` (libcst-equivalent via stdlib `ast`) and `outline_typescript` (ts-morph). No regex on source. *(Matches §1 rule + always-outline-able invariant — the graph is guaranteed lossless on the EXTRACTED layer.)*
- **Derive-only, regenerable** — `graph.json` is never hand-maintained; pre-commit incremental rebuild keeps it fresh. *(Cannot drift, can only be stale; staleness surfaceable by re-running.)*

---

## 3. Design principles

1. **Reuse, don't replicate.** Feeders are existing tools: `outline_python` / `outline_typescript` / `refs` / `hound.scan` / `scan_*`. The graph is the *join*, not a competitor. Recurrence rule fires if any feeder is reimplemented.
2. **Confidence ≡ source provenance.** AST-derived edges = `EXTRACTED` (1.0). Authored-doc edges (KB pointers, `[[name]]` links, manifest manifests) = `EXTRACTED` (1.0). Scanner-mined edges (hound.scan, scan_cross_product_helpers) = `MINED` (the scanner's own score). No LLM ⇒ no `INFERRED`/`AMBIGUOUS` class in v1.
3. **Two-layer node taxonomy.** L1 *Code* (module/class/function/route/mcp_tool/component/hook/migration). L2 *Knowledge* (kb_pattern/memory/master_prompt_section/finding/project/proposal/product). Edges cross layers (e.g. `kb_pattern --documents--> mcp_tool`).
4. **Open taxonomy.** New node/edge kinds extend the enum; non-fitting instance ⇒ add the class, never force-fit. Matches always-hardening posture.
5. **Symbol-first ids.** Node id = `<path>:<symbol>` for code, `kb:<filename>#<section>` for KB, `mem:<slug>` for memory. Stable across rebuilds.
6. **HTML viz inherits the doc-symbology palette.** Node colors map to the same kind-classes used in symbology (`✅` / status / `s1-s4` stages). Visual language consistent with the rest of the platform.

---

## 3a. Seed-first analysis (REQUIRED)

1. **Is the contract identical for every product?** YES — every product is an input to the same graph; every product wants the same query surface; the extractor walks the unified file tree. ⇒ Cross-product concern.
2. **Is the data source product-specific?** NO — the extractor reads from a uniform substrate (`products/*/`, `seed/`, `mcp/`, `KNOWLEDGE-BASE/`, `MEMORY/`). Per-product specifics surface as *node attributes* (`product=<slug>`), not as separate code paths.
3. **Is the placement product-specific?** NO — output lives at `.noc-graph/` (top-level, gitignored, single cache for the whole repo) + MCP tools at `mcp/noctusai/tools/noctus/graph/`. Library at `seed/lib/backend/noctusai_lib/graph/`.
4. **Is the visibility / permission rule the same?** YES — read-only over the repo; no per-product gate.
5. **Does the seam already exist in seed?** NO — new `noctusai_lib.graph` module. *Verified*: `ls seed/lib/backend/noctusai_lib/` shows no `graph/` ⇒ green-field; not lifting from an existing product.
6. **Default-on or opt-in?** OPT-IN — agents call `noctus.graph.*` when researching. Pre-commit rebuild gated behind `NOC_GRAPH_PRECOMMIT=1` env flag (off by default to keep the gate fast).

**Litmus — per-product code count this design requires:** ✅ **0 lines.** Pure cross-product concern. Library + MCP tools + HTML template all live in shared locations; no product gets its own `graph_config.py`.

**Phase plan implications:** §6 phases work *in seed and in the MCP toolkit*, not per-product. There is no `products/<slug>/` walk-through. Validation runs against `products/social-wiring/` as a representative input — not because the code lives there.

---

## 4. Scope

**In scope (v1 / this project):**
- `noctusai_lib.graph` — schema (Node/Edge/Graph dataclasses + enums), L1 code extractor, L2 doc/memory extractor, JSON + HTML serializers.
- `noctus.graph.{build, query, neighbors, path, explain, report}` — 6 MCP tools.
- Single-file interactive `graph.html` template (vis-network, search, type/confidence/product filters, click-to-expand neighborhood, hover details, animated transitions, mini-map, dark theme matching noc).
- `cli.py --graph-build [scope]` flag (entry point for hooks + manual rebuild).
- End-to-end smoke against the whole repo + `products/social-wiring/` as focal product.
- KB pattern doc + CLAUDE.md pointer + MEMORY index entry + feedback memory.

**Out of scope (deferred — destinations named):**
- **L3 mined-edge layer** (consume `hound.scan` / `scan_cross_product_helpers` / `seed.scan_fusions` outputs as edge feeders) — destination: follow-up project `noc-graph-mined-layer`. Reason: feeders ship today; the join logic is its own contained piece of work; v1 ships value without it.
- **Pre-commit incremental rebuild hook** — destination: follow-up `noc-graph-precommit`. Reason: needs benchmarking on a large change-set first; not blocking v1 utility.
- **Git merge driver for `graph.json`** — destination: same follow-up. Only matters once the file is committed.
- **`graph.json` *committed* to the repo** — v1 keeps it gitignored cache. Promotion gated on user signal that the artifact is stable.
- **Vector embedding / semantic search over node descriptions** — destination: not-yet-filed follow-up. v1 has structured search only.
- **Cross-language call graphs** (Python→TS via API contracts) — destination: not-yet-filed. v1 builds the per-language call graphs separately.

---

## 5. Architecture / Data Model

### Library layout

```
seed/lib/backend/noctusai_lib/graph/
├── __init__.py         # exports: Node, Edge, Graph, NodeKind, EdgeKind, Confidence, build_graph
├── schema.py           # dataclasses + enums + JSON (de)serialization
├── extract_code.py     # walks .py/.ts/.tsx; emits L1 nodes + edges via outline_*
├── extract_docs.py     # parses KB §, [[name]], MASTER-PROMPT.md headers, findings.md
├── extract_memory.py   # parses MEMORY.md index + memory/<slug>.md frontmatter
├── extract_products.py # parses 02-LANDSCAPE Products table; emits product nodes + product-of edges
├── build.py            # orchestrator: extractors → dedup → cluster (Louvain via networkx)
├── serialize.py        # graph.to_json() + render_html() (loads vis-network from CDN)
└── html_template.py    # the single-file graph.html string template
```

### Schema

```python
@dataclass(frozen=True)
class Node:
    id: str                       # stable: "code:products/social-wiring/.../routes.py:WhatsAppRouter"
                                  #         "kb:PATTERNS/whatsapp-chatbot-seed.md"
                                  #         "mem:feedback_seed_first"
                                  #         "product:social-wiring"
    label: str                    # display name
    kind: NodeKind                # see enum below
    path: str | None              # source file (None for synthetic nodes like "product:<slug>")
    line: int | None
    end_line: int | None
    product: str | None           # "social-wiring" | "seed" | "core" | None (cross-cutting)
    cluster: int | None           # community id (populated by build orchestrator)
    confidence: float             # 0..1; 1.0 for EXTRACTED
    meta: dict[str, Any]          # docstring_first_line, kb_section, etc.

class NodeKind(str, Enum):
    # L1 — code
    MODULE = "module"
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"
    ROUTE = "route"
    MCP_TOOL = "mcp_tool"
    COMPONENT = "component"        # React component
    HOOK = "hook"                  # React hook
    MIGRATION = "migration"        # SQL migration
    # L2 — knowledge
    KB_PATTERN = "kb_pattern"
    KB_GUIDE = "kb_guide"
    MEMORY = "memory"
    MASTER_PROMPT_SECTION = "master_prompt_section"
    FINDING = "finding"
    PROJECT = "project"
    PROPOSAL = "proposal"
    # L0 — anchor
    PRODUCT = "product"
    SEED = "seed"

@dataclass(frozen=True)
class Edge:
    source: str                   # Node.id
    target: str                   # Node.id
    kind: EdgeKind
    confidence: float             # 0..1
    weight: float = 1.0
    meta: dict[str, Any] = field(default_factory=dict)

class EdgeKind(str, Enum):
    IMPORTS = "imports"           # python import / TS import
    CALLS = "calls"               # call-graph (best-effort, libcst+ts-morph)
    INHERITS = "inherits"
    DECORATES = "decorates"
    MOUNTS = "mounts"             # FastAPI router include
    CONSUMES_SEED = "consumes_seed"  # ".. import .. from noctusai_lib"
    EXPORTS = "exports"           # __all__ / index.ts re-export
    KB_POINTER = "kb_pointer"     # "KB § X.md" reference
    MEMORY_LINK = "memory_link"   # [[name]] in memory body
    DOCUMENTS = "documents"       # kb_pattern → code/seed it documents
    DEFINED_IN = "defined_in"     # symbol → module
    BELONGS_TO = "belongs_to"     # file → product

@dataclass
class Graph:
    nodes: list[Node]
    edges: list[Edge]
    meta: dict[str, Any]          # build_timestamp, scope, version, source counts
    def to_json(self) -> dict: ...
    @classmethod
    def from_json(cls, data: dict) -> "Graph": ...
```

### MCP tool surface

| Tool | Inputs | Returns |
|---|---|---|
| `noctus.graph.build` | `scope: "repo"\|"product:<slug>"\|"seed"\|"kb"`, `output_dir: str = ".noc-graph"` | `{nodes_count, edges_count, output_path, took_seconds}` |
| `noctus.graph.query` | `q: str`, `kinds: list[NodeKind]? = None`, `limit: int = 20` | `{matches: [{node, score, neighbors_preview}]}` |
| `noctus.graph.neighbors` | `node_id: str`, `depth: int = 1`, `edge_kinds: list[EdgeKind]? = None` | `{node, edges_out, edges_in, subgraph}` |
| `noctus.graph.path` | `source_id: str`, `target_id: str`, `max_depth: int = 6` | `{path: [{node, edge}], length, via_kinds}` |
| `noctus.graph.explain` | `node_id: str` | `{node, neighbors_grouped_by_kind, cluster_members, kb_references}` |
| `noctus.graph.report` | `scope: str = "repo"` | `{ summary_md: str, highlights: list, hot_clusters: list }` — replaces ad-hoc "give me an orientation on this product" pipeline |

### HTML viz spec (graphify-shaped, noc-themed)

- **Library**: vis-network@9 from cdn.jsdelivr.net (single `<script>` tag; no build step).
- **Layout**: force-directed (Barnes-Hut), Louvain community clustering colors.
- **Node visuals**:
  - **Color** = kind (palette draws from doc-symbology: kb=purple, memory=teal, code=blue, seed=gold, product=green-per-product-hue).
  - **Size** ∝ in-degree (centrality hint).
  - **Border** = confidence (solid 1.0, dashed <1.0).
  - **Shape** = layer (circle=code, square=knowledge, diamond=product/seed anchor).
- **Edge visuals**: thickness ∝ weight; opacity ∝ confidence; arrow direction always shown.
- **Interactions**:
  - Top-bar **search** with live-filter (label + path substring).
  - Left-rail **filter chips**: kind (multi-select), product (multi-select), confidence range.
  - **Click node** → focus + halo + 2-hop neighborhood expand-on-click animation.
  - **Double-click node** → opens a side panel with full metadata + KB/code references.
  - **Hover** → tooltip with first-line doc + path:line.
  - **Drag** → physics simulates.
  - **Cluster collapse**: shift-click a cluster member to collapse its cluster into a meta-node.
  - **Mini-map** bottom-right.
  - **Keyboard**: `/` focuses search, `f` toggles filters, `esc` deselects.
- **Effects**:
  - Smooth zoom/pan with easing.
  - Node pulse on selection (CSS-keyframe halo).
  - Edge highlight propagates 2-hop with fade on adjacent.
  - "Path mode": pick source + target, animated path traversal.
- **Theme**: dark background (#0b1020) matching noc's gamification palette; high-contrast colors; legible at 1080p+4k.
- **Footer**: build timestamp + node/edge counts + the graphify reference link (per user request).

### Output artifacts

```
.noc-graph/                       # gitignored
├── graph.json                    # canonical Graph data
├── graph.html                    # interactive viz (loads graph.json via fetch)
└── REPORT.md                     # plain-text summary (counts + top clusters + highlights)
```

---

## 6. Implementation phases

### Phase 1 — Library + schema + L1 code extractor
- [ ] Create `seed/lib/backend/noctusai_lib/graph/__init__.py` + `schema.py` (Node, Edge, Graph dataclasses + enums + `to_json`/`from_json`)
- [ ] Implement `extract_code.py` — walks `.py` via `ast` (mirrors `outline_python` discipline), `.ts`/`.tsx` via `outline_typescript` invocation
- [ ] Capture: modules, classes, functions, methods, imports as `IMPORTS` edges, `BELONGS_TO` product edges, `DEFINED_IN` symbol-to-module edges
- [ ] Unit tests at `seed/lib/backend/tests/graph/` with synthetic Python + TS fixtures

### Phase 2 — L2 doc + memory + product extractors
- [ ] `extract_docs.py` — parses `KNOWLEDGE-BASE/**/*.md`: emits `KB_PATTERN`/`KB_GUIDE` nodes; parses `KB § X.md` literals as `KB_POINTER` edges
- [ ] `extract_memory.py` — parses `~/.claude/projects/.../memory/MEMORY.md` index + each `<slug>.md` frontmatter; emits `MEMORY` nodes + `[[name]]` `MEMORY_LINK` edges
- [ ] `extract_products.py` — parses `KB § 02-LANDSCAPE.md ## Products` table; emits `PRODUCT` nodes
- [ ] Cross-layer `DOCUMENTS` edges: KB pattern body greps for code paths/symbol names and links them
- [ ] Tests with KB + memory fixtures

### Phase 3 — Build orchestrator + community clustering
- [ ] `build.py` — pipeline: collect extractor outputs → dedup → assign clusters via `networkx.algorithms.community.louvain_communities`
- [ ] Graceful fallback when networkx not installed (warn, skip clustering, emit `cluster=None`)
- [ ] `serialize.py` — `to_json` + `render_html` (loads `html_template.py` string, injects `graph.json` URL)
- [ ] CLI: `python mcp/noctusai/cli.py --graph-build [--scope SCOPE] [--output PATH]`

### Phase 4 — MCP tool surface (`noctus.graph.*`)
- [ ] `mcp/noctusai/tools/noctus/graph/__init__.py` (umbrella `register_all`)
- [ ] `build.py` / `query.py` / `neighbors.py` / `path.py` / `explain.py` / `report.py` — Pydantic-schema-shaped wrappers
- [ ] Register `noctus.graph.*` umbrella in `tools/noctus/__init__.py`
- [ ] Tests per tool + an integration test that builds → queries

### Phase 5 — Interactive HTML viz (graphify-shaped, with effects)
- [ ] `html_template.py` — single-file template with vis-network@9 CDN script tag
- [ ] Filters (kind multi-select, product multi-select, confidence slider)
- [ ] Live search + keyboard shortcuts (`/`, `f`, `esc`)
- [ ] Click-to-expand neighborhood with smooth animation; double-click for side panel
- [ ] Cluster collapse, mini-map, path mode
- [ ] Dark theme + node-pulse/edge-highlight CSS effects
- [ ] Footer with build timestamp + graphify-reference link

### Phase 6 — End-to-end smoke + docs
- [ ] Run `--graph-build --scope repo` against the whole noc workspace; verify `.noc-graph/graph.{json,html}` produced
- [ ] Open `graph.html` in browser; manual UX pass (search/filter/expand/path)
- [ ] Add `.noc-graph/` to `.gitignore`
- [ ] Author `KB § PATTERNS/noc-graph.md`
- [ ] CLAUDE.md §2/§3 pointers
- [ ] MEMORY index row + `feedback_noc_graph.md`
- [ ] `README.md` in `projects/noc-graph/` linking to outputs
- [ ] End-of-session verification: `pytest seed/lib/backend/tests/graph/` + `pytest mcp/noctusai/tests/` green

---

## 7. Open questions

1. **`networkx` as a hard dep on `noctusai_lib`?** Recommendation: soft — `try: import networkx` in `build.py`, skip clustering if absent (already on `mcp/noctusai/requirements.txt` though — verify). Needs decision before Phase 3.
2. **Where does the user run the viz from?** Default: open `file://.noc-graph/graph.html` directly (no server). Alt: serve via `python -m http.server -d .noc-graph 8765`. Recommendation: file:// works because `graph.json` is sibling; document both. Discover during Phase 6 smoke.
3. **Should `noctus.graph.build` accept `scope="changed_files"` for incremental?** Deferred to `noc-graph-precommit` follow-up; v1 ships full-repo rebuild only.

---

## 8. Dependencies & blockers

- **networkx** for Louvain clustering — likely already in `mcp/noctusai/requirements.txt`; verify in Phase 1.
- **vis-network@9** — CDN, no build-step dep.
- **No Anthropic/OpenAI API calls** — v1 hard rule.

---

## 9. Success criteria

- `pytest seed/lib/backend/tests/graph/ mcp/noctusai/tests/` green.
- `python mcp/noctusai/cli.py --graph-build --scope repo` produces `.noc-graph/graph.{json,html}` in < 60 s on the current workspace.
- Opening `graph.html` shows an interactive force-directed graph; search/filter/click-expand/path mode all work.
- `noctus.graph.query "whatsapp"` returns ≥ 5 relevant nodes (whatsapp pattern + integration + chatbot pieces).
- `noctus.graph.neighbors product:social-wiring` returns the product's anchor node + 1-hop modules.
- KB pattern + CLAUDE.md pointer + MEMORY row authored; `verify-kb-sync` passes.

---

## 10. How to use this plan

- Single-session execution per user request "implement it all the way" — phases run sequentially in one go but each phase concludes with a live tick + change-log entry.
- Improvements captured in-block during each phase; one phase-proposal bundle filed at end if non-trivial improvements emerged.
- Live-tick `- [ ]` → `- [x]` immediately.
- End-of-session: full `pytest` + visual UX check + three-way doc sync.

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-20 | Initial PROJECT drafted from `templates/PROJECT-TEMPLATE.md` after researching Graphify (https://graphify.net/ + https://github.com/safishamsi/graphify) on user request. | Architect (claude-opus-4-7) |
