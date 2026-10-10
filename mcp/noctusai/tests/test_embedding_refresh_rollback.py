"""Every refresh failure path keeps a file's LAST GOOD rows (2026-10-09).

The loops delete a file's old rows before embedding its new ones. Only the
quota path rolled back; a provider error / bad batch / read error deleted the
partial NEW rows and left the file with NO rows — silent search data loss.
All paths now share `_embedding_corpus.restore_file_rows` (rollback to the
per-file checkpoint). Embedding is faked at the provider boundary, the same
seam the sibling batching/quota tests use.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import _embedding_corpus as ec  # noqa: E402
from tools.noctus.dev import code_embeddings as ce  # noqa: E402
from tools.noctus.dev import kb_embeddings as kbe  # noqa: E402


def _ok(texts):
    return [[0.1] * ec.EMBEDDING_DIM for _ in texts]


def _fail_on(n_fail: int):
    calls = {"n": 0}

    def _embed(texts):
        calls["n"] += 1
        if calls["n"] == n_fail:
            raise RuntimeError("simulated provider 500")
        return [[0.2] * ec.EMBEDDING_DIM for _ in texts]

    return _embed


def _rows(path: Path, table: str) -> list[tuple]:
    conn = sqlite3.connect(str(path))
    try:
        return conn.execute(
            f"SELECT path, chunk_idx, source_sha FROM {table} ORDER BY 1, 2").fetchall()
    finally:
        conn.close()


# ── shared markdown corpus (memory + corpus refreshers) ─────────────────────
def _doc(n: int) -> str:
    return "# T\n\n" + "".join(f"## S{i}\n\n" + ("palavra " * 60) + "\n\n" for i in range(n))


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    monkeypatch.setattr(ec, "HAS_VEC", False)
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.md").write_text(_doc(3))
    (src / "b.md").write_text(_doc(3))
    c = ec.MarkdownCorpus(
        cache_path=tmp_path / "c.sqlite",
        chunks_table="t_chunks", vec_table="t_vec", json_table="t_json",
        enumerate_sources=lambda: ((r, src / r, {}) for r in ("a.md", "b.md")),
    )
    monkeypatch.setattr(ec, "embed_batch_sync", _ok)
    ec.refresh_markdown_corpus(c)
    return c, src


def test_corpus_first_batch_failure_keeps_old_rows(corpus, monkeypatch):
    c, src = corpus
    before = _rows(c.cache_path, c.chunks_table)
    (src / "a.md").write_text(_doc(5))
    monkeypatch.setattr(ec, "embed_batch_sync", _fail_on(1))  # a.md's FIRST batch

    result = ec.refresh_markdown_corpus(c)

    assert result["errors"] and "a.md" not in result["refreshed"]
    assert [r for r in _rows(c.cache_path, c.chunks_table) if r[0] == "a.md"] == \
        [r for r in before if r[0] == "a.md"]


def test_corpus_mid_batch_failure_keeps_old_rows(corpus, monkeypatch):
    c, src = corpus
    monkeypatch.setenv("NOCTUS_EMBED_BATCH_SIZE", "2")
    before = _rows(c.cache_path, c.chunks_table)
    (src / "a.md").write_text(_doc(6))
    monkeypatch.setattr(ec, "embed_batch_sync", _fail_on(2))  # after one batch landed

    ec.refresh_markdown_corpus(c)

    assert [r for r in _rows(c.cache_path, c.chunks_table) if r[0] == "a.md"] == \
        [r for r in before if r[0] == "a.md"]


def test_corpus_read_error_keeps_old_rows(corpus, monkeypatch):
    c, src = corpus
    before = _rows(c.cache_path, c.chunks_table)
    (src / "a.md").write_bytes(b"\xff\xfe not utf-8 \xc3\x28")

    result = ec.refresh_markdown_corpus(c)

    assert any("read" in e.get("error", "") for e in result["errors"])
    assert [r for r in _rows(c.cache_path, c.chunks_table) if r[0] == "a.md"] == \
        [r for r in before if r[0] == "a.md"]


# ── kb refresher ─────────────────────────────────────────────────────────────
def _kb_doc(n: int) -> str:
    body = "padding text to clear the minimum chunk size threshold. " * 4
    return "# Title\n\n" + "\n".join(f"## Section {i}\n\n{body}\n" for i in range(n))


def test_kb_mid_batch_failure_keeps_last_good_rows(tmp_path, monkeypatch):
    kb_dir = tmp_path / "KNOWLEDGE-BASE"
    kb_dir.mkdir()
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    monkeypatch.setattr(kbe, "KB_DIR", kb_dir)
    monkeypatch.setattr(kbe, "CACHE_DIR", cache_dir)
    monkeypatch.setattr(kbe, "CACHE_PATH", cache_dir / "kb-embeddings.sqlite")
    from tools.noctus.dev import vector_costs as _vc
    monkeypatch.setattr(_vc, "log_refresh_batch", lambda **kwargs: None)
    monkeypatch.setenv("NOCTUS_EMBED_BATCH_SIZE", "3")

    monkeypatch.setattr(kbe, "_embed_batch_sync", _ok)
    (kb_dir / "doc.md").write_text(_kb_doc(5))
    kbe.refresh()
    before = _rows(kbe.CACHE_PATH, "kb_chunks")
    assert before

    (kb_dir / "doc.md").write_text(_kb_doc(8))
    monkeypatch.setattr(kbe, "_embed_batch_sync", _fail_on(2))
    result = kbe.refresh()

    assert result["ok"] is False
    assert _rows(kbe.CACHE_PATH, "kb_chunks") == before


# ── code refresher ───────────────────────────────────────────────────────────
def _src(n: int) -> str:
    return "\n".join(
        f"def fn_{i}():\n    'docstring padding to clear the min-chunk size {i}'\n    return {i}\n"
        for i in range(n))


def test_code_mid_batch_failure_keeps_last_good_rows(tmp_path, monkeypatch):
    for r in ce._CODE_ROOTS:
        (tmp_path / r).mkdir(parents=True, exist_ok=True)
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    monkeypatch.setattr(ce, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(ce, "CACHE_DIR", cache_dir)
    monkeypatch.setattr(ce, "CACHE_PATH", cache_dir / "code-embeddings.sqlite")
    monkeypatch.setenv("NOCTUS_EMBED_BATCH_SIZE", "5")

    monkeypatch.setattr(ce, "_embed_batch_sync", _ok)
    (tmp_path / "mcp" / "mod.py").write_text(_src(6))
    ce.refresh(repo_root=tmp_path)
    before = _rows(ce.CACHE_PATH, "code_chunks")
    assert before

    (tmp_path / "mcp" / "mod.py").write_text(_src(12))
    monkeypatch.setattr(ce, "_embed_batch_sync", _fail_on(2))
    result = ce.refresh(repo_root=tmp_path)

    assert result["ok"] is False
    assert _rows(ce.CACHE_PATH, "code_chunks") == before
