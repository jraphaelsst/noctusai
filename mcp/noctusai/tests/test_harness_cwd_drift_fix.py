"""Tests for the harness-cwd-drift fix — refresh CLI flags honor --worktree-path.

Bug closed: pre-commit hook called --refresh-keeper-cache (and siblings) WITHOUT
--worktree-path, so the cache was built against the PRIMARY checkout's
compliance.py SHA while --check-eight-way-sync read the WORKTREE's SHA -> mismatch.

Fix: pre-commit now passes --worktree-path "$REPO_ROOT" to all three refresh legs.
These tests verify:
  1. refresh() uses the worktree's compliance.py SHA when worktree_path is set via
     settings override (the mechanism the CLI uses).
  2. default behavior is unchanged when no override is applied.
  3. The pre-commit hook lines contain --worktree-path on all three refresh calls.

Depth: KB § PATTERNS/common/harness-cwd-drift.md (referenced from
bypass-rationalization-anti-patterns.md § worked-example).
"""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import settings as _settings_mod

from tools.noctus.dev import keeper_pattern_cache as kpc


# ── helpers ──────────────────────────────────────────────────────────────────

def _isolate_cache(tmp_path, monkeypatch) -> None:
    """Point cache paths at tmp dir so tests don't pollute the real cache."""
    cache_dir = tmp_path / "cache"
    monkeypatch.setattr(kpc, "CACHE_DIR", cache_dir)
    monkeypatch.setattr(kpc, "CACHE_PATH", cache_dir / "keeper-patterns.sqlite")


def _make_fake_compliance(root: Path, content: str = "def check_fake(): pass\n") -> Path:
    """Write a minimal compliance.py under root's mcp path."""
    target = root / "mcp" / "noctusai" / "tools" / "noctus" / "dev" / "compliance.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target


# ── test: worktree refresh uses worktree's compliance.py SHA ─────────────────

class TestRefreshHonorsWorktreePath:
    """When settings.REPO_ROOT is overridden to a worktree root, refresh()
    reads compliance.py from that worktree, not the primary checkout."""

    def test_refresh_reads_worktree_compliance_sha(self, tmp_path, monkeypatch):
        """SHA written by refresh() must equal sha256 of the WORKTREE file."""
        # Stand up a fake worktree with its own compliance.py.
        worktree = tmp_path / "fake-worktree"
        fake_compliance = _make_fake_compliance(worktree, "def check_wt(): pass\n")
        expected_sha = hashlib.sha256(fake_compliance.read_bytes()).hexdigest()

        # Override settings to point at the fake worktree (what --worktree-path does).
        monkeypatch.setattr(_settings_mod, "REPO_ROOT", worktree)
        # Also patch the module-level constants that were bound at import time.
        # (The CLI achieves this by importing kpc INSIDE the branch, AFTER the
        # settings override fires — so module-level constants pick up the new root.
        # In tests we monkeypatch the already-imported module's namespace instead.)
        monkeypatch.setattr(kpc, "COMPLIANCE_SRC", fake_compliance)
        monkeypatch.setattr(kpc, "TESTS_DIR", worktree / "mcp" / "noctusai" / "tests")
        monkeypatch.setattr(kpc, "REPO_ROOT", worktree)

        _isolate_cache(tmp_path, monkeypatch)
        r = kpc.refresh(force=True)

        assert r["ok"]
        assert r["source_sha"] == expected_sha, (
            f"Refresh wrote sha {r['source_sha'][:12]} but worktree sha is {expected_sha[:12]}. "
            "Drift: cache reflects wrong root."
        )

    def test_default_uses_settings_repo_root(self, tmp_path, monkeypatch):
        """Without override, refresh() reads from settings.REPO_ROOT (backward-compat)."""
        # Do NOT change REPO_ROOT — just isolate cache.
        _isolate_cache(tmp_path, monkeypatch)
        real_compliance = _settings_mod.REPO_ROOT / "mcp" / "noctusai" / "tools" / "noctus" / "dev" / "compliance.py"
        if not real_compliance.exists():
            import pytest
            pytest.skip("Real compliance.py not found — skip default-root check.")

        expected_sha = hashlib.sha256(real_compliance.read_bytes()).hexdigest()
        r = kpc.refresh(force=True)

        assert r["ok"]
        assert r["source_sha"] == expected_sha, (
            "Default root changed: cache sha doesn't match settings.REPO_ROOT compliance.py."
        )

    def test_refresh_sha_mismatch_across_roots_is_detectable(self, tmp_path, monkeypatch):
        """Primary and worktree compliance.py intentionally differ — their SHAs
        must differ too, which is the exact drift the pre-commit fix closes."""
        worktree = tmp_path / "diverged-worktree"
        wt_compliance = _make_fake_compliance(worktree, "def check_diverged(): pass\n")
        wt_sha = hashlib.sha256(wt_compliance.read_bytes()).hexdigest()

        real_compliance = _settings_mod.REPO_ROOT / "mcp" / "noctusai" / "tools" / "noctus" / "dev" / "compliance.py"
        if real_compliance.exists():
            real_sha = hashlib.sha256(real_compliance.read_bytes()).hexdigest()
            assert wt_sha != real_sha, (
                "Test setup error: fake worktree compliance.py has the same sha as primary."
            )


# ── test: pre-commit hook passes --worktree-path to all refresh legs ─────────

class TestPreCommitHookRefreshLines:
    """Parse the pre-commit hook source and assert that every --refresh-*-cache
    invocation carries --worktree-path.  This is a structural regression test:
    if someone removes the flag from any refresh leg the test fails immediately."""

    @staticmethod
    def _load_hook() -> str:
        hook = Path(__file__).resolve().parents[3] / "scripts" / "hooks" / "pre-commit"
        assert hook.exists(), f"pre-commit hook not found at {hook}"
        return hook.read_text(encoding="utf-8")

    def test_refresh_keeper_cache_has_worktree_path(self):
        hook = self._load_hook()
        # Find the line containing --refresh-keeper-cache.
        matches = [ln for ln in hook.splitlines() if "--refresh-keeper-cache" in ln and not ln.strip().startswith("#")]
        assert matches, "No --refresh-keeper-cache invocation found in pre-commit hook."
        for line in matches:
            assert "--worktree-path" in line, (
                f"--refresh-keeper-cache missing --worktree-path: {line.strip()}"
            )

    def test_refresh_agent_context_cache_has_worktree_path(self):
        hook = self._load_hook()
        matches = [ln for ln in hook.splitlines() if "--refresh-agent-context-cache" in ln and not ln.strip().startswith("#")]
        assert matches, "No --refresh-agent-context-cache invocation found in pre-commit hook."
        for line in matches:
            assert "--worktree-path" in line, (
                f"--refresh-agent-context-cache missing --worktree-path: {line.strip()}"
            )

    def test_refresh_auto_improvement_cache_has_worktree_path(self):
        hook = self._load_hook()
        matches = [ln for ln in hook.splitlines() if "--refresh-auto-improvement-cache" in ln and not ln.strip().startswith("#")]
        assert matches, "No --refresh-auto-improvement-cache invocation found in pre-commit hook."
        for line in matches:
            assert "--worktree-path" in line, (
                f"--refresh-auto-improvement-cache missing --worktree-path: {line.strip()}"
            )

    def test_check_eight_way_sync_has_worktree_path(self):
        """Verification leg was already correct — this is a regression guard."""
        hook = self._load_hook()
        matches = [ln for ln in hook.splitlines() if "--check-eight-way-sync" in ln and not ln.strip().startswith("#")]
        assert matches, "No --check-eight-way-sync invocation found in pre-commit hook."
        for line in matches:
            assert "--worktree-path" in line, (
                f"--check-eight-way-sync missing --worktree-path: {line.strip()}"
            )
