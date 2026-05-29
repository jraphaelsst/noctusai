"""Tests for noctus.dev.component_list.

Covers:
- test_lists_all_components: returns list for all component nodes
- test_sort_consumers_desc: LoginForm/ForgotPasswordPage/AcceptInvitePage at top
- test_filter_shelfware: returns PageSkeleton/LLMSpendBadge etc. with 0 consumers
- test_filter_validated: returns only status=validated entries
- test_results_cache_by_graph_sha: sha change → re-compute; same sha → cached
- test_fallback_to_imports_edges: W1 not landed → imports edges used with warning
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.component_list import (
    ComponentListEntry,
    _RESULT_CACHE,
    _get_cached,
    _set_cached,
    list_components,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────


def _make_node(label: str, path: str | None = None, product: str | None = None):
    """Build a synthetic noc-graph Node-like object."""
    from noctusai_lib.graph.schema import Node, NodeKind
    return Node(
        id=f"component:{label}",
        label=label,
        kind=NodeKind.COMPONENT,
        path=path,
        product=product,
        confidence=1.0,
    )


def _make_edge(source: str, target: str, kind: str):
    """Build a synthetic Edge-like object."""
    from noctusai_lib.graph.schema import Edge, EdgeKind
    # Use the enum value for standard kinds; fall back to a mock for custom.
    try:
        ek = EdgeKind(kind)
    except ValueError:
        ek = MagicMock()
        ek.value = kind
    return Edge(source=source, target=target, kind=ek, confidence=1.0, weight=1.0)


def _build_mock_index(nodes, edges):
    """Build a mock GraphIndex mirroring the real interface."""
    from collections import defaultdict

    graph_mock = MagicMock()
    graph_mock.nodes = nodes
    graph_mock.edges = edges

    out_edges = defaultdict(list)
    in_edges = defaultdict(list)
    for e in edges:
        out_edges[e.source].append(e)
        in_edges[e.target].append(e)

    index = MagicMock()
    index.graph = graph_mock
    index.out_edges = out_edges
    index.in_edges = in_edges
    return index


FIVE_SEED_ORGANS = [
    "LoginForm",
    "ForgotPasswordPage",
    "AcceptInvitePage",
    "ResourceManager",
    "DigestCard",
]

SHELFWARE_ORGANS = [
    "PageSkeleton",
    "LLMSpendBadge",
    "FakeModeBadge",
    "ErrorBoundary",
]


def _build_catalog_index():
    """Build a synthetic GraphIndex mirroring Phase-1 canonical set.

    Consumer counts per PROJECT.md §4a:
      LoginForm → 9 consumers
      ForgotPasswordPage → 8 consumers
      AcceptInvitePage → 8 consumers
      ResourceManager → 3 consumers
      DigestCard → 3 consumers
      PageSkeleton, LLMSpendBadge, FakeModeBadge, ErrorBoundary → 0 (shelfware)
    """
    counts = {
        "LoginForm": 9,
        "ForgotPasswordPage": 8,
        "AcceptInvitePage": 8,
        "ResourceManager": 3,
        "DigestCard": 3,
        "PageSkeleton": 0,
        "LLMSpendBadge": 0,
        "FakeModeBadge": 0,
        "ErrorBoundary": 0,
    }

    nodes = []
    edges = []
    for label, count in counts.items():
        node_id = f"component:{label}"
        nodes.append(_make_node(label, path=f"seed/lib/frontend/src/{label}.tsx"))
        for i in range(count):
            edges.append(
                _make_edge(
                    source=f"product_{i}:SomeConsumer",
                    target=node_id,
                    kind="consumes_component",
                )
            )

    return _build_mock_index(nodes, edges)


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestListComponents:
    def setup_method(self):
        _RESULT_CACHE.clear()

    def _run_list(self, sort="consumers_desc", filter_status=None, tmp_path=None):
        """Run list_components with a patched graph index."""
        idx = _build_catalog_index()
        with (
            patch("tools.noctus.dev.component_list._load_graph_index", return_value=idx),
            patch("tools.noctus.dev.component_list._get_source_sha", return_value="test-sha-001"),
            patch("tools.noctus.dev.component_list._last_touched_for_path", return_value="2026-05-29T00:00:00+00:00"),
            patch("tools.noctus.dev.component_list.compute_signal_inputs") as mock_compute,
        ):
            # compute_signal_inputs delegates to validation_signal — patch it to
            # return consistent inputs based on the node's consumer count.
            def _fake_compute(component_path, neighbors, repo_root):
                label = component_path.stem if hasattr(component_path, "stem") else str(component_path)
                consumers = sum(
                    1 for e in neighbors.get("edges", [])
                    if e.get("kind") == "consumes_component"
                )
                has_test = consumers >= 3
                return {
                    "consumers_count": consumers,
                    "has_test": has_test,
                    "test_passes_ci": True if consumers >= 3 else None,
                    "has_noc_remediate_markers": False,
                    "recent_bugfix_commits_14d": 0,
                }

            mock_compute.side_effect = _fake_compute

            root = tmp_path or Path("/fake/repo")
            # Patch Path.exists to return True for our fake component paths.
            with patch.object(Path, "exists", return_value=True):
                return list_components(sort=sort, filter_status=filter_status, repo_root=root)

    def test_lists_all_components(self, tmp_path):
        entries = self._run_list(tmp_path=tmp_path)
        names = [e.name for e in entries]
        for organ in FIVE_SEED_ORGANS + SHELFWARE_ORGANS:
            assert organ in names, f"Expected {organ} in component list"

    def test_sort_consumers_desc(self, tmp_path):
        """LoginForm (9) > ForgotPasswordPage (8) == AcceptInvitePage (8) > others."""
        entries = self._run_list(sort="consumers_desc", tmp_path=tmp_path)
        assert entries[0].name == "LoginForm"
        # Second and third should be ForgotPasswordPage / AcceptInvitePage (tied at 8).
        top3_names = {e.name for e in entries[:3]}
        assert "ForgotPasswordPage" in top3_names
        assert "AcceptInvitePage" in top3_names

    def test_sort_name(self, tmp_path):
        entries = self._run_list(sort="name", tmp_path=tmp_path)
        names = [e.name for e in entries]
        assert names == sorted(names, key=str.lower)

    def test_sort_last_touched(self, tmp_path):
        """last_touched sort: all have same mocked date, just verify it runs."""
        entries = self._run_list(sort="last_touched", tmp_path=tmp_path)
        assert len(entries) > 0

    def test_filter_shelfware(self, tmp_path):
        """filter_status=['shelfware'] returns exactly the 4 zero-consumer organs."""
        entries = self._run_list(filter_status=["shelfware"], tmp_path=tmp_path)
        names = {e.name for e in entries}
        for shelfware in SHELFWARE_ORGANS:
            assert shelfware in names, f"Expected {shelfware} in shelfware filter"
        for organ in FIVE_SEED_ORGANS:
            assert organ not in names, f"Did not expect {organ} in shelfware filter"
        assert all(e.validation_status == "shelfware" for e in entries)
        assert all(e.consumers_count == 0 for e in entries)

    def test_filter_validated(self, tmp_path):
        """filter_status=['validated'] returns only fully validated components.

        With the fake compute_signal_inputs, components with 3+ consumers AND
        test_passes_ci=True → validated.
        """
        entries = self._run_list(filter_status=["validated"], tmp_path=tmp_path)
        assert all(e.validation_status == "validated" for e in entries)
        assert all(e.consumers_count >= 3 for e in entries)

    def test_filter_multiple_statuses(self, tmp_path):
        entries = self._run_list(filter_status=["validated", "emerging"], tmp_path=tmp_path)
        for e in entries:
            assert e.validation_status in ("validated", "emerging")

    def test_entry_shape(self, tmp_path):
        """Every entry has the required fields."""
        entries = self._run_list(tmp_path=tmp_path)
        assert len(entries) > 0
        for entry in entries:
            assert isinstance(entry, ComponentListEntry)
            assert entry.name
            assert entry.validation_status in ("validated", "emerging", "shelfware", "unknown")
            assert isinstance(entry.consumers_count, int)

    def test_returns_empty_list_when_graph_missing(self, tmp_path):
        with (
            patch(
                "tools.noctus.dev.component_list._load_graph_index",
                side_effect=FileNotFoundError("graph missing"),
            ),
            patch("tools.noctus.dev.component_list._get_source_sha", return_value="sha-x"),
        ):
            entries = list_components(repo_root=tmp_path)
        assert entries == []


class TestResultsCacheByGraphSha:
    def setup_method(self):
        _RESULT_CACHE.clear()

    def _build_simple_index(self):
        nodes = [_make_node("LoginForm", path="seed/lib/frontend/src/LoginForm.tsx")]
        return _build_mock_index(nodes, [])

    def test_same_sha_returns_cached(self, tmp_path):
        """Second call with same sha skips graph traversal."""
        idx = self._build_simple_index()
        call_count = {"n": 0}

        def _fake_load_index(repo_root):
            call_count["n"] += 1
            return idx

        with (
            patch("tools.noctus.dev.component_list._load_graph_index", side_effect=_fake_load_index),
            patch("tools.noctus.dev.component_list._get_source_sha", return_value="stable-sha"),
            patch("tools.noctus.dev.component_list._last_touched_for_path", return_value=None),
            patch("tools.noctus.dev.component_list.compute_signal_inputs", return_value={
                "consumers_count": 0,
                "has_test": False,
                "test_passes_ci": None,
                "has_noc_remediate_markers": False,
                "recent_bugfix_commits_14d": 0,
            }),
            patch.object(Path, "exists", return_value=True),
        ):
            list_components(repo_root=tmp_path)  # first call — builds
            list_components(repo_root=tmp_path)  # second call — should use cache

        # Index loaded only once (second call hit the cache).
        assert call_count["n"] == 1

    def test_sha_change_triggers_recompute(self, tmp_path):
        """Different sha on second call → re-traverses the graph."""
        idx = self._build_simple_index()
        call_count = {"n": 0}

        def _fake_load_index(repo_root):
            call_count["n"] += 1
            return idx

        sha_store = {"current": "sha-v1"}

        def _fake_sha(root):
            return sha_store["current"]

        with (
            patch("tools.noctus.dev.component_list._load_graph_index", side_effect=_fake_load_index),
            patch("tools.noctus.dev.component_list._get_source_sha", side_effect=_fake_sha),
            patch("tools.noctus.dev.component_list._last_touched_for_path", return_value=None),
            patch("tools.noctus.dev.component_list.compute_signal_inputs", return_value={
                "consumers_count": 0,
                "has_test": False,
                "test_passes_ci": None,
                "has_noc_remediate_markers": False,
                "recent_bugfix_commits_14d": 0,
            }),
            patch.object(Path, "exists", return_value=True),
        ):
            list_components(repo_root=tmp_path)  # sha-v1
            sha_store["current"] = "sha-v2"      # simulate a graph source change
            list_components(repo_root=tmp_path)  # sha-v2 → recompute

        # Index loaded twice (each sha is a cache miss).
        assert call_count["n"] == 2


class TestFallbackToImportsEdges:
    def setup_method(self):
        _RESULT_CACHE.clear()

    def test_fallback_logs_warning_and_counts_imports(self, tmp_path, caplog):
        """When no consumes_component edges exist, falls back to imports edges."""
        import logging

        node_id = "component:LoginForm"
        node = _make_node("LoginForm", path="seed/lib/frontend/src/LoginForm.tsx")
        # Only imports edges — no consumes_component.
        edges = [
            _make_edge("productA:Page", node_id, "imports"),
            _make_edge("productB:Page", node_id, "imports"),
        ]
        idx = _build_mock_index([node], edges)

        with (
            patch("tools.noctus.dev.component_list._load_graph_index", return_value=idx),
            patch("tools.noctus.dev.component_list._get_source_sha", return_value="sha-imports"),
            patch("tools.noctus.dev.component_list._last_touched_for_path", return_value=None),
            patch("tools.noctus.dev.component_list.compute_signal_inputs", return_value={
                "consumers_count": 2,  # overridden by index count below
                "has_test": False,
                "test_passes_ci": None,
                "has_noc_remediate_markers": False,
                "recent_bugfix_commits_14d": 0,
            }),
            patch.object(Path, "exists", return_value=True),
            caplog.at_level(logging.WARNING),
        ):
            entries = list_components(repo_root=tmp_path)

        login_entry = next(e for e in entries if e.name == "LoginForm")
        # Should count 2 inbound imports edges as consumers.
        assert login_entry.consumers_count == 2
        assert any("imports" in record.message for record in caplog.records)
