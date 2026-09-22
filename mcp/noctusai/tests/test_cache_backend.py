"""Tests for the cache_backend abstraction layer (`cache_backend.py`).

These tests lock the Protocol contract + the default SqliteCacheBackend
behavior so future remote-backend implementations have a fixed target.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import sqlite3

import pytest

from tools.noctus.dev import cache_backend as cb


class TestCatalog:
    def test_known_caches_returns_registered_set(self):
        names = cb.known_caches()
        assert set(names) == {
            "keeper-patterns",
            "agent-context",
            "auto-improvement",
            "kb-embeddings",
            "code-embeddings",
            "memory-embeddings",
            "corpus-embeddings",
            "noc-graph",
            "absorptions",
        }

    def test_known_caches_stable_order(self):
        # Order matters for deterministic refresh sequences.
        assert cb.known_caches() == cb.known_caches()


class TestCachePath:
    def test_resolves_under_git_common_dir_cache(self, tmp_path):
        # Tier-1 layout: <git-common-dir>/noctusai/cache/<name>.sqlite — shared
        # by all worktrees (KB § PATTERNS/common/cache-portable-architecture.md).
        # Asserted via cache_dir + layout (robust to the git-common-dir fallback)
        # rather than the retired <repo>/.claude/cache path. Uses a SHARED
        # (content-addressed) cache — single-slot mirrors are per-tree, see
        # TestPerTreeCaches.
        p = cb.cache_path("kb-embeddings", repo_root=tmp_path)
        assert p == cb.cache_dir(tmp_path) / "kb-embeddings.sqlite"
        assert p.name == "kb-embeddings.sqlite"
        assert p.parent.name == "cache" and p.parent.parent.name == "noctusai"

    def test_unknown_cache_raises_KeyError(self, tmp_path):
        with pytest.raises(KeyError, match="Unknown cache name"):
            cb.cache_path("not-a-cache", repo_root=tmp_path)

    def test_uses_settings_repo_root_by_default(self):
        # No explicit repo_root → falls back to settings.REPO_ROOT.
        p = cb.cache_path("kb-embeddings")
        assert p.name == "kb-embeddings.sqlite"
        assert "noctusai/cache" in str(p)


class TestSqliteBackend:
    def test_kind_is_sqlite(self, tmp_path):
        be = cb.SqliteCacheBackend(repo_root=tmp_path)
        assert be.kind() == "sqlite"

    def test_location_returns_file_path(self, tmp_path):
        be = cb.SqliteCacheBackend(repo_root=tmp_path)
        loc = be.location("kb-embeddings")
        assert loc.endswith("noctusai/cache/kb-embeddings.sqlite")

    def test_connect_creates_parent_dir(self, tmp_path):
        be = cb.SqliteCacheBackend(repo_root=tmp_path)
        with be.connect("keeper-patterns") as conn:
            assert isinstance(conn, sqlite3.Connection)
        # File created on connect, parent dir auto-mkdir'd (Tier-1 location).
        assert cb.cache_dir(tmp_path).exists()

    def test_connect_applies_wal_mode(self, tmp_path):
        be = cb.SqliteCacheBackend(repo_root=tmp_path)
        with be.connect("keeper-patterns") as conn:
            cur = conn.execute("PRAGMA journal_mode")
            mode = cur.fetchone()[0]
            assert mode.lower() == "wal"

    def test_connect_sets_row_factory_to_Row(self, tmp_path):
        be = cb.SqliteCacheBackend(repo_root=tmp_path)
        with be.connect("keeper-patterns") as conn:
            assert conn.row_factory is sqlite3.Row

    def test_connect_closes_on_exit(self, tmp_path):
        be = cb.SqliteCacheBackend(repo_root=tmp_path)
        with be.connect("keeper-patterns") as conn:
            conn.execute("CREATE TABLE t (x INTEGER)")
            conn.commit()
        # After exit, the connection is closed — re-use raises ProgrammingError.
        with pytest.raises(sqlite3.ProgrammingError):
            conn.execute("SELECT 1")

    def test_connect_roundtrip_persists(self, tmp_path):
        be = cb.SqliteCacheBackend(repo_root=tmp_path)
        with be.connect("keeper-patterns") as conn:
            conn.execute("CREATE TABLE t (x INTEGER)")
            conn.execute("INSERT INTO t VALUES (?)", (42,))
            conn.commit()
        # Reopen — data survives (real file, real persistence).
        with be.connect("keeper-patterns") as conn:
            row = conn.execute("SELECT x FROM t").fetchone()
            assert row["x"] == 42

    def test_unknown_cache_raises_via_connect(self, tmp_path):
        be = cb.SqliteCacheBackend(repo_root=tmp_path)
        with pytest.raises(KeyError):
            with be.connect("not-a-cache"):
                pass


class TestFactory:
    def test_get_backend_default_is_sqlite(self, monkeypatch, tmp_path):
        monkeypatch.delenv(cb._ENV_VAR, raising=False)
        be = cb.get_backend(repo_root=tmp_path)
        assert be.kind() == "sqlite"
        assert isinstance(be, cb.SqliteCacheBackend)

    def test_get_backend_respects_env_var(self, monkeypatch, tmp_path):
        monkeypatch.setenv(cb._ENV_VAR, "sqlite")
        be = cb.get_backend(repo_root=tmp_path)
        assert be.kind() == "sqlite"

    def test_get_backend_case_insensitive(self, monkeypatch, tmp_path):
        monkeypatch.setenv(cb._ENV_VAR, "SQLITE")
        be = cb.get_backend(repo_root=tmp_path)
        assert be.kind() == "sqlite"

    def test_get_backend_unknown_raises_ValueError(self, monkeypatch):
        # "postgres" is now valid (Phase 3.1); use a truly unknown value.
        monkeypatch.setenv(cb._ENV_VAR, "supabase")
        with pytest.raises(ValueError, match="not a valid backend yet"):
            cb.get_backend()

    def test_protocol_isinstance_check(self, tmp_path):
        # Runtime-checkable Protocol — confirms SqliteCacheBackend satisfies.
        be = cb.SqliteCacheBackend(repo_root=tmp_path)
        assert isinstance(be, cb.CacheBackend)


class TestLockingPragmas:
    """The cache-locking discipline: WAL + busy_timeout, applied uniformly.

    Regression guard for the 2026-05-30 pre-push writer-contention incident —
    WAL alone does not serialize writer-vs-writer, so a contending writer hit
    `sqlite3.OperationalError: database is locked`. busy_timeout closes the gap.
    """

    def test_sets_wal_and_busy_timeout(self, tmp_path):
        conn = sqlite3.connect(str(tmp_path / "t.sqlite"))
        try:
            cb.apply_locking_pragmas(conn)
            assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
            assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == cb.CACHE_BUSY_TIMEOUT_MS
        finally:
            conn.close()

    def test_custom_timeout_honored(self, tmp_path):
        conn = sqlite3.connect(str(tmp_path / "t.sqlite"))
        try:
            cb.apply_locking_pragmas(conn, timeout_ms=1234)
            assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 1234
        finally:
            conn.close()

    def test_default_timeout_is_positive(self):
        # A zero/absent busy_timeout is the bug — must be a real wait window.
        assert cb.CACHE_BUSY_TIMEOUT_MS > 0

    def test_backend_connect_applies_busy_timeout(self, tmp_path):
        # The backend's own connect() must carry the discipline end-to-end.
        be = cb.SqliteCacheBackend(repo_root=tmp_path)
        with be.connect("keeper-patterns") as conn:
            assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == cb.CACHE_BUSY_TIMEOUT_MS

    def test_idempotent(self, tmp_path):
        # Safe to call more than once on the same connection.
        conn = sqlite3.connect(str(tmp_path / "t.sqlite"))
        try:
            cb.apply_locking_pragmas(conn)
            cb.apply_locking_pragmas(conn)
            assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == cb.CACHE_BUSY_TIMEOUT_MS
        finally:
            conn.close()


class TestCacheUsesLockingHelper:
    """Regression-test-the-detector for check_cache_uses_locking_helper — the
    s4 keeper that blocks a new cache from inlining raw `PRAGMA journal_mode=WAL`
    instead of calling apply_locking_pragmas (the 2026-05-30 busy_timeout gap)."""

    def _tools_file(self, root, rel, body):
        p = root / "mcp" / "noctusai" / "tools" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
        return p

    def test_silent_skip_non_noc_tree(self, tmp_path):
        from tools.noctus.dev.compliance import check_cache_uses_locking_helper
        assert check_cache_uses_locking_helper(repo_root=tmp_path) == []

    def test_raw_wal_flagged_high(self, tmp_path):
        from tools.noctus.dev.compliance import check_cache_uses_locking_helper
        self._tools_file(tmp_path, "noctus/dev/newcache.py",
            'import sqlite3\n'
            'def _connect(p):\n'
            '    conn = sqlite3.connect(str(p))\n'
            '    conn.execute("PRAGMA journal_mode=WAL")\n'
            '    return conn\n')
        issues = check_cache_uses_locking_helper(repo_root=tmp_path)
        hits = [i for i in issues if i["symbol"] == "cache-raw-wal-without-helper"]
        assert hits and all(i["severity"] == "high" for i in hits)
        assert hits[0]["file"].endswith("newcache.py")

    def test_helper_usage_not_flagged(self, tmp_path):
        from tools.noctus.dev.compliance import check_cache_uses_locking_helper
        self._tools_file(tmp_path, "noctus/dev/newcache.py",
            'from .cache_backend import apply_locking_pragmas\n'
            'import sqlite3\n'
            'def _connect(p):\n'
            '    conn = sqlite3.connect(str(p))\n'
            '    apply_locking_pragmas(conn)\n'
            '    return conn\n')
        assert check_cache_uses_locking_helper(repo_root=tmp_path) == []

    def test_comment_reference_not_flagged(self, tmp_path):
        from tools.noctus.dev.compliance import check_cache_uses_locking_helper
        self._tools_file(tmp_path, "noctus/dev/newcache.py",
            '# legacy: we used to inline PRAGMA journal_mode=WAL here\n'
            'x = 1\n')
        assert check_cache_uses_locking_helper(repo_root=tmp_path) == []

    def test_helper_home_exempt(self, tmp_path):
        # cache_backend.py defines the helper — it legitimately holds the literal.
        from tools.noctus.dev.compliance import check_cache_uses_locking_helper
        self._tools_file(tmp_path, "noctus/dev/cache_backend.py",
            'conn.execute("PRAGMA journal_mode=WAL")\n')
        assert check_cache_uses_locking_helper(repo_root=tmp_path) == []

    def test_real_repo_has_no_violations(self):
        # Proves the 2026-05-30 centralization is complete across the live tree
        # AND fails loudly if anyone re-introduces a raw WAL cache connection.
        from tools.noctus.dev.compliance import check_cache_uses_locking_helper
        assert check_cache_uses_locking_helper() == []

    # ── Leg 2: the MISSING-pragma omission detector (2026-05-30 hardening) ──
    # The original keeper only grepped the journal_mode=WAL literal, so a raw
    # sqlite3.connect() that omitted the pragmas ENTIRELY was invisible — exactly
    # the shape that caused the code-embed `database is locked`.
    def test_bare_connect_without_helper_flagged(self, tmp_path):
        from tools.noctus.dev.compliance import check_cache_uses_locking_helper
        self._tools_file(tmp_path, "noctus/dev/newcache.py",
            'import sqlite3\n'
            'def get_source_sha(p):\n'
            '    conn = sqlite3.connect(str(p))\n'
            '    return conn.execute("SELECT 1").fetchone()\n')
        issues = check_cache_uses_locking_helper(repo_root=tmp_path)
        hits = [i for i in issues if i["symbol"] == "cache-connect-without-locking-helper"]
        assert hits and all(i["severity"] == "high" for i in hits)
        assert hits[0]["file"].endswith("newcache.py")

    def test_connect_with_helper_in_same_fn_not_flagged(self, tmp_path):
        from tools.noctus.dev.compliance import check_cache_uses_locking_helper
        self._tools_file(tmp_path, "noctus/dev/newcache.py",
            'from .cache_backend import apply_locking_pragmas\n'
            'import sqlite3\n'
            'def get_source_sha(p):\n'
            '    conn = sqlite3.connect(str(p))\n'
            '    apply_locking_pragmas(conn)\n'
            '    return conn.execute("SELECT 1").fetchone()\n')
        assert check_cache_uses_locking_helper(repo_root=tmp_path) == []

    def test_delegating_fn_with_no_raw_connect_not_flagged(self, tmp_path):
        # A freshness reader that delegates to _connect() holds no raw connect —
        # the canonical compliant remediation. Must NOT be flagged.
        from tools.noctus.dev.compliance import check_cache_uses_locking_helper
        self._tools_file(tmp_path, "noctus/dev/newcache.py",
            'import sqlite3\n'
            'def _connect():\n'
            '    conn = sqlite3.connect("x")\n'
            '    apply_locking_pragmas(conn)\n'
            '    return conn\n'
            'def get_source_sha(p):\n'
            '    conn = _connect()\n'
            '    return conn.execute("SELECT 1").fetchone()\n')
        issues = check_cache_uses_locking_helper(repo_root=tmp_path)
        # _connect() applies the helper; get_source_sha() has no raw connect.
        assert [i for i in issues if i["symbol"] == "cache-connect-without-locking-helper"] == []


# ── Per-tree caches (2026-09-22) ─────────────────────────────────────────────
# A single-slot mirror (freshness = ONE aggregate sha of a tracked source) must
# never be shared across worktrees: tree A's refresh flipped tree B's slot to
# "stale" and a high-severity keeper blocked B's unrelated commits. These tests
# use a REAL repo + linked worktree, because the whole point is how
# `git rev-parse` resolves the two trees differently.

import subprocess as _sp


def _git(*args, cwd):
    _sp.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


@pytest.fixture
def repo_with_worktree(tmp_path):
    primary = tmp_path / "primary"
    primary.mkdir()
    _git("init", "-q", "-b", "dev", cwd=primary)
    _git("-c", "user.email=t@t", "-c", "user.name=t",
         "commit", "-q", "--allow-empty", "-m", "init", cwd=primary)
    wt = tmp_path / "wt"
    _git("worktree", "add", "-q", "-b", "feat/x", str(wt), cwd=primary)
    return primary, wt


class TestPerTreeCaches:
    SINGLE_SLOT = ("keeper-patterns", "agent-context", "auto-improvement", "absorptions")

    def test_single_slot_caches_are_private_per_worktree(self, repo_with_worktree):
        primary, wt = repo_with_worktree
        for name in self.SINGLE_SLOT:
            assert cb.is_per_tree_cache(name)
            p_primary = cb.cache_path(name, repo_root=primary)
            p_wt = cb.cache_path(name, repo_root=wt)
            assert p_primary != p_wt, name
            # Primary keeps its exact pre-change file (no migration needed) …
            assert p_primary == primary.resolve() / ".git" / "noctusai" / "cache" / p_primary.name
            # … and the worktree's lives under ITS git-dir, so `git worktree
            # remove` deletes it with the worktree.
            assert p_wt.parent.parent.parent == (primary.resolve() / ".git" / "worktrees" / "wt")

    def test_content_addressed_caches_stay_shared(self, repo_with_worktree):
        primary, wt = repo_with_worktree
        for name in ("kb-embeddings", "code-embeddings", "noc-graph"):
            assert not cb.is_per_tree_cache(name)
            assert cb.cache_path(name, repo_root=primary) == cb.cache_path(name, repo_root=wt)

    def test_unresolvable_git_dir_falls_back_to_tree_local_cache(self, tmp_path):
        # A dangling worktree stub (`.git` FILE git can't follow) must not
        # raise NotADirectoryError — it lands in the tree's gitignored
        # .claude/cache instead, still private to that tree.
        (tmp_path / ".git").write_text("gitdir: /nowhere\n")
        p = cb.cache_path("auto-improvement", repo_root=tmp_path)
        assert p == tmp_path / ".claude" / "cache" / "auto-improvement.sqlite"
