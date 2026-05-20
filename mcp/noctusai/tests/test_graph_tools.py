"""MCP tool smoke for ``noctus.graph.*``.

Builds against a synthetic fixture repo via the library, then exercises
the query/neighbors/path/explain/report wrappers with the cache pointing
at a tmp dir.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

MCP_ROOT = Path(__file__).resolve().parent.parent
if str(MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(MCP_ROOT))


def _fixture_repo(tmp_path: Path) -> Path:
    (tmp_path / "KNOWLEDGE-BASE").mkdir()
    (tmp_path / "KNOWLEDGE-BASE" / "02-LANDSCAPE.md").write_text(
        "# x\n\n## Products\n\n| slug | desc |\n|---|---|\n| `foo` | f |\n",
        encoding="utf-8",
    )
    (tmp_path / "KNOWLEDGE-BASE" / "PATTERNS").mkdir()
    (tmp_path / "KNOWLEDGE-BASE" / "PATTERNS" / "x.md").write_text(
        "# X pattern\n\nRefs `KB § PATTERNS/y.md`.\n", encoding="utf-8"
    )
    (tmp_path / "KNOWLEDGE-BASE" / "PATTERNS" / "y.md").write_text(
        "# Y pattern\n\nMore.\n", encoding="utf-8"
    )
    foo = tmp_path / "products" / "foo" / "backend"
    foo.mkdir(parents=True)
    (foo / "svc.py").write_text(
        '"""svc."""\nclass FooSvc:\n    def hello(self): return 1\n',
        encoding="utf-8",
    )
    seed = tmp_path / "seed" / "lib" / "backend" / "noctusai_lib"
    seed.mkdir(parents=True)
    (seed / "api.py").write_text('"""api."""\nclass StrictHttpModel: pass\n', encoding="utf-8")
    return tmp_path


def test_build_writes_artifacts(tmp_path, monkeypatch):
    from noctusai_lib.graph import build_graph
    from noctusai_lib.graph.serialize import write_graph_html, write_graph_json

    repo = _fixture_repo(tmp_path)
    graph = build_graph(repo, scope="repo")
    out = tmp_path / ".noc-graph"
    json_path = write_graph_json(graph, out)
    html_path = write_graph_html(graph, out)
    assert json_path.exists()
    assert html_path.exists()
    payload = json.loads(json_path.read_text())
    assert payload["schema_version"] == 1
    assert payload["nodes"]


def test_loader_and_query_round_trip(tmp_path, monkeypatch):
    from noctusai_lib.graph import build_graph
    from noctusai_lib.graph.serialize import write_graph_json
    from tools.noctus.graph import _loader as loader_mod

    repo = _fixture_repo(tmp_path)
    graph = build_graph(repo, scope="repo")
    write_graph_json(graph, tmp_path / ".noc-graph")

    monkeypatch.setattr(loader_mod, "REPO_ROOT", tmp_path)

    idx = loader_mod.load_index()
    hits = idx.search("FooSvc")
    assert hits, "FooSvc should be findable"
    explain_payload = idx.explain(hits[0][0].id)
    assert explain_payload["node"]["label"] == "FooSvc"


def test_report_returns_counts(tmp_path, monkeypatch):
    from noctusai_lib.graph import build_graph
    from noctusai_lib.graph.serialize import write_graph_json
    from tools.noctus.graph import _loader as loader_mod
    from tools.noctus.graph.report import report

    repo = _fixture_repo(tmp_path)
    graph = build_graph(repo, scope="repo")
    write_graph_json(graph, tmp_path / ".noc-graph")
    monkeypatch.setattr(loader_mod, "REPO_ROOT", tmp_path)

    out = report()
    assert out["node_count"] > 0
    assert "kind_counts" in out
    assert isinstance(out["top_clusters"], list)


def test_loader_raises_when_cache_missing(tmp_path, monkeypatch):
    from tools.noctus.graph import _loader as loader_mod

    monkeypatch.setattr(loader_mod, "REPO_ROOT", tmp_path)
    with pytest.raises(FileNotFoundError):
        loader_mod.load_index()
