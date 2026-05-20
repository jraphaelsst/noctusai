"""``noctus.graph.report`` — summary markdown for a scope or product.

Pulls the cached graph, computes a few highlights, returns a structured
report. Replaces the "give me an orientation on this product" pipeline.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Optional

from ._loader import load_cached_graph


def report(focus_product: Optional[str] = None) -> dict:
    graph = load_cached_graph()
    nodes = graph.nodes
    edges = graph.edges
    if focus_product:
        nodes = [n for n in nodes if n.product == focus_product or n.id == f"product:{focus_product}"]
        node_ids = {n.id for n in nodes}
        edges = [e for e in edges if e.source in node_ids or e.target in node_ids]

    kind_counts = Counter(n.kind.value for n in nodes)
    cluster_sizes = Counter(n.cluster for n in nodes if n.cluster is not None)
    top_clusters = cluster_sizes.most_common(8)

    # Most-imported packages (proxy for hot dependencies)
    pkg_uses: Counter = Counter()
    for e in edges:
        if e.target.startswith("pkg:") and e.kind.value in ("imports", "consumes_seed"):
            pkg_uses[e.target] += 1
    top_pkgs = pkg_uses.most_common(15)

    # Most-documented code paths (KB documents → code edges)
    kb_to_code: defaultdict[str, list[str]] = defaultdict(list)
    for e in edges:
        if e.kind.value == "documents":
            kb_to_code[e.source].append(e.target)
    most_documented = sorted(kb_to_code.items(), key=lambda p: -len(p[1]))[:10]

    return {
        "focus_product": focus_product,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "kind_counts": dict(kind_counts.most_common()),
        "top_clusters": [
            {"cluster": int(c), "size": s} for c, s in top_clusters
        ],
        "top_packages": [{"pkg": p, "uses": n} for p, n in top_pkgs],
        "most_documented_kb": [
            {"kb": k, "documents_count": len(v)} for k, v in most_documented
        ],
    }


def register(server) -> None:
    @server.tool(
        name="noctus.graph.report",
        description=(
            "Summary report from the cached graph. Optional "
            "`focus_product=<slug>` to scope. Returns kind-counts, top "
            "clusters, hottest imported packages, and KB nodes that "
            "document the most code."
        ),
    )
    def _report(focus_product: Optional[str] = None) -> dict:
        return report(focus_product=focus_product)
