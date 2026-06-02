"""Tests for the absorption-tracking ledger + cache (9th keeper-mirror).

Covers:
  - append → derive round-trip (latest-event-wins)
  - status read + lazy rebuild
  - freshness keeper (sha mismatch detected)
  - heal-on-contact rebuild
  - enum validation refusal
  - query_capabilities filters

KB § PATTERNS/common/absorption-tracking.md (tech-lead wires after integration).
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import absorption_tracking as ab  # noqa: E402
from tools.noctus.dev.compliance import check_absorptions_cache_freshness  # noqa: E402


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_env(tmp_path, monkeypatch):
    """Redirect ledger + cache paths to a temporary directory."""
    ledger = tmp_path / "project-history" / "absorptions.ndjson"
    cache = tmp_path / "cache" / "absorptions.sqlite"
    monkeypatch.setattr(ab, "LEDGER_PATH", ledger)
    monkeypatch.setattr(ab, "CACHE_PATH", cache)
    monkeypatch.setattr(ab, "CACHE_DIR", cache.parent)
    return tmp_path, ledger, cache


# ── TestLogEntry ──────────────────────────────────────────────────────────────

class TestLogEntry:
    def test_lifecycle_appends_to_ndjson(self, tmp_env):
        _, ledger, _ = tmp_env
        r = ab.log_entry(
            slug="orbity", kind="lifecycle", stage="diagnosed",
            source_repo="github.com/foo/bar.git", source_head="abc123",
            note="initial diagnosis",
        )
        assert r["ok"] is True
        text = ledger.read_text(encoding="utf-8")
        e = json.loads(text.strip())
        assert e["slug"] == "orbity"
        assert e["stage"] == "diagnosed"
        assert e["source_repo"] == "github.com/foo/bar.git"
        assert e["kind"] == "lifecycle"

    def test_capability_appends_to_ndjson(self, tmp_env):
        _, ledger, _ = tmp_env
        r = ab.log_entry(
            slug="orbity", kind="capability",
            capability="financial-management",
            target_organ="noctusai_lib.domain.finance",
            status="identified", pilot="erp-imobiliario",
        )
        assert r["ok"] is True
        e = json.loads(ledger.read_text(encoding="utf-8").strip())
        assert e["capability"] == "financial-management"
        assert e["target_organ"] == "noctusai_lib.domain.finance"
        assert e["status"] == "identified"
        assert e["pilot"] == "erp-imobiliario"

    def test_invalid_kind_rejected(self, tmp_env):
        r = ab.log_entry(slug="x", kind="unknown_kind")
        assert r["ok"] is False
        assert "kind must be one of" in r["error"]

    def test_invalid_stage_rejected(self, tmp_env):
        r = ab.log_entry(slug="x", kind="lifecycle", stage="teleport")
        assert r["ok"] is False
        assert "stage must be one of" in r["error"]

    def test_invalid_capability_status_rejected(self, tmp_env):
        r = ab.log_entry(
            slug="x", kind="capability",
            capability="foo", target_organ="bar", status="launched"
        )
        assert r["ok"] is False
        assert "status must be one of" in r["error"]

    def test_missing_stage_for_lifecycle_rejected(self, tmp_env):
        r = ab.log_entry(slug="x", kind="lifecycle")
        assert r["ok"] is False
        assert "stage is required" in r["error"]

    def test_missing_capability_fields_rejected(self, tmp_env):
        r = ab.log_entry(slug="x", kind="capability", capability="foo")
        assert r["ok"] is False
        assert "target_organ is required" in r["error"]

    def test_missing_capability_status_rejected(self, tmp_env):
        r = ab.log_entry(
            slug="x", kind="capability",
            capability="foo", target_organ="bar",
        )
        assert r["ok"] is False
        assert "status is required" in r["error"]


# ── TestRefresh ───────────────────────────────────────────────────────────────

class TestRefresh:
    def test_rebuild_populates_absorptions_and_capabilities(self, tmp_env):
        _, ledger, cache = tmp_env
        ab.log_entry(slug="orbity", kind="lifecycle", stage="diagnosed", note="diag")
        ab.log_entry(
            slug="orbity", kind="capability",
            capability="fin-mgmt", target_organ="noctusai_lib.domain.finance",
            status="identified", pilot="erp",
        )
        r = ab.refresh(force=True, ledger=ledger, cache=cache)
        assert r["status"] == "rebuilt"
        assert r["rows_written"] == 2

    def test_idempotent_short_circuit(self, tmp_env):
        _, ledger, cache = tmp_env
        ab.log_entry(slug="orbity", kind="lifecycle", stage="done")
        ab.refresh(force=True, ledger=ledger, cache=cache)
        r2 = ab.refresh(ledger=ledger, cache=cache)
        assert r2["status"] == "in-sync"

    def test_latest_event_wins_lifecycle(self, tmp_env):
        """Two lifecycle events for the same slug: the last one's stage is kept."""
        _, ledger, cache = tmp_env
        ab.log_entry(
            slug="orbity", kind="lifecycle", stage="diagnosed",
            ts="2026-06-02T00:00:00+00:00",
        )
        ab.log_entry(
            slug="orbity", kind="lifecycle", stage="uplifting",
            ts="2026-06-02T01:00:00+00:00",
        )
        r = ab.refresh(force=True, ledger=ledger, cache=cache)
        assert r["rows_written"] == 1  # only one absorption row
        conn = sqlite3.connect(str(cache))
        row = conn.execute("SELECT stage FROM absorptions WHERE slug='orbity'").fetchone()
        conn.close()
        assert row[0] == "uplifting"

    def test_latest_event_wins_capability(self, tmp_env):
        """Two capability events for (slug, capability): the last status wins."""
        _, ledger, cache = tmp_env
        ab.log_entry(
            slug="orbity", kind="capability",
            capability="fin-mgmt", target_organ="noctusai_lib.domain.finance",
            status="identified", ts="2026-06-02T00:00:00+00:00",
        )
        ab.log_entry(
            slug="orbity", kind="capability",
            capability="fin-mgmt", target_organ="noctusai_lib.domain.finance",
            status="building", ts="2026-06-02T01:00:00+00:00",
        )
        ab.refresh(force=True, ledger=ledger, cache=cache)
        conn = sqlite3.connect(str(cache))
        row = conn.execute(
            "SELECT status FROM capabilities WHERE slug='orbity' AND capability='fin-mgmt'"
        ).fetchone()
        conn.close()
        assert row[0] == "building"

    def test_empty_ledger_produces_empty_cache(self, tmp_env):
        _, ledger, cache = tmp_env
        ledger.parent.mkdir(parents=True, exist_ok=True)
        ledger.write_text("", encoding="utf-8")
        r = ab.refresh(force=True, ledger=ledger, cache=cache)
        assert r["rows_written"] == 0


# ── TestStatus ────────────────────────────────────────────────────────────────

class TestStatus:
    def test_status_returns_absorption_with_capabilities(self, tmp_env):
        _, ledger, cache = tmp_env
        ab.log_entry(slug="orbity", kind="lifecycle", stage="diagnosed")
        ab.log_entry(
            slug="orbity", kind="capability",
            capability="fin-mgmt", target_organ="noctusai_lib.domain.finance",
            status="identified", pilot="erp",
        )
        r = ab.status(ledger=ledger, cache=cache)
        assert r["ok"] is True
        assert len(r["absorptions"]) == 1
        a = r["absorptions"][0]
        assert a["slug"] == "orbity"
        assert a["stage"] == "diagnosed"
        assert len(a["capabilities"]) == 1
        assert a["capabilities"][0]["capability"] == "fin-mgmt"

    def test_status_lazy_rebuild_on_sha_mismatch(self, tmp_env):
        """Adding an entry after a refresh triggers a lazy rebuild on next status read."""
        _, ledger, cache = tmp_env
        ab.log_entry(slug="orbity", kind="lifecycle", stage="diagnosed")
        ab.refresh(force=True, ledger=ledger, cache=cache)
        # Add another absorption without calling refresh.
        ab.log_entry(slug="newco", kind="lifecycle", stage="cloned")
        r = ab.status(ledger=ledger, cache=cache)
        slugs = [a["slug"] for a in r["absorptions"]]
        assert "newco" in slugs

    def test_status_filter_by_slug(self, tmp_env):
        _, ledger, cache = tmp_env
        ab.log_entry(slug="alpha", kind="lifecycle", stage="diagnosed")
        ab.log_entry(slug="beta", kind="lifecycle", stage="cloned")
        r = ab.status(slug="alpha", ledger=ledger, cache=cache)
        assert len(r["absorptions"]) == 1
        assert r["absorptions"][0]["slug"] == "alpha"

    def test_status_filter_by_stage(self, tmp_env):
        _, ledger, cache = tmp_env
        ab.log_entry(slug="alpha", kind="lifecycle", stage="diagnosed")
        ab.log_entry(slug="beta", kind="lifecycle", stage="cloned")
        r = ab.status(stage="cloned", ledger=ledger, cache=cache)
        assert all(a["stage"] == "cloned" for a in r["absorptions"])


# ── TestQueryCapabilities ─────────────────────────────────────────────────────

class TestQueryCapabilities:
    def test_filter_by_status(self, tmp_env):
        _, ledger, cache = tmp_env
        ab.log_entry(slug="orbity", kind="capability", capability="a",
                     target_organ="noctusai_lib.domain.x", status="identified")
        ab.log_entry(slug="orbity", kind="capability", capability="b",
                     target_organ="noctusai_lib.domain.y", status="building")
        rows = ab.query_capabilities(cap_status="identified", ledger=ledger, cache=cache)
        assert len(rows) == 1
        assert rows[0]["capability"] == "a"

    def test_filter_by_target_organ_substring(self, tmp_env):
        _, ledger, cache = tmp_env
        ab.log_entry(slug="orbity", kind="capability", capability="a",
                     target_organ="noctusai_lib.domain.finance", status="identified")
        ab.log_entry(slug="orbity", kind="capability", capability="b",
                     target_organ="noctusai_lib.integrations.meta", status="identified")
        rows = ab.query_capabilities(target_organ="noctusai_lib.domain.", ledger=ledger, cache=cache)
        assert len(rows) == 1
        assert rows[0]["capability"] == "a"

    def test_filter_by_slug(self, tmp_env):
        _, ledger, cache = tmp_env
        ab.log_entry(slug="alpha", kind="capability", capability="x",
                     target_organ="organ.a", status="identified")
        ab.log_entry(slug="beta", kind="capability", capability="y",
                     target_organ="organ.b", status="identified")
        rows = ab.query_capabilities(slug="alpha", ledger=ledger, cache=cache)
        assert len(rows) == 1
        assert rows[0]["slug"] == "alpha"


# ── TestAbsorptionsFreshness ──────────────────────────────────────────────────

class TestAbsorptionsFreshness:
    def test_no_issues_when_ndjson_absent(self, tmp_path):
        """Fresh repo with no absorptions.ndjson → keeper is silent."""
        root = tmp_path
        (root / "project-history").mkdir(parents=True, exist_ok=True)
        issues = check_absorptions_cache_freshness(repo_root=root)
        assert issues == []

    def test_missing_cache_reported(self, tmp_path):
        """ndjson exists but cache absent → issue reported."""
        root = tmp_path
        ledger = root / "project-history" / "absorptions.ndjson"
        ledger.parent.mkdir(parents=True, exist_ok=True)
        ledger.write_text(
            '{"ts":"2026-06-02T00:00:00+00:00","slug":"x","kind":"lifecycle","stage":"diagnosed","note":""}\n',
            encoding="utf-8",
        )
        issues = check_absorptions_cache_freshness(repo_root=root)
        assert any("absorptions-cache-missing" in i.get("symbol", "") for i in issues)

    def test_stale_cache_reported(self, tmp_path, monkeypatch):
        """ndjson sha ≠ cache.meta.source_sha → issue reported."""
        root = tmp_path
        ledger = root / "project-history" / "absorptions.ndjson"
        ledger.parent.mkdir(parents=True, exist_ok=True)
        line = '{"ts":"2026-06-02T00:00:00+00:00","slug":"x","kind":"lifecycle","stage":"diagnosed","note":""}\n'
        ledger.write_text(line, encoding="utf-8")

        # Create a cache with a WRONG source_sha to simulate staleness.
        import sqlite3 as _sq3
        from tools.noctus.dev.cache_backend import apply_locking_pragmas, cache_dir
        cache_d = cache_dir(root)
        cache_file = cache_d / "absorptions.sqlite"
        conn = _sq3.connect(str(cache_file))
        apply_locking_pragmas(conn)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        """)
        conn.execute("INSERT OR REPLACE INTO meta(key,value) VALUES ('source_sha','stale-sha')")
        conn.commit()
        conn.close()

        issues = check_absorptions_cache_freshness(repo_root=root)
        assert any("absorptions-cache-stale" in i.get("symbol", "") for i in issues)

    def test_fresh_cache_no_issues(self, tmp_path):
        """Cache matches ndjson sha → no issues."""
        root = tmp_path
        ledger = root / "project-history" / "absorptions.ndjson"
        ledger.parent.mkdir(parents=True, exist_ok=True)
        line = '{"ts":"2026-06-02T00:00:00+00:00","slug":"x","kind":"lifecycle","stage":"diagnosed","note":""}\n'
        ledger.write_text(line, encoding="utf-8")
        sha = hashlib.sha256(ledger.read_bytes()).hexdigest()

        from tools.noctus.dev.cache_backend import apply_locking_pragmas, cache_dir
        import sqlite3 as _sq3
        cache_d = cache_dir(root)
        cache_file = cache_d / "absorptions.sqlite"
        conn = _sq3.connect(str(cache_file))
        apply_locking_pragmas(conn)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        """)
        conn.execute("INSERT OR REPLACE INTO meta(key,value) VALUES ('source_sha',?)", (sha,))
        conn.commit()
        conn.close()

        issues = check_absorptions_cache_freshness(repo_root=root)
        assert issues == []

    def test_heal_on_contact_rebuild(self, tmp_path, monkeypatch):
        """After a stale log_entry append, status() triggers a lazy rebuild."""
        ledger = tmp_path / "project-history" / "absorptions.ndjson"
        cache = tmp_path / "cache" / "absorptions.sqlite"
        monkeypatch.setattr(ab, "LEDGER_PATH", ledger)
        monkeypatch.setattr(ab, "CACHE_PATH", cache)
        monkeypatch.setattr(ab, "CACHE_DIR", cache.parent)

        # Seed initial state.
        ab.log_entry(slug="orbity", kind="lifecycle", stage="diagnosed")
        ab.refresh(force=True, ledger=ledger, cache=cache)

        # Write directly to the ledger to simulate out-of-band mutation (no refresh).
        with ledger.open("a", encoding="utf-8") as f:
            import json as _json
            f.write(_json.dumps({
                "ts": "2026-06-02T02:00:00+00:00",
                "slug": "orbity",
                "kind": "lifecycle",
                "stage": "uplifting",
                "note": "heal test",
            }) + "\n")

        # status() must see the new state via lazy rebuild.
        r = ab.status(ledger=ledger, cache=cache)
        a = next(x for x in r["absorptions"] if x["slug"] == "orbity")
        assert a["stage"] == "uplifting"


# ── TestOrbitySeeds ───────────────────────────────────────────────────────────

class TestOrbitySeeds:
    """Validate that the seeded orbity events are loadable + round-trip correctly."""

    def test_orbity_ndjson_parses(self, tmp_env):
        import json as _json
        _, ledger, cache = tmp_env
        # Copy the real seeded file for this test.
        real_ledger = Path(__file__).resolve().parents[3] / "project-history" / "absorptions.ndjson"
        if not real_ledger.exists():
            pytest.skip("absorptions.ndjson not seeded yet")
        ledger.parent.mkdir(parents=True, exist_ok=True)
        ledger.write_bytes(real_ledger.read_bytes())
        r = ab.refresh(force=True, ledger=ledger, cache=cache)
        assert r["ok"] is True
        s = ab.status(slug="orbity", ledger=ledger, cache=cache)
        assert s["ok"] is True
        assert len(s["absorptions"]) == 1
        orbity = s["absorptions"][0]
        assert orbity["stage"] == "diagnosed"
        assert len(orbity["capabilities"]) == 5

    def test_orbity_capabilities_all_identified(self, tmp_env):
        real_ledger = Path(__file__).resolve().parents[3] / "project-history" / "absorptions.ndjson"
        if not real_ledger.exists():
            pytest.skip("absorptions.ndjson not seeded yet")
        _, ledger, cache = tmp_env
        ledger.parent.mkdir(parents=True, exist_ok=True)
        ledger.write_bytes(real_ledger.read_bytes())
        ab.refresh(force=True, ledger=ledger, cache=cache)
        rows = ab.query_capabilities(slug="orbity", ledger=ledger, cache=cache)
        assert len(rows) == 5
        assert all(r["status"] == "identified" for r in rows)
        caps = {r["capability"] for r in rows}
        assert caps == {
            "financial-management",
            "meta-capi-leadads",
            "automation-flow-engine",
            "multi-channel-notifications",
            "br-payment-fiscal",
        }
