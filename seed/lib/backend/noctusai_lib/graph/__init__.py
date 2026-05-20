"""``noctusai_lib.graph`` — queryable knowledge graph of the noc platform.

Materializes the implicit relational index that's otherwise reconstructed
each turn from N composed scans (`outline_*`, `refs`, `hound.scan`,
`scan_*`, manual KB / MEMORY reads). Single derive-only artifact;
regenerable from inputs; AST + authored-prose only — no LLM-inference
layer (rationale already lives as durable prose in KB + memory).

Layers:

- **L1 code** — `extract_code`: modules / classes / functions / methods
  via stdlib `ast` (Python) + `outline_typescript` (TS).
- **L2 knowledge** — `extract_docs` + `extract_memory` + `extract_products`:
  KB patterns + memory entries + product anchors. Cross-layer
  ``DOCUMENTS`` edges link KB prose to the code it documents.

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

__all__ = [
    "Confidence",
    "Edge",
    "EdgeKind",
    "Graph",
    "Node",
    "NodeKind",
    "build_graph",
]
