"""Round-trip + serialization invariants on the Graph schema."""

from __future__ import annotations

import json

from noctusai_lib.graph.schema import (
    Confidence,
    Edge,
    EdgeKind,
    Graph,
    Node,
    NodeKind,
    SCHEMA_VERSION,
)


def test_node_round_trip_preserves_fields():
    node = Node(
        id="code:foo/bar.py:Klass",
        label="Klass",
        kind=NodeKind.CLASS,
        path="foo/bar.py",
        line=10,
        end_line=42,
        product="erp-imobiliario",
        cluster=3,
        confidence=Confidence.EXTRACTED.value,
        meta=(("docstring", "hi"),),
    )
    payload = node.to_dict()
    restored = Node.from_dict(payload)
    assert restored.id == node.id
    assert restored.kind is NodeKind.CLASS
    assert restored.product == node.product
    assert restored.cluster == 3
    assert dict(restored.meta) == {"docstring": "hi"}


def test_edge_round_trip_preserves_fields():
    edge = Edge(
        source="code:a",
        target="code:b",
        kind=EdgeKind.IMPORTS,
        confidence=0.7,
        weight=1.5,
        meta=(("note", "x"),),
    )
    restored = Edge.from_dict(edge.to_dict())
    assert restored.kind is EdgeKind.IMPORTS
    assert restored.confidence == 0.7
    assert restored.weight == 1.5
    assert dict(restored.meta) == {"note": "x"}


def test_graph_json_round_trip():
    g = Graph(
        nodes=[
            Node(id="a", label="A", kind=NodeKind.MODULE),
            Node(id="b", label="B", kind=NodeKind.MODULE),
        ],
        edges=[
            Edge(source="a", target="b", kind=EdgeKind.IMPORTS),
        ],
        meta={"scope": "test"},
    )
    payload = g.to_json()
    restored = Graph.from_json(payload)
    assert len(restored.nodes) == 2
    assert len(restored.edges) == 1
    assert restored.edges[0].kind is EdgeKind.IMPORTS
    assert restored.meta["scope"] == "test"


def test_schema_version_in_payload():
    g = Graph()
    payload = json.loads(g.to_json())
    assert payload["schema_version"] == SCHEMA_VERSION
