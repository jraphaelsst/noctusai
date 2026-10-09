"""A provider quota error (OpenAI `insufficient_quota`) aborts a refresh on
the FIRST failure, reports `quota_exhausted`, and leaves existing rows alone.

Incident 2026-10-09: an account with no credits made `--refresh-memory-
embeddings` grind 271-346 s (119 identical errors) inside the git post-merge
hook. KB § PATTERNS/common/vectorize-embed-cache-framework.md
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from noctusai_lib.integrations.llm.exceptions import ProviderQuotaExhausted  # noqa: E402
from tools.noctus.dev import _embedding_corpus as ec  # noqa: E402


def _doc(n: int) -> str:
    return "# T\n\n" + "".join(f"## S{i}\n\n" + ("palavra " * 60) + "\n\n" for i in range(n))


def _corpus(tmp_path: Path, docs: dict[str, str]) -> ec.MarkdownCorpus:
    src = tmp_path / "src"
    src.mkdir(exist_ok=True)
    for rel, text in docs.items():
        (src / rel).write_text(text)
    return ec.MarkdownCorpus(
        cache_path=tmp_path / "c.sqlite",
        chunks_table="t_chunks", vec_table="t_vec", json_table="t_json",
        enumerate_sources=lambda: ((r, src / r, {}) for r in docs),
    )


def _rows(corpus: ec.MarkdownCorpus) -> list[tuple]:
    conn = sqlite3.connect(corpus.cache_path)
    try:
        return conn.execute(
            f"SELECT path, chunk_idx, source_sha FROM {corpus.chunks_table} ORDER BY 1,2"
        ).fetchall()
    finally:
        conn.close()


def test_quota_aborts_on_first_call_and_keeps_existing_rows(tmp_path, monkeypatch):
    monkeypatch.setattr(ec, "HAS_VEC", False)
    ok = lambda texts: [[0.1] * ec.EMBEDDING_DIM for _ in texts]  # noqa: E731
    monkeypatch.setattr(ec, "embed_batch_sync", ok)
    corpus = _corpus(tmp_path, {f"d{i}.md": _doc(3) for i in range(5)})
    ec.refresh_markdown_corpus(corpus)
    before = _rows(corpus)
    assert before

    # Every doc changes, then the provider runs out of credit.
    for i in range(5):
        (tmp_path / "src" / f"d{i}.md").write_text(_doc(4))
    calls = {"n": 0}

    def _quota(texts):
        calls["n"] += 1
        raise ProviderQuotaExhausted("openai", "insufficient_quota")

    monkeypatch.setattr(ec, "embed_batch_sync", _quota)
    result = ec.refresh_markdown_corpus(corpus)

    assert calls["n"] == 1  # stopped at the first quota error, not 5 docs
    assert result["status"] == "quota_exhausted"
    assert result["ok"] is False
    assert result["refreshed"] == []
    assert _rows(corpus) == before  # old rows untouched (delete rolled back)


def test_quota_mid_run_keeps_files_already_refreshed(tmp_path, monkeypatch):
    monkeypatch.setattr(ec, "HAS_VEC", False)
    monkeypatch.setattr(
        ec, "embed_batch_sync",
        lambda texts: [[0.1] * ec.EMBEDDING_DIM for _ in texts],
    )
    corpus = _corpus(tmp_path, {"a.md": _doc(2), "b.md": _doc(2)})
    ec.refresh_markdown_corpus(corpus)
    old_b = [r for r in _rows(corpus) if r[0] == "b.md"]
    (tmp_path / "src" / "a.md").write_text(_doc(3))
    (tmp_path / "src" / "b.md").write_text(_doc(3))
    n = {"n": 0}

    def _second_quota(texts):
        n["n"] += 1
        if n["n"] == 2:
            raise ProviderQuotaExhausted("openai", "insufficient_quota")
        return [[0.2] * ec.EMBEDDING_DIM for _ in texts]

    monkeypatch.setattr(ec, "embed_batch_sync", _second_quota)
    result = ec.refresh_markdown_corpus(corpus)

    assert result["status"] == "quota_exhausted"
    assert result["refreshed"] == ["a.md"]
    rows = _rows(corpus)
    assert len([r for r in rows if r[0] == "a.md"]) == 3  # refreshed, kept
    assert [r for r in rows if r[0] == "b.md"] == old_b  # untouched


def test_memory_refresh_does_not_stamp_source_sha_on_quota(tmp_path, monkeypatch):
    from tools.noctus.dev import memory_embeddings as me

    monkeypatch.setattr(me, "_resolve_memory_dir", lambda: tmp_path)
    monkeypatch.setattr(
        me._ec, "refresh_markdown_corpus",
        lambda *a, **k: {"ok": False, "status": "quota_exhausted", "errors": []},
    )
    stamped = []
    monkeypatch.setattr(me._ec, "connect_cache", lambda p: stamped.append(p))
    assert me.refresh()["status"] == "quota_exhausted"
    assert stamped == []
