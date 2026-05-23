# noc-graph — quickstart

A queryable knowledge graph of the noc platform. Materializes the implicit relational index (code AST + KB pointers + memory `[[name]]` links + product anchors + KB→code documents edges) into a single derive-only artifact at `<repo>/.noc-graph/`.

Inspired by [graphify.net](https://graphify.net/) — but noc-native and **no LLM-inference layer**: every edge has a deterministic source (AST or authored prose), confidence 1.0 from provenance.

## Build the graph

```bash
# whole repo (~6-7s, ~20k nodes / ~32k edges)
python mcp/noctusai/cli.py --graph-build repo

# one product + seed + KB
python mcp/noctusai/cli.py --graph-build product:social-wiring

# seed library + MCP only
python mcp/noctusai/cli.py --graph-build seed

# KB + memory only (no code walk)
python mcp/noctusai/cli.py --graph-build kb
```

Outputs three artifacts into `.noc-graph/`:
- `graph.json` — canonical graph data (schema v1)
- `graph.html` — interactive vis-network visualization, open in any browser
- `REPORT.md` — plain-text summary (counts, top clusters, kind distribution)

`.noc-graph/` is gitignored — it's a regenerable cache, not source of truth.

## Query via MCP

After running `noctus.graph.build` once:

```
noctus.graph.query "whatsapp"           # ranked node search
noctus.graph.neighbors <id> depth=2     # N-hop neighborhood
noctus.graph.path <src-id> <dst-id>     # shortest path
noctus.graph.explain <id>               # full node detail
noctus.graph.report focus_product=foo   # summary
```

Node ids returned by `query` are stable; pass them straight into the other tools.

## Interactive HTML

Open `.noc-graph/graph.html` in any browser (file:// works — `graph.json` is inlined).

- **Search** — `/` focuses; live-ranked, click a result to focus + animate.
- **Filters** — left rail: node kinds, products, confidence slider.
- **Click** a node → halo + 2-hop emphasis. **Double-click** → full side panel.
- **Path mode** — press `p`, pick source, pick target → animated traversal.
- **Drag** nodes; physics simulates. `esc` clears, `f` toggles filters.

Footer links to the graphify reference.

## Structure

```
projects/noc-graph/
├── PROJECT.md                          # design + phases
├── README.md                           # this file
└── findings.md                         # session learnings (empty unless surfaced)

seed/lib/backend/noctusai_lib/graph/
├── __init__.py
├── schema.py                           # Node, Edge, Graph dataclasses + enums
├── extract_code.py                     # AST walker (Python ast + anchored TS regex)
├── extract_docs.py                     # KB pattern parser + KB-pointer edges
├── extract_memory.py                   # MEMORY.md + frontmatter + [[name]] links
├── extract_products.py                 # product anchors from 02-LANDSCAPE.md
├── build.py                            # orchestrator + clustering (Louvain / fallback)
├── query.py                            # GraphIndex (search / neighbors / path / explain)
├── serialize.py                        # JSON + HTML writers
└── html_template.py                    # the single-file interactive viz

seed/lib/backend/tests/graph/
├── test_schema.py
├── test_extract_code.py
└── test_build_and_query.py

mcp/noctusai/tools/noctus/graph/
├── __init__.py                         # umbrella registration
├── _loader.py                          # shared cache loader
├── build.py · query.py · neighbors.py · path.py · explain.py · report.py

mcp/noctusai/tests/test_graph_tools.py

KNOWLEDGE-BASE/CONTEXT/PATTERNS/noc-graph.md   # KB pattern doc
~/.claude/projects/.../memory/feedback_noc_graph.md  # memory entry
```

## Deferred (named destinations)

- L3 *mined* edges from `noctus.hound.scan` family → project `noc-graph-mined-layer`.
- Pre-commit incremental rebuild + git merge driver for committed `graph.json` → project `noc-graph-precommit`.
- Cross-language call graph (Python ↔ TS via API contracts) → not yet filed.
- Vector-embedding semantic search → not yet filed.

## References

- KB pattern: `KB § PATTERNS/noc-graph.md`
- External inspiration: https://graphify.net/ + https://github.com/safishamsi/graphify
- Sibling primitives: AST-first (`KB § PATTERNS/ast.md`), narrow-read (`KB § PATTERNS/agent-reading-discipline.md`), hound (`KB § PATTERNS/seed-absorption.md`).
