"""``noctus.graph.build`` — (re)build the graph and write artifacts.

Writes `.noc-graph/{graph.json,graph.html,REPORT.md}` under the repo
root. Idempotent. No external API calls.

L3 enhancement slices (R3):
- SEMANTIC_NEIGHBOR edges: computed from embedding caches via
  ``_compute_semantic_neighbors`` — zero OpenAI calls, pure SQLite reads.
- GUARDED_BY edges: computed from keeper-patterns cache via
  ``_compute_guarded_by_edges`` — maps keeper targets to graph nodes.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from pathlib import Path
from typing import Optional

from noctusai_lib.graph import build_graph
from noctusai_lib.graph.serialize import write_graph_html, write_graph_json, write_graph_report

from settings import REPO_ROOT

logger = logging.getLogger(__name__)

# ── Semantic-neighbor constants ───────────────────────────────────────────────
_COSINE_THRESHOLD = 0.85   # only edges at or above this score are emitted
_TOP_K = 3                 # top-k neighbors per node (before threshold filter)


# ── Slice 1: SEMANTIC_NEIGHBOR ────────────────────────────────────────────────

def _load_all_embeddings(repo_root: Path) -> list[tuple[str, str, list[float]]]:
    """Load (cache_name, path_or_symbol, vector) from all 4 embedding caches.

    Returns a flat list; each entry carries its source cache name so node-id
    resolution can try multiple prefixes. Falls back gracefully if a cache
    file is absent or its JSON table is empty — the embedding layer is additive.

    Only the JSON fallback table is read (``*_embeddings_json``), which is
    always populated even when sqlite-vec is unavailable. Each row is
    deduplicated at the (path, chunk_idx=0) level so only the first chunk of
    each symbol/doc contributes a representative vector.
    """
    from tools.noctus.dev.cache_backend import apply_locking_pragmas, cache_path as _cache_path

    # (cache_name, chunks_table, json_table, path_col, extra_id_col_or_None)
    cache_configs = [
        ("kb-embeddings",     "kb_chunks",   "kb_embeddings_json",   "path", None),
        ("code-embeddings",   "code_chunks",  "code_embeddings_json", "path", "symbol_name"),
        ("memory-embeddings", "memory_chunks", "memory_embeddings_json", "path", None),
        ("corpus-embeddings", "corpus_chunks", "corpus_embeddings_json", "path", "source_type"),
    ]

    rows: list[tuple[str, str, list[float]]] = []
    for cache_name, chunks_tbl, json_tbl, path_col, extra_col in cache_configs:
        try:
            p = _cache_path(cache_name, repo_root)
            if not p.exists():
                logger.debug("graph.build: %s cache absent — skipping", cache_name)
                continue
            conn = sqlite3.connect(str(p))
            conn.row_factory = sqlite3.Row
            apply_locking_pragmas(conn)
            # Only chunk_idx=0 per path/symbol — representative vector only.
            sql = (
                f"SELECT c.{path_col} AS id_path, c.chunk_idx, j.embedding "
                f"FROM {chunks_tbl} c "
                f"JOIN {json_tbl} j ON j.chunk_rowid = c.rowid_alias "
                f"WHERE c.chunk_idx = 0"
            )
            for r in conn.execute(sql).fetchall():
                try:
                    vec = json.loads(r["embedding"])
                except (TypeError, ValueError):
                    continue
                if not vec:
                    continue
                rows.append((cache_name, str(r["id_path"]), vec))
            conn.close()
        except Exception as exc:
            logger.warning(
                "graph.build: failed loading embeddings from %s — %s",
                cache_name, exc,
            )
    logger.debug("graph.build: loaded %d embedding vectors across 4 caches", len(rows))
    return rows


def _resolve_node_id(cache_name: str, path: str, node_index: dict) -> str | None:
    """Map a cache (cache_name, path) entry to a graph node id.

    Tries a cascade of id prefix conventions:
      code-embeddings  → ``code:<path>``
      kb-embeddings    → ``kb:<path>``
      memory-embeddings→ ``mem:<path>``
      corpus-embeddings→ ``mem:<path>`` or ``kb:<path>``
    Falls back to an exact key match (covers cases where path is already a
    full node id).
    """
    prefix_map = {
        "kb-embeddings":     ["kb:"],
        "code-embeddings":   ["code:"],
        "memory-embeddings": ["mem:"],
        "corpus-embeddings": ["mem:", "kb:", "code:"],
    }
    prefixes = prefix_map.get(cache_name, [])
    for pfx in prefixes:
        candidate = pfx + path if not path.startswith(pfx) else path
        if candidate in node_index:
            return candidate
    # Direct match (path is already the node id).
    if path in node_index:
        return path
    return None


def _compute_semantic_neighbors(
    graph,
    repo_root: Path,
) -> list[tuple[str, str, float]]:
    """Compute top-3 cosine pairs per node, threshold >= 0.85.

    Returns list of (node_id_a, node_id_b, cosine_score) — canonical
    (lower-string-id first) so the caller emits both directed edges.
    Zero OpenAI calls — pure SQLite reads.
    """
    from tools.noctus.dev._embedding_corpus import cosine as _cosine

    node_index = {n.id: n for n in graph.nodes}
    raw = _load_all_embeddings(repo_root)

    # Resolve path → node id; skip unresolvable entries.
    vectored: list[tuple[str, list[float]]] = []
    seen_ids: set[str] = set()
    for cache_name, path, vec in raw:
        nid = _resolve_node_id(cache_name, path, node_index)
        if nid is None or nid in seen_ids:
            continue
        seen_ids.add(nid)
        vectored.append((nid, vec))

    if len(vectored) < 2:
        logger.debug("graph.build: fewer than 2 vectored nodes — skipping SEMANTIC_NEIGHBOR")
        return []

    logger.debug(
        "graph.build: computing cosine over %d vectored nodes (threshold=%.2f, top_k=%d)",
        len(vectored), _COSINE_THRESHOLD, _TOP_K,
    )

    # O(N²) cosine — acceptable for N≤5000 at ~10ms per 1536-D pair.
    pairs_seen: set[tuple[str, str]] = set()
    result: list[tuple[str, str, float]] = []

    for i, (id_a, vec_a) in enumerate(vectored):
        scored: list[tuple[float, str]] = []
        for j, (id_b, vec_b) in enumerate(vectored):
            if i == j:
                continue
            score = _cosine(vec_a, vec_b)
            if score >= _COSINE_THRESHOLD:
                scored.append((score, id_b))
        scored.sort(reverse=True)
        for score, id_b in scored[:_TOP_K]:
            # Canonical pair key: lower-string first.
            key = (min(id_a, id_b), max(id_a, id_b))
            if key in pairs_seen:
                continue
            pairs_seen.add(key)
            result.append((key[0], key[1], score))

    logger.info(
        "graph.build: SEMANTIC_NEIGHBOR — %d pairs above threshold %.2f",
        len(result), _COSINE_THRESHOLD,
    )
    return result


def semantic_neighbor_fingerprint(graph, repo_root: Path) -> str:
    """Deterministic fingerprint of every SEMANTIC_NEIGHBOR input.

    The pairs ``_compute_semantic_neighbors`` returns are a PURE FUNCTION of
    exactly two things:

      1. the embedding vectors (``cache_name``, ``path``, vector) loaded from
         the 4 embedding caches, and
      2. the graph's resolvable node-id set (the ``node_index`` filter — a pair
         survives only when BOTH endpoints resolve to a live node).

    Both are captured here, so an unchanged fingerprint ⇒ an IDENTICAL pair set
    by construction. This is the cross-bucket-edge reuse gate: the (expensive,
    O(N²) cosine) recompute is skipped iff this fingerprint is unchanged.

    Cheap to compute (~1s on the live tree, dominated by the embeddings read
    that the recompute would pay anyway) vs. the ~60s O(N²) cosine it guards.
    """
    h = hashlib.sha256()
    # (1) embeddings — content-sensitive + machine-stable (vector floats, not
    # mtime). Sorted for order-independence.
    for cache_name, path, vec in sorted(_load_all_embeddings(repo_root), key=lambda r: (r[0], r[1])):
        h.update(cache_name.encode("utf-8"))
        h.update(b"\0")
        h.update(path.encode("utf-8"))
        h.update(b"\0")
        h.update(",".join(format(x, ".6g") for x in vec).encode("utf-8"))
        h.update(b"\x1e")
    h.update(b"||nodes||")
    # (2) the resolvable node-id set (the filter that decides which pairs land).
    for nid in sorted(n.id for n in graph.nodes):
        h.update(nid.encode("utf-8"))
        h.update(b"\0")
    return h.hexdigest()[:16]


# ── Slice 2: GUARDED_BY ───────────────────────────────────────────────────────

def _compute_guarded_by_edges(graph, repo_root: Path) -> list[tuple[str, str]]:
    """Resolve keeper-patterns → (guarded_node_id, keeper_node_id) pairs.

    Strategy:
    1. Read all keeper_name values from the keeper-patterns cache.
    2. For each keeper_name, look for a KEEPER_RULE node in the graph
       (these are extracted by ``extract_harness.walk_harness`` from
       compliance.py; node ids follow ``code:mcp/noctusai/tools/noctus/dev/compliance.py::<keeper_name>``).
    3. Resolve the keeper's target path from its ``source_file`` column
       (when present) — this identifies WHICH file/node the keeper guards.
    4. Emit (guarded_node_id, keeper_node_id). Keepers with no resolvable
       target (cross-cutting, no specific file) are skipped — no zero-target
       edges emitted.
    """
    from tools.noctus.dev.cache_backend import apply_locking_pragmas, cache_path as _cache_path
    from noctusai_lib.graph.schema import Node, NodeKind

    node_index = {n.id: n for n in graph.nodes}

    try:
        kp = _cache_path("keeper-patterns", repo_root)
        if not kp.exists():
            logger.debug("graph.build: keeper-patterns cache absent — skipping GUARDED_BY")
            return []
        conn = sqlite3.connect(str(kp))
        conn.row_factory = sqlite3.Row
        apply_locking_pragmas(conn)
        rows = conn.execute(
            "SELECT DISTINCT keeper_name, source_file FROM keeper_patterns "
            "WHERE scope='permanent' ORDER BY keeper_name"
        ).fetchall()
        conn.close()
    except Exception as exc:
        logger.warning("graph.build: failed reading keeper-patterns cache — %s", exc)
        return []

    # Build a keeper_name → keeper graph-node lookup from KEEPER_RULE nodes.
    # If no KEEPER_RULE nodes exist yet (extract_code does not mark check_*
    # functions with this kind), bootstrap them synthetically from the
    # keeper-patterns cache. These nodes are injected into the graph so
    # GUARDED_BY edges have valid targets.
    keeper_nodes: dict[str, str] = {}  # keeper_name → node.id
    for node in graph.nodes:
        if node.kind == NodeKind.KEEPER_RULE:
            keeper_nodes[node.label] = node.id

    if not keeper_nodes:
        # Synthesize KEEPER_RULE nodes from the cache (one node per unique
        # keeper_name; source_file provides the path label).
        _COMPLIANCE_REL = "mcp/noctusai/tools/noctus/dev/compliance.py"
        seen_keepers: set[str] = set()
        for row in rows:
            kn = row["keeper_name"]
            base_name = kn.split("::")[0]
            if base_name in seen_keepers:
                continue
            seen_keepers.add(base_name)
            sf = row["source_file"] or _COMPLIANCE_REL
            node_id = f"code:{sf}::{base_name}"
            keeper_node = Node(
                id=node_id,
                label=base_name,
                kind=NodeKind.KEEPER_RULE,
                path=sf,
            )
            graph.add_node(keeper_node)
            node_index[node_id] = keeper_node
            keeper_nodes[base_name] = node_id
            # Also map the full name (with ::SET suffix) if present.
            if kn != base_name:
                keeper_nodes[kn] = node_id
        logger.debug(
            "graph.build: synthesized %d KEEPER_RULE nodes from keeper-patterns cache",
            len(seen_keepers),
        )

    bindings: list[tuple[str, str]] = []
    repo_root_str = str(repo_root)

    for row in rows:
        keeper_name = row["keeper_name"]
        source_file = row["source_file"] or ""

        # Find the keeper's KEEPER_RULE node in the graph.
        # keeper_name may be "check_foo" or "check_foo::CONST_NAME".
        base_name = keeper_name.split("::")[0]
        keeper_node_id = keeper_nodes.get(keeper_name) or keeper_nodes.get(base_name)
        if not keeper_node_id:
            continue

        # Resolve source_file to a node. source_file is the compliance.py path —
        # that's the keeper's own file, not the guarded file. We need to look
        # for nodes the keeper logically guards based on naming convention.
        # Convention: check_<domain>_<thing> guards module nodes whose path
        # contains the domain hint. We use the keeper_name prefix to find
        # candidate nodes.
        guarded_ids = _resolve_guarded_targets(keeper_name, node_index, repo_root_str)
        for guarded_id in guarded_ids:
            bindings.append((guarded_id, keeper_node_id))

    logger.info(
        "graph.build: GUARDED_BY — %d keeper bindings from %d keepers",
        len(bindings), len(set(b[1] for b in bindings)),
    )
    return bindings


def _resolve_guarded_targets(
    keeper_name: str,
    node_index: dict,
    repo_root_str: str,
) -> list[str]:
    """Map a keeper_name to the node ids it logically guards.

    Heuristic: extract domain hints from the keeper function name and match
    against node paths. For example:
      check_kb_sync → nodes with path containing 'KNOWLEDGE-BASE' or 'INDEX.md'
      check_agent_kb_alignment → HARNESS_AGENT nodes
      check_noc_graph_cache_freshness → noc-graph related nodes

    Returns an empty list when no specific target can be inferred (cross-
    cutting keepers like ``check_eight_way_sync`` that touch everything).
    """
    from noctusai_lib.graph.schema import NodeKind

    # Strip set-membership suffix (check_foo::CONST → check_foo)
    base = keeper_name.split("::")[0].lower()

    # Explicit high-signal mappings: keeper_name_fragment → path substring(s)
    # These emit at most a few edges each; deliberately conservative.
    _PATH_HINTS: list[tuple[str, list[str], NodeKind | None]] = [
        # KB-sync keeper guards the INDEX.md file.
        ("check_kb_sync",            ["KNOWLEDGE-BASE/INDEX.md", "KB/INDEX.md"],       None),
        # Agent-KB alignment → harness agent nodes.
        ("check_agent_kb_alignment", [],                                                NodeKind.HARNESS_AGENT),
        ("check_agent_context_cache",["agent-context"],                                 None),
        # Auto-improvement cache.
        ("check_auto_improvement",   ["auto-improvement"],                               None),
        # KB vector canonical → kb-embeddings paths.
        ("check_kb_vector_canonical",["kb-embeddings", "KNOWLEDGE-BASE"],              None),
        # noc-graph cache.
        ("check_noc_graph_cache",    ["noc-graph"],                                     None),
        # Keeper-pattern cache itself.
        ("check_keeper_cache",       ["keeper-patterns", "keeper_pattern"],             None),
        # Claude.md router discipline.
        ("check_claude_md_router",   ["CLAUDE.md", "claude-md-router"],                 None),
        # Eight-way sync (and back-compat aliases) — too cross-cutting; skip.
        ("check_eight_way_sync",     [],                                                None),
        ("check_seven_way_sync",     [],                                                None),
        ("check_six_way_sync",       [],                                                None),
        ("check_all_cache_freshness",[],                                                None),
        # Pre-commit / hook scripts.
        ("check_files_outlined",     ["scripts/hooks", "pre-commit"],                  None),
        # Code embeddings cache.
        ("check_code_embeddings",    ["code-embeddings"],                               None),
        # Memory embeddings.
        ("check_memory_embeddings",  ["memory-embeddings", "memory.sqlite"],            None),
        # Corpus embeddings.
        ("check_corpus_embeddings",  ["corpus-embeddings"],                             None),
    ]

    targets: list[str] = []
    for hint_frag, path_hints, kind_filter in _PATH_HINTS:
        if not base.startswith(hint_frag):
            continue
        # Kind-filter match: select all nodes of the given kind.
        if kind_filter is not None:
            for node in node_index.values():
                if node.kind == kind_filter:
                    targets.append(node.id)
            break
        # Path-hint match: select nodes whose path contains any hint substring.
        if path_hints:
            for node in node_index.values():
                if node.path and any(h in node.path for h in path_hints):
                    targets.append(node.id)
            break
        # path_hints=[] and kind_filter=None → cross-cutting, skip.
        break

    return targets


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

    R3 note: after core graph assembly, injects SEMANTIC_NEIGHBOR edges
    (slice 1) and GUARDED_BY edges (slice 2). Both slices are purely additive;
    a failure in either logs a warning and continues.
    """
    out_dir = Path(output_dir) if output_dir else (REPO_ROOT / ".noc-graph")
    mem_root = Path(memory_root) if memory_root else None
    graph = build_graph(REPO_ROOT, scope=scope, memory_root=mem_root)

    # R3 slice 1: SEMANTIC_NEIGHBOR edges from embedding caches.
    try:
        from noctusai_lib.graph.extract_mined import ingest_semantic_neighbors
        sem_pairs = _compute_semantic_neighbors(graph, REPO_ROOT)
        if sem_pairs:
            ingest_semantic_neighbors(graph, sem_pairs)
    except Exception as exc:
        logger.warning("graph.build: SEMANTIC_NEIGHBOR computation failed — %s", exc)

    # R3 slice 2: GUARDED_BY edges from keeper-patterns cache.
    try:
        from noctusai_lib.graph.extract_mined import ingest_guarded_by_edges
        gb_bindings = _compute_guarded_by_edges(graph, REPO_ROOT)
        if gb_bindings:
            ingest_guarded_by_edges(graph, gb_bindings)
    except Exception as exc:
        logger.warning("graph.build: GUARDED_BY computation failed — %s", exc)

    json_path = write_graph_json(graph, out_dir)
    html_path = write_graph_html(graph, out_dir)
    report_path = write_graph_report(graph, out_dir)

    sem_count = sum(1 for e in graph.edges if e.kind.value == "semantic_neighbor")
    gb_count = sum(1 for e in graph.edges if e.kind.value == "guarded_by")

    return {
        "scope": scope,
        "nodes_count": len(graph.nodes),
        "edges_count": len(graph.edges),
        "semantic_neighbor_edges": sem_count,
        "guarded_by_edges": gb_count,
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
            "Pure local — no LLM calls. Idempotent. "
            "R3: includes SEMANTIC_NEIGHBOR edges (embedding-cosine, threshold=0.85) "
            "and GUARDED_BY edges (keeper-patterns cache)."
        ),
    )
    def _build(
        scope: str = "repo",
        output_dir: Optional[str] = None,
        memory_root: Optional[str] = None,
    ) -> dict:
        return build_and_write(scope=scope, output_dir=output_dir, memory_root=memory_root)
