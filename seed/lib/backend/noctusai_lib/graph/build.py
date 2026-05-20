"""Build orchestrator — runs every extractor and assembles a ``Graph``.

Public entry point: ``build_graph(repo_root, *, scope, memory_root)``.

Scope values:
- ``"repo"`` (default) — everything: every product + seed + mcp + KB + memory.
- ``"product:<slug>"`` — one product + seed + KB (no other products).
- ``"seed"`` — seed + KB only.
- ``"kb"`` — KB + memory only (no code walk).

Clustering is best-effort — uses ``networkx`` Louvain when available,
falls back to a simple degree-based bucketing.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from pathlib import Path

from .extract_code import CodeRoot, walk
from .extract_docs import walk_findings, walk_kb, walk_projects
from .extract_memory import walk_memory
from .extract_products import walk_products
from .schema import Graph, NodeKind

logger = logging.getLogger(__name__)


def build_graph(
    repo_root: Path,
    *,
    scope: str = "repo",
    memory_root: Path | None = None,
) -> Graph:
    """Run extractors and return the assembled, deduplicated, clustered graph."""
    start = time.monotonic()
    graph = Graph(meta={"scope": scope, "repo_root": str(repo_root)})

    # L0: product + seed anchors. Landscape lives at one of two known paths
    # (KB layout varies: flat KB/02-LANDSCAPE.md, or KB/CONTEXT/02-LANDSCAPE.md).
    landscape_candidates = [
        repo_root / "KNOWLEDGE-BASE" / "02-LANDSCAPE.md",
        repo_root / "KNOWLEDGE-BASE" / "CONTEXT" / "02-LANDSCAPE.md",
    ]
    landscape = next((p for p in landscape_candidates if p.exists()), landscape_candidates[0])
    walk_products(graph, landscape)

    # L1: code walks
    code_roots = _resolve_code_roots(repo_root, scope)
    for root in code_roots:
        walk(graph, root, repo_root=repo_root)

    # L2: knowledge layers (after code so DOCUMENTS edges can resolve)
    if scope != "code-only":
        kb_root = repo_root / "KNOWLEDGE-BASE"
        walk_kb(graph, kb_root, repo_root=repo_root)
        walk_projects(graph, repo_root / "projects", repo_root=repo_root)
        for products_projects in (repo_root / "products").glob("*/projects"):
            walk_projects(graph, products_projects, repo_root=repo_root)
        walk_findings(graph, repo_root)
        if memory_root is not None:
            walk_memory(graph, memory_root, repo_root=repo_root)

    _dedup(graph)
    _cluster(graph)

    graph.meta.update({
        "node_count": len(graph.nodes),
        "edge_count": len(graph.edges),
        "build_seconds": round(time.monotonic() - start, 3),
        "node_count_by_kind": _count_by_kind(graph),
    })
    logger.info(
        "graph.build: %d nodes, %d edges in %.2fs (scope=%s)",
        len(graph.nodes), len(graph.edges), time.monotonic() - start, scope,
    )
    return graph


def _resolve_code_roots(repo_root: Path, scope: str) -> list[CodeRoot]:
    """Pick which code trees to walk based on scope."""
    seed_roots = [
        CodeRoot(
            path=repo_root / "seed" / "lib" / "backend" / "noctusai_lib",
            label="seed/lib/backend",
            product=None,
            kind_hint=NodeKind.SEED,
        ),
        CodeRoot(
            path=repo_root / "seed" / "lib" / "frontend" / "src",
            label="seed/lib/frontend",
            product=None,
            kind_hint=NodeKind.SEED,
        ),
        CodeRoot(
            path=repo_root / "mcp",
            label="mcp",
            product=None,
            kind_hint=NodeKind.SEED,
        ),
    ]

    if scope == "kb":
        return []
    if scope == "seed":
        return seed_roots

    if scope.startswith("product:"):
        slug = scope.split(":", 1)[1]
        product_root = repo_root / "products" / slug
        if not product_root.exists():
            logger.warning("graph.build: product %s missing — skipping", slug)
            return seed_roots
        return seed_roots + _product_roots(product_root, slug)

    # scope == "repo"
    roots = list(seed_roots)
    products_dir = repo_root / "products"
    if products_dir.exists():
        for product_dir in sorted(products_dir.iterdir()):
            if not product_dir.is_dir() or product_dir.name.startswith("."):
                continue
            roots.extend(_product_roots(product_dir, product_dir.name))
    return roots


def _product_roots(product_dir: Path, slug: str) -> list[CodeRoot]:
    roots: list[CodeRoot] = []
    backend = product_dir / "backend"
    frontend_src = product_dir / "frontend" / "src"
    if backend.exists():
        roots.append(CodeRoot(path=backend, label=f"{slug}/backend", product=slug))
    if frontend_src.exists():
        roots.append(CodeRoot(path=frontend_src, label=f"{slug}/frontend", product=slug))
    return roots


def _dedup(graph: Graph) -> None:
    """Drop duplicate nodes (keep first) and duplicate edges (keep first)."""
    seen_nodes: set[str] = set()
    deduped_nodes = []
    for node in graph.nodes:
        if node.id in seen_nodes:
            continue
        seen_nodes.add(node.id)
        deduped_nodes.append(node)
    graph.nodes = deduped_nodes

    seen_edges: set[tuple[str, str, str]] = set()
    deduped_edges = []
    for edge in graph.edges:
        key = (edge.source, edge.target, edge.kind.value)
        if key in seen_edges:
            continue
        seen_edges.add(key)
        deduped_edges.append(edge)
    graph.edges = deduped_edges


def _cluster(graph: Graph) -> None:
    """Assign cluster ids. Tries networkx-Louvain; falls back to product-grouping."""
    try:
        import networkx as nx
        from networkx.algorithms.community import louvain_communities

        g = nx.Graph()
        for node in graph.nodes:
            g.add_node(node.id)
        for edge in graph.edges:
            g.add_edge(edge.source, edge.target)
        communities = louvain_communities(g, seed=42)
        cluster_of: dict[str, int] = {}
        for idx, community in enumerate(communities):
            for node_id in community:
                cluster_of[node_id] = idx
        graph.nodes = [_with_cluster(n, cluster_of.get(n.id)) for n in graph.nodes]
        graph.meta["clustering"] = "louvain"
        return
    except ImportError:
        pass

    # Fallback: cluster by product / seed / kb-folder.
    cluster_of: dict[str, int] = {}
    cluster_names: dict[str, int] = {}
    next_id = 0
    for node in graph.nodes:
        if node.product:
            key = f"product:{node.product}"
        elif node.id.startswith("seed:") or node.id.startswith("code:seed/"):
            key = "seed"
        elif node.id.startswith("code:mcp/"):
            key = "mcp"
        elif node.id.startswith("kb:"):
            top = node.id.split("/", 1)[1].split("/", 1)[0] if "/" in node.id else "kb-root"
            key = f"kb:{top}"
        elif node.id.startswith("mem:"):
            key = "memory"
        else:
            key = "other"
        if key not in cluster_names:
            cluster_names[key] = next_id
            next_id += 1
        cluster_of[node.id] = cluster_names[key]
    graph.nodes = [_with_cluster(n, cluster_of.get(n.id)) for n in graph.nodes]
    graph.meta["clustering"] = "fallback-grouping"
    graph.meta["cluster_names"] = {v: k for k, v in cluster_names.items()}


def _with_cluster(node, cluster_id):
    """Return a copy of ``node`` with ``cluster`` set (dataclass frozen, so replace)."""
    from dataclasses import replace
    return replace(node, cluster=cluster_id)


def _count_by_kind(graph: Graph) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for node in graph.nodes:
        counts[node.kind.value] += 1
    return dict(counts)
