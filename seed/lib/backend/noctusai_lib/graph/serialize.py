"""Serialization — JSON to disk + HTML viz template.

The HTML template lives in ``html_template.py`` as a Python string
constant so the lib has no separate asset file (single ``.whl`` ships
everything).
"""

from __future__ import annotations

from pathlib import Path

from .html_template import HTML_TEMPLATE
from .schema import Graph


def write_graph_json(graph: Graph, output_dir: Path) -> Path:
    """Write ``graph.json`` into ``output_dir``. Returns the path."""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "graph.json"
    path.write_text(graph.to_json(indent=2), encoding="utf-8")
    return path


def write_graph_html(graph: Graph, output_dir: Path) -> Path:
    """Write the interactive ``graph.html``. Inlines graph.json for file:// loads."""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "graph.html"
    html = HTML_TEMPLATE.replace(
        "{{GRAPH_JSON_INLINE}}",
        graph.to_json(indent=None),
    ).replace(
        "{{BUILD_META}}",
        _format_meta(graph),
    )
    path.write_text(html, encoding="utf-8")
    return path


def write_graph_report(graph: Graph, output_dir: Path) -> Path:
    """Write a plain-text REPORT.md summary."""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "REPORT.md"
    lines = [
        "# noc-graph — build report",
        "",
        f"- Nodes: **{len(graph.nodes)}**",
        f"- Edges: **{len(graph.edges)}**",
        f"- Scope: `{graph.meta.get('scope', 'repo')}`",
        f"- Build time: {graph.meta.get('build_seconds', '?')}s",
        f"- Clustering: {graph.meta.get('clustering', '?')}",
        "",
        "## Node counts by kind",
        "",
    ]
    by_kind = graph.meta.get("node_count_by_kind", {})
    for kind, count in sorted(by_kind.items(), key=lambda p: -p[1]):
        lines.append(f"- `{kind}` — {count}")
    lines.append("")
    lines.append("## How to use")
    lines.append("")
    lines.append("- Open `graph.html` in a browser.")
    lines.append("- Or query via MCP: `noctus.graph.query 'pattern'`.")
    lines.append("- Reference (inspiration): https://graphify.net/")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _format_meta(graph: Graph) -> str:
    return (
        f"{len(graph.nodes)} nodes · {len(graph.edges)} edges · "
        f"scope={graph.meta.get('scope', 'repo')} · "
        f"built in {graph.meta.get('build_seconds', '?')}s · "
        f"clustering={graph.meta.get('clustering', '?')}"
    )
