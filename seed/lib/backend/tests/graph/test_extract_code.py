"""L1 code extractor — uses tmp_path fixtures with synthetic Python + TS sources."""

from __future__ import annotations

from pathlib import Path

from noctusai_lib.graph.extract_code import CodeRoot, walk
from noctusai_lib.graph.schema import EdgeKind, Graph, NodeKind


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def test_python_walker_emits_module_class_function_nodes(tmp_path):
    repo = tmp_path
    _write(repo / "pkg" / "mod.py", '''"""Module docstring."""
import os
from noctusai_lib.api import StrictHttpModel

class Foo(StrictHttpModel):
    def bar(self):
        return 1

def top_level():
    return 2
''')
    graph = Graph()
    walk(graph, CodeRoot(path=repo / "pkg", label="pkg", product="testprod"), repo_root=repo)

    kinds = {n.kind for n in graph.nodes}
    labels = {n.label for n in graph.nodes}
    edge_kinds = {e.kind for e in graph.edges}

    assert NodeKind.MODULE in kinds
    assert NodeKind.CLASS in kinds
    assert NodeKind.METHOD in kinds
    assert NodeKind.FUNCTION in kinds
    assert "Foo" in labels
    assert "Foo.bar" in labels
    assert "top_level" in labels
    assert EdgeKind.CONSUMES_SEED in edge_kinds  # from noctusai_lib.api import
    assert EdgeKind.IMPORTS in edge_kinds  # import os
    assert EdgeKind.DEFINED_IN in edge_kinds
    assert EdgeKind.CONTAINS in edge_kinds  # product anchor → module


def test_python_walker_detects_mcp_tool_decorator(tmp_path):
    repo = tmp_path
    _write(repo / "tools" / "foo.py", '''
@server.tool(name="x")
def some_tool():
    return {}
''')
    graph = Graph()
    walk(graph, CodeRoot(path=repo / "tools", label="t", product=None), repo_root=repo)
    kinds = {n.kind for n in graph.nodes if n.label == "some_tool"}
    assert NodeKind.MCP_TOOL in kinds


def test_typescript_walker_picks_components_and_hooks(tmp_path):
    repo = tmp_path
    _write(repo / "frontend" / "src" / "Card.tsx", '''
import { useState } from 'react';
import { useToast } from '@/lib/toast';

export function MyCard() {
  return null;
}

export const useThing = () => 1;
''')
    graph = Graph()
    walk(graph, CodeRoot(path=repo / "frontend" / "src", label="fe", product="x"), repo_root=repo)

    by_label = {n.label: n for n in graph.nodes}
    assert by_label["MyCard"].kind is NodeKind.COMPONENT
    assert by_label["useThing"].kind is NodeKind.HOOK


def test_python_walker_skips_syntax_error_gracefully(tmp_path):
    repo = tmp_path
    _write(repo / "broken.py", "def x(:\n")
    graph = Graph()
    walk(graph, CodeRoot(path=repo, label="r", product=None), repo_root=repo)
    # No module node for the broken file; walker keeps going.
    assert not any(n.path == "broken.py" for n in graph.nodes)
