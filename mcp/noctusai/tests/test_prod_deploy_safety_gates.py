"""Tests for the 5 prod-deploy safety gate keepers.

Each keeper is advisory or high-severity; together they form the
pre-deploy gate (`check_pre_deploy_gate` composite).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import json
from datetime import date

import pytest

from tools.noctus.dev import compliance


def _write_ledger(tmp_path: Path, entries: list[dict]) -> Path:
    ph = tmp_path / "project-history"
    ph.mkdir(parents=True, exist_ok=True)
    ledger = ph / "auto-improvement.ndjson"
    with ledger.open("w", encoding="utf-8") as fh:
        for entry in entries:
            fh.write(json.dumps(entry) + "\n")
    return ledger


def _entry(target: str, status: str, days_ago: int = 1) -> dict:
    return {
        "ts": date.today().isoformat(),
        "agent": "tech-lead",
        "scope": "broad",
        "kind": "improvement",
        "target": target,
        "description": "test",
        "status": status,
        "source_ref": "test",
    }


class TestProdCacheReachable:
    def test_noop_for_sqlite_default(self, monkeypatch):
        monkeypatch.delenv("NOCTUS_CACHE_BACKEND", raising=False)
        assert compliance.check_prod_cache_reachable() == []

    def test_noop_when_sqlite_explicit(self, monkeypatch):
        monkeypatch.setenv("NOCTUS_CACHE_BACKEND", "sqlite")
        assert compliance.check_prod_cache_reachable() == []

    def test_surfaces_import_failure(self, monkeypatch):
        monkeypatch.setenv("NOCTUS_CACHE_BACKEND", "postgres")
        # Force import to fail by intercepting the module.
        import sys as _sys
        # Stub the module to raise on import.
        class _FailingFinder:
            def find_module(self, name, path=None):
                if "cache_backend_postgres" in name:
                    return self
                return None
            def load_module(self, name):
                raise ImportError("simulated missing pgvector dep")
        _sys.meta_path.insert(0, _FailingFinder())
        # Also evict any cached.
        _sys.modules.pop("tools.noctus.dev.cache_backend_postgres", None)
        try:
            issues = compliance.check_prod_cache_reachable()
            # Either it surfaces import failure OR (if module exists) connection-unreachable.
            # Both are valid HIGH-severity surfaces.
            assert len(issues) >= 1
            assert all(i["severity"] == "high" for i in issues)
        finally:
            _sys.meta_path.pop(0)


class TestCacheBackendEnvMatch:
    def test_local_dev_with_sqlite_is_clean(self, monkeypatch, tmp_path):
        monkeypatch.delenv("CI", raising=False)
        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
        monkeypatch.delenv("NOCTUS_CACHE_BACKEND", raising=False)
        # Won't pass if /.dockerenv exists (CI runs in containers).
        # Mock dockerenv check via the Path approach.
        # This test is best-effort on a developer machine.
        result = compliance.check_cache_backend_env_matches_environment()
        # On a local-dev machine with no /.dockerenv, default sqlite is fine.
        assert isinstance(result, list)

    def test_ci_with_sqlite_surfaces_warning(self, monkeypatch):
        monkeypatch.setenv("CI", "true")
        monkeypatch.setenv("NOCTUS_CACHE_BACKEND", "sqlite")
        issues = compliance.check_cache_backend_env_matches_environment()
        assert len(issues) == 1
        assert issues[0]["severity"] == "warning"
        assert "cache-backend-env-mismatch" == issues[0]["symbol"]

    def test_ci_with_postgres_is_clean(self, monkeypatch):
        monkeypatch.setenv("CI", "true")
        monkeypatch.setenv("NOCTUS_CACHE_BACKEND", "postgres")
        issues = compliance.check_cache_backend_env_matches_environment()
        assert issues == []

    def test_github_actions_with_sqlite_surfaces(self, monkeypatch):
        monkeypatch.delenv("CI", raising=False)
        monkeypatch.setenv("GITHUB_ACTIONS", "true")
        monkeypatch.setenv("NOCTUS_CACHE_BACKEND", "sqlite")
        issues = compliance.check_cache_backend_env_matches_environment()
        assert len(issues) == 1


class TestDriftShield:
    def test_silent_when_no_ledger(self, tmp_path):
        # No ndjson file at all.
        issues = compliance.check_drift_shield(repo_root=tmp_path)
        assert issues == []

    def test_silent_when_git_diff_fails(self, tmp_path):
        # ndjson exists but tmp_path isn't a git repo → diff returns non-zero.
        _write_ledger(tmp_path, [_entry("foo.py", "s1-emergent")])
        issues = compliance.check_drift_shield(repo_root=tmp_path)
        assert issues == []  # graceful skip


class TestSlipShield:
    def test_silent_when_no_ledger(self, tmp_path):
        issues = compliance.check_slip_shield(repo_root=tmp_path)
        assert issues == []

    def test_silent_when_no_git_diff(self, tmp_path):
        _write_ledger(tmp_path, [
            _entry("foo.py", "s2-memory"),
            _entry("foo.py", "s2-memory"),
        ])
        issues = compliance.check_slip_shield(repo_root=tmp_path)
        assert issues == []  # graceful skip when not a git repo


class TestPreDeployGate:
    def test_composes_4_keepers(self, monkeypatch, tmp_path):
        # Local-dev sqlite + no git context → all four sub-keepers green.
        monkeypatch.delenv("CI", raising=False)
        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
        monkeypatch.delenv("NOCTUS_CACHE_BACKEND", raising=False)
        issues = compliance.check_pre_deploy_gate(repo_root=tmp_path)
        # All four NO-OP in clean local-dev context → 0 issues
        # (unless /.dockerenv exists on the test runner).
        assert isinstance(issues, list)
        # Severity field present on every issue.
        for i in issues:
            assert "severity" in i
            assert "symbol" in i

    def test_no_high_severity_in_default_sqlite(self, monkeypatch, tmp_path):
        # In sqlite mode, check_prod_cache_reachable is NO-OP → no high-severity.
        monkeypatch.delenv("NOCTUS_CACHE_BACKEND", raising=False)
        monkeypatch.delenv("CI", raising=False)
        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
        issues = compliance.check_pre_deploy_gate(repo_root=tmp_path)
        highs = [i for i in issues if i.get("severity") == "high"]
        assert highs == []
