"""``noctusai_lib.graph`` — queryable knowledge graph of the noc platform.

Materializes the implicit relational index that's otherwise reconstructed
each turn from N composed scans (`outline_*`, `refs`, `hound.scan`,
`scan_*`, manual KB / MEMORY reads). Single derive-only artifact;
regenerable from inputs; AST + authored-prose only — no LLM-inference
layer (rationale already lives as durable prose in KB + memory).

Layers:

- **L1 code** — `extract_code`: modules / classes / functions / methods /
  ROUTES (FastAPI decorator) / MCP_TOOLs (server.tool decorator) /
  React components / hooks via stdlib `ast` (Python) + anchored regex (TS).
- **L2 knowledge** — `extract_docs` + `extract_memory` + `extract_products` +
  `extract_landscape` + `extract_harness` + `extract_cli`: KB patterns +
  memory entries + product anchors + CLAUDE.md/CLAUDE/* + .claude/agents +
  .claude/skills + .claude/commands + cli.py flag surface. Cross-layer
  ``DOCUMENTS`` / ``OWNS_KB`` / ``INVOKES_SKILL`` / ``EXPOSES_FLAG`` edges
  link the methodology fabric to the code it governs.
- **L2.5 history** — `extract_history`: aggregates
  ``project-history/auto-improvement.ndjson`` into per-node decorations +
  hot-aggregate nodes for surfaces with ≥ 3 events.
- **L3 mined** — `extract_mined`: ``MINED_RECURRENCE`` edges injected from
  the mcp boundary (`hound.scan`, `scan_cross_product_helpers`,
  `seed.scan_fusions`, …).

Public surface — see ``schema`` + ``build`` modules.
"""

from __future__ import annotations

from .schema import (
    Confidence,
    Edge,
    EdgeKind,
    Graph,
    Node,
    NodeKind,
)
from .build import build_graph
from .extract_mined import ingest_mined_rows

__all__ = [
    "Confidence",
    "Edge",
    "EdgeKind",
    "Graph",
    "Node",
    "NodeKind",
    "build_graph",
    "ingest_mined_rows",
]
