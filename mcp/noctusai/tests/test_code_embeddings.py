"""Regression tests for `code_embeddings` — the fifth keeper-mirror cache.

Mirrors the structure of `test_kb_embeddings` (where applicable) but
swaps in code-specific surfaces: AST chunker, source-tree walker, kind
metadata, code_neighbors anchor-based search.

KB § CONTEXT/PATTERNS/common/code-embeddings.md.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import code_embeddings as ce  # noqa: E402


# ── Fixtures ─────────────────────────────────────────────────────────────────
@pytest.fixture
def tmp_repo(tmp_path, monkeypatch):
    """A fake repo root with minimal _CODE_ROOTS structure and an isolated cache."""
    for r in ce._CODE_ROOTS:
        (tmp_path / r).mkdir(parents=True, exist_ok=True)
    cache_dir = tmp_path / ".claude" / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(ce, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(ce, "CACHE_DIR", cache_dir)
    monkeypatch.setattr(ce, "CACHE_PATH", cache_dir / "code-embeddings.sqlite")
    return tmp_path


@pytest.fixture
def fake_embed(monkeypatch):
    """Deterministic 'embedding': sha256 → 1536-D float vector.

    Also mocks `vector_costs.log_refresh_batch` so tests don't pollute the
    real durable ledger at `project-history/vector-costs.ndjson`.
    """
    import hashlib

    def _fake(text: str) -> list[float]:
        seed = int.from_bytes(hashlib.sha256(text.encode()).digest()[:4], "big")
        return [((seed * (i + 1)) % 1000) / 1000.0 - 0.5 for i in range(ce.EMBEDDING_DIM)]

    monkeypatch.setattr(ce, "_embed_sync", _fake)
    # Isolate from the real vector-costs ledger.
    from tools.noctus.dev import vector_costs as _vc
    monkeypatch.setattr(_vc, "log_refresh_batch", lambda **kwargs: None)
    return _fake


# ── Cosine helper ────────────────────────────────────────────────────────────
class TestCosineHelper:
    def test_identical_vectors_score_one(self):
        v = [1.0, 0.0, 0.0]
        assert ce._cosine(v, v) == pytest.approx(1.0)

    def test_orthogonal_vectors_score_zero(self):
        assert ce._cosine([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)

    def test_zero_vector_returns_zero(self):
        assert ce._cosine([0.0, 0.0], [1.0, 1.0]) == 0.0

    def test_empty_inputs_return_zero(self):
        assert ce._cosine([], []) == 0.0


# ── Python AST chunker ──────────────────────────────────────────────────────
class TestPythonChunker:
    def test_simple_function_emits_one_chunk(self):
        src = (
            "def hello():\n"
            "    'docstring that pushes body past the min-chunk threshold'\n"
            "    return 'hi' * 50\n"
        )
        chunks = ce._chunk_python(src, src.splitlines())
        assert len(chunks) == 1
        assert chunks[0][0] == "hello"
        assert chunks[0][1] == "function"
        assert "def hello" in chunks[0][2]

    def test_async_function_kind(self):
        src = (
            "async def fetch():\n"
            "    'async helper that pushes body past min threshold ok ok'\n"
            "    await something()\n"
            "    return [1, 2, 3, 4, 5]\n"
        )
        chunks = ce._chunk_python(src, src.splitlines())
        assert chunks[0][1] == "async_function"

    def test_class_kind(self):
        src = (
            "class Foo:\n"
            "    'class with enough body to clear the min-chunk threshold'\n"
            "    def method(self):\n"
            "        return self.x + self.y + 1\n"
        )
        chunks = ce._chunk_python(src, src.splitlines())
        assert chunks[0][1] == "class"
        assert chunks[0][0] == "Foo"

    def test_multiple_top_level_defs(self):
        src = (
            "def alpha():\n"
            "    'docstring padding to clear min-chunk threshold for alpha'\n"
            "    return 'a' * 100\n\n"
            "def beta():\n"
            "    'docstring padding to clear min-chunk threshold for beta'\n"
            "    return 'b' * 100\n\n"
            "class Gamma:\n"
            "    'docstring padding to clear min-chunk threshold for Gamma'\n"
            "    def m(self): pass\n"
            "    def n(self): pass\n"
        )
        chunks = ce._chunk_python(src, src.splitlines())
        names = [c[0] for c in chunks]
        assert "alpha" in names
        assert "beta" in names
        assert "Gamma" in names

    def test_syntax_error_falls_back_to_whole_file(self):
        src = "def broken(\n    no close paren ever here\n" + ("# pad " * 50)
        chunks = ce._chunk_python(src, src.splitlines())
        assert len(chunks) == 1
        assert chunks[0][1] == "file"

    def test_tiny_function_below_min_skipped(self):
        src = "def x(): pass\n"
        chunks = ce._chunk_python(src, src.splitlines())
        # body too short → no chunk; whole-file fallback kicks in only when
        # no top-level def parsed at all, so here we expect empty.
        assert chunks == []

    def test_module_with_only_imports_emits_file_chunk(self):
        src = "import os\nimport sys\n" + ("# pad " * 50)
        chunks = ce._chunk_python(src, src.splitlines())
        assert len(chunks) == 1
        assert chunks[0][1] == "file"


# ── TypeScript chunker ──────────────────────────────────────────────────────
class TestTypeScriptChunker:
    def test_ts_file_emits_one_file_chunk(self):
        src = "export function foo() { return 'bar' + 'baz'; }\n" + ("// comment ok\n" * 5)
        chunks = ce._chunk_typescript(src)
        assert len(chunks) == 1
        assert chunks[0][1] == "file"
        assert chunks[0][0] == ""

    def test_ts_below_min_skipped(self):
        src = "x"
        assert ce._chunk_typescript(src) == []

    def test_ts_oversized_is_capped(self):
        src = "x" * (ce.MAX_CHUNK_CHARS + 1000)
        chunks = ce._chunk_typescript(src)
        assert len(chunks[0][2]) == ce.MAX_CHUNK_CHARS


# ── Source-tree walker ──────────────────────────────────────────────────────
class TestSourceWalker:
    def test_skips_pycache(self, tmp_repo):
        py = tmp_repo / "mcp" / "good.py"
        py.write_text("def good(): return 1 + 1 + 1 + 1 + 1\n")
        cached = tmp_repo / "mcp" / "__pycache__" / "bad.cpython-312.pyc"
        cached.parent.mkdir(parents=True)
        cached.write_text("binary garbage")
        bad_py = tmp_repo / "mcp" / "__pycache__" / "bad.py"
        bad_py.write_text("def bad(): pass\n")
        files = ce._iter_code_files(tmp_repo)
        assert py in files
        assert bad_py not in files

    def test_skips_node_modules(self, tmp_repo):
        ts = tmp_repo / "products" / "seed" / "app.ts"
        ts.write_text("export const x = 1;\n" + ("// ok\n" * 5))
        bad = tmp_repo / "products" / "seed" / "node_modules" / "lib" / "dep.ts"
        bad.parent.mkdir(parents=True)
        bad.write_text("export const y = 2;\n")
        files = ce._iter_code_files(tmp_repo)
        assert ts in files
        assert bad not in files

    def test_only_tracked_extensions(self, tmp_repo):
        py = tmp_repo / "mcp" / "x.py"
        py.write_text("def x(): return 1 + 2 + 3\n")
        md = tmp_repo / "mcp" / "x.md"
        md.write_text("# not code\n")
        files = ce._iter_code_files(tmp_repo)
        assert py in files
        assert md not in files


# ── Refresh + search end-to-end ─────────────────────────────────────────────
class TestRefreshAndSearch:
    def test_empty_tree_in_sync(self, tmp_repo):
        # Roots exist but no files → in-sync, zero rows.
        result = ce.refresh(repo_root=tmp_repo)
        assert result["ok"] is True
        assert result["status"] == "in-sync"
        assert result["rows_written"] == 0

    def test_refresh_writes_rows(self, tmp_repo, fake_embed):
        (tmp_repo / "mcp" / "alpha.py").write_text(
            "def compute_window():\n"
            "    'docstring padding to clear the min-chunk size threshold'\n"
            "    return [1, 2, 3] * 20\n"
        )
        result = ce.refresh(repo_root=tmp_repo)
        assert result["ok"] is True
        assert result["rows_written"] >= 1
        assert "mcp/alpha.py" in result["refreshed"]
        assert ce.list_files() == ["mcp/alpha.py"]

    def test_per_file_sha_skips_in_sync(self, tmp_repo, fake_embed):
        (tmp_repo / "mcp" / "stable.py").write_text(
            "def stable():\n"
            "    'docstring padding to clear the min-chunk size threshold'\n"
            "    return 'never changes' * 5\n"
        )
        ce.refresh(repo_root=tmp_repo)
        # Second refresh — file unchanged, must be skipped.
        result = ce.refresh(repo_root=tmp_repo)
        assert "mcp/stable.py" in result["skipped"]
        assert result["rows_written"] == 0

    def test_force_rebuilds_anyway(self, tmp_repo, fake_embed):
        (tmp_repo / "mcp" / "f.py").write_text(
            "def f():\n"
            "    'docstring padding to clear the min-chunk size threshold'\n"
            "    return 'x' * 100\n"
        )
        ce.refresh(repo_root=tmp_repo)
        result = ce.refresh(repo_root=tmp_repo, force=True)
        assert result["status"] != "in-sync"
        assert result["rows_written"] >= 1

    def test_provider_failure_logs_error_and_continues(self, tmp_repo, monkeypatch):
        (tmp_repo / "mcp" / "broken.py").write_text(
            "def broken():\n"
            "    'docstring padding to clear the min-chunk size threshold'\n"
            "    return 'will fail' * 20\n"
        )

        def _boom(text: str) -> list[float]:
            raise RuntimeError("provider unreachable")

        monkeypatch.setattr(ce, "_embed_sync", _boom)
        result = ce.refresh(repo_root=tmp_repo)
        assert result["ok"] is False
        assert any("provider unreachable" in e["error"] for e in result["errors"])
        # No partial rows persisted (per-file all-or-nothing rollback).
        assert ce.list_files() == []

    def test_get_source_sha_returns_pair(self, tmp_repo, fake_embed):
        src = tmp_repo / "mcp" / "tracked.py"
        src.write_text(
            "def tracked():\n"
            "    'docstring padding to clear the min-chunk size threshold'\n"
            "    return 'value' * 30\n"
        )
        ce.refresh(repo_root=tmp_repo)
        live, cached = ce.get_source_sha("mcp/tracked.py", repo_root=tmp_repo)
        assert live == cached
        # Mutate and the pair diverges (refresh-needed signal).
        src.write_text(
            "def tracked():\n"
            "    'docstring padding to clear the min-chunk size threshold'\n"
            "    return 'CHANGED' * 30\n"
        )
        live2, cached2 = ce.get_source_sha("mcp/tracked.py", repo_root=tmp_repo)
        assert live2 != cached2  # cached_sha is the OLD one

    def test_search_returns_hits(self, tmp_repo, fake_embed):
        (tmp_repo / "mcp" / "phone.py").write_text(
            "def normalize_phone():\n    return '+5511' + '999999999'\n"
        )
        ce.refresh(repo_root=tmp_repo)
        hits = ce.search("normalize phone", top_k=5)
        assert len(hits) >= 1
        h = hits[0]
        assert h["path"] == "mcp/phone.py"
        assert h["symbol_name"] == "normalize_phone"
        assert h["kind"] == "function"

    def test_search_empty_cache_returns_empty(self, tmp_repo):
        # No refresh → no cache file.
        assert ce.search("anything", top_k=5) == []

    def test_kind_filter(self, tmp_repo, fake_embed):
        (tmp_repo / "mcp" / "mixed.py").write_text(
            "def my_func():\n    return 1 + 1 + 1 + 1 + 1\n\n"
            "class MyClass:\n    def m(self):\n        return self.x + 1\n"
        )
        ce.refresh(repo_root=tmp_repo)
        # Force min_score=0 to keep both engines comparable.
        functions = ce.search("anything", top_k=10, kind="function")
        classes = ce.search("anything", top_k=10, kind="class")
        for h in functions:
            assert h["kind"] == "function"
        for h in classes:
            assert h["kind"] == "class"


# ── code_neighbors ──────────────────────────────────────────────────────────
class TestCodeNeighbors:
    def test_returns_other_symbols_only(self, tmp_repo, fake_embed):
        (tmp_repo / "mcp" / "a.py").write_text(
            "def anchor():\n    return 'a' * 100\n\n"
            "def sibling():\n    return 'b' * 100\n"
        )
        ce.refresh(repo_root=tmp_repo)
        neighbors = ce.code_neighbors("mcp/a.py", "anchor", top_k=5)
        # The anchor itself is excluded.
        assert all(n["symbol_name"] != "anchor" for n in neighbors)

    def test_missing_anchor_returns_empty(self, tmp_repo, fake_embed):
        (tmp_repo / "mcp" / "x.py").write_text(
            "def real():\n    return 1 + 2 + 3 + 4 + 5\n"
        )
        ce.refresh(repo_root=tmp_repo)
        assert ce.code_neighbors("mcp/x.py", "does_not_exist") == []


# ── Cost instrumentation hook ───────────────────────────────────────────────
class TestCostInstrumentation:
    def test_log_refresh_batch_called_when_rows_written(self, tmp_repo, fake_embed):
        (tmp_repo / "mcp" / "cost.py").write_text(
            "def cost_test():\n"
            "    'docstring padding to clear the min-chunk size threshold'\n"
            "    return 'data' * 30\n"
        )
        with patch("tools.noctus.dev.vector_costs.log_refresh_batch") as mock_log:
            ce.refresh(repo_root=tmp_repo)
            assert mock_log.called
            kwargs = mock_log.call_args.kwargs
            assert kwargs["namespace"] == "code-embeddings"
            assert kwargs["chunk_count"] >= 1

    def test_no_log_when_no_rows_written(self, tmp_repo):
        # Empty tree (no .py/.ts under roots) → no embed calls, no log.
        with patch("tools.noctus.dev.vector_costs.log_refresh_batch") as mock_log:
            ce.refresh(repo_root=tmp_repo)
            assert not mock_log.called
