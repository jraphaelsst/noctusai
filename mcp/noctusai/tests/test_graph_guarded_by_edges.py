"""Unit tests for Slice 2: GUARDED_BY edges.

Tests ``ingest_guarded_by_edges`` (seed side) and the MCP-boundary helpers
``_resolve_guarded_targets`` / ``_compute_guarded_by_edges`` against synthetic
fixtures — zero real keeper-patterns cache reads.
"""

from __future__ import annotations

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

def _make_graph_with_nodes(nodes: list[tuple[str, str]]):  # (id, kind_str)
    """Minimal Graph with the given (id, kind) pairs."""
    from noctusai_lib.graph.schema import Graph, Node, NodeKind
    g = Graph()
    for nid, kind_str in nodes:
        g.add_node(Node(id=nid, label=nid, kind=NodeKind(kind_str)))
    return g


def _make_keeper_patterns_cache(tmp_path: Path, keepers: list[dict]) -> Path:
    """Build a minimal keeper-patterns SQLite with given keepers."""
    p = tmp_path / "keeper-patterns.sqlite"
    conn = sqlite3.connect(str(p))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        "CREATE TABLE keeper_patterns ("
        "keeper_name TEXT, pattern_kind TEXT, pattern_value TEXT, "
        "severity TEXT, remediation TEXT, source_file TEXT, "
        "source_line INTEGER, fixture_example TEXT, "
        "scope TEXT DEFAULT 'permanent', cached_at TEXT)"
    )
    for k in keepers:
        conn.execute(
            "INSERT INTO keeper_patterns"
            "(keeper_name,pattern_kind,pattern_value,severity,remediation,"
            "source_file,source_line,fixture_example,scope,cached_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                k.get("keeper_name", "check_test"),
                k.get("pattern_kind", "contract-clause"),
                k.get("pattern_value", ""),
                k.get("severity", "warning"),
                k.get("remediation", ""),
                k.get("source_file", ""),
                k.get("source_line", 0),
                k.get("fixture_example", ""),
                k.get("scope", "permanent"),
                "2026-01-01T00:00:00",
            ),
        )
    conn.commit()
    conn.close()
    return p


# ── ingest_guarded_by_edges (seed side) ──────────────────────────────────────

class TestIngestGuardedByEdges:
    def test_injects_guarded_by_edges(self):
        """Valid bindings produce GUARDED_BY directed edges."""
        from noctusai_lib.graph.extract_mined import ingest_guarded_by_edges
        from noctusai_lib.graph.schema import EdgeKind

        g = _make_graph_with_nodes([
            ("kb:PATTERNS/x.md", "kb_pattern"),
            ("code:mcp/noctusai/tools/noctus/dev/compliance.py::check_kb_sync", "keeper_rule"),
        ])
        ingest_guarded_by_edges(g, [
            ("kb:PATTERNS/x.md",
             "code:mcp/noctusai/tools/noctus/dev/compliance.py::check_kb_sync"),
        ])
        gb_edges = [e for e in g.edges if e.kind == EdgeKind.GUARDED_BY]
        assert len(gb_edges) == 1
        assert gb_edges[0].source == "kb:PATTERNS/x.md"
        assert "check_kb_sync" in gb_edges[0].target

    def test_skips_unknown_nodes(self):
        """Bindings where either id is absent → silently skipped."""
        from noctusai_lib.graph.extract_mined import ingest_guarded_by_edges
        from noctusai_lib.graph.schema import EdgeKind

        g = _make_graph_with_nodes([
            ("kb:PATTERNS/x.md", "kb_pattern"),
        ])
        ingest_guarded_by_edges(g, [
            ("kb:PATTERNS/x.md", "code:MISSING_KEEPER"),
        ])
        assert len([e for e in g.edges if e.kind == EdgeKind.GUARDED_BY]) == 0

    def test_empty_bindings_no_edges(self):
        from noctusai_lib.graph.extract_mined import ingest_guarded_by_edges

        g = _make_graph_with_nodes([("kb:x", "kb_pattern")])
        ingest_guarded_by_edges(g, [])
        assert len(g.edges) == 0

    def test_confidence_is_one(self):
        """GUARDED_BY edges have confidence=1.0 (extracted, not mined)."""
        from noctusai_lib.graph.extract_mined import ingest_guarded_by_edges
        from noctusai_lib.graph.schema import EdgeKind

        g = _make_graph_with_nodes([
            ("code:x.py", "module"),
            ("code:c.py::check_foo", "keeper_rule"),
        ])
        ingest_guarded_by_edges(g, [("code:x.py", "code:c.py::check_foo")])
        gb = [e for e in g.edges if e.kind == EdgeKind.GUARDED_BY]
        assert gb[0].confidence == 1.0


# ── _resolve_guarded_targets (mcp-side heuristic) ────────────────────────────

class TestResolveGuardedTargets:
    def test_check_kb_sync_resolves_index(self):
        """check_kb_sync → nodes whose path contains 'KNOWLEDGE-BASE/INDEX.md'."""
        from tools.noctus.graph.build import _resolve_guarded_targets
        from noctusai_lib.graph.schema import Graph, Node, NodeKind

        node = Node(
            id="kb:KNOWLEDGE-BASE/INDEX.md",
            label="INDEX.md",
            kind=NodeKind.KB_PATTERN,
            path="KNOWLEDGE-BASE/INDEX.md",
        )
        index = {node.id: node}
        results = _resolve_guarded_targets("check_kb_sync", index, "/repo")
        assert node.id in results

    def test_check_agent_kb_alignment_resolves_harness_agents(self):
        """check_agent_kb_alignment → HARNESS_AGENT nodes."""
        from tools.noctus.graph.build import _resolve_guarded_targets
        from noctusai_lib.graph.schema import Graph, Node, NodeKind

        agent_node = Node(
            id="agent:backend-engineer",
            label="backend-engineer",
            kind=NodeKind.HARNESS_AGENT,
            path=".claude/agents/backend-engineer.md",
        )
        other_node = Node(
            id="kb:x.md",
            label="x.md",
            kind=NodeKind.KB_PATTERN,
            path="KNOWLEDGE-BASE/x.md",
        )
        index = {agent_node.id: agent_node, other_node.id: other_node}
        results = _resolve_guarded_targets("check_agent_kb_alignment", index, "/repo")
        assert agent_node.id in results
        assert other_node.id not in results

    def test_cross_cutting_keeper_returns_empty(self):
        """check_seven_way_sync has no path hints → returns []."""
        from tools.noctus.graph.build import _resolve_guarded_targets

        index = {"kb:x": object()}
        results = _resolve_guarded_targets("check_seven_way_sync", index, "/repo")
        assert results == []

    def test_unknown_keeper_returns_empty(self):
        """Keepers not in the mapping → [] (no silent injection)."""
        from tools.noctus.graph.build import _resolve_guarded_targets

        index = {"kb:x": object()}
        results = _resolve_guarded_targets("check_completely_unknown_keeper", index, "/repo")
        assert results == []


# ── _compute_guarded_by_edges (mcp-side, synthetic keeper-patterns cache) ────

class TestComputeGuardedByEdges:
    def test_keeper_with_matching_node_produces_binding(self, tmp_path, monkeypatch):
        """A keeper whose name matches a known hint → binding emitted."""
        from tools.noctus.graph.build import _compute_guarded_by_edges
        from tools.noctus.dev import cache_backend
        from noctusai_lib.graph.schema import Graph, Node, NodeKind

        kp = _make_keeper_patterns_cache(tmp_path, [
            {"keeper_name": "check_kb_sync", "source_file": "mcp/noctusai/tools/noctus/dev/compliance.py"},
        ])
        monkeypatch.setattr(
            cache_backend, "cache_path",
            lambda name, root=None: kp if name == "keeper-patterns" else tmp_path / "nope.sqlite",
        )

        keeper_node = Node(
            id="code:mcp/noctusai/tools/noctus/dev/compliance.py::check_kb_sync",
            label="check_kb_sync",
            kind=NodeKind.KEEPER_RULE,
            path="mcp/noctusai/tools/noctus/dev/compliance.py",
        )
        kb_index_node = Node(
            id="kb:KNOWLEDGE-BASE/INDEX.md",
            label="INDEX.md",
            kind=NodeKind.KB_PATTERN,
            path="KNOWLEDGE-BASE/INDEX.md",
        )
        g = Graph()
        g.add_node(keeper_node)
        g.add_node(kb_index_node)

        bindings = _compute_guarded_by_edges(g, tmp_path)
        assert any(b[1] == keeper_node.id for b in bindings)

    def test_no_keeper_rule_nodes_returns_empty(self, tmp_path, monkeypatch):
        """Graph with no KEEPER_RULE nodes → no bindings."""
        from tools.noctus.graph.build import _compute_guarded_by_edges
        from tools.noctus.dev import cache_backend

        monkeypatch.setattr(
            cache_backend, "cache_path",
            lambda name, root=None: tmp_path / "nope.sqlite",
        )
        g = _make_graph_with_nodes([("kb:x", "kb_pattern")])
        bindings = _compute_guarded_by_edges(g, tmp_path)
        assert bindings == []

    def test_absent_cache_returns_empty(self, tmp_path, monkeypatch):
        """Missing keeper-patterns cache → empty list, no exception."""
        from tools.noctus.graph.build import _compute_guarded_by_edges
        from tools.noctus.dev import cache_backend
        from noctusai_lib.graph.schema import Graph, Node, NodeKind

        monkeypatch.setattr(
            cache_backend, "cache_path",
            lambda name, root=None: tmp_path / "nonexistent.sqlite",
        )
        keeper_node = Node(
            id="code:c.py::check_kb_sync",
            label="check_kb_sync",
            kind=NodeKind.KEEPER_RULE,
        )
        g = Graph()
        g.add_node(keeper_node)
        bindings = _compute_guarded_by_edges(g, tmp_path)
        assert bindings == []
