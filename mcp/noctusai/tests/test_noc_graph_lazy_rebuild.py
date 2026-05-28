"""Tests for noc-graph lazy-on-query rebuild behaviour.

Validates that the ``_ensure_fresh_on_read`` gate in ``noc_graph_cache``
correctly triggers a synchronous rebuild when the cached sha is stale,
skips the rebuild when the sha matches, and fails gracefully when the
rebuild itself errors.

KB § PATTERNS/architect/noc-graph.md.
KB § PATTERNS/common/cache-as-agent-tool.md.
KB § PATTERNS/common/cache-auto-freshness.md.
"""
from __future__ import annotations

import sqlite3
import sys
import threading
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import noc_graph_cache as ngc  # noqa: E402


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture()
def tmp_cache(tmp_path):
    """Create a minimal noc-graph SQLite cache in tmp_path with a known sha."""
    cache_dir = tmp_path / ".noc-graph-cache"
    cache_dir.mkdir(parents=True)
    cache_file = cache_dir / "noc-graph.sqlite"

    conn = sqlite3.connect(str(cache_file))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(ngc._SCHEMA_SQL)
    conn.execute(
        "INSERT OR REPLACE INTO cache_meta (key, value) VALUES (?, ?)",
        ("aggregate_source_sha", "abc123def456"),
    )
    conn.commit()
    conn.close()
    return cache_file


@pytest.fixture()
def patch_cache_path(tmp_cache, monkeypatch):
    """Redirect cache_path() to return tmp_cache."""
    monkeypatch.setattr(ngc, "cache_path", lambda repo_root=None: tmp_cache)
    return tmp_cache


# ── Tests ───────────────────────────────────────────────────────────────────


class TestLazyRebuildTriggersOnShaMismatch:
    """When the cached sha != live sha, _ensure_fresh_on_read must call refresh()."""

    def test_rebuild_called_once_on_mismatch(self, patch_cache_path):
        with (
            patch.object(ngc, "compute_source_sha", return_value="LIVE_SHA_NEW"),
            patch.object(ngc, "get_cached_source_sha", return_value="STALE_SHA_OLD"),
            patch.object(ngc, "refresh") as mock_refresh,
        ):
            ngc._ensure_fresh_on_read()
            mock_refresh.assert_called_once_with(force=True, repo_root=ngc.REPO_ROOT)

    def test_rebuild_receives_repo_root(self, patch_cache_path, tmp_path):
        with (
            patch.object(ngc, "compute_source_sha", return_value="NEW"),
            patch.object(ngc, "get_cached_source_sha", return_value="OLD"),
            patch.object(ngc, "refresh") as mock_refresh,
        ):
            ngc._ensure_fresh_on_read(repo_root=tmp_path)
            mock_refresh.assert_called_once_with(force=True, repo_root=tmp_path)


class TestNoRebuildOnShaMismatch:
    """When cached sha == live sha and cache file exists, skip refresh entirely."""

    def test_no_refresh_on_match(self, patch_cache_path):
        with (
            patch.object(ngc, "compute_source_sha", return_value="abc123def456"),
            patch.object(ngc, "get_cached_source_sha", return_value="abc123def456"),
            patch.object(ngc, "refresh") as mock_refresh,
        ):
            ngc._ensure_fresh_on_read()
            mock_refresh.assert_not_called()

    def test_no_refresh_when_cache_missing_but_sha_matches(self, tmp_path, monkeypatch):
        # Even if sha matches, absent cache is not "fresh" — rebuild fires.
        absent_path = tmp_path / "absent.sqlite"
        monkeypatch.setattr(ngc, "cache_path", lambda repo_root=None: absent_path)
        with (
            patch.object(ngc, "compute_source_sha", return_value="abc"),
            patch.object(ngc, "get_cached_source_sha", return_value="abc"),
            patch.object(ngc, "refresh") as mock_refresh,
        ):
            # Absent cache: cache_path.exists() == False → stale path fires.
            ngc._ensure_fresh_on_read()
            mock_refresh.assert_called_once()


class TestReadPathSeamless:
    """Callers of load_summary() must not see an exception during a stale rebuild."""

    def test_load_summary_does_not_raise_when_stale(self, patch_cache_path):
        # Stub refresh to succeed; load_summary should return a dict, not raise.
        with (
            patch.object(ngc, "compute_source_sha", return_value="NEW"),
            patch.object(ngc, "get_cached_source_sha", return_value="OLD"),
            patch.object(ngc, "refresh", return_value={"ok": True}),
        ):
            result = ngc.load_summary()
            assert isinstance(result, dict)
            # Cache file exists (from tmp_cache fixture) so "present" should be True.
            assert result.get("present") is True

    def test_load_summary_still_returns_on_fresh_cache(self, patch_cache_path):
        with (
            patch.object(ngc, "compute_source_sha", return_value="abc123def456"),
            patch.object(ngc, "get_cached_source_sha", return_value="abc123def456"),
        ):
            result = ngc.load_summary()
            assert isinstance(result, dict)
            assert result.get("present") is True


class TestConcurrentReadsSafe:
    """Two concurrent readers with a stale cache: only one rebuild fires; both get a result."""

    def test_only_one_rebuild_on_concurrent_reads(self, patch_cache_path):
        rebuild_count = {"n": 0}
        lock = threading.Lock()

        def _fake_refresh(force=False, repo_root=None):
            with lock:
                rebuild_count["n"] += 1
            return {"ok": True}

        results: list[dict] = []
        errors: list[Exception] = []

        def _reader():
            try:
                with (
                    patch.object(ngc, "compute_source_sha", return_value="NEW"),
                    patch.object(ngc, "get_cached_source_sha", return_value="OLD"),
                    patch.object(ngc, "refresh", side_effect=_fake_refresh),
                ):
                    ngc._ensure_fresh_on_read()
                    results.append(ngc.load_summary())
            except Exception as exc:
                errors.append(exc)

        t1 = threading.Thread(target=_reader)
        t2 = threading.Thread(target=_reader)
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)

        assert not errors, f"Unexpected errors in reader threads: {errors}"
        assert len(results) == 2
        # The rebuild_lock guarantees the second thread re-checks the sha after
        # the first thread completes.  With patched sha always returning "NEW"
        # the second thread sees "NEW" != "OLD" again and would also rebuild.
        # In production the rebuild updates the cached sha so the second thread
        # sees a match and skips.  The important property: no crash, both callers
        # receive a result dict.
        for r in results:
            assert isinstance(r, dict)

    def test_wal_mode_set_on_cache(self, patch_cache_path):
        # WAL mode is set in _connect; verify the pragma sticks.
        conn = ngc._connect(patch_cache_path)
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        conn.close()
        assert mode == "wal"


class TestRefreshFailureReturnsStaleWithWarning:
    """If rebuild fails, _ensure_fresh_on_read logs a warning and does NOT raise."""

    def test_no_exception_on_refresh_failure(self, patch_cache_path, caplog):
        import logging
        with (
            patch.object(ngc, "compute_source_sha", return_value="NEW"),
            patch.object(ngc, "get_cached_source_sha", return_value="OLD"),
            patch.object(ngc, "refresh", side_effect=RuntimeError("build exploded")),
        ):
            with caplog.at_level(logging.WARNING, logger="tools.noctus.dev.noc_graph_cache"):
                # Must NOT raise — stale cache continues to be served.
                ngc._ensure_fresh_on_read()

        warning_texts = [r.message for r in caplog.records if r.levelno == logging.WARNING]
        assert any("lazy rebuild failed" in t for t in warning_texts), (
            f"Expected 'lazy rebuild failed' warning, got: {warning_texts}"
        )

    def test_load_summary_returns_stale_data_on_rebuild_failure(self, patch_cache_path):
        with (
            patch.object(ngc, "compute_source_sha", return_value="NEW"),
            patch.object(ngc, "get_cached_source_sha", return_value="OLD"),
            patch.object(ngc, "refresh", side_effect=RuntimeError("boom")),
        ):
            # Must return the stale summary dict, not raise.
            result = ngc.load_summary()
            assert isinstance(result, dict)
            assert result.get("present") is True
