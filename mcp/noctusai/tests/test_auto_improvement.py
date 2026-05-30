"""Regression tests for the scoped-auto-improvement ledger + cache +
`check_auto_improvement_cache_freshness` keeper.

KB § PATTERNS/common/scoped-auto-improvement.md. Phase B (2026-05-26).
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import auto_improvement as ai  # noqa: E402
from tools.noctus.dev.compliance import check_auto_improvement_cache_freshness  # noqa: E402


@pytest.fixture
def tmp_repo(tmp_path, monkeypatch):
    monkeypatch.setattr(ai, "CACHE_DIR", tmp_path / ".claude" / "cache")
    monkeypatch.setattr(ai, "CACHE_PATH", tmp_path / ".claude" / "cache" / "auto-improvement.sqlite")
    monkeypatch.setattr(ai, "LEDGER_PATH", tmp_path / "project-history" / "auto-improvement.ndjson")
    return tmp_path


class TestLogEntry:
    def test_log_appends_to_ndjson(self, tmp_repo):
        r = ai.log_entry(
            scope="scoped", kind="drift",
            target=".claude/agents/backend-engineer.md",
            description="Pydantic silent-drop in routers.example",
            agent="backend-engineer",
        )
        assert r["ok"] is True
        text = ai.LEDGER_PATH.read_text(encoding="utf-8")
        line = text.strip()
        e = json.loads(line)
        assert e["scope"] == "scoped"
        assert e["kind"] == "drift"
        assert e["target"] == ".claude/agents/backend-engineer.md"
        assert e["status"] == "s1-emergent"  # default

    def test_invalid_scope_rejected(self, tmp_repo):
        r = ai.log_entry(scope="invalid", kind="drift", target="*", description="x")
        assert r["ok"] is False
        assert "scope must be one of" in r["error"]

    def test_invalid_kind_rejected(self, tmp_repo):
        r = ai.log_entry(scope="scoped", kind="bogus", target="*", description="x")
        assert r["ok"] is False
        assert "kind must be one of" in r["error"]

    def test_invalid_status_rejected(self, tmp_repo):
        r = ai.log_entry(scope="scoped", kind="drift", target="*", description="x", status="bogus")
        assert r["ok"] is False
        assert "status must be one of" in r["error"]


class TestRefreshAndQuery:
    def test_refresh_populates_cache(self, tmp_repo):
        ai.log_entry(scope="broad", kind="improvement", target="*", description="A pattern", agent="tech-lead")
        ai.log_entry(scope="scoped", kind="drift", target=".claude/agents/x.md", description="B drift", agent="alpha")
        r = ai.refresh(force=True)
        assert r["status"] == "rebuilt"
        assert r["rows_written"] == 2

    def test_idempotent_short_circuit(self, tmp_repo):
        ai.log_entry(scope="broad", kind="improvement", target="*", description="X", agent="tech-lead")
        ai.refresh(force=True)
        r2 = ai.refresh()
        assert r2["status"] == "in-sync"

    def test_lazy_rebuild_on_sha_mismatch(self, tmp_repo):
        ai.log_entry(scope="broad", kind="drift", target="t1", description="first", agent="tl")
        ai.refresh(force=True)
        # Add a new entry — sha drifts; next query rebuilds.
        ai.log_entry(scope="broad", kind="drift", target="t2", description="second", agent="tl")
        rows = ai.query()
        assert len(rows) == 2

    def test_query_filters_by_target(self, tmp_repo):
        ai.log_entry(scope="broad", kind="drift", target=".claude/agents/a.md", description="x", agent="tl")
        ai.log_entry(scope="broad", kind="drift", target=".claude/agents/b.md", description="y", agent="tl")
        ai.log_entry(scope="broad", kind="drift", target="KB § PATTERNS/z.md", description="z", agent="tl")
        ai.refresh(force=True)
        rows_a = ai.query(target=".claude/agents/a.md")
        assert len(rows_a) == 1
        rows_agents = ai.query(target=".claude/agents/")  # substring
        assert len(rows_agents) == 2
        rows_kb = ai.query(target="KB §")
        assert len(rows_kb) == 1

    def test_query_open_only_excludes_closed(self, tmp_repo):
        ai.log_entry(scope="broad", kind="drift", target="t1", description="x", agent="tl", status="s1-emergent")
        ai.log_entry(scope="broad", kind="drift", target="t2", description="y", agent="tl", status="closed")
        ai.refresh(force=True)
        rows = ai.query(open_only=True)
        targets = {r["target"] for r in rows}
        assert "t1" in targets
        assert "t2" not in targets

    def test_query_filter_by_kind(self, tmp_repo):
        ai.log_entry(scope="broad", kind="drift", target="t1", description="x", agent="tl")
        ai.log_entry(scope="broad", kind="improvement", target="t1", description="y", agent="tl")
        ai.refresh(force=True)
        assert len(ai.query(kind="drift")) == 1
        assert len(ai.query(kind="improvement")) == 1

    def test_malformed_ndjson_line_skipped(self, tmp_repo):
        ai.log_entry(scope="broad", kind="drift", target="t1", description="x", agent="tl")
        # Write a malformed line directly.
        with ai.LEDGER_PATH.open("a", encoding="utf-8") as f:
            f.write("not valid json at all\n")
        ai.log_entry(scope="broad", kind="drift", target="t2", description="y", agent="tl")
        ai.refresh(force=True)
        rows = ai.query()
        # Two valid entries; the malformed line was silently skipped.
        targets = {r["target"] for r in rows}
        assert targets == {"t1", "t2"}


class TestFreshnessKeeper:
    def test_fresh_repo_no_issues(self, tmp_repo):
        # No ndjson present → keeper silently passes.
        issues = check_auto_improvement_cache_freshness(repo_root=tmp_repo)
        assert issues == []

    def test_cache_missing_when_ndjson_exists_flagged(self, tmp_repo, monkeypatch):
        # Disable Tier-2 auto-pull so the missing cache stays missing (else the
        # Tier-1 resolver would pull it from the prod mirror and create it).
        monkeypatch.setenv("NOCTUS_DISABLE_AUTO_CACHE_PULL", "1")
        # Write the ndjson directly (without the helper, so the cache isn't built).
        ai.LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
        ai.LEDGER_PATH.write_text(
            json.dumps({
                "ts": "2026-05-26", "agent": "tl", "scope": "broad", "kind": "drift",
                "target": "*", "description": "x", "status": "s1-emergent", "source_ref": None,
            }) + "\n",
            encoding="utf-8",
        )
        issues = check_auto_improvement_cache_freshness(repo_root=tmp_repo)
        assert any(i["symbol"] == "auto-improvement-cache-missing" for i in issues)

    def test_clean_state_passes(self, tmp_repo):
        ai.log_entry(scope="broad", kind="improvement", target="*", description="X", agent="tl")
        ai.refresh(force=True)
        issues = check_auto_improvement_cache_freshness(repo_root=tmp_repo)
        assert issues == []
