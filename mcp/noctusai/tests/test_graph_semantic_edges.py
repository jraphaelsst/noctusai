"""Unit tests for Slice 1: SEMANTIC_NEIGHBOR edges.

Tests ``ingest_semantic_neighbors`` (seed side) and the MCP-boundary helpers
``_load_all_embeddings`` / ``_resolve_node_id`` / ``_compute_semantic_neighbors``
against synthetic fixtures — zero real cache reads or OpenAI calls.
"""

from __future__ import annotations

import json
import math
import sqlite3
import sys
from pathlib import Path

import pytest

MCP_ROOT = Path(__file__).resolve().parent.parent
if str(MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(MCP_ROOT))

# Prefer the worktree's local seed lib over the venv-installed package.
# This matters when running tests from a git worktree (the venv points at the
# primary checkout's noctusai_lib, not the edited worktree copy).
_WORKTREE_ROOT = MCP_ROOT.parent.parent  # .claude/worktrees/<name>
_WORKTREE_SEED_LIB = _WORKTREE_ROOT / "seed" / "lib" / "backend"
if _WORKTREE_SEED_LIB.exists() and str(_WORKTREE_SEED_LIB) not in sys.path:
    sys.path.insert(0, str(_WORKTREE_SEED_LIB))


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_unit_vec(dim: int, index: int) -> list[float]:
    """Return a unit vector with 1.0 at `index`, 0.0 elsewhere."""
    v = [0.0] * dim
    v[index % dim] = 1.0
    return v


def _cosine_ref(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _make_graph_with_nodes(node_ids: list[str]):
    """Minimal Graph with the given node ids (kind=module)."""
    from noctusai_lib.graph.schema import Graph, Node, NodeKind
    g = Graph()
    for nid in node_ids:
        g.add_node(Node(id=nid, label=nid, kind=NodeKind.MODULE))
    return g


# ── ingest_semantic_neighbors (seed side) ─────────────────────────────────────

class TestIngestSemanticNeighbors:
    def test_injects_both_directions(self):
        """Each pair → 2 directed edges (undirected stored as directed)."""
        from noctusai_lib.graph.extract_mined import ingest_semantic_neighbors
        from noctusai_lib.graph.schema import EdgeKind

        g = _make_graph_with_nodes(["kb:a", "kb:b"])
        ingest_semantic_neighbors(g, [("kb:a", "kb:b", 0.92)])

        edge_kinds = [e.kind for e in g.edges]
        assert edge_kinds.count(EdgeKind.SEMANTIC_NEIGHBOR) == 2

        sources = {e.source for e in g.edges}
        targets = {e.target for e in g.edges}
        assert "kb:a" in sources
        assert "kb:b" in sources
        assert "kb:a" in targets
        assert "kb:b" in targets

    def test_canonical_ordering_emits_lower_id_first(self):
        """If id_a > id_b, the function still normalises to lower-first before emit."""
        from noctusai_lib.graph.extract_mined import ingest_semantic_neighbors
        from noctusai_lib.graph.schema import EdgeKind

        g = _make_graph_with_nodes(["kb:z", "kb:a"])
        # Pass in reverse-canonical order — should still emit both directions.
        ingest_semantic_neighbors(g, [("kb:z", "kb:a", 0.90)])

        assert sum(1 for e in g.edges if e.kind == EdgeKind.SEMANTIC_NEIGHBOR) == 2

    def test_skips_unknown_node_ids(self):
        """Pairs where either id is not in the graph are silently skipped."""
        from noctusai_lib.graph.extract_mined import ingest_semantic_neighbors
        from noctusai_lib.graph.schema import EdgeKind

        g = _make_graph_with_nodes(["kb:a"])
        ingest_semantic_neighbors(g, [("kb:a", "kb:MISSING", 0.95)])

        assert len(g.edges) == 0

    def test_weight_equals_cosine_score(self):
        """Edge weight should equal the cosine score provided."""
        from noctusai_lib.graph.extract_mined import ingest_semantic_neighbors

        g = _make_graph_with_nodes(["kb:x", "kb:y"])
        ingest_semantic_neighbors(g, [("kb:x", "kb:y", 0.87)])

        for edge in g.edges:
            assert abs(edge.weight - 0.87) < 1e-6
            assert abs(edge.confidence - 0.87) < 1e-6

    def test_empty_pairs_no_edges(self):
        from noctusai_lib.graph.extract_mined import ingest_semantic_neighbors

        g = _make_graph_with_nodes(["kb:a", "kb:b"])
        ingest_semantic_neighbors(g, [])
        assert len(g.edges) == 0

    def test_duplicate_pairs_not_deduplicated_at_ingest_level(self):
        """Dedup happens at the graph _dedup pass, not ingest_semantic_neighbors."""
        from noctusai_lib.graph.extract_mined import ingest_semantic_neighbors
        from noctusai_lib.graph.schema import EdgeKind

        g = _make_graph_with_nodes(["kb:a", "kb:b"])
        # Call with the same pair twice → 4 raw edges; graph dedup collapses to 2.
        ingest_semantic_neighbors(g, [("kb:a", "kb:b", 0.91), ("kb:a", "kb:b", 0.91)])
        raw_count = sum(1 for e in g.edges if e.kind == EdgeKind.SEMANTIC_NEIGHBOR)
        assert raw_count == 4  # dedup not applied here


# ── _resolve_node_id (mcp-side helper) ───────────────────────────────────────

class TestResolveNodeId:
    def test_kb_prefix(self):
        from tools.noctus.graph.build import _resolve_node_id

        index = {"kb:KNOWLEDGE-BASE/PATTERNS/x.md": object()}
        result = _resolve_node_id("kb-embeddings", "KNOWLEDGE-BASE/PATTERNS/x.md", index)
        assert result == "kb:KNOWLEDGE-BASE/PATTERNS/x.md"

    def test_code_prefix(self):
        from tools.noctus.graph.build import _resolve_node_id

        index = {"code:seed/lib/backend/api.py": object()}
        result = _resolve_node_id("code-embeddings", "seed/lib/backend/api.py", index)
        assert result == "code:seed/lib/backend/api.py"

    def test_direct_match_fallback(self):
        from tools.noctus.graph.build import _resolve_node_id

        index = {"myid": object()}
        result = _resolve_node_id("kb-embeddings", "myid", index)
        assert result == "myid"

    def test_absent_returns_none(self):
        from tools.noctus.graph.build import _resolve_node_id

        result = _resolve_node_id("kb-embeddings", "nonexistent.md", {})
        assert result is None


# ── _compute_semantic_neighbors (mcp-side, synthetic embedding caches) ────────

class TestComputeSemanticNeighbors:
    def _make_kb_cache(self, tmp_path: Path, entries: list[tuple[str, list[float]]]) -> Path:
        """Build a minimal kb-embeddings SQLite with JSON-fallback vectors."""
        p = tmp_path / "kb-embeddings.sqlite"
        conn = sqlite3.connect(str(p))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            "CREATE TABLE kb_chunks "
            "(rowid_alias INTEGER PRIMARY KEY AUTOINCREMENT, "
            "path TEXT, chunk_idx INTEGER, chunk_text TEXT, source_sha TEXT, cached_at TEXT)"
        )
        conn.execute(
            "CREATE TABLE kb_embeddings_json "
            "(chunk_rowid INTEGER, embedding TEXT)"
        )
        for path, vec in entries:
            cur = conn.execute(
                "INSERT INTO kb_chunks(path,chunk_idx,chunk_text,source_sha,cached_at) "
                "VALUES (?,0,'text','sha','now')",
                (path,),
            )
            rowid = cur.lastrowid
            conn.execute(
                "INSERT INTO kb_embeddings_json(chunk_rowid,embedding) VALUES (?,?)",
                (rowid, json.dumps(vec)),
            )
        conn.commit()
        conn.close()
        return p

    def test_pairs_above_threshold_emitted(self, tmp_path, monkeypatch):
        """Two identical vectors → cosine=1.0 → above 0.85 → pair emitted."""
        from tools.noctus.graph.build import _compute_semantic_neighbors
        from tools.noctus.dev import cache_backend

        vec = _make_unit_vec(4, 0)
        kb_path = self._make_kb_cache(tmp_path, [
            ("PATTERNS/x.md", vec),
            ("PATTERNS/y.md", vec),
        ])
        monkeypatch.setattr(cache_backend, "cache_path", lambda name, root=None: {
            "kb-embeddings": kb_path,
            "code-embeddings": tmp_path / "nope.sqlite",
            "memory-embeddings": tmp_path / "nope2.sqlite",
            "corpus-embeddings": tmp_path / "nope3.sqlite",
        }[name])

        g = _make_graph_with_nodes([
            "kb:PATTERNS/x.md",
            "kb:PATTERNS/y.md",
        ])
        pairs = _compute_semantic_neighbors(g, tmp_path)
        assert len(pairs) >= 1
        score = pairs[0][2]
        assert score >= 0.85

    def test_below_threshold_not_emitted(self, tmp_path, monkeypatch):
        """Orthogonal vectors → cosine=0.0 → below 0.85 → no pairs."""
        from tools.noctus.graph.build import _compute_semantic_neighbors
        from tools.noctus.dev import cache_backend

        kb_path = self._make_kb_cache(tmp_path, [
            ("PATTERNS/x.md", _make_unit_vec(4, 0)),
            ("PATTERNS/y.md", _make_unit_vec(4, 1)),
        ])
        monkeypatch.setattr(cache_backend, "cache_path", lambda name, root=None: {
            "kb-embeddings": kb_path,
            "code-embeddings": tmp_path / "nope.sqlite",
            "memory-embeddings": tmp_path / "nope2.sqlite",
            "corpus-embeddings": tmp_path / "nope3.sqlite",
        }[name])

        g = _make_graph_with_nodes([
            "kb:PATTERNS/x.md",
            "kb:PATTERNS/y.md",
        ])
        pairs = _compute_semantic_neighbors(g, tmp_path)
        assert pairs == []

    def test_missing_cache_files_handled_gracefully(self, tmp_path, monkeypatch):
        """When all cache files are absent, returns empty (no exception)."""
        from tools.noctus.graph.build import _compute_semantic_neighbors
        from tools.noctus.dev import cache_backend

        monkeypatch.setattr(
            cache_backend, "cache_path",
            lambda name, root=None: tmp_path / "nonexistent.sqlite",
        )
        g = _make_graph_with_nodes(["kb:x", "kb:y"])
        pairs = _compute_semantic_neighbors(g, tmp_path)
        assert pairs == []
