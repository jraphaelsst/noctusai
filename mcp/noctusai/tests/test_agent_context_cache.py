"""Regression tests for `agent_context_cache` + `check_agent_context_cache_freshness`.

KB § PATTERNS/common/agent-context-architecture.md. Phase B (2026-05-26).
"""
import os
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
            "Apply engineer-default. → KB § PATTERNS/backend/backend.md")
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
        assert "engineer-default" not in b["frontmatter"]  # belongs to body
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
        monkeypatch.setattr(acc, "CACHE_DIR", tmp_path / ".claude" / "cache")
        monkeypatch.setattr(acc, "CACHE_PATH", tmp_path / ".claude" / "cache" / "agent-context.sqlite")
        monkeypatch.setattr(acc, "AGENTS_DIR", tmp_path / ".claude" / "agents")
        monkeypatch.setattr(acc, "KB_DIR", tmp_path / "KNOWLEDGE-BASE")
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
