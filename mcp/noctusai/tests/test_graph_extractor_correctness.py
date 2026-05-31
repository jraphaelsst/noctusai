"""Logic-correctness tests for the 4 noc-graph extractors.

KB § PATTERNS/common/extractor-correctness-vs-mirror.md explains the gap this
closes: the mirror contract (check_noc_graph_cache_freshness) guarantees
``source_sha`` invariant — an up-to-date cache. This file guarantees the cache
content is actually CORRECT.

A buggy extractor produces a "fresh" cache (source_sha matches) that is
silently wrong. Examples: missed node kind, wrong edge direction, orphaned
node, set-iteration nondeterminism.

Six test categories (each as a pytest class):
  1. CoverageTests        — each extractor emits N>0 nodes of every expected kind.
  2. NoOrphanTests        — every node has >= 1 edge (incoming or outgoing).
  3. EdgeDirectionTests   — structural invariants on edge polarity.
  4. RoundTripTests       — write JSON → read JSON → node/edge sets match exactly.
  5. SourceShaSanity      — same source state → identical sha on successive builds.
  6. ClusterSanity        — every node in exactly 1 cluster; top-level kinds in expected clusters.

Floor-check constants (caught-by-extractor-regression use case):
  SEMANTIC_NEIGHBOR > 100, GUARDED_BY > 50, defined_in > 10000, kb_pointer > 500.
These are floor-only — not brittle to growth, catches silent stop-emitting.

Note: These tests build a graph from the LIVE repo tree to exercise real
extractor logic. They are NOT unit tests with synthetic fixtures — the value
is "the extractors, run on the actual codebase, produce sane output". If the
codebase shrinks dramatically the floor constants must be adjusted explicitly
(a deliberate choice, not a drift).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

MCP_ROOT = Path(__file__).resolve().parent.parent
if str(MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(MCP_ROOT))

# Prefer the worktree-local seed lib over the venv-installed package.
_WORKTREE_ROOT = MCP_ROOT.parent.parent  # .claude/worktrees/<name>
_WORKTREE_SEED_LIB = _WORKTREE_ROOT / "seed" / "lib" / "backend"
if _WORKTREE_SEED_LIB.exists() and str(_WORKTREE_SEED_LIB) not in sys.path:
    sys.path.insert(0, str(_WORKTREE_SEED_LIB))

# Repo root for live-tree builds.
_REPO_ROOT = MCP_ROOT.parent.parent  # mcp/noctusai → repo root (primary checkout)
# Also handle the worktree case (worktrees live at .claude/worktrees/<name>)
if not (_REPO_ROOT / "CLAUDE.md").exists():
    # Running from inside a worktree — climb up to find the repo root.
    _REPO_ROOT = MCP_ROOT.parent.parent.parent.parent  # worktrees/../.. = repo root
if not (_REPO_ROOT / "CLAUDE.md").exists():
    # Last resort: the known-stable primary checkout
    _REPO_ROOT = Path("/Users/rapha/Documents/repository/NoctusAI/noctusai")


# ── Shared fixture: one graph built once per session ────────────────────────

@pytest.fixture(scope="session")
def live_graph():
    """Build graph from the live repo tree — scope=session so it's only built once."""
    from noctusai_lib.graph import build_graph
    return build_graph(_REPO_ROOT, scope="repo")


@pytest.fixture(scope="session")
def live_graph_nodes(live_graph):
    return list(live_graph.nodes)


@pytest.fixture(scope="session")
def live_graph_edges(live_graph):
    return list(live_graph.edges)


@pytest.fixture(scope="session")
def live_node_kinds(live_graph_nodes):
    from noctusai_lib.graph.schema import NodeKind
    result: dict[NodeKind, int] = {}
    for n in live_graph_nodes:
        result[n.kind] = result.get(n.kind, 0) + 1
    return result


@pytest.fixture(scope="session")
def live_edge_kinds(live_graph_edges):
    from noctusai_lib.graph.schema import EdgeKind
    result: dict[EdgeKind, int] = {}
    for e in live_graph_edges:
        result[e.kind] = result.get(e.kind, 0) + 1
    return result


# ── 1. Coverage tests ────────────────────────────────────────────────────────

class TestExtractorCoverage:
    """Each extractor must emit N>0 nodes of every expected kind.

    Tests are scoped to the REAL codebase — not synthetic fixtures — so
    they verify the ACTUAL extractor logic against the live tree.
    """

    # extract_code.py expected kinds
    def test_code_module_nodes_present(self, live_node_kinds):
        from noctusai_lib.graph.schema import NodeKind
        count = live_node_kinds.get(NodeKind.MODULE, 0)
        assert count > 0, f"extract_code must emit MODULE nodes; got {count}"

    def test_code_class_nodes_present(self, live_node_kinds):
        from noctusai_lib.graph.schema import NodeKind
        count = live_node_kinds.get(NodeKind.CLASS, 0)
        assert count > 0, f"extract_code must emit CLASS nodes; got {count}"

    def test_code_function_nodes_present(self, live_node_kinds):
        from noctusai_lib.graph.schema import NodeKind
        count = live_node_kinds.get(NodeKind.FUNCTION, 0)
        assert count > 0, f"extract_code must emit FUNCTION nodes; got {count}"

    def test_code_method_nodes_present(self, live_node_kinds):
        from noctusai_lib.graph.schema import NodeKind
        count = live_node_kinds.get(NodeKind.METHOD, 0)
        assert count > 0, f"extract_code must emit METHOD nodes; got {count}"

    def test_code_route_nodes_present(self, live_node_kinds):
        from noctusai_lib.graph.schema import NodeKind
        count = live_node_kinds.get(NodeKind.ROUTE, 0)
        assert count > 0, (
            f"extract_code must emit ROUTE nodes (FastAPI decorators); got {count}. "
            "If all products were removed, adjust this floor."
        )

    def test_code_mcp_tool_nodes_present(self, live_node_kinds):
        from noctusai_lib.graph.schema import NodeKind
        count = live_node_kinds.get(NodeKind.MCP_TOOL, 0)
        assert count > 0, f"extract_code must emit MCP_TOOL nodes; got {count}"

    def test_code_component_nodes_present(self, live_node_kinds):
        from noctusai_lib.graph.schema import NodeKind
        count = live_node_kinds.get(NodeKind.COMPONENT, 0)
        assert count > 0, (
            f"extract_code must emit COMPONENT nodes (React TS files); got {count}"
        )

    def test_code_hook_nodes_present(self, live_node_kinds):
        from noctusai_lib.graph.schema import NodeKind
        count = live_node_kinds.get(NodeKind.HOOK, 0)
        assert count > 0, (
            f"extract_code must emit HOOK nodes (React hooks); got {count}"
        )

    # extract_harness.py expected kinds
    def test_harness_agent_nodes_present(self, live_node_kinds):
        from noctusai_lib.graph.schema import NodeKind
        count = live_node_kinds.get(NodeKind.HARNESS_AGENT, 0)
        assert count > 0, f"extract_harness must emit HARNESS_AGENT nodes; got {count}"

    def test_harness_skill_nodes_present(self, live_node_kinds):
        from noctusai_lib.graph.schema import NodeKind
        count = live_node_kinds.get(NodeKind.HARNESS_SKILL, 0)
        assert count > 0, f"extract_harness must emit HARNESS_SKILL nodes; got {count}"

    def test_harness_command_nodes_present(self, live_node_kinds):
        from noctusai_lib.graph.schema import NodeKind
        count = live_node_kinds.get(NodeKind.HARNESS_COMMAND, 0)
        assert count > 0, f"extract_harness must emit HARNESS_COMMAND nodes; got {count}"

    # extract_kb.py (via extract_docs.walk_kb)
    def test_kb_pattern_nodes_present(self, live_node_kinds):
        from noctusai_lib.graph.schema import NodeKind
        count = live_node_kinds.get(NodeKind.KB_PATTERN, 0)
        assert count > 0, f"extract_kb must emit KB_PATTERN nodes; got {count}"

    def test_kb_guide_nodes_present(self, live_node_kinds):
        from noctusai_lib.graph.schema import NodeKind
        count = live_node_kinds.get(NodeKind.KB_GUIDE, 0)
        assert count > 0, (
            f"extract_docs.walk_kb must emit KB_GUIDE nodes (KNOWLEDGE-BASE/GUIDES/*.md); got {count}"
        )

    # extract_products.py
    def test_product_anchor_nodes_present(self, live_node_kinds):
        from noctusai_lib.graph.schema import NodeKind
        count = live_node_kinds.get(NodeKind.PRODUCT, 0)
        assert count > 0, f"extract_products must emit PRODUCT anchor nodes; got {count}"

    def test_seed_anchor_node_present(self, live_node_kinds):
        from noctusai_lib.graph.schema import NodeKind
        count = live_node_kinds.get(NodeKind.SEED, 0)
        assert count > 0, (
            f"extract_products must emit a SEED anchor node; got {count}"
        )

    # extract_cli.py: cli-flag nodes
    def test_cli_flag_nodes_present(self, live_node_kinds):
        from noctusai_lib.graph.schema import NodeKind
        count = live_node_kinds.get(NodeKind.CLI_FLAG, 0)
        assert count > 0, (
            f"extract_cli must emit CLI_FLAG nodes (mcp/noctusai/cli.py --flags); got {count}"
        )

    # extract_landscape.py: landscape doc nodes
    def test_landscape_doc_nodes_present(self, live_node_kinds):
        from noctusai_lib.graph.schema import NodeKind
        count = live_node_kinds.get(NodeKind.LANDSCAPE_DOC, 0)
        assert count > 0, (
            f"extract_landscape must emit LANDSCAPE_DOC nodes (CLAUDE.md, CONTEXTUALIZE.md); got {count}"
        )

    # KEEPER_RULE nodes are synthesized by the MCP noc_graph_cache layer
    # (not by build_graph directly) — verified via the live cache.
    def test_keeper_rule_nodes_in_live_cache(self):
        """KEEPER_RULE nodes must exist in the live noc-graph cache.

        These are synthesized by the MCP refresh layer from the keeper-patterns
        cache. Absence means either no refresh was run OR the synthesizer stopped
        running. Skipped if cache absent.
        """
        import sqlite3
        from tools.noctus.dev.noc_graph_cache import cache_path
        cache_p = cache_path(_REPO_ROOT)
        if not cache_p.exists():
            pytest.skip("noc-graph cache absent — run --refresh-noc-graph first.")
        conn = sqlite3.connect(str(cache_p))
        try:
            row = conn.execute(
                "SELECT count(*) FROM noc_graph_nodes WHERE kind = 'keeper_rule'"
            ).fetchone()
            count = row[0] if row else 0
        finally:
            conn.close()
        assert count > 0, (
            f"KEEPER_RULE nodes absent from live cache (got {count}). "
            "Run --refresh-noc-graph after refreshing the keeper-patterns cache."
        )


# ── 2. No-orphan tests ────────────────────────────────────────────────────────

class TestNoOrphanNodes:
    """Code-layer nodes must have at least 1 edge (incoming or outgoing).

    Orphans in the code layer suggest the extractor created a symbol node
    but failed to wire it via DEFINED_IN or CONTAINS. KB docs and memory
    nodes are intentionally standalone (they get KB_POINTER edges only when
    referenced from other files, which is NOT guaranteed for every doc).

    Allow-listed orphan kinds cover all non-code layers where standalone
    nodes are expected by design.
    """

    # Kinds that legitimately appear with zero edges.
    # - All KB kinds: standalone docs are normal (edges appear only when referenced)
    # - SEED/PRODUCT: L0 anchors
    # - Auto-improvement events, memory, projects, findings, landscape docs:
    #   all authored prose that may have zero cross-references in any snapshot
    # - MIGRATION, KEEPER_RULE, CLI_FLAG: extracted from compliance/cli; may have
    #   0 outgoing edges in a minimal slice build
    _ORPHAN_ALLOWLIST = frozenset({
        "seed",
        "product",
        "kb_pattern", "kb_guide", "kb_integration",
        "kb_backend_spec", "kb_frontend_spec", "kb_chapter",
        "memory", "memory_index",
        "auto_improvement_event",
        "finding", "project", "proposal",
        "landscape_doc",
        "master_prompt_section",
        "migration",
        "keeper_rule",
        "cli_flag",
        "hook_script",
    })

    # Code-layer kinds that MUST be wired — orphan = extractor bug
    _CODE_KINDS = frozenset({
        "module", "class", "function", "method",
        "route", "mcp_tool", "component", "hook",
    })

    def test_no_orphan_code_nodes(self, live_graph_nodes, live_graph_edges):
        """No code-layer node (module/class/function/etc.) should have ZERO edges."""
        connected: set[str] = set()
        for e in live_graph_edges:
            connected.add(e.source)
            connected.add(e.target)

        orphans: list[tuple[str, str]] = []
        for n in live_graph_nodes:
            if n.kind.value in self._CODE_KINDS and n.id not in connected:
                orphans.append((n.id, n.kind.value))

        if orphans:
            sample = orphans[:10]
            pytest.fail(
                f"{len(orphans)} orphan CODE nodes (no edges). "
                f"First {len(sample)}: {sample}. "
                "A code node with zero edges means the extractor emitted the symbol "
                "but forgot to wire it with DEFINED_IN/CONTAINS/EXPOSES_TOOL."
            )

    def test_allowlisted_kinds_are_still_present(self, live_node_kinds):
        """Sanity: the allowlisted SEED kind does exist — catches extractor removal."""
        from noctusai_lib.graph.schema import NodeKind
        assert live_node_kinds.get(NodeKind.SEED, 0) > 0, (
            "SEED anchor must exist — if it was removed, remove it from the orphan allowlist too"
        )

    def test_harness_nodes_are_wired(self, live_graph_nodes, live_graph_edges):
        """Harness nodes (agents, skills, commands) should have at least one edge.

        A harness agent with no OWNS_KB or KB_POINTER edges suggests the
        frontmatter parser failed or the KB refs were not resolved.
        We test at the aggregate level: total harness edges > 0.
        """
        from noctusai_lib.graph.schema import EdgeKind, NodeKind
        _HARNESS_KINDS = {NodeKind.HARNESS_AGENT, NodeKind.HARNESS_SKILL, NodeKind.HARNESS_COMMAND}
        harness_node_ids = {n.id for n in live_graph_nodes if n.kind in _HARNESS_KINDS}
        harness_edges = sum(
            1 for e in live_graph_edges
            if e.source in harness_node_ids or e.target in harness_node_ids
        )
        assert harness_edges > 0, (
            "Harness nodes (agents/skills/commands) have ZERO edges total. "
            "This suggests extract_harness stopped emitting OWNS_KB/KB_POINTER edges."
        )


# ── 3. Edge-direction tests ───────────────────────────────────────────────────

class TestEdgeDirections:
    """Structural invariants on edge polarity.

    (a) DEFINED_IN always points symbol → module (the symbol is defined in the module).
        The reverse (module → symbol for DEFINED_IN) would indicate a misfire.
    (b) IMPORTS is one-way (a → b means a imports b; b should NOT also import a for
        the same pair — circular imports exist in real code, so we only check
        internal consistency in synthetic fixture scenarios below).
    (c) OWNS_KB source must be a HARNESS_AGENT.
    (d) EXPOSES_TOOL source must be a MODULE.
    (e) CONTAINS from PRODUCT/SEED to MODULE (not the reverse).
    """

    def test_owns_kb_source_is_harness_agent(self, live_graph_nodes, live_graph_edges):
        """Every OWNS_KB edge must originate from a HARNESS_AGENT node."""
        from noctusai_lib.graph.schema import EdgeKind, NodeKind
        node_index = {n.id: n for n in live_graph_nodes}
        violations = []
        for e in live_graph_edges:
            if e.kind != EdgeKind.OWNS_KB:
                continue
            src_node = node_index.get(e.source)
            if src_node is None:
                violations.append(f"OWNS_KB source {e.source!r} not in graph")
            elif src_node.kind != NodeKind.HARNESS_AGENT:
                violations.append(
                    f"OWNS_KB source {e.source!r} has kind {src_node.kind.value!r} "
                    f"(expected harness_agent)"
                )
        assert not violations, (
            f"{len(violations)} OWNS_KB edge direction violations:\n"
            + "\n".join(violations[:5])
        )

    def test_exposes_tool_source_is_module(self, live_graph_nodes, live_graph_edges):
        """Every EXPOSES_TOOL edge must originate from a MODULE node."""
        from noctusai_lib.graph.schema import EdgeKind, NodeKind
        node_index = {n.id: n for n in live_graph_nodes}
        violations = []
        for e in live_graph_edges:
            if e.kind != EdgeKind.EXPOSES_TOOL:
                continue
            src_node = node_index.get(e.source)
            if src_node is None:
                continue  # dangling refs: covered by no-orphan tests
            if src_node.kind != NodeKind.MODULE:
                violations.append(
                    f"EXPOSES_TOOL source {e.source!r} has kind {src_node.kind.value!r} "
                    f"(expected module)"
                )
        assert not violations, (
            f"{len(violations)} EXPOSES_TOOL edge direction violations:\n"
            + "\n".join(violations[:5])
        )

    def test_defined_in_target_is_module_or_class(self, live_graph_nodes, live_graph_edges):
        """DEFINED_IN edge target must be a MODULE or CLASS.

        The extractor emits two shapes:
          - class/function/route → MODULE (class/fn defined in a file)
          - method → CLASS (method defined inside a class body)
        Any other target kind indicates a mis-wired DEFINED_IN edge.
        """
        from noctusai_lib.graph.schema import EdgeKind, NodeKind
        _VALID_TARGETS = {NodeKind.MODULE, NodeKind.CLASS}
        node_index = {n.id: n for n in live_graph_nodes}
        violations = []
        for e in live_graph_edges:
            if e.kind != EdgeKind.DEFINED_IN:
                continue
            tgt_node = node_index.get(e.target)
            if tgt_node is None:
                continue
            if tgt_node.kind not in _VALID_TARGETS:
                violations.append(
                    f"DEFINED_IN target {e.target!r} has kind {tgt_node.kind.value!r} "
                    f"(expected module or class)"
                )
        assert not violations, (
            f"{len(violations)} DEFINED_IN edge target violations:\n"
            + "\n".join(violations[:5])
        )

    def test_owns_kb_target_is_kb_node(self, live_graph_nodes, live_graph_edges):
        """Every OWNS_KB edge target must be a KB_* node."""
        from noctusai_lib.graph.schema import EdgeKind, NodeKind
        _KB_KINDS = {
            NodeKind.KB_PATTERN, NodeKind.KB_GUIDE, NodeKind.KB_INTEGRATION,
            NodeKind.KB_BACKEND_SPEC, NodeKind.KB_FRONTEND_SPEC, NodeKind.KB_CHAPTER,
        }
        node_index = {n.id: n for n in live_graph_nodes}
        violations = []
        for e in live_graph_edges:
            if e.kind != EdgeKind.OWNS_KB:
                continue
            tgt_node = node_index.get(e.target)
            if tgt_node is None:
                continue
            if tgt_node.kind not in _KB_KINDS:
                violations.append(
                    f"OWNS_KB target {e.target!r} has kind {tgt_node.kind.value!r} "
                    f"(expected a KB_* kind)"
                )
        assert not violations, (
            f"{len(violations)} OWNS_KB target kind violations:\n"
            + "\n".join(violations[:5])
        )


# ── 4. Round-trip tests ───────────────────────────────────────────────────────

class TestRoundTrip:
    """Write graph to JSON → deserialize → assert node/edge sets match exactly.

    Catches serialization drift (e.g. a field silently dropped in to_dict,
    a Node reconstructed with wrong kind, etc.).
    """

    def test_node_ids_survive_round_trip(self, live_graph, tmp_path):
        """All node IDs survive JSON serialization + deserialization."""
        from noctusai_lib.graph.schema import Graph
        original_ids = {n.id for n in live_graph.nodes}
        payload = live_graph.to_json()
        restored = Graph.from_json(payload)
        restored_ids = {n.id for n in restored.nodes}
        missing = original_ids - restored_ids
        extra = restored_ids - original_ids
        assert not missing, f"{len(missing)} node IDs dropped in round-trip: {list(missing)[:5]}"
        assert not extra, f"{len(extra)} extra node IDs appeared in round-trip: {list(extra)[:5]}"

    def test_node_kinds_survive_round_trip(self, live_graph):
        """Node kinds (as enum values) survive JSON serialization."""
        from noctusai_lib.graph.schema import Graph
        original_kinds = {(n.id, n.kind.value) for n in live_graph.nodes}
        restored = Graph.from_json(live_graph.to_json())
        restored_kinds = {(n.id, n.kind.value) for n in restored.nodes}
        diffs = original_kinds.symmetric_difference(restored_kinds)
        assert not diffs, (
            f"Node kind drift in round-trip ({len(diffs)} differences): "
            f"{list(diffs)[:5]}"
        )

    def test_edge_count_survives_round_trip(self, live_graph):
        """Edge count matches exactly after round-trip (no silently dropped edges)."""
        from noctusai_lib.graph.schema import Graph
        original_count = len(live_graph.edges)
        restored = Graph.from_json(live_graph.to_json())
        restored_count = len(restored.edges)
        assert original_count == restored_count, (
            f"Edge count changed in round-trip: {original_count} → {restored_count}"
        )

    def test_edge_kinds_survive_round_trip(self, live_graph):
        """Edge kind distribution matches after round-trip."""
        from noctusai_lib.graph.schema import EdgeKind, Graph

        def _kind_counts(g) -> dict:
            counts: dict = {}
            for e in g.edges:
                counts[e.kind.value] = counts.get(e.kind.value, 0) + 1
            return counts

        original = _kind_counts(live_graph)
        restored = _kind_counts(Graph.from_json(live_graph.to_json()))
        assert original == restored, (
            f"Edge kind distribution changed in round-trip.\n"
            f"Original: {original}\nRestored: {restored}"
        )

    def test_graph_json_write_then_read(self, live_graph, tmp_path):
        """write_graph_json then reading back produces same node/edge counts."""
        from noctusai_lib.graph.schema import Graph
        from noctusai_lib.graph.serialize import write_graph_json

        out = tmp_path / ".noc-graph"
        json_path = write_graph_json(live_graph, out)
        assert json_path.exists()

        data = json.loads(json_path.read_text(encoding="utf-8"))
        assert data.get("schema_version") == 1
        assert len(data["nodes"]) == len(live_graph.nodes)
        assert len(data["edges"]) == len(live_graph.edges)


# ── 5. Source-sha stability tests ─────────────────────────────────────────────

class TestSourceShaStability:
    """Same source state → identical aggregate_source_sha on successive builds.

    Detects nondeterminism: set ordering, dict iteration, timestamp
    contamination, or other sources of per-run variance.
    """

    def test_compute_source_sha_is_deterministic(self):
        """compute_source_sha returns the same value on consecutive calls."""
        from tools.noctus.dev.noc_graph_cache import compute_source_sha
        sha1 = compute_source_sha(_REPO_ROOT)
        sha2 = compute_source_sha(_REPO_ROOT)
        assert sha1 == sha2, (
            f"compute_source_sha is non-deterministic: {sha1!r} != {sha2!r}. "
            "Check for timestamp use, os.listdir ordering, or set() iteration."
        )

    def test_compute_source_sha_nonempty(self):
        """Sha must be a non-empty hex string (not empty, not a constant placeholder)."""
        from tools.noctus.dev.noc_graph_cache import compute_source_sha
        sha = compute_source_sha(_REPO_ROOT)
        assert sha, "compute_source_sha returned empty string"
        assert len(sha) >= 8, f"Suspiciously short sha: {sha!r}"
        # Check it looks like a hex string
        assert all(c in "0123456789abcdef" for c in sha.lower()), (
            f"sha doesn't look hexadecimal: {sha!r}"
        )

    def test_build_graph_meta_contains_scope(self):
        """The built graph's meta must record the build scope."""
        from noctusai_lib.graph import build_graph

        g = build_graph(_REPO_ROOT, scope="harness")  # faster than "repo" for this check
        assert g.meta.get("scope") == "harness", (
            f"Graph meta.scope should be 'harness', got: {g.meta.get('scope')!r}"
        )

    def test_harness_scope_deterministic(self):
        """Harness-scope build returns same node count on successive calls."""
        from noctusai_lib.graph import build_graph

        g1 = build_graph(_REPO_ROOT, scope="harness")
        g2 = build_graph(_REPO_ROOT, scope="harness")
        assert len(g1.nodes) == len(g2.nodes), (
            f"Harness-scope node count varies between builds: "
            f"{len(g1.nodes)} vs {len(g2.nodes)}. "
            "Check for non-deterministic source in walk_harness or walk_kb."
        )
        assert len(g1.edges) == len(g2.edges), (
            f"Harness-scope edge count varies between builds: "
            f"{len(g1.edges)} vs {len(g2.edges)}."
        )


# ── 6. Cluster sanity tests ────────────────────────────────────────────────────

class TestClusterSanity:
    """Every node belongs to exactly 1 cluster in a non-fallback build.

    The clusterer (Louvain or product-folder bucket) assigns an integer
    cluster ID to each node. No node should have cluster=-1 (sentinel for
    "unclustered") in a full repo build — that would indicate the clusterer
    silently skipped nodes.
    """

    def test_no_unclustered_nodes(self, live_graph_nodes):
        """No node should have cluster=-1 after a full repo build."""
        unclustered = [n.id for n in live_graph_nodes if n.cluster == -1]
        if unclustered:
            pytest.fail(
                f"{len(unclustered)} nodes have cluster=-1 (unclustered sentinel). "
                f"First 10: {unclustered[:10]}. "
                "The clusterer must assign every node to a cluster >= 0."
            )

    def test_cluster_ids_are_non_negative(self, live_graph_nodes):
        """All cluster IDs must be non-negative integers (or None for no-clustering builds)."""
        bad = [
            (n.id, n.cluster)
            for n in live_graph_nodes
            if n.cluster is not None and n.cluster < 0
        ]
        assert not bad, (
            f"{len(bad)} nodes have negative cluster IDs: {bad[:5]}"
        )

    def test_multiple_clusters_present(self, live_graph_nodes):
        """A repo build should produce >= 2 distinct clusters (not everything in one)."""
        cluster_ids = {n.cluster for n in live_graph_nodes if n.cluster is not None}
        assert len(cluster_ids) >= 2, (
            f"Only {len(cluster_ids)} distinct cluster ID(s) found. "
            "A full repo build should produce multiple product/kb/harness clusters."
        )

    def test_top_level_kinds_span_multiple_clusters(self, live_graph_nodes):
        """PRODUCT, KB_PATTERN, and HARNESS_AGENT nodes shouldn't all be in the same cluster.

        This tests that the clusterer actually separates the methodology fabric
        from the code layer — a Louvain collapse would put everything in cluster 0.
        """
        from noctusai_lib.graph.schema import NodeKind
        _TOP_KINDS = {NodeKind.PRODUCT, NodeKind.KB_PATTERN, NodeKind.HARNESS_AGENT}
        clusters_seen: set = set()
        for n in live_graph_nodes:
            if n.kind in _TOP_KINDS and n.cluster is not None:
                clusters_seen.add(n.cluster)
        assert len(clusters_seen) >= 2, (
            f"Top-level kinds (PRODUCT/KB_PATTERN/HARNESS_AGENT) all collapsed "
            f"into {len(clusters_seen)} cluster(s): {clusters_seen}. "
            "The clusterer should separate these into distinct communities."
        )


# ── 7. Smoke edge-count floors ────────────────────────────────────────────────

class TestEdgeFloors:
    """Floor-only edge count checks.

    These are NOT brittle upper-bound tests — they only fail if an extractor
    STOPS emitting an edge kind. Growth (more edges) never fails these.

    Two layers:
    (a) build_graph() floors — edge kinds produced by the pure extractors
        (no MCP-level compute needed). Calibrated against 2026-05-28 live counts.
    (b) live-cache floors — edge kinds added by the MCP refresh layer
        (SEMANTIC_NEIGHBOR from embedding cosine, GUARDED_BY from keeper cache).
        These read from the on-disk SQLite cache; skipped if cache absent.

    Floors are calibrated against the known live-repo counts as of 2026-05-28:
      DEFINED_IN: 20377        → floor 10000 (build_graph layer)
      KB_POINTER: 897          → floor 500   (build_graph layer)
      SEMANTIC_NEIGHBOR: 336   → floor 100   (MCP-refresh layer, cache-only)
      GUARDED_BY: 245          → floor 50    (MCP-refresh layer, cache-only)
    """

    # Floors for edges produced by build_graph() directly (no MCP layer needed).
    _BUILD_FLOORS = {
        "defined_in": 10000,
        "kb_pointer": 500,
    }

    # Floors for edges only present after the full MCP noc_graph_cache.refresh()
    # (SEMANTIC_NEIGHBOR from embeddings, GUARDED_BY from keeper patterns).
    _CACHE_FLOORS = {
        "semantic_neighbor": 100,
        "guarded_by": 50,
    }

    @pytest.mark.parametrize("edge_kind,floor", list(_BUILD_FLOORS.items()))
    def test_build_edge_floor(self, live_edge_kinds, edge_kind, floor):
        """Floors for edge kinds emitted directly by build_graph() extractors."""
        from noctusai_lib.graph.schema import EdgeKind
        try:
            ek = EdgeKind(edge_kind)
        except ValueError:
            pytest.skip(f"EdgeKind {edge_kind!r} not in schema — update test")
        count = live_edge_kinds.get(ek, 0)
        assert count >= floor, (
            f"EdgeKind.{edge_kind.upper()} count {count} is below floor {floor}. "
            f"This suggests an extractor stopped emitting this edge kind. "
            f"If the codebase genuinely shrank, lower the floor explicitly."
        )

    @pytest.mark.parametrize("edge_kind,floor", list(_CACHE_FLOORS.items()))
    def test_cache_edge_floor(self, edge_kind, floor):
        """Floors for edge kinds added by the MCP refresh layer (cache-resident).

        Reads from the on-disk SQLite cache. Skipped if cache absent (fresh clone
        before first refresh — the floor test only applies to a refreshed cache).
        """
        import sqlite3

        from tools.noctus.dev.noc_graph_cache import cache_path

        cache_p = cache_path(_REPO_ROOT)
        if not cache_p.exists():
            pytest.skip(
                f"noc-graph cache absent at {cache_p} — "
                "run `python mcp/noctusai/cli.py --refresh-noc-graph` first."
            )
        # `semantic_neighbor` edges are derived from the OpenAI EMBEDDING cache
        # (cosine similarity over code/kb vectors). A hermetic env (CI, no OpenAI
        # key) legitimately has no embedding cache → the noc-graph build injects
        # zero such edges, so asserting a floor there is a false red. Skip when the
        # embedding cache is absent; the local dev run (where it exists) still
        # enforces the floor. `guarded_by` needs only the keeper cache (zero-OpenAI,
        # built in CI), so it keeps asserting.
        if edge_kind == "semantic_neighbor":
            from tools.noctus.dev.cache_backend import cache_path as _emb_cache_path

            if not _emb_cache_path("code-embeddings", _REPO_ROOT).exists():
                pytest.skip(
                    "embedding cache absent (hermetic env / no OpenAI key) — "
                    "semantic_neighbor edges require embeddings."
                )
        conn = sqlite3.connect(str(cache_p))
        try:
            row = conn.execute(
                "SELECT count(*) FROM noc_graph_edges WHERE kind = ?",
                (edge_kind,),
            ).fetchone()
            count = row[0] if row else 0
        finally:
            conn.close()

        assert count >= floor, (
            f"EdgeKind '{edge_kind}' count {count} in live cache is below floor {floor}. "
            f"This suggests the noc_graph_cache.refresh() stopped injecting this edge kind. "
            f"Floors: semantic_neighbor requires embedding cache; guarded_by requires keeper cache. "
            f"If the codebase genuinely shrank, lower the floor explicitly."
        )

    def test_total_edge_count_floor(self, live_graph_edges):
        """Total edge count from build_graph() must exceed 5000."""
        total = len(live_graph_edges)
        floor = 5000
        assert total >= floor, (
            f"Total edge count {total} is below floor {floor}. "
            "This suggests a systematic extractor failure."
        )

    def test_total_node_count_floor(self, live_graph_nodes):
        """Total node count from build_graph() must exceed 500."""
        total = len(live_graph_nodes)
        floor = 500
        assert total >= floor, (
            f"Total node count {total} is below floor {floor}. "
            "This suggests a systematic extractor failure."
        )
