"""Tests for the keeper-pattern cache (`keeper_pattern_cache.py`)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import hashlib
import sqlite3
import time

from tools.noctus.dev import keeper_pattern_cache as kpc


def _isolate_cache(tmp_path, monkeypatch) -> None:
    """Point the cache module's paths at a tmp dir (still reads REAL compliance.py + tests)."""
    cache_dir = tmp_path / "cache"
    monkeypatch.setattr(kpc, "CACHE_DIR", cache_dir)
    monkeypatch.setattr(kpc, "CACHE_PATH", cache_dir / "keeper-patterns.sqlite")


class TestRefresh:
    def test_refresh_creates_cache_with_rows(self, tmp_path, monkeypatch):
        _isolate_cache(tmp_path, monkeypatch)
        r = kpc.refresh(force=True)
        assert r["ok"] and r["status"] == "rebuilt"
        assert r["rows_written"] > 0
        assert kpc.CACHE_PATH.exists()

    def test_refresh_in_sync_short_circuits(self, tmp_path, monkeypatch):
        _isolate_cache(tmp_path, monkeypatch)
        kpc.refresh(force=True)
        r2 = kpc.refresh(force=False)
        assert r2["status"] == "in-sync"
        assert r2["rows_written"] == 0

    def test_refresh_force_rebuilds_even_when_in_sync(self, tmp_path, monkeypatch):
        _isolate_cache(tmp_path, monkeypatch)
        first = kpc.refresh(force=True)
        forced = kpc.refresh(force=True)
        assert forced["status"] == "rebuilt"
        assert forced["rows_written"] == first["rows_written"]


class TestSchemaAndMeta:
    def test_cache_meta_source_sha_matches_compliance_hash(self, tmp_path, monkeypatch):
        _isolate_cache(tmp_path, monkeypatch)
        kpc.refresh(force=True)
        expected = hashlib.sha256(kpc.COMPLIANCE_SRC.read_bytes()).hexdigest()
        conn = sqlite3.connect(str(kpc.CACHE_PATH))
        row = conn.execute(
            "SELECT value FROM cache_meta WHERE key='source_sha'"
        ).fetchone()
        conn.close()
        assert row and row[0] == expected


class TestLookup:
    def test_lookup_by_keeper_name_returns_rows(self, tmp_path, monkeypatch):
        _isolate_cache(tmp_path, monkeypatch)
        kpc.refresh(force=True)
        rows = kpc.lookup(keeper_name="agent_format")
        assert rows, "expected rows for check_agent_format"
        assert all("agent_format" in r["keeper_name"] for r in rows)

    def test_lookup_by_file_path_for_agent_md(self, tmp_path, monkeypatch):
        _isolate_cache(tmp_path, monkeypatch)
        kpc.refresh(force=True)
        rows = kpc.lookup(file_path=".claude/agents/devops-engineer.md")
        names = {r["keeper_name"] for r in rows}
        assert any(
            "agent_format" in n or "agent_archetype" in n for n in names
        ), f"expected agent-format/archetype hits, got {sorted(names)[:5]}"

    def test_lookup_combined_filters(self, tmp_path, monkeypatch):
        _isolate_cache(tmp_path, monkeypatch)
        kpc.refresh(force=True)
        rows = kpc.lookup(
            keeper_name="agent_format", file_path=".claude/agents/x.md"
        )
        assert rows
        assert all("agent_format" in r["keeper_name"] for r in rows)

    def test_lookup_no_filters_returns_all_permanent(self, tmp_path, monkeypatch):
        _isolate_cache(tmp_path, monkeypatch)
        kpc.refresh(force=True)
        rows = kpc.lookup()
        assert len(rows) > 10  # the real compliance.py has many keepers
        assert all(r["scope"] == "permanent" for r in rows)


class TestSetMembership:
    def test_harness_executor_agents_extracted_with_devops(self, tmp_path, monkeypatch):
        _isolate_cache(tmp_path, monkeypatch)
        kpc.refresh(force=True)
        rows = kpc.lookup(keeper_name="_HARNESS_EXECUTOR_AGENTS")
        assert rows, "must extract _HARNESS_EXECUTOR_AGENTS"
        members = rows[0]["pattern_value"].split(",")
        # devops-engineer added 2026-05-25 (the prior commit on this dev line)
        assert "devops-engineer" in members
        assert "backend-engineer" in members
        assert "engineer-seed" in members

    def test_set_membership_severity_high(self, tmp_path, monkeypatch):
        _isolate_cache(tmp_path, monkeypatch)
        kpc.refresh(force=True)
        rows = kpc.lookup(keeper_name="_HARNESS_")
        assert rows
        assert all(r["severity"] == "high" for r in rows if r["pattern_kind"] == "set-membership")


class TestFixtureExtraction:
    def test_fixtures_extracted_from_agent_format_tests(self, tmp_path, monkeypatch):
        _isolate_cache(tmp_path, monkeypatch)
        kpc.refresh(force=True)
        rows = kpc.lookup(keeper_name="check_agent_format")
        kinds = {r["pattern_kind"] for r in rows}
        assert "fixture-example" in kinds, f"expected fixture extraction, got {kinds}"


class TestSessionLane:
    def test_session_set_get_roundtrip(self, tmp_path, monkeypatch):
        _isolate_cache(tmp_path, monkeypatch)
        kpc.refresh(force=True)
        sid = "test-roundtrip"
        kpc.session_set(sid, "k1", "v1")
        kpc.session_set(sid, "k2", "v2")
        out = kpc.session_get(sid)
        assert len(out) == 2
        assert {r["keeper_name"] for r in out} == {"k1", "k2"}

    def test_session_sweep_removes_aged_rows(self, tmp_path, monkeypatch):
        _isolate_cache(tmp_path, monkeypatch)
        kpc.refresh(force=True)
        kpc.session_set("expire-test", "k", "v")
        time.sleep(1.1)  # ensure cached_at < cutoff when ttl=0
        removed = kpc.sweep_session(ttl_hours=0)
        assert removed >= 1
        # permanent rows untouched
        assert kpc.lookup() != []

    def test_session_get_specific_key(self, tmp_path, monkeypatch):
        _isolate_cache(tmp_path, monkeypatch)
        kpc.refresh(force=True)
        sid = "specific"
        kpc.session_set(sid, "alpha", "1")
        kpc.session_set(sid, "beta", "2")
        out = kpc.session_get(sid, key="alpha")
        assert len(out) == 1 and out[0]["pattern_value"] == "1"


class TestLazyFreshness:
    def test_lookup_self_heals_stale_cache(self, tmp_path, monkeypatch):
        _isolate_cache(tmp_path, monkeypatch)
        kpc.refresh(force=True)
        # Tamper with source_sha to simulate stale cache.
        conn = sqlite3.connect(str(kpc.CACHE_PATH))
        conn.execute(
            "UPDATE cache_meta SET value='stale-sha' WHERE key='source_sha'"
        )
        conn.commit()
        conn.close()
        # lookup() must rebuild because source_sha mismatch.
        rows = kpc.lookup(keeper_name="agent_format")
        assert rows
        conn = sqlite3.connect(str(kpc.CACHE_PATH))
        row = conn.execute(
            "SELECT value FROM cache_meta WHERE key='source_sha'"
        ).fetchone()
        conn.close()
        expected = hashlib.sha256(kpc.COMPLIANCE_SRC.read_bytes()).hexdigest()
        assert row[0] == expected


class TestListKeepers:
    def test_list_keepers_returns_distinct_names(self, tmp_path, monkeypatch):
        _isolate_cache(tmp_path, monkeypatch)
        kpc.refresh(force=True)
        names = kpc.list_keepers()
        assert len(names) > 10
        assert len(names) == len(set(names))
        assert any("agent_format" in n for n in names)
