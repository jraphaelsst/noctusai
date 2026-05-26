"""Regression tests for `check_kb_vector_canonical` — enforces the
markdown-canonical / vector-DB-is-enrichment principle.

KB § PATTERNS/common/kb-vector-search.md. Phase B follow-up (2026-05-26).
"""
import hashlib
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.compliance import check_kb_vector_canonical  # noqa: E402


def _setup(tmp_path: Path) -> tuple[Path, Path]:
    """Returns (kb_dir, cache_path) for a fresh harness."""
    kb_dir = tmp_path / "KNOWLEDGE-BASE"
    kb_dir.mkdir(parents=True)
    cache_dir = tmp_path / ".claude" / "cache"
    cache_dir.mkdir(parents=True)
    cache_path = cache_dir / "kb-embeddings.sqlite"
    return kb_dir, cache_path


def _make_cache(cache_path: Path, rows: list[tuple[str, str]]) -> None:
    """Build a minimal cache with kb_chunks rows (path, source_sha)."""
    conn = sqlite3.connect(str(cache_path))
    conn.execute(
        "CREATE TABLE kb_chunks (path TEXT, chunk_idx INTEGER, chunk_text TEXT, source_sha TEXT, cached_at TEXT)"
    )
    for path, sha in rows:
        conn.execute(
            "INSERT INTO kb_chunks(path, chunk_idx, chunk_text, source_sha, cached_at) VALUES (?, 0, 'x', ?, '')",
            (path, sha),
        )
    conn.commit()
    conn.close()


class TestCheckKbVectorCanonical:
    def test_silent_skip_no_kb_dir(self, tmp_path):
        # No KNOWLEDGE-BASE dir → silent skip (test/vendored context).
        assert check_kb_vector_canonical(repo_root=tmp_path) == []

    def test_silent_skip_no_cache(self, tmp_path):
        # KB exists but cache absent → silent skip (fresh clone, no embeds yet).
        (tmp_path / "KNOWLEDGE-BASE").mkdir()
        assert check_kb_vector_canonical(repo_root=tmp_path) == []

    def test_clean_state_no_issues(self, tmp_path):
        kb, cache = _setup(tmp_path)
        # Author a real markdown file.
        md = kb / "CONTEXT" / "PATTERNS" / "common" / "foo.md"
        md.parent.mkdir(parents=True)
        md.write_text("# foo\n", encoding="utf-8")
        sha = hashlib.sha256(md.read_bytes()).hexdigest()
        _make_cache(cache, [("CONTEXT/PATTERNS/common/foo.md", sha)])
        assert check_kb_vector_canonical(repo_root=tmp_path) == []

    def test_orphan_row_flagged(self, tmp_path):
        # Cache row for a doc that doesn't exist on disk → orphan.
        kb, cache = _setup(tmp_path)
        _make_cache(cache, [("CONTEXT/PATTERNS/common/orphan.md", "abc")])
        issues = check_kb_vector_canonical(repo_root=tmp_path)
        assert any(i["symbol"] == "kb-vector-orphan" for i in issues)
        # Severity is warning (advisory layer).
        assert all(i["severity"] == "warning" for i in issues)

    def test_stale_sha_flagged(self, tmp_path):
        kb, cache = _setup(tmp_path)
        md = kb / "CONTEXT" / "PATTERNS" / "common" / "bar.md"
        md.parent.mkdir(parents=True)
        md.write_text("# bar v1\n", encoding="utf-8")
        # Cache the doc with a WRONG sha (simulating stale).
        _make_cache(cache, [("CONTEXT/PATTERNS/common/bar.md", "wrong-sha")])
        issues = check_kb_vector_canonical(repo_root=tmp_path)
        assert any(i["symbol"] == "kb-vector-stale" for i in issues)

    def test_severity_is_warning_not_high(self, tmp_path):
        # The principle: vector layer is advisory, never blocking.
        kb, cache = _setup(tmp_path)
        _make_cache(cache, [("CONTEXT/PATTERNS/common/orphan.md", "abc")])
        issues = check_kb_vector_canonical(repo_root=tmp_path)
        assert issues  # has issues
        assert all(i["severity"] == "warning" for i in issues), \
            "Vector-canonical keeper is advisory — must NEVER be severity high"
