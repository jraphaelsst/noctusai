"""Tests for noc-graph re-export attribution — ``consumes_component`` edges.

Root-cause: previously the TS extractor emitted only ``consumes_seed`` edges
pointing at the barrel package path (e.g. ``pkg:@noctusai/lib/design-system``).
Named symbols like ``LoginForm`` were never resolved to their canonical
``seed/lib/frontend/src/.../LoginForm.tsx`` component files. This left 9
products invisibly consuming the component with zero graph attribution.

Fix: ``BarrelResolver`` walks every ``index.ts`` barrel under
``seed/lib/frontend/src/``, builds a ``symbol → canonical_path`` map, and the
TS extractor emits a ``consumes_component`` edge for each named barrel import.

Test categories:
  1. Real-graph counts  — LoginForm ≥9, ResourceManager ≥3 consumers.
  2. Zero-consumer shelfware  — PageSkeleton, LLMSpendBadge, FakeModeBadge,
     ErrorBoundary emit zero ``consumes_component`` edges FROM product files.
  3. Synthetic barrel traversal  — deterministic unit test with synthetic
     barrel + component files.
  4. No circular attribution  — no edge FROM a barrel index.ts file itself.

Note: tests that build from the live tree (categories 1 & 2) are
``scope="session"`` shared; only built once for the whole test run.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

MCP_ROOT = Path(__file__).resolve().parent.parent
if str(MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(MCP_ROOT))

_WORKTREE_ROOT = MCP_ROOT.parent.parent
_WORKTREE_SEED_LIB = _WORKTREE_ROOT / "seed" / "lib" / "backend"
if _WORKTREE_SEED_LIB.exists() and str(_WORKTREE_SEED_LIB) not in sys.path:
    sys.path.insert(0, str(_WORKTREE_SEED_LIB))

_REPO_ROOT = MCP_ROOT.parent.parent
if not (_REPO_ROOT / "CLAUDE.md").exists():
    _REPO_ROOT = MCP_ROOT.parent.parent.parent.parent
if not (_REPO_ROOT / "CLAUDE.md").exists():
    _REPO_ROOT = Path("/Users/rapha/Documents/repository/NoctusAI/noctusai")


# ── Shared live-graph fixture ─────────────────────────────────────────────────

@pytest.fixture(scope="session")
def live_graph():
    from noctusai_lib.graph import build_graph
    return build_graph(_REPO_ROOT, scope="repo")


@pytest.fixture(scope="session")
def consumes_component_edges(live_graph):
    from noctusai_lib.graph.schema import EdgeKind
    return [e for e in live_graph.edges if e.kind == EdgeKind.CONSUMES_COMPONENT]


@pytest.fixture(scope="session")
def cc_by_target(consumes_component_edges):
    """Map target node_id → list[source node_id]."""
    from collections import defaultdict
    result: dict[str, list[str]] = defaultdict(list)
    for e in consumes_component_edges:
        result[e.target].append(e.source)
    return dict(result)


@pytest.fixture(scope="session")
def cc_by_source(consumes_component_edges):
    """Map source node_id → list[target node_id]."""
    from collections import defaultdict
    result: dict[str, list[str]] = defaultdict(list)
    for e in consumes_component_edges:
        result[e.source].append(e.target)
    return dict(result)


# ── 1. Real-graph consumer counts ─────────────────────────────────────────────

class TestRealGraphConsumerCounts:
    """LoginForm and ResourceManager must resolve to ≥ expected consumer counts."""

    def test_login_form_attributes_to_9_consumers(self, cc_by_target):
        """LoginForm is imported via @noctusai/lib/design-system in 9 products.

        The target node id is ``code:seed/lib/frontend/src/design-system/components/LoginForm.tsx:LoginForm``.
        """
        # Find all targets that mention LoginForm (handles both with and
        # without the :LoginForm suffix — pick the one with most consumers).
        login_form_targets = {
            tid: sources
            for tid, sources in cc_by_target.items()
            if "LoginForm" in tid and "seed/lib/frontend" in tid
        }
        assert login_form_targets, (
            "No consumes_component edges found targeting a LoginForm node in "
            "seed/lib/frontend. Barrel resolution failed or LoginForm was "
            "renamed. Targets with LoginForm: "
            + str([t for t in cc_by_target if "LoginForm" in t])
        )
        max_consumers = max(len(v) for v in login_form_targets.values())
        assert max_consumers >= 9, (
            f"Expected ≥9 products to consume LoginForm via barrel resolution; "
            f"got {max_consumers}. "
            f"Consumers found: {list(login_form_targets.items())}"
        )

    def test_resource_manager_attributes_correctly(self, cc_by_target):
        """ResourceManager is imported from @noctusai/lib/components in ≥3 places."""
        rm_targets = {
            tid: sources
            for tid, sources in cc_by_target.items()
            if "ResourceManager" in tid and "seed/lib/frontend" in tid
        }
        assert rm_targets, (
            "No consumes_component edges found targeting ResourceManager in seed/lib/frontend. "
            "Available targets: " + str([t for t in cc_by_target if "Resource" in t])
        )
        max_consumers = max(len(v) for v in rm_targets.values())
        assert max_consumers >= 3, (
            f"Expected ≥3 consumers of ResourceManager; got {max_consumers}"
        )


# ── 2. Zero-consumer shelfware ────────────────────────────────────────────────

class TestShelfwareHasZeroConsumers:
    """Shelfware components must have zero consumes_component edges FROM product files.

    ``PageSkeleton``, ``LLMSpendBadge``, ``FakeModeBadge``, ``ErrorBoundary``
    are declared in the design-system barrel but not consumed directly by
    products (they're used internally by the seed framework shell or not yet
    used at all).

    Checking "zero PRODUCT consumers" (source contains a product path), not
    zero edges total — seed-internal references between barrel siblings are
    excluded.
    """

    def _product_consumers(self, cc_by_target: dict, symbol: str) -> list[str]:
        """Return list of source node IDs from product code that consume ``symbol``."""
        result = []
        for tid, sources in cc_by_target.items():
            if symbol in tid and "seed/lib/frontend" in tid:
                for src in sources:
                    # Product code lives under products/<slug>/; seed under seed/
                    if src.startswith("code:products/"):
                        result.append(src)
        return result

    def test_page_skeleton_zero_product_consumers(self, cc_by_target):
        consumers = self._product_consumers(cc_by_target, "PageSkeleton")
        assert consumers == [], (
            f"PageSkeleton has unexpected direct product consumers: {consumers}"
        )

    def test_llm_spend_badge_zero_product_consumers(self, cc_by_target):
        consumers = self._product_consumers(cc_by_target, "LLMSpendBadge")
        assert consumers == [], (
            f"LLMSpendBadge has unexpected direct product consumers: {consumers}"
        )

    def test_fake_mode_badge_zero_product_consumers(self, cc_by_target):
        consumers = self._product_consumers(cc_by_target, "FakeModeBadge")
        assert consumers == [], (
            f"FakeModeBadge has unexpected direct product consumers: {consumers}"
        )

    def test_error_boundary_zero_product_consumers(self, cc_by_target):
        consumers = self._product_consumers(cc_by_target, "ErrorBoundary")
        assert consumers == [], (
            f"ErrorBoundary has unexpected direct product consumers: {consumers}"
        )


# ── 3. Synthetic barrel traversal (deterministic unit test) ──────────────────

class TestDesignSystemBarrelTraversal:
    """Deterministic unit test with synthetic barrel + component in a temp dir.

    Verifies:
    - BarrelResolver resolves symbol through a barrel index.ts re-export
    - ``consumes_component`` edge is emitted from consumer to canonical component
    - No edge is emitted from the barrel index.ts itself (is_barrel_shim guard)
    """

    @pytest.fixture(scope="class")
    def synthetic_graph(self):
        """Build a mini-graph from a synthetic tree: barrel + component + consumer.

        Imports are done inside the fixture to pick up sys.modules state set by
        conftest (worktree evict+prepend already ran by fixture collection time).
        """
        from noctusai_lib.graph.extract_code import BarrelResolver, CodeRoot, walk
        from noctusai_lib.graph.schema import EdgeKind, Graph

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)

            # Synthetic seed/lib/frontend/src structure
            seed_src = root / "seed" / "lib" / "frontend" / "src"
            ds_dir = seed_src / "design-system"
            components_dir = ds_dir / "components"
            components_dir.mkdir(parents=True)

            # Canonical component file
            foo_tsx = components_dir / "Foo.tsx"
            foo_tsx.write_text(
                'export const Foo = () => <div>Foo</div>;\n', encoding="utf-8"
            )

            # Barrel index.ts re-exporting Foo
            barrel = ds_dir / "index.ts"
            barrel.write_text(
                'export { Foo } from "./components/Foo";\n', encoding="utf-8"
            )

            # Consumer product file importing Foo from the barrel
            product_dir = root / "products" / "my-product" / "frontend" / "src"
            product_dir.mkdir(parents=True)
            consumer_tsx = product_dir / "MyPage.tsx"
            consumer_tsx.write_text(
                'import { Foo } from "@noctusai/lib/design-system";\n'
                'export const MyPage = () => <Foo />;\n',
                encoding="utf-8",
            )

            # Build graph
            graph = Graph()
            resolver = BarrelResolver(seed_src, root)

            for code_root, product_name in [
                (CodeRoot(path=seed_src, label="seed/lib/frontend", product=None,
                          kind_hint=None), None),
                (CodeRoot(path=product_dir, label="my-product/frontend", product="my-product",
                          kind_hint=None), "my-product"),
            ]:
                walk(graph, code_root, repo_root=root, barrel_resolver=resolver)

            return graph, root

    def test_consumes_component_edge_emitted(self, synthetic_graph):
        """Consumer → canonical component edge must exist."""
        from noctusai_lib.graph.schema import EdgeKind
        graph, root = synthetic_graph
        cc_edges = [e for e in graph.edges if e.kind == EdgeKind.CONSUMES_COMPONENT]
        assert len(cc_edges) >= 1, (
            f"Expected ≥1 consumes_component edge; got 0. "
            f"All edges: {[(e.source, e.target, e.kind) for e in graph.edges]}"
        )

    def test_consumes_component_edge_points_at_canonical(self, synthetic_graph):
        """Target must be the canonical Foo.tsx node, not the barrel."""
        from noctusai_lib.graph.schema import EdgeKind
        graph, root = synthetic_graph
        cc_edges = [e for e in graph.edges if e.kind == EdgeKind.CONSUMES_COMPONENT]
        targets = [e.target for e in cc_edges]
        assert any("Foo.tsx" in t or "/Foo" in t for t in targets), (
            f"consumes_component edge should target canonical Foo.tsx, not barrel; "
            f"targets: {targets}"
        )
        # Must NOT point at the barrel index.ts itself
        assert not any("index.ts" in t or "index" in t.split(":")[-1] for t in targets), (
            f"consumes_component edge must not target barrel index.ts; targets: {targets}"
        )

    def test_barrel_shim_has_no_consumes_component_source(self, synthetic_graph):
        """The barrel index.ts itself must not be the SOURCE of consumes_component edges."""
        from noctusai_lib.graph.schema import EdgeKind
        graph, root = synthetic_graph
        cc_edges = [e for e in graph.edges if e.kind == EdgeKind.CONSUMES_COMPONENT]
        barrel_sources = [
            e.source for e in cc_edges
            if "index.ts" in e.source or e.source.endswith(":index")
        ]
        assert barrel_sources == [], (
            f"Barrel index.ts must not be source of consumes_component edges; "
            f"found: {barrel_sources}"
        )


# ── 4. No circular attribution ───────────────────────────────────────────────

class TestNoCircularAttribution:
    """No ``consumes_component`` edge from a barrel index.ts source.

    Barrel shims re-export FROM canonical components — they are not consumers.
    Emitting barrel→component edges would create a false cycle.
    """

    def test_no_barrel_index_as_source(self, consumes_component_edges):
        """All consumes_component sources must be non-barrel (non-index.ts) files."""
        barrel_sources = [
            e.source for e in consumes_component_edges
            if (
                # barrel indices under seed/lib/frontend/src always named index.ts
                "/index.ts" in e.source
                and "seed/lib/frontend/src" in e.source
            )
        ]
        assert barrel_sources == [], (
            f"Found {len(barrel_sources)} consumes_component edges sourced from "
            f"barrel index.ts files (is_barrel_shim guard failed): "
            f"{barrel_sources[:10]}"
        )

    def test_consumes_component_edge_count_positive(self, consumes_component_edges):
        """Sanity: must have at least 9 consumes_component edges (LoginForm alone)."""
        count = len(consumes_component_edges)
        assert count >= 9, (
            f"Expected ≥9 consumes_component edges across repo; got {count}"
        )
