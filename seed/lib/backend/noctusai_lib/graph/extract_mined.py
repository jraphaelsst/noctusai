"""L3 mined-edge extractor — consume scanner outputs as MINED_RECURRENCE edges.

Feeders (all already exist in the MCP toolkit):
- `noctus.hound.scan`              — semantic-recurrence scanner.
- `scan_cross_product_helpers`     — same helper minted in N≥2 products.
- `scan_within_product_helpers`    — same helper minted N×in one product.
- `noctus.seed.scan_fusions`       — fusion-candidate detector across seed surfaces.
- `noctus.seed.scan_repetition`    — generic repetition scanner.

Each feeder is invoked LAZILY (try-import; missing = silently skipped — pure
additive layer). Output rows become MINED_RECURRENCE edges between the
involved nodes, with confidence taken from the scanner's own score.

This is the layer that answers "which N≥3 recurrences haven't been
formalized yet?" — every MINED edge with weight ≥ 3 + confidence ≥ 0.6
is a codification candidate.

Defensive: when a feeder is absent OR raises OR returns unexpected shape,
log + continue. The mined layer is a strict enhancement; the graph stays
valid without it.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Iterable

from .schema import Confidence, Edge, EdgeKind, Graph

logger = logging.getLogger(__name__)


# ── Public entry ───────────────────────────────────────────────────────────

def walk_mined(graph: Graph, repo_root: Path) -> None:
    """Run every available feeder and add MINED_RECURRENCE edges.

    No edges fail the build; this is purely additive.
    """
    node_index = {n.id: n for n in graph.nodes}
    _mine_cross_product(graph, repo_root, node_index)
    _mine_within_product(graph, repo_root, node_index)
    _mine_hound(graph, repo_root, node_index)
    _mine_seed_fusions(graph, repo_root, node_index)


# ── Per-feeder wrappers ────────────────────────────────────────────────────

def _mine_cross_product(graph: Graph, repo_root: Path, node_index: dict) -> None:
    """Pair every (slug-a/path-a, slug-b/path-b) the cross-product scanner reports."""
    rows = _safe_call("scan_cross_product_helpers", lambda mod: mod.scan(repo_root))
    if not rows:
        return
    for row in rows:
        helpers = row.get("helpers") or []
        score = float(row.get("score", 0.6))
        for a, b in _pairs(_helper_to_ids(helpers, node_index)):
            graph.add_edge(Edge(
                source=a, target=b,
                kind=EdgeKind.MINED_RECURRENCE,
                confidence=min(score, 1.0),
                weight=float(len(helpers)),
                meta=(("scanner", "cross_product_helpers"), ("size", len(helpers))),
            ))


def _mine_within_product(graph: Graph, repo_root: Path, node_index: dict) -> None:
    rows = _safe_call("scan_within_product_helpers", lambda mod: mod.scan(repo_root))
    if not rows:
        return
    for row in rows:
        helpers = row.get("helpers") or []
        score = float(row.get("score", 0.6))
        for a, b in _pairs(_helper_to_ids(helpers, node_index)):
            graph.add_edge(Edge(
                source=a, target=b,
                kind=EdgeKind.MINED_RECURRENCE,
                confidence=min(score, 1.0),
                weight=float(len(helpers)),
                meta=(("scanner", "within_product_helpers"), ("size", len(helpers))),
            ))


def _mine_hound(graph: Graph, repo_root: Path, node_index: dict) -> None:
    rows = _safe_call("hound", lambda mod: mod.scan(repo_root))
    if not rows:
        return
    for row in rows:
        members = row.get("members") or row.get("matches") or []
        score = float(row.get("score") or row.get("confidence") or 0.6)
        for a, b in _pairs(_helper_to_ids(members, node_index)):
            graph.add_edge(Edge(
                source=a, target=b,
                kind=EdgeKind.MINED_RECURRENCE,
                confidence=min(score, 1.0),
                weight=float(len(members)),
                meta=(("scanner", "hound"), ("size", len(members))),
            ))


def _mine_seed_fusions(graph: Graph, repo_root: Path, node_index: dict) -> None:
    rows = _safe_call("seed_fusions", lambda mod: mod.scan(repo_root))
    if not rows:
        return
    for row in rows:
        surfaces = row.get("surfaces") or []
        score = float(row.get("score", 0.6))
        for a, b in _pairs(_helper_to_ids(surfaces, node_index)):
            graph.add_edge(Edge(
                source=a, target=b,
                kind=EdgeKind.MINED_RECURRENCE,
                confidence=min(score, 1.0),
                weight=float(len(surfaces)),
                meta=(("scanner", "seed_fusions"), ("size", len(surfaces))),
            ))


# ── Helpers ────────────────────────────────────────────────────────────────


def _safe_call(name: str, runner) -> list[dict] | None:
    """Try to load the named MCP scanner and run it. None on any failure."""
    # The graph lib lives in seed and CANNOT import from mcp/ directly (mcp/
    # depends on seed, not the other way). The runtime call is intentionally
    # deferred to the mcp-side glue (see mcp/noctusai/tools/noctus/graph/build.py)
    # which can inject scanner outputs via `mined_rows={}` kwarg later.
    #
    # For now this returns None — the layer is wired but the actual feeder
    # invocations happen at the mcp boundary. KB §
    # PATTERNS/architect/noc-graph.md § Layer separation.
    logger.debug("graph.extract_mined: %s — deferred to mcp boundary", name)
    return None


def _helper_to_ids(helpers: Iterable[Any], node_index: dict) -> list[str]:
    """Resolve scanner-reported helpers (path or symbol) to graph node ids."""
    ids: list[str] = []
    for h in helpers:
        if isinstance(h, dict):
            cand = h.get("id") or h.get("node_id") or h.get("path") or h.get("symbol")
        else:
            cand = str(h)
        if not cand:
            continue
        # Direct hit?
        if cand in node_index:
            ids.append(cand)
            continue
        # Try common prefixes.
        for prefix in ("code:", "kb:", "agent:", "skill:", "mem:"):
            full = prefix + cand if not cand.startswith(prefix) else cand
            if full in node_index:
                ids.append(full)
                break
    return ids


def _pairs(items: list[str]) -> list[tuple[str, str]]:
    """All unique unordered pairs (i, j) with i < j (by index)."""
    out: list[tuple[str, str]] = []
    n = len(items)
    for i in range(n):
        for j in range(i + 1, n):
            out.append((items[i], items[j]))
    return out


# ── External-injection path (preferred at the mcp boundary) ────────────────

def ingest_semantic_neighbors(
    graph: Graph,
    pairs: list[tuple[str, str, float]],
) -> None:
    """Inject SEMANTIC_NEIGHBOR edges from pre-computed cosine pairs.

    Args:
        graph: the graph being assembled (nodes must already be populated).
        pairs: list of ``(node_id_a, node_id_b, cosine_score)`` triples.
               Canonical ordering: lower-id-source first (emit both directions
               so graph is undirected in practice but stored as directed). The
               caller (mcp boundary) is responsible for deduplication at the
               pair level; the graph ``_dedup`` pass removes exact duplicates
               at the edge level.

    Source: kb-embeddings + code-embeddings + memory-embeddings +
    corpus-embeddings caches, top-3 cosine per node, threshold >= 0.85.
    Zero OpenAI calls — pure SQLite reads from the embedding caches.
    """
    node_ids = {n.id for n in graph.nodes}
    added = 0
    for id_a, id_b, score in pairs:
        if id_a not in node_ids or id_b not in node_ids:
            continue
        # Emit both directions — the graph treats SEMANTIC_NEIGHBOR as undirected
        # but stores directed edges. Canonical: lower-string-id is the source.
        if id_a > id_b:
            id_a, id_b = id_b, id_a
        for src, tgt in ((id_a, id_b), (id_b, id_a)):
            graph.add_edge(Edge(
                source=src,
                target=tgt,
                kind=EdgeKind.SEMANTIC_NEIGHBOR,
                confidence=min(score, 1.0),
                weight=score,
                meta=(("cosine", round(score, 4)),),
            ))
        added += 1
    logger.debug(
        "graph.extract_mined.ingest_semantic_neighbors: %d pairs → %d edges",
        added, added * 2,
    )


def ingest_guarded_by_edges(
    graph: Graph,
    bindings: list[tuple[str, str]],
) -> None:
    """Inject GUARDED_BY edges: guarded_node --GUARDED_BY--> keeper_node.

    Args:
        graph: the graph being assembled.
        bindings: list of ``(guarded_node_id, keeper_node_id)`` pairs.
                  The caller (mcp boundary) resolves keeper-patterns → graph
                  node ids. Bindings where either id is absent from the graph
                  are silently skipped (additive layer — graph stays valid).

    Source: keeper-patterns SQLite cache. Only keepers with a resolvable
    path/locator (pointing at a specific file or node) emit edges; cross-
    cutting keepers with no path target are skipped.
    """
    node_ids = {n.id for n in graph.nodes}
    added = 0
    for guarded_id, keeper_id in bindings:
        if guarded_id not in node_ids or keeper_id not in node_ids:
            continue
        graph.add_edge(Edge(
            source=guarded_id,
            target=keeper_id,
            kind=EdgeKind.GUARDED_BY,
            confidence=1.0,
            weight=1.0,
            meta=(("source", "keeper-patterns-cache"),),
        ))
        added += 1
    logger.debug(
        "graph.extract_mined.ingest_guarded_by_edges: %d bindings → %d edges",
        len(bindings), added,
    )


def ingest_mined_rows(graph: Graph, rows_by_scanner: dict[str, list[dict]]) -> None:
    """Idempotent ingestion of pre-collected mined rows.

    Schema per row::
        {
          "members": [<node-id-or-path>, ...],   # required
          "score":   0.0..1.0,                    # required (mined confidence)
          "meta":    {...},                       # optional, merged into edge.meta
        }

    Used by the mcp boundary (`mcp/noctusai/tools/noctus/graph/build.py`) to
    inject scanner outputs into the graph without violating the
    seed-cannot-import-mcp boundary.
    """
    node_index = {n.id: n for n in graph.nodes}
    for scanner_name, rows in rows_by_scanner.items():
        for row in rows:
            members = row.get("members") or row.get("helpers") or row.get("matches") or []
            score = float(row.get("score") or row.get("confidence") or 0.6)
            ids = _helper_to_ids(members, node_index)
            for a, b in _pairs(ids):
                graph.add_edge(Edge(
                    source=a, target=b,
                    kind=EdgeKind.MINED_RECURRENCE,
                    confidence=min(score, 1.0),
                    weight=float(len(ids)),
                    meta=tuple(sorted({
                        "scanner": scanner_name,
                        "size": len(ids),
                        **(row.get("meta") or {}),
                    }.items())),
                ))
