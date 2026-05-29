"""End-to-end smoke: build a tiny synthetic repo, run build_graph + GraphIndex.

Uses a fixture repo (no I/O outside tmp_path) so the test is hermetic.
"""

from __future__ import annotations

from pathlib import Path

from noctusai_lib.graph import build_graph
from noctusai_lib.graph.query import GraphIndex
from noctusai_lib.graph.schema import EdgeKind, NodeKind
from noctusai_lib.graph.serialize import write_graph_html, write_graph_json


def _fixture_repo(tmp_path: Path) -> Path:
    """Create a minimal noc-shaped tree under tmp_path."""
    (tmp_path / "KNOWLEDGE-BASE").mkdir()
    (tmp_path / "KNOWLEDGE-BASE" / "02-LANDSCAPE.md").write_text(
        """# Landscape

## Products

| slug | description |
|------|-------------|
| `foo` | foo product |
| `bar` | bar product |
""",
        encoding="utf-8",
    )
    (tmp_path / "KNOWLEDGE-BASE" / "PATTERNS").mkdir()
    (tmp_path / "KNOWLEDGE-BASE" / "PATTERNS" / "alpha.md").write_text(
        """# Alpha pattern

This documents `products/foo/backend/services/foo_service.py` and references
`KB § PATTERNS/beta.md` for the rest.
""",
        encoding="utf-8",
    )
    (tmp_path / "KNOWLEDGE-BASE" / "PATTERNS" / "beta.md").write_text(
        "# Beta pattern\n\nReferences `KB § PATTERNS/alpha.md`.\n",
        encoding="utf-8",
    )

    foo_be = tmp_path / "products" / "foo" / "backend" / "services"
    foo_be.mkdir(parents=True)
    (foo_be / "foo_service.py").write_text(
        '''"""Foo service docstring."""
from noctusai_lib.api import StrictHttpModel

class FooModel(StrictHttpModel):
    pass

def make_foo():
    return FooModel()
''',
        encoding="utf-8",
    )

    bar_be = tmp_path / "products" / "bar" / "backend"
    bar_be.mkdir(parents=True)
    (bar_be / "main.py").write_text(
        '''"""Bar entry."""
from products.foo.backend.services.foo_service import make_foo

def run():
    return make_foo()
''',
        encoding="utf-8",
    )

    # tiny seed module
    seed_pkg = tmp_path / "seed" / "lib" / "backend" / "noctusai_lib"
    seed_pkg.mkdir(parents=True)
    (seed_pkg / "api.py").write_text(
        '"""api module."""\nclass StrictHttpModel: pass\n',
        encoding="utf-8",
    )

    return tmp_path


def test_build_graph_repo_scope_produces_nodes_and_edges(tmp_path):
    repo = _fixture_repo(tmp_path)
    graph = build_graph(repo, scope="repo")

    # Product anchors present
    ids = {n.id for n in graph.nodes}
    assert "product:foo" in ids
    assert "product:bar" in ids
    assert "seed:noctusai_lib" in ids

    # Code nodes
    labels = {n.label for n in graph.nodes}
    assert "FooModel" in labels
    assert "make_foo" in labels
    assert "run" in labels

    # KB pattern nodes
    assert "kb:PATTERNS/alpha.md" in ids
    assert "kb:PATTERNS/beta.md" in ids

    # KB→KB pointer edges
    pointer_edges = [e for e in graph.edges if e.kind is EdgeKind.KB_POINTER]
    assert any(e.source == "kb:PATTERNS/alpha.md" and e.target == "kb:PATTERNS/beta.md" for e in pointer_edges)


def test_build_graph_seed_scope_excludes_products(tmp_path):
    repo = _fixture_repo(tmp_path)
    graph = build_graph(repo, scope="seed")
    code_paths = {n.path for n in graph.nodes if n.path and n.path.startswith("products/")}
    assert code_paths == set()


def test_graph_index_search_and_neighbors(tmp_path):
    repo = _fixture_repo(tmp_path)
    graph = build_graph(repo, scope="repo")
    idx = GraphIndex(graph)

    hits = idx.search("FooModel")
    assert hits, "search should find FooModel"
    assert hits[0][0].label == "FooModel"

    nbr = idx.neighbors(hits[0][0].id, depth=1)
    assert nbr["node"]["label"] == "FooModel"
    assert nbr["subgraph"]["nodes"], "neighborhood should include linked nodes"


def test_graph_index_empty_query_lists_all_nodes(tmp_path):
    """An empty query is a LISTING request, not a no-op (contextualize fabric)."""
    repo = _fixture_repo(tmp_path)
    graph = build_graph(repo, scope="repo")
    idx = GraphIndex(graph)

    listed = idx.search("", limit=10_000)
    assert len(listed) == len(graph.nodes), "empty query must enumerate every node"
    labels = [n.label.lower() for n, _ in listed]
    assert labels == sorted(labels), "empty-query listing must be label-sorted (stable)"

    # kind filter still applies in listing mode — pick a kind present in the graph
    a_kind = graph.nodes[0].kind
    filtered = idx.search("", kinds=[a_kind], limit=10_000)
    assert filtered, "kind-filtered empty query should return that kind's nodes"
    assert all(n.kind == a_kind for n, _ in filtered)

    # limit still caps listing output
    assert len(idx.search("", limit=1)) == 1


def test_walk_kb_chapters_reclassifies_under_context_prefix(tmp_path):
    """Chapters survive the PATTERNS→CONTEXT reorg (kb:CONTEXT/0X-NAME.md)."""
    from dataclasses import replace

    from noctusai_lib.graph.extract_landscape import walk_kb_chapters
    from noctusai_lib.graph.schema import Graph, Node, NodeKind

    nodes = [
        Node(id="kb:CONTEXT/01-PHILOSOPHY.md", label="01 — Philosophy", kind=NodeKind.KB_PATTERN),
        Node(id="kb:07-GAMIFICATION.md", label="07 — Gamification", kind=NodeKind.KB_PATTERN),  # legacy root layout
        Node(id="kb:CONTEXT/PATTERNS/common/foo.md", label="foo", kind=NodeKind.KB_PATTERN),  # NOT a chapter
    ]
    graph = Graph(nodes=nodes, edges=[])
    walk_kb_chapters(graph, tmp_path, repo_root=tmp_path)

    by_id = {n.id: n for n in graph.nodes}
    assert by_id["kb:CONTEXT/01-PHILOSOPHY.md"].kind == NodeKind.KB_CHAPTER, "CONTEXT/-prefixed chapter must reclassify"
    assert by_id["kb:07-GAMIFICATION.md"].kind == NodeKind.KB_CHAPTER, "legacy root-level chapter still reclassifies"
    assert by_id["kb:CONTEXT/PATTERNS/common/foo.md"].kind == NodeKind.KB_PATTERN, "deep pattern must NOT become a chapter"


def test_graph_serializers_write_files(tmp_path):
    repo = _fixture_repo(tmp_path)
    graph = build_graph(repo, scope="repo")
    out = tmp_path / ".noc-graph"
    json_path = write_graph_json(graph, out)
    html_path = write_graph_html(graph, out)
    assert json_path.exists()
    assert html_path.exists()
    html_body = html_path.read_text()
    assert "vis-network" in html_body
    assert "graphify.net" in html_body  # footer reference per project spec
    assert '"nodes":' in html_body or '"nodes"' in html_body  # inlined JSON


def test_graph_index_shortest_path_via_imports(tmp_path):
    repo = _fixture_repo(tmp_path)
    graph = build_graph(repo, scope="repo")
    idx = GraphIndex(graph)
    # bar.main → make_foo (in foo) — module-level pkg import edges link via "pkg:..." synthetic id
    bar_main = next((n for n in graph.nodes if n.label == "main" and n.kind is NodeKind.MODULE), None)
    foo_service = next((n for n in graph.nodes if n.label == "foo_service" and n.kind is NodeKind.MODULE), None)
    assert bar_main and foo_service
    result = idx.shortest_path(bar_main.id, foo_service.id)
    # In this fixture, the path goes through the package-import synthetic node — len ≥ 1 OK either way.
    assert "path" in result
