"""``noctus.graph.build`` — (re)build the graph and write artifacts.

Writes `.noc-graph/{graph.json,graph.html,REPORT.md}` under the repo
root. Idempotent. No external API calls.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from noctusai_lib.graph import build_graph
from noctusai_lib.graph.serialize import write_graph_html, write_graph_json, write_graph_report

from settings import REPO_ROOT

logger = logging.getLogger(__name__)


def build_and_write(
    scope: str = "repo",
    output_dir: Optional[str] = None,
    memory_root: Optional[str] = None,
) -> dict:
    """Build the graph and write artifacts.

    Args:
        scope: ``"repo"`` | ``"product:<slug>"`` | ``"seed"`` | ``"kb"``.
        output_dir: where to write artifacts (default ``<repo>/.noc-graph``).
        memory_root: optional path to the agent's memory dir (e.g. ``~/.claude/projects/<ws>/memory``).

    Returns:
        ``{nodes_count, edges_count, output_dir, took_seconds, paths: {json, html, report}}``
    """
    out_dir = Path(output_dir) if output_dir else (REPO_ROOT / ".noc-graph")
    mem_root = Path(memory_root) if memory_root else None
    graph = build_graph(REPO_ROOT, scope=scope, memory_root=mem_root)
    json_path = write_graph_json(graph, out_dir)
    html_path = write_graph_html(graph, out_dir)
    report_path = write_graph_report(graph, out_dir)
    return {
        "scope": scope,
        "nodes_count": len(graph.nodes),
        "edges_count": len(graph.edges),
        "output_dir": str(out_dir),
        "took_seconds": graph.meta.get("build_seconds"),
        "clustering": graph.meta.get("clustering"),
        "paths": {
            "json": str(json_path),
            "html": str(html_path),
            "report": str(report_path),
        },
    }


def register(server) -> None:
    @server.tool(
        name="noctus.graph.build",
        description=(
            "Build (or rebuild) the noc knowledge graph and write "
            "`.noc-graph/{graph.json,graph.html,REPORT.md}`. Scope options: "
            "`repo` (default — everything), `product:<slug>`, `seed`, `kb`. "
            "Pure local — no LLM calls. Idempotent."
        ),
    )
    def _build(
        scope: str = "repo",
        output_dir: Optional[str] = None,
        memory_root: Optional[str] = None,
    ) -> dict:
        return build_and_write(scope=scope, output_dir=output_dir, memory_root=memory_root)
