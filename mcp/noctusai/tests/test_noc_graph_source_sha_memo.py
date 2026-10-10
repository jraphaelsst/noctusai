"""compute_source_sha stat-signature memo (2026-10-10): an unchanged tree is
answered from the memo without reading file contents, the answer is identical
to the uncached computation, and any input change (even same-size) busts it."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import noc_graph_cache as ngc  # noqa: E402


def _repo(tmp_path: Path) -> Path:
    (tmp_path / "mcp").mkdir()
    (tmp_path / "mcp" / "a.py").write_text("A = 1\n")
    (tmp_path / "KNOWLEDGE-BASE").mkdir()
    (tmp_path / "KNOWLEDGE-BASE" / "x.md").write_text("# x\n")
    return tmp_path


def _uncached(repo: Path) -> str:
    ngc._source_sha_memo_path(repo).unlink(missing_ok=True)
    return ngc.compute_source_sha(repo)


def test_memo_hit_returns_identical_sha_without_reading_contents(tmp_path):
    repo = _repo(tmp_path)
    cold = _uncached(repo)
    assert ngc._source_sha_memo_path(repo).exists()
    with patch.object(Path, "read_bytes", side_effect=AssertionError("memo hit must not read")):
        assert ngc.compute_source_sha(repo) == cold


def test_same_size_edit_busts_memo(tmp_path):
    repo = _repo(tmp_path)
    before = _uncached(repo)
    f = repo / "mcp" / "a.py"
    st = f.stat()
    f.write_text("A = 2\n")  # same size
    os.utime(f, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000))
    after = ngc.compute_source_sha(repo)
    assert after != before
    assert after == _uncached(repo)


def test_new_file_busts_memo(tmp_path):
    repo = _repo(tmp_path)
    before = _uncached(repo)
    (repo / "mcp" / "b.py").write_text("B = 1\n")
    assert ngc.compute_source_sha(repo) != before


def test_corrupt_memo_is_recomputed_not_trusted(tmp_path):
    repo = _repo(tmp_path)
    cold = _uncached(repo)
    ngc._source_sha_memo_path(repo).write_text("{not json")
    assert ngc.compute_source_sha(repo) == cold


def test_memo_is_bounded(tmp_path):
    repo = _repo(tmp_path)
    f = repo / "mcp" / "a.py"
    for i in range(ngc._SOURCE_SHA_MEMO_MAX + 5):
        f.write_text(f"A = {i}\n")
        ngc.compute_source_sha(repo)
    assert len(ngc._read_source_sha_memo(ngc._source_sha_memo_path(repo))) == ngc._SOURCE_SHA_MEMO_MAX
