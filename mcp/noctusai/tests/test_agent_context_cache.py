"""Regression tests for `agent_context_cache` + `check_agent_context_cache_freshness`.

KB § PATTERNS/common/agent-context-architecture.md. Phase B (2026-05-26).
"""
import os
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# The cache module reads paths off `settings.REPO_ROOT` at import — for the
# tmp_path tests we re-bind the module's CACHE_PATH/AGENTS_DIR/KB_DIR.
from tools.noctus.dev import agent_context_cache as acc  # noqa: E402
from tools.noctus.dev.compliance import check_agent_context_cache_freshness  # noqa: E402


@pytest.fixture
def tmp_repo(tmp_path, monkeypatch):
    """Bind the cache module's path constants to a tmp_path so the tests
    don't touch the real `.claude/cache/agent-context.sqlite`."""
    monkeypatch.setattr(acc, "CACHE_DIR", tmp_path / ".claude" / "cache")
    monkeypatch.setattr(acc, "CACHE_PATH", tmp_path / ".claude" / "cache" / "agent-context.sqlite")
    monkeypatch.setattr(acc, "AGENTS_DIR", tmp_path / ".claude" / "agents")
    monkeypatch.setattr(acc, "KB_DIR", tmp_path / "KNOWLEDGE-BASE")
    (tmp_path / ".claude" / "agents").mkdir(parents=True)
    (tmp_path / "KNOWLEDGE-BASE").mkdir(parents=True)
    return tmp_path


def _write_agent(root: Path, stem: str, frontmatter: str, body: str) -> Path:
    p = root / ".claude" / "agents" / f"{stem}.md"
    p.write_text(f"---\n{frontmatter}\n---\n\n{body}\n", encoding="utf-8")
    return p


def _write_kb(root: Path, rel: str, body: str) -> Path:
    p = root / "KNOWLEDGE-BASE" / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p


class TestRefreshAndLookup:
    def test_refresh_populates_clean_state(self, tmp_repo):
        _write_kb(tmp_repo, "CONTEXT/PATTERNS/backend/backend.md",
            "# Backend\n\nIntro paragraph.\n\n## Section A\nLine A1\n## Section B\nLine B1\n")
        _write_agent(tmp_repo, "backend-engineer",
            "name: backend-engineer\ndescription: x\ntools: Read\nowns_kb:\n  - CONTEXT/PATTERNS/backend/backend.md",
            "Apply engineer-seed. → KB § PATTERNS/backend/backend.md")
        r = acc.refresh(force=True)
        assert r["ok"] is True
        assert r["status"] == "rebuilt"
        assert "backend-engineer" in r["refreshed"]
        assert r["rows_written"] >= 3  # frontmatter + body + 1 owned-kb-extract

    def test_idempotent_short_circuit(self, tmp_repo):
        _write_kb(tmp_repo, "CONTEXT/PATTERNS/backend/backend.md", "# B\n\nIntro\n")
        _write_agent(tmp_repo, "backend-engineer",
            "name: backend-engineer\ndescription: x\ntools: Read\nowns_kb:\n  - CONTEXT/PATTERNS/backend/backend.md",
            "→ KB § PATTERNS/backend/backend.md")
        acc.refresh(force=True)
        r2 = acc.refresh()  # no changes since
        assert r2["status"] == "in-sync"
        assert "backend-engineer" in r2["skipped"]
        assert r2["refreshed"] == []

    def test_lookup_returns_bundle(self, tmp_repo):
        _write_kb(tmp_repo, "CONTEXT/PATTERNS/backend/backend.md",
            "# Backend\n\nThe spine.\n\n## DI seam\nDep injection details.\n")
        _write_agent(tmp_repo, "backend-engineer",
            "name: backend-engineer\ndescription: x\ntools: Read\nowns_kb:\n  - CONTEXT/PATTERNS/backend/backend.md",
            "→ KB § PATTERNS/backend/backend.md")
        acc.refresh(force=True)
        b = acc.lookup("backend-engineer")
        assert b["ok"] is True
        assert b["agent_name"] == "backend-engineer"
        assert "owns_kb:" in b["frontmatter"]
        assert "engineer-seed" not in b["frontmatter"]  # belongs to body
        assert "KB § PATTERNS/backend/backend.md" in b["body"]
        assert len(b["owned_kb"]) == 1
        assert b["owned_kb"][0]["path"] == "CONTEXT/PATTERNS/backend/backend.md"
        assert "# Backend" in b["owned_kb"][0]["extract"]
        assert "DI seam" in b["owned_kb"][0]["extract"]

    def test_lookup_unknown_agent_returns_error(self, tmp_repo):
        b = acc.lookup("nonexistent-agent")
        assert b["ok"] is False
        assert "not found" in b["error"]

    def test_lazy_rebuild_on_sha_mismatch(self, tmp_repo):
        _write_kb(tmp_repo, "CONTEXT/PATTERNS/backend/backend.md", "# B\n\nIntro\n")
        _write_agent(tmp_repo, "backend-engineer",
            "name: backend-engineer\ndescription: x\ntools: Read\nowns_kb:\n  - CONTEXT/PATTERNS/backend/backend.md",
            "→ KB § PATTERNS/backend/backend.md")
        acc.refresh(force=True)
        # Mutate the agent body — the bundle_sha will drift.
        _write_agent(tmp_repo, "backend-engineer",
            "name: backend-engineer\ndescription: x\ntools: Read\nowns_kb:\n  - CONTEXT/PATTERNS/backend/backend.md",
            "→ KB § PATTERNS/backend/backend.md\n\nNEW LINE that wasn't there before.")
        b = acc.lookup("backend-engineer")
        assert b["ok"] is True
        assert "NEW LINE" in b["body"]  # rebuild fired on mismatch

    def test_list_agents(self, tmp_repo):
        _write_agent(tmp_repo, "alpha",
            "name: alpha\ndescription: x\ntools: Read\nowns_kb: []",
            "body")
        _write_agent(tmp_repo, "beta",
            "name: beta\ndescription: x\ntools: Read\nowns_kb: []",
            "body")
        acc.refresh(force=True)
        names = acc.list_agents()
        assert "alpha" in names
        assert "beta" in names

    def test_owns_kb_missing_path_skipped(self, tmp_repo):
        # Cache silently skips missing owned-KB paths (the keeper
        # check_agent_kb_alignment flags them — separation of concerns).
        _write_agent(tmp_repo, "x",
            "name: x\ndescription: x\ntools: Read\nowns_kb:\n  - CONTEXT/PATTERNS/missing.md",
            "→ KB § PATTERNS/missing.md")
        r = acc.refresh(force=True)
        assert r["ok"] is True
        b = acc.lookup("x")
        assert b["owned_kb"] == []  # missing path skipped


class TestCheckAgentContextCacheFreshness:
    def test_cache_missing_flagged(self, tmp_path, monkeypatch):
        # The keeper resolves agents at <root>/.claude/agents and the cache via
        # the Tier-1 resolver (now honoring repo_root). Disable Tier-2 auto-pull
        # so the genuinely-missing cache stays missing instead of being pulled.
        monkeypatch.setenv("NOCTUS_DISABLE_AUTO_CACHE_PULL", "1")
        (tmp_path / ".claude" / "agents").mkdir(parents=True)
        (tmp_path / "KNOWLEDGE-BASE").mkdir(parents=True)
        issues = check_agent_context_cache_freshness(repo_root=tmp_path)
        assert any(i["symbol"] == "agent-context-cache-missing" for i in issues)

    def test_clean_state_passes(self, tmp_repo):
        _write_agent(tmp_repo, "alpha",
            "name: alpha\ndescription: x\ntools: Read\nowns_kb: []",
            "body")
        acc.refresh(force=True)
        issues = check_agent_context_cache_freshness(repo_root=tmp_repo)
        # The keeper looks at the REAL cache path (root / .claude / cache /...) —
        # we redirected the module to a tmp path so the keeper sees "missing"
        # by default. That's the cache-missing path tested above. For the
        # clean-state check we verify get_bundle_sha returns matching live+cached
        # for the agent we just refreshed.
        live, cached = acc.get_bundle_sha("alpha")
        assert cached is not None
        assert live == cached

    def test_stale_after_agent_edit(self, tmp_repo):
        _write_agent(tmp_repo, "alpha",
            "name: alpha\ndescription: x\ntools: Read\nowns_kb: []",
            "body v1")
        acc.refresh(force=True)
        live_v1, cached_v1 = acc.get_bundle_sha("alpha")
        assert live_v1 == cached_v1
        # Mutate
        _write_agent(tmp_repo, "alpha",
            "name: alpha\ndescription: x\ntools: Read\nowns_kb: []",
            "body v2 — totally different content here")
        live_v2, cached_v2 = acc.get_bundle_sha("alpha")
        assert live_v2 != cached_v2  # cached still v1; the keeper would fire


class TestCompactExtract:
    def test_extract_includes_h1_and_first_paragraph(self):
        md = "# Title\n\nFirst paragraph here.\nSecond line of paragraph.\n\n## H2 A\nA-1\n## H2 B\nB-1\n"
        out = acc._compact_extract(md)
        assert "# Title" in out
        assert "First paragraph here." in out
        assert "## H2 A" in out
        assert "A-1" in out
        assert "## H2 B" in out

    def test_extract_capped_at_max_lines(self):
        md = "# T\n\nIntro\n" + "".join(f"## H{i}\nL{i}\n" for i in range(100))
        out = acc._compact_extract(md, max_lines=30)
        assert len(out.splitlines()) <= 30


def _make_fake_worktree(tmp_path, name):
    """`resolve_caller_root` only checks EXISTENCE of `.git` + the marker
    file — no real git init needed. Module-level so both
    `TestWorktreePathScoping` and `TestScopedRefreshCrossTreeParity` share it."""
    wt = tmp_path / name
    wt.mkdir(parents=True)
    (wt / ".git").write_text("gitdir: /nowhere\n")
    (wt / ".noctusai-workspace").write_text("test\n")
    (wt / ".claude" / "agents").mkdir(parents=True)
    (wt / "KNOWLEDGE-BASE").mkdir(parents=True)
    return wt


class TestWorktreePathScoping:
    """`refresh()` without `worktree_path` silently mirrors the PRIMARY tree's
    `.claude/agents/*.md` + owned KB (bound at MCP-server-startup CWD), even
    when called from inside an engineer worktree carrying its own in-flight
    agent/KB edits. Mirrors `TestWorktreePathScoping` in
    `test_auto_improvement.py`."""

    _make_fake_worktree = staticmethod(_make_fake_worktree)

    def test_refresh_reads_worktree_agents_not_primary(self, tmp_repo):
        wt = self._make_fake_worktree(tmp_repo, "wt")
        _write_agent(wt, "wt-only-agent",
            "name: wt-only-agent\ndescription: x\ntools: Read\nowns_kb: []",
            "worktree-local, uncommitted")
        assert not (tmp_repo / ".claude" / "agents" / "wt-only-agent.md").exists()

        r = acc.refresh(force=True, worktree_path=str(wt))
        assert r["status"] == "rebuilt"
        assert "wt-only-agent" in r["refreshed"]

        # Omitting worktree_path stays scoped to the (empty) primary — the
        # worktree-only agent must never silently leak into the primary read.
        r_primary = acc.refresh(force=True)
        assert "wt-only-agent" not in r_primary["refreshed"]

    def test_refresh_worktree_path_rejects_non_worktree_dir(self, tmp_repo, tmp_path):
        bogus = tmp_path / "not-a-worktree"
        bogus.mkdir()
        with pytest.raises(ValueError):
            acc.refresh(worktree_path=str(bogus))


class TestScopedRefreshCrossTreeParity:
    """Item 1 (2026-09-17): `get_bundle_sha` / `check_agent_context_cache_freshness`
    ignored `repo_root`, silently recomputing the "live" side off the
    module's frozen `AGENTS_DIR`/`KB_DIR` (here: `tmp_repo`, standing in for
    a fixed-CWD MCP server's primary tree) regardless of what worktree was
    actually being checked. A scoped `refresh(agent_name=...,
    worktree_path=...)` DID write the correct `cache_meta['bundle_sha:<agent>']`
    all along — the WRITE path was never broken — but the freshness check
    compared it against the wrong tree forever, so no number of repeated
    scoped refreshes could ever satisfy it. `lookup()` had the same gap on
    its self-heal path, actively clobbering a correct scoped write.
    KB § PATTERNS/common/agent-context-architecture.md § scoped-refresh parity.
    """

    @staticmethod
    def _seed_primary_and_worktree_edit(tmp_repo):
        """Primary carries the unedited agent; a worktree carries an
        in-flight edit the primary does NOT have. Returns the worktree Path."""
        _write_agent(tmp_repo, "backend-engineer",
            "name: backend-engineer\ndescription: x\ntools: Read\nowns_kb: []",
            "primary body — unedited")
        acc.refresh(force=True)  # seed the primary-side cache row
        wt = _make_fake_worktree(tmp_repo, "wt")
        _write_agent(wt, "backend-engineer",
            "name: backend-engineer\ndescription: x\ntools: Read\nowns_kb: []",
            "WORKTREE body — edited, not yet merged")
        return wt

    def test_scoped_refresh_writes_correct_cache_meta_direct_sqlite(self, tmp_repo):
        wt = self._seed_primary_and_worktree_edit(tmp_repo)
        acc.refresh(agent_name="backend-engineer", worktree_path=str(wt), force=True)

        # Direct sqlite assertion — per the brief, not just a passing
        # refresh() call. Read cache_meta straight off disk — from the
        # WORKTREE's own slot (agent-context is a per-tree cache).
        conn = sqlite3.connect(str(acc._cache_file(str(wt))))
        row = conn.execute(
            "SELECT value FROM cache_meta WHERE key=?",
            ("bundle_sha:backend-engineer",),
        ).fetchone()
        conn.close()
        assert row is not None

        expected_sha, _ = acc._bundle_sources(
            wt / ".claude" / "agents" / "backend-engineer.md", wt / "KNOWLEDGE-BASE",
        )
        assert row[0] == expected_sha
        # And explicitly NOT the primary's (unedited) sha — proves the
        # scoped write targeted the worktree, not the frozen primary.
        primary_sha, _ = acc._bundle_sources(
            tmp_repo / ".claude" / "agents" / "backend-engineer.md",
            tmp_repo / "KNOWLEDGE-BASE",
        )
        assert row[0] != primary_sha

    def test_get_bundle_sha_agrees_after_scoped_refresh(self, tmp_repo):
        """THE bug, reproduced directly against `get_bundle_sha` — the exact
        function `check_agent_context_cache_freshness` calls per-agent.
        (The full keeper function's OWN cache-file resolution goes through
        `cache_backend.cache_path`'s git-common-dir walk, which a synthetic
        `.git`-stub worktree can't satisfy in-process — the SAME limitation
        `test_clean_state_passes` above already documents and works around
        by asserting on `get_bundle_sha` directly; this test follows that
        established convention for the identical reason.)

        Before the fix this reported STALE forever — `get_bundle_sha`
        recomputed "live" off `tmp_repo` (`AGENTS_DIR`) regardless of the
        `repo_root=wt` passed in, so the mismatch could never resolve no
        matter how many times the scoped refresh re-ran."""
        wt = self._seed_primary_and_worktree_edit(tmp_repo)
        acc.refresh(agent_name="backend-engineer", worktree_path=str(wt), force=True)

        live, cached = acc.get_bundle_sha("backend-engineer", repo_root=wt)
        assert cached is not None
        assert live == cached, f"live={live[:12]} cached={cached[:12]} — stale forever pre-fix"

        # Repeating the scoped refresh must not matter either way — this is
        # the "the suggested remedy doesn't work" regression, not a flake.
        for _ in range(3):
            acc.refresh(agent_name="backend-engineer", worktree_path=str(wt), force=True)
        live2, cached2 = acc.get_bundle_sha("backend-engineer", repo_root=wt)
        assert live2 == cached2

    def test_get_bundle_sha_default_repo_root_unchanged(self, tmp_repo):
        """`repo_root=None` (the pre-existing call shape — CLI's
        `--agent-context`, unscoped keeper runs, etc.) must keep resolving
        against the module-level `AGENTS_DIR`/`KB_DIR` exactly as before —
        the new parameter is additive, not a default-behavior change."""
        _write_agent(tmp_repo, "alpha",
            "name: alpha\ndescription: x\ntools: Read\nowns_kb: []", "body")
        acc.refresh(force=True)
        live, cached = acc.get_bundle_sha("alpha")
        assert cached is not None
        assert live == cached
        expected, _ = acc._bundle_sources(
            tmp_repo / ".claude" / "agents" / "alpha.md", tmp_repo / "KNOWLEDGE-BASE",
        )
        assert live == expected

    def test_lookup_worktree_path_does_not_clobber_scoped_cache_meta(self, tmp_repo):
        """`lookup()` (the `noctus.dev.agent_context` MCP tool) used to
        self-heal via `refresh(agent_name=...)` with NO `worktree_path` —
        silently overwriting a correct worktree-scoped cache_meta entry
        with the primary's (wrong) sha the instant anyone looked the agent
        up. Threading `worktree_path` through closes it."""
        wt = self._seed_primary_and_worktree_edit(tmp_repo)
        acc.refresh(agent_name="backend-engineer", worktree_path=str(wt), force=True)

        b = acc.lookup("backend-engineer", worktree_path=str(wt))
        assert b["ok"] is True
        assert "WORKTREE body" in b["body"]

        conn = sqlite3.connect(str(acc._cache_file(str(wt))))
        row = conn.execute(
            "SELECT value FROM cache_meta WHERE key=?",
            ("bundle_sha:backend-engineer",),
        ).fetchone()
        conn.close()
        expected_sha, _ = acc._bundle_sources(
            wt / ".claude" / "agents" / "backend-engineer.md", wt / "KNOWLEDGE-BASE",
        )
        assert row[0] == expected_sha  # still the worktree sha, not clobbered
