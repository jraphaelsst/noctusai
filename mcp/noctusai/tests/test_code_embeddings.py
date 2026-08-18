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


def _deterministic_vector(text: str) -> list[float]:
    """Deterministic 'embedding': sha256 → 1536-D float vector."""
    import hashlib

    seed = int.from_bytes(hashlib.sha256(text.encode()).digest()[:4], "big")
    return [((seed * (i + 1)) % 1000) / 1000.0 - 0.5 for i in range(ce.EMBEDDING_DIM)]


@pytest.fixture
def fake_embed(monkeypatch):
    """Deterministic 'embedding' — patches BOTH the single-text (`_embed_sync`,
    used at query time by `search()`) and the batch (`_embed_batch_sync`, used
    by `refresh()`) funnels, so every call path in this test module is covered
    without callers needing to know which one a given code path uses.

    `_fake_batch` records call-count + per-call batch sizes on itself (`.calls`)
    so tests can assert the request-count win directly (batching collapses N
    chunks into `ceil(N/batch_size)` provider calls, not N).

    Also mocks `vector_costs.log_refresh_batch` so tests don't pollute the
    real durable ledger at `project-history/vector-costs.ndjson`.
    """
    def _fake_batch(texts: list[str]) -> list[list[float]]:
        _fake_batch.calls.append(len(texts))
        return [_deterministic_vector(t) for t in texts]

    _fake_batch.calls = []

    monkeypatch.setattr(ce, "_embed_sync", _deterministic_vector)
    monkeypatch.setattr(ce, "_embed_batch_sync", _fake_batch)
    # Isolate from the real vector-costs ledger.
    from tools.noctus.dev import vector_costs as _vc
    monkeypatch.setattr(_vc, "log_refresh_batch", lambda **kwargs: None)
    return _fake_batch


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

    def test_full_refresh_prunes_orphan_rows(self, tmp_repo, fake_embed):
        """A full pass drops rows for files no longer on disk (the orphan-prune
        that fixes the perpetual `code-vector-orphan` freshness warning)."""
        f = tmp_repo / "mcp" / "gone.py"
        f.write_text(
            "def gone():\n"
            "    'docstring padding to clear the min-chunk size threshold'\n"
            "    return 'bye' * 40\n"
        )
        ce.refresh(repo_root=tmp_repo)
        assert "mcp/gone.py" in ce.list_files()
        f.unlink()
        result = ce.refresh(repo_root=tmp_repo)
        assert "mcp/gone.py" in result.get("pruned", [])
        assert "mcp/gone.py" not in ce.list_files()

    def test_scoped_refresh_does_not_prune(self, tmp_repo, fake_embed):
        """A scoped (`paths=`) refresh must NOT prune out-of-scope rows."""
        (tmp_repo / "mcp" / "keep.py").write_text(
            "def keep():\n"
            "    'docstring padding to clear the min-chunk size threshold'\n"
            "    return 'stay' * 40\n"
        )
        ce.refresh(repo_root=tmp_repo)
        (tmp_repo / "mcp" / "other.py").write_text(
            "def other():\n"
            "    'docstring padding to clear the min-chunk size threshold'\n"
            "    return 'new' * 40\n"
        )
        result = ce.refresh(repo_root=tmp_repo, paths=["mcp/other.py"])
        assert result.get("pruned", []) == []
        assert "mcp/keep.py" in ce.list_files()

    def test_full_refresh_preserves_organ_rows(self, tmp_repo, fake_embed):
        """Organ rows (kind='organ', often OUTSIDE _CODE_ROOTS) must survive a
        full prune — they're managed by register_organ, not this refresh."""
        # First refresh creates the schema via the extension-loading connection.
        (tmp_repo / "mcp" / "real.py").write_text(
            "def real():\n"
            "    'docstring padding to clear the min-chunk size threshold'\n"
            "    return 'x' * 40\n"
        )
        ce.refresh(repo_root=tmp_repo)
        # Seed an organ row whose path is outside _CODE_ROOTS and not on disk.
        conn = ce._connect()
        conn.execute(
            "INSERT INTO code_chunks(path,chunk_idx,symbol_name,kind,chunk_text,source_sha,cached_at) "
            "VALUES (?,?,?,?,?,?,?)",
            ("seed/lib/frontend/src/design-system/components/Sidebar.tsx", 0,
             "Sidebar", "organ", "organ bundle text", "bundlesha", "2026-05-29"),
        )
        conn.commit()
        conn.close()
        result = ce.refresh(repo_root=tmp_repo, force=True)
        # The organ row's path doesn't exist on disk, but it must NOT be pruned.
        assert "seed/lib/frontend/src/design-system/components/Sidebar.tsx" not in result.get("pruned", [])
        conn = ce._connect()
        n = conn.execute("SELECT count(*) FROM code_chunks WHERE kind='organ'").fetchone()[0]
        conn.close()
        assert n == 1

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

        def _boom(texts: list[str]) -> list[list[float]]:
            raise RuntimeError("provider unreachable")

        monkeypatch.setattr(ce, "_embed_batch_sync", _boom)
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


# ── Embed batching — the 2026-08 retry-storm fix ────────────────────────────
def _many_functions_source(n: int) -> str:
    """A single Python source with `n` distinct top-level functions — each
    one is its own chunk under `_chunk_python`, so this is the lever for
    controlling chunk COUNT independent of file count."""
    parts = []
    for i in range(n):
        parts.append(
            f"def fn_{i}():\n"
            f"    'docstring padding to clear the min-chunk size threshold for func {i}'\n"
            f"    return {i} * 2 + 1\n"
        )
    return "\n".join(parts)


class TestEmbedBatching:
    """Proves the root fix: a refresh with MANY chunks makes FEW provider
    calls (batched), not one call per chunk — and that batching never
    breaks the per-file source_sha idempotency contract."""

    def test_many_chunks_collapse_into_few_provider_calls(self, tmp_repo, fake_embed, monkeypatch):
        # Deterministic batch size for the assertion (independent of the
        # env-tunable default).
        from tools.noctus.dev import _embedding_corpus as _ec
        monkeypatch.setenv("NOCTUS_EMBED_BATCH_SIZE", "20")

        n_chunks = 137  # deliberately not a multiple of the batch size
        (tmp_repo / "mcp" / "many.py").write_text(_many_functions_source(n_chunks))

        result = ce.refresh(repo_root=tmp_repo)
        assert result["ok"] is True
        assert result["rows_written"] == n_chunks

        # BEFORE this fix: n_chunks embed calls (one per chunk, each its own
        # HTTP round-trip). AFTER: ceil(n_chunks / batch_size) calls.
        import math
        expected_calls = math.ceil(n_chunks / 20)
        assert len(fake_embed.calls) == expected_calls
        assert expected_calls < n_chunks  # the actual win, asserted directly
        # Every call except (maybe) the last is a full batch; texts are never
        # dropped or duplicated across batches.
        assert sum(fake_embed.calls) == n_chunks

    def test_unchanged_file_makes_zero_embed_calls(self, tmp_repo, fake_embed):
        """Idempotency contract intact: a file whose content (source_sha) is
        unchanged must not re-embed ANY of its chunks — batching must not
        weaken the per-file skip-if-unchanged guard."""
        (tmp_repo / "mcp" / "stable.py").write_text(_many_functions_source(30))
        ce.refresh(repo_root=tmp_repo)
        assert len(fake_embed.calls) > 0  # first pass did embed

        fake_embed.calls.clear()
        result = ce.refresh(repo_root=tmp_repo)  # nothing changed
        assert result["rows_written"] == 0
        assert "mcp/stable.py" in result["skipped"]
        assert fake_embed.calls == []  # zero provider calls — true no-op

    def test_batch_failure_rolls_back_whole_file(self, tmp_repo, monkeypatch):
        """A batch that fails mid-file rolls back EVERY row for that file
        (including chunks embedded by an earlier successful batch in the
        same file) — the per-file all-or-nothing contract survives batching
        even though failure is now detected at batch, not chunk, granularity."""
        monkeypatch.setenv("NOCTUS_EMBED_BATCH_SIZE", "5")
        (tmp_repo / "mcp" / "flaky.py").write_text(_many_functions_source(12))

        call_n = {"n": 0}

        def _flaky_batch(texts: list[str]) -> list[list[float]]:
            call_n["n"] += 1
            if call_n["n"] == 2:  # first batch (5 chunks) succeeds, second fails
                raise RuntimeError("simulated 429 exhaustion")
            return [_deterministic_vector(t) for t in texts]

        monkeypatch.setattr(ce, "_embed_batch_sync", _flaky_batch)
        result = ce.refresh(repo_root=tmp_repo)
        assert result["ok"] is False
        # Nothing persisted for the file — including the first batch's 5
        # rows, which must be rolled back too.
        assert ce.list_files() == []

    def test_cost_logging_sums_tokens_across_batches_not_per_batch(self, tmp_repo, monkeypatch):
        """The vector-costs ledger row must reflect the WHOLE refresh's real
        chunk/token totals summed across every batch call — not one row
        mis-attributed to a single batch, and not `chunk_count` conflated
        with the number of provider CALLS."""
        monkeypatch.setenv("NOCTUS_EMBED_BATCH_SIZE", "10")
        n_chunks = 25  # -> 3 batch calls (10, 10, 5) at batch size 10
        (tmp_repo / "mcp" / "costly.py").write_text(_many_functions_source(n_chunks))

        # Simulate the REAL usage-capture path: each batch call reports the
        # provider's total_tokens for JUST that batch via the usage sink.
        from tools.noctus.dev import _embedding_corpus as _ec

        class _FakeUsageEvent:
            def __init__(self, total_tokens):
                self.total_tokens = total_tokens
                self.prompt_tokens = total_tokens
                self.cost_estimate_usd = total_tokens * 0.00001

        class _FakeConfig:
            usage_sink = None

        fake_config = _FakeConfig()
        monkeypatch.setattr(
            "noctusai_lib.integrations.llm.client.get_llm_config",
            lambda: fake_config,
        )

        def _batch_with_usage(texts: list[str]) -> list[list[float]]:
            import asyncio
            tokens_this_batch = len(texts) * 100  # deterministic per-call usage
            if fake_config.usage_sink is not None:
                asyncio.run(fake_config.usage_sink.record(_FakeUsageEvent(tokens_this_batch)))
            return [_deterministic_vector(t) for t in texts]

        monkeypatch.setattr(ce, "_embed_batch_sync", _batch_with_usage)

        with patch("tools.noctus.dev.vector_costs.log_refresh_batch") as mock_log:
            result = ce.refresh(repo_root=tmp_repo)
        assert result["ok"] is True
        assert result["rows_written"] == n_chunks
        kwargs = mock_log.call_args.kwargs
        assert kwargs["chunk_count"] == n_chunks  # rows, not provider-call count
        # 25 chunks * 100 tokens/chunk, summed across all 3 batch calls.
        assert kwargs["actual_tokens"] == n_chunks * 100


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
