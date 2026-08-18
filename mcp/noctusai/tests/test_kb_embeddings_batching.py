"""Batching tests for `kb_embeddings.refresh()` — the third instance of the
2026-08 retry-storm shape.

`kb_embeddings.py` carries its OWN per-chunk embed loop (independent of the
shared `refresh_markdown_corpus` helper corpus/memory-embeddings delegate
to) — same bug shape as `code_embeddings.py` before its fix: one
`embed_sync()` call PER CHUNK, one HTTP round-trip per chunk. kb-embeddings
is one of the four OpenAI-backed refreshes the pre-push hook runs on every
`dev`/`main`/`prod` delivery (`--refresh-kb-embeddings`, gated on `*.md`
changes), so a large KB diff was exactly as exposed to the retry-storm as
the code-embeddings refresh that surfaced the incident. Fixed the same way:
batch via `_embedding_corpus.embed_batch_sync` + `iter_batches`.

KB § PATTERNS/common/vectorize-embed-cache-framework.md
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import kb_embeddings as kbe  # noqa: E402


@pytest.fixture
def tmp_kb(tmp_path, monkeypatch):
    """A fake KNOWLEDGE-BASE/ tree + an isolated cache."""
    kb_dir = tmp_path / "KNOWLEDGE-BASE"
    kb_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = tmp_path / ".claude" / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(kbe, "KB_DIR", kb_dir)
    monkeypatch.setattr(kbe, "CACHE_DIR", cache_dir)
    monkeypatch.setattr(kbe, "CACHE_PATH", cache_dir / "kb-embeddings.sqlite")
    return kb_dir


@pytest.fixture
def fake_batch_embed(monkeypatch):
    """Deterministic batch embed — records call count + per-call sizes.
    Also patches the single-text funnel (`_embed_sync`, used at QUERY time
    by `search()`) with the same deterministic shape so a post-refresh
    search in the same test doesn't need a second fixture."""
    def _fake(texts: list[str]) -> list[list[float]]:
        _fake.calls.append(len(texts))
        return [[float(i)] * kbe.EMBEDDING_DIM for i, _ in enumerate(texts)]

    _fake.calls = []
    monkeypatch.setattr(kbe, "_embed_batch_sync", _fake)
    monkeypatch.setattr(kbe, "_embed_sync", lambda text: [1.0] * kbe.EMBEDDING_DIM)
    from tools.noctus.dev import vector_costs as _vc
    monkeypatch.setattr(_vc, "log_refresh_batch", lambda **kwargs: None)
    return _fake


def _doc_with_n_sections(n: int) -> str:
    body = "padding text to clear the minimum chunk size threshold. " * 4
    sections = [f"## Section {i}\n\n{body}\n" for i in range(n)]
    return "# Title\n\n" + "\n".join(sections)


class TestKbEmbeddingsBatching:
    def test_many_chunks_collapse_into_few_provider_calls(
        self, tmp_kb, fake_batch_embed, monkeypatch
    ):
        monkeypatch.setenv("NOCTUS_EMBED_BATCH_SIZE", "10")
        n_chunks = 27
        (tmp_kb / "big.md").write_text(_doc_with_n_sections(n_chunks))

        result = kbe.refresh()
        assert result["ok"] is True
        assert result["rows_written"] == n_chunks

        import math
        expected_calls = math.ceil(n_chunks / 10)
        assert len(fake_batch_embed.calls) == expected_calls
        assert expected_calls < n_chunks
        assert sum(fake_batch_embed.calls) == n_chunks

    def test_unchanged_doc_makes_zero_embed_calls(self, tmp_kb, fake_batch_embed):
        (tmp_kb / "stable.md").write_text(_doc_with_n_sections(6))
        kbe.refresh()
        assert len(fake_batch_embed.calls) > 0

        fake_batch_embed.calls.clear()
        result = kbe.refresh()  # unchanged
        assert result["rows_written"] == 0
        assert "stable.md" in result["skipped"]
        assert fake_batch_embed.calls == []

    def test_batch_failure_rolls_back_whole_doc(self, tmp_kb, monkeypatch):
        monkeypatch.setenv("NOCTUS_EMBED_BATCH_SIZE", "3")
        call_n = {"n": 0}

        def _flaky(texts: list[str]) -> list[list[float]]:
            call_n["n"] += 1
            if call_n["n"] == 2:
                raise RuntimeError("simulated rate-limit exhaustion")
            return [[0.1] * kbe.EMBEDDING_DIM for _ in texts]

        monkeypatch.setattr(kbe, "_embed_batch_sync", _flaky)
        from tools.noctus.dev import vector_costs as _vc
        monkeypatch.setattr(_vc, "log_refresh_batch", lambda **kwargs: None)

        (tmp_kb / "flaky.md").write_text(_doc_with_n_sections(8))
        result = kbe.refresh()
        assert result["ok"] is False
        assert kbe.CACHE_PATH.exists()

        import sqlite3
        conn = sqlite3.connect(str(kbe.CACHE_PATH))
        n_rows = conn.execute("SELECT count(*) FROM kb_chunks").fetchone()[0]
        conn.close()
        assert n_rows == 0

    def test_search_still_works_after_batched_refresh(self, tmp_kb, fake_batch_embed):
        body = "padding text to clear the minimum chunk size threshold entirely. " * 3
        (tmp_kb / "topic.md").write_text(f"# Phone Normalization\n\n## Section\n\n{body}\n")
        kbe.refresh()
        hits = kbe.search("phone normalization", top_k=5)
        assert len(hits) >= 1
