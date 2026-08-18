"""Batching tests for `_embedding_corpus.py` — the shared root fix for the
2026-08 pre-push retry-storm.

Root cause: every embed-corpus refresh loop (code / kb / memory / corpus)
called `embed_sync()` ONCE PER CHUNK — 508 chunks meant 508 independent
OpenAI `/embeddings` HTTP requests, each paced+retried on its own, which
self-inflicted 429s despite the account and provider being healthy the whole
time (`models.list()` succeeded; a single direct embed call always returned
immediately). The `/embeddings` endpoint accepts an array `input`, so this
adds `embed_batch_sync()` + `iter_batches()` as the shared batching
primitives and proves:

  1. `iter_batches` slices correctly (env-tunable, override-able per call).
  2. `embed_batch_sync` funnels through the batch-capable
     `noctusai_lib.integrations.llm.generate_embeddings_batch` in ONE call
     for N texts, throttles ONCE per call (not per text), and no-ops on an
     empty list (never calls the provider at all).
  3. `refresh_markdown_corpus` (the kb/memory/corpus refresher) collapses a
     many-chunk document into few provider calls, preserves the per-file
     `source_sha` idempotency no-op, and rolls back a whole doc's rows on a
     mid-doc batch failure — same contract the per-chunk loop had, just at
     batch granularity.

KB § PATTERNS/common/vectorize-embed-cache-framework.md
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import _embedding_corpus as ec  # noqa: E402


# ── iter_batches ─────────────────────────────────────────────────────────────
class TestIterBatches:
    def test_slices_into_fixed_size_batches(self):
        batches = list(ec.iter_batches(list(range(10)), batch_size=3))
        assert batches == [[0, 1, 2], [3, 4, 5], [6, 7, 8], [9]]

    def test_empty_input_yields_no_batches(self):
        assert list(ec.iter_batches([], batch_size=5)) == []

    def test_exact_multiple_has_no_short_last_batch(self):
        batches = list(ec.iter_batches(list(range(9)), batch_size=3))
        assert [len(b) for b in batches] == [3, 3, 3]

    def test_batch_size_larger_than_input_yields_one_batch(self):
        batches = list(ec.iter_batches([1, 2], batch_size=100))
        assert batches == [[1, 2]]

    def test_default_batch_size_env_tunable(self, monkeypatch):
        monkeypatch.setenv("NOCTUS_EMBED_BATCH_SIZE", "4")
        batches = list(ec.iter_batches(list(range(10))))  # no explicit batch_size
        assert [len(b) for b in batches] == [4, 4, 2]

    def test_invalid_env_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv("NOCTUS_EMBED_BATCH_SIZE", "not-a-number")
        assert ec._embed_batch_size() == ec._DEFAULT_EMBED_BATCH_SIZE

    def test_unset_env_uses_default(self, monkeypatch):
        monkeypatch.delenv("NOCTUS_EMBED_BATCH_SIZE", raising=False)
        assert ec._embed_batch_size() == ec._DEFAULT_EMBED_BATCH_SIZE

    def test_explicit_batch_size_overrides_env(self, monkeypatch):
        monkeypatch.setenv("NOCTUS_EMBED_BATCH_SIZE", "50")
        batches = list(ec.iter_batches(list(range(6)), batch_size=2))
        assert [len(b) for b in batches] == [2, 2, 2]


# ── embed_batch_sync ─────────────────────────────────────────────────────────
class TestEmbedBatchSync:
    def test_empty_list_short_circuits_without_provider_call(self, monkeypatch):
        called = {"n": 0}

        async def _boom(texts):
            called["n"] += 1
            raise AssertionError("must not be called for an empty batch")

        monkeypatch.setattr(
            "noctusai_lib.integrations.llm.generate_embeddings_batch", _boom
        )
        result = ec.embed_batch_sync([])
        assert result == []
        assert called["n"] == 0

    def test_one_call_embeds_all_texts(self, monkeypatch):
        """The defining property: N texts -> ONE provider call, not N."""
        calls = []

        async def _fake_batch(texts, **kwargs):
            calls.append(list(texts))
            return [[float(len(t))] * ec.EMBEDDING_DIM for t in texts]

        monkeypatch.setattr(
            "noctusai_lib.integrations.llm.generate_embeddings_batch", _fake_batch
        )
        monkeypatch.setattr(ec, "ensure_llm_configured", lambda: None)
        texts = ["alpha", "beta", "gamma delta"]
        result = ec.embed_batch_sync(texts)
        assert len(calls) == 1  # exactly one provider round-trip
        assert calls[0] == texts
        assert len(result) == 3
        assert all(len(v) == ec.EMBEDDING_DIM for v in result)

    def test_throttles_once_per_call_not_per_text(self, monkeypatch):
        """Pacing gates the HTTP ROUND-TRIP, not the chunk — a 50-text batch
        must consume exactly ONE throttle slot, same as a 1-text batch."""
        throttle_calls = {"n": 0}

        def _count_throttle():
            throttle_calls["n"] += 1

        async def _fake_batch(texts, **kwargs):
            return [[0.0] * ec.EMBEDDING_DIM for _ in texts]

        monkeypatch.setattr(ec, "_throttle_embed", _count_throttle)
        monkeypatch.setattr(ec, "ensure_llm_configured", lambda: None)
        monkeypatch.setattr(
            "noctusai_lib.integrations.llm.generate_embeddings_batch", _fake_batch
        )
        ec.embed_batch_sync([f"text-{i}" for i in range(50)])
        assert throttle_calls["n"] == 1

    def test_provider_error_propagates(self, monkeypatch):
        async def _boom(texts, **kwargs):
            raise RuntimeError("rate limited")

        monkeypatch.setattr(ec, "ensure_llm_configured", lambda: None)
        monkeypatch.setattr(
            "noctusai_lib.integrations.llm.generate_embeddings_batch", _boom
        )
        with pytest.raises(RuntimeError, match="rate limited"):
            ec.embed_batch_sync(["x"])


# ── refresh_markdown_corpus batching (kb / memory / corpus refresher) ───────
def _markdown_with_n_sections(n: int) -> str:
    """A doc with `n` H2 sections, each comfortably inside
    [MIN_CHUNK_CHARS, MAX_CHUNK_CHARS] so `chunk_markdown` emits exactly one
    chunk per section — the lever for controlling chunk COUNT."""
    body_line = "padding text to clear the minimum chunk size threshold. " * 4
    sections = [f"## Section {i}\n\n{body_line}\n" for i in range(n)]
    return "# Title\n\n" + "\n".join(sections)


class TestRefreshMarkdownCorpusBatching:
    def _make_corpus(self, tmp_path, docs: dict[str, str]) -> ec.MarkdownCorpus:
        src_dir = tmp_path / "src"
        src_dir.mkdir(exist_ok=True)
        for rel, text in docs.items():
            p = src_dir / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text)

        def _enumerate():
            for rel in docs:
                yield rel, src_dir / rel, {}

        return ec.MarkdownCorpus(
            cache_path=tmp_path / "cache.sqlite",
            chunks_table="t_chunks",
            vec_table="t_vec",
            json_table="t_json",
            enumerate_sources=_enumerate,
        )

    def _patch_batch(self, monkeypatch, calls: list):
        def _fake(texts: list[str]) -> list[list[float]]:
            calls.append(len(texts))
            return [[float(i)] * ec.EMBEDDING_DIM for i, _ in enumerate(texts)]

        monkeypatch.setattr(ec, "embed_batch_sync", _fake)
        monkeypatch.setattr(ec, "HAS_VEC", False)  # exercise the JSON-fallback path (no sqlite-vec dep)
        return _fake

    def test_many_chunks_collapse_into_few_calls(self, tmp_path, monkeypatch):
        calls: list[int] = []
        self._patch_batch(monkeypatch, calls)
        monkeypatch.setenv("NOCTUS_EMBED_BATCH_SIZE", "10")

        n_chunks = 33
        corpus = self._make_corpus(tmp_path, {"doc.md": _markdown_with_n_sections(n_chunks)})
        result = ec.refresh_markdown_corpus(corpus)

        assert result["ok"] is True
        assert result["rows_written"] == n_chunks
        import math
        assert len(calls) == math.ceil(n_chunks / 10)
        assert len(calls) < n_chunks
        assert sum(calls) == n_chunks

    def test_unchanged_doc_makes_zero_embed_calls(self, tmp_path, monkeypatch):
        calls: list[int] = []
        self._patch_batch(monkeypatch, calls)

        corpus = self._make_corpus(tmp_path, {"doc.md": _markdown_with_n_sections(5)})
        ec.refresh_markdown_corpus(corpus)
        assert len(calls) > 0

        calls.clear()
        result = ec.refresh_markdown_corpus(corpus)  # unchanged source_sha
        assert result["rows_written"] == 0
        assert "doc.md" in result["skipped"]
        assert calls == []  # true no-op — idempotency contract intact

    def test_batch_failure_rolls_back_whole_doc(self, tmp_path, monkeypatch):
        monkeypatch.setenv("NOCTUS_EMBED_BATCH_SIZE", "3")
        call_n = {"n": 0}

        def _flaky(texts: list[str]) -> list[list[float]]:
            call_n["n"] += 1
            if call_n["n"] == 2:  # first batch of 3 succeeds, second fails
                raise RuntimeError("simulated rate-limit exhaustion")
            return [[0.1] * ec.EMBEDDING_DIM for _ in texts]

        monkeypatch.setattr(ec, "embed_batch_sync", _flaky)
        monkeypatch.setattr(ec, "HAS_VEC", False)

        corpus = self._make_corpus(tmp_path, {"flaky.md": _markdown_with_n_sections(8)})
        result = ec.refresh_markdown_corpus(corpus)
        assert result["ok"] is False
        # Nothing persisted for the doc — including the first successful
        # batch's 3 rows, which must be rolled back too.
        conn = sqlite3.connect(str(corpus.cache_path))
        n_rows = conn.execute(f"SELECT count(*) FROM {corpus.chunks_table}").fetchone()[0]
        conn.close()
        assert n_rows == 0
