"""Regression tests for `check_keeper_cache_freshness` (Stage-4 keeper)."""
import sys
import hashlib
import sqlite3
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.compliance import check_keeper_cache_freshness  # noqa: E402


def _write_compliance(root: Path, body: str) -> Path:
    p = root / "mcp" / "noctusai" / "tools" / "noctus" / "dev" / "compliance.py"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p


def _seed_cache(root: Path, sha: str) -> Path:
    cache_dir = root / ".claude" / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache = cache_dir / "keeper-patterns.sqlite"
    conn = sqlite3.connect(str(cache))
    conn.execute("CREATE TABLE cache_meta(key TEXT PRIMARY KEY, value TEXT)")
    conn.execute(
        "INSERT INTO cache_meta(key,value) VALUES ('source_sha', ?)", (sha,)
    )
    conn.commit()
    conn.close()
    return cache


class TestKeeperCacheFreshness:
    def test_silent_skip_when_no_compliance(self, tmp_path):
        # Non-noc tree → silent skip (no errors).
        assert check_keeper_cache_freshness(repo_root=tmp_path) == []

    def test_missing_cache_flagged_high(self, tmp_path):
        _write_compliance(tmp_path, "# compliance v1\n")
        issues = check_keeper_cache_freshness(repo_root=tmp_path)
        assert any("cache missing" in i["issue"] for i in issues)
        assert all(i["severity"] == "high" for i in issues)
        assert all(i["symbol"] == "keeper-cache-missing" for i in issues)

    def test_in_sync_passes(self, tmp_path):
        body = "# compliance v1\n"
        src = _write_compliance(tmp_path, body)
        sha = hashlib.sha256(src.read_bytes()).hexdigest()
        _seed_cache(tmp_path, sha)
        assert check_keeper_cache_freshness(repo_root=tmp_path) == []

    def test_stale_cache_flagged_high(self, tmp_path):
        _write_compliance(tmp_path, "# compliance v1\n")
        _seed_cache(tmp_path, "stale-sha-fake")
        issues = check_keeper_cache_freshness(repo_root=tmp_path)
        assert any("STALE" in i["issue"] for i in issues)
        assert all(i["severity"] == "high" for i in issues)
        assert all(i["symbol"] == "keeper-cache-stale" for i in issues)

    def test_source_change_invalidates_in_sync(self, tmp_path):
        # Seed cache with the v1 sha, then change the source — cache should be flagged stale.
        src = _write_compliance(tmp_path, "# compliance v1\n")
        v1_sha = hashlib.sha256(src.read_bytes()).hexdigest()
        _seed_cache(tmp_path, v1_sha)
        # Modify the source — the cache mirror now lies.
        src.write_text("# compliance v2 — added a new keeper\n", encoding="utf-8")
        issues = check_keeper_cache_freshness(repo_root=tmp_path)
        assert any("STALE" in i["issue"] for i in issues)

    def test_unreadable_cache_flagged_high(self, tmp_path):
        _write_compliance(tmp_path, "# compliance v1\n")
        cache_dir = tmp_path / ".claude" / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        # Write garbage bytes (not a valid sqlite file).
        (cache_dir / "keeper-patterns.sqlite").write_bytes(b"NOT A SQLITE FILE")
        issues = check_keeper_cache_freshness(repo_root=tmp_path)
        assert any("unreadable" in i["issue"] for i in issues)
        assert all(i["severity"] == "high" for i in issues)
