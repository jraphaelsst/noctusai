"""Regression tests for `code_baseline` — ratified-canonical layer for
code recurrence findings. Sister tests to `test_kb_baseline`.

KB § CONTEXT/PATTERNS/common/code-recurrence-baseline.md.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import code_baseline as cb  # noqa: E402


# ── Fixtures ─────────────────────────────────────────────────────────────────
@pytest.fixture
def tmp_baselines(tmp_path, monkeypatch):
    """Isolate BASELINE_DIR + REPO_ROOT to a tmp tree with a fake cache."""
    baseline_dir = tmp_path / "project-history" / "code-baselines"
    baseline_dir.mkdir(parents=True)
    monkeypatch.setattr(cb, "BASELINE_DIR", baseline_dir)
    monkeypatch.setattr(cb, "REPO_ROOT", tmp_path)
    # Seed a fake mcp/ tree so the keeper proceeds past the tracked-roots guard.
    (tmp_path / "mcp").mkdir()
    # Seed a fake code-embeddings cache with deterministic rows for sha calc.
    cache_dir = tmp_path / ".claude" / "cache"
    cache_dir.mkdir(parents=True)
    cache = cache_dir / "code-embeddings.sqlite"
    conn = sqlite3.connect(str(cache))
    conn.execute(
        "CREATE TABLE code_chunks (path TEXT, symbol_name TEXT, source_sha TEXT)"
    )
    conn.execute(
        "INSERT INTO code_chunks VALUES (?, ?, ?)",
        ("mcp/a.py", "alpha", "sha-aaa"),
    )
    conn.execute(
        "INSERT INTO code_chunks VALUES (?, ?, ?)",
        ("mcp/b.py", "beta", "sha-bbb"),
    )
    conn.commit()
    conn.close()
    return tmp_path


def _match(p1="p1.py", s1="f", p2="p2.py", s2="g", score=0.85):
    return {
        "score": score,
        "band": "medium",
        "a": {"path": p1, "symbol_name": s1, "kind": "function"},
        "b": {"path": p2, "symbol_name": s2, "kind": "function"},
    }


# ── _pair_key (canonical key) ──────────────────────────────────────────────
class TestPairKey:
    def test_symmetric(self):
        a = _match("p1.py", "x", "p2.py", "y")
        b = _match("p2.py", "y", "p1.py", "x")
        assert cb._pair_key(a) == cb._pair_key(b)

    def test_includes_both_paths_and_symbols(self):
        key = cb._pair_key(_match("a.py", "f", "b.py", "g"))
        assert "a.py" in key and "b.py" in key
        assert "f" in key and "g" in key


# ── _code_corpus_sha ────────────────────────────────────────────────────────
class TestCorpusSha:
    def test_deterministic_for_same_cache(self, tmp_baselines):
        sha1 = cb._code_corpus_sha(tmp_baselines)
        sha2 = cb._code_corpus_sha(tmp_baselines)
        assert sha1 == sha2
        assert sha1

    def test_changes_when_cache_changes(self, tmp_baselines):
        sha1 = cb._code_corpus_sha(tmp_baselines)
        cache = tmp_baselines / ".claude" / "cache" / "code-embeddings.sqlite"
        conn = sqlite3.connect(str(cache))
        conn.execute(
            "INSERT INTO code_chunks VALUES (?, ?, ?)",
            ("mcp/c.py", "gamma", "sha-ccc"),
        )
        conn.commit()
        conn.close()
        sha2 = cb._code_corpus_sha(tmp_baselines)
        assert sha1 != sha2

    def test_empty_when_no_cache(self, tmp_path):
        # No cache file → empty string.
        assert cb._code_corpus_sha(tmp_path) == ""


# ── ratify ──────────────────────────────────────────────────────────────────
class TestRatify:
    def test_empty_reason_rejected(self, tmp_baselines):
        result = cb.ratify("")
        assert not result["ok"]
        assert "reason" in result["error"].lower()

    def test_writes_baseline_file(self, tmp_baselines):
        matches = [_match("a.py", "x", "b.py", "y"), _match("a.py", "z", "c.py", "w")]
        result = cb.ratify("two reviewed pairs", matches=matches)
        assert result["ok"]
        assert result["pair_count"] == 2
        target = tmp_baselines / result["path"]
        assert target.exists()
        payload = json.loads(target.read_text())
        assert payload["pair_count"] == 2
        assert payload["reason"] == "two reviewed pairs"

    def test_same_day_same_corpus_does_not_overwrite(self, tmp_baselines):
        r1 = cb.ratify("first", matches=[_match()])
        r2 = cb.ratify("second", matches=[_match("x.py", "z", "y.py", "w")])
        assert r1["baseline_id"] != r2["baseline_id"]
        assert (tmp_baselines / r1["path"]).exists()
        assert (tmp_baselines / r2["path"]).exists()

    def test_ratify_uses_live_scan_when_matches_omitted(self, tmp_baselines, monkeypatch):
        # Stub _current_matches to return a known fixture.
        live = [_match("auto.py", "f", "auto2.py", "g")]
        monkeypatch.setattr(cb, "_current_matches", lambda threshold=0.7: live)
        result = cb.ratify("auto-pulled")
        assert result["pair_count"] == 1


# ── list / latest ────────────────────────────────────────────────────────────
class TestListAndLatest:
    def test_empty_when_no_baselines(self, tmp_baselines):
        assert cb.list_baselines() == []
        assert cb.latest() is None

    def test_chronological_order(self, tmp_baselines):
        cb.ratify("first", matches=[_match()])
        # Mutate cache so the second ratification gets a different corpus_sha.
        cache = tmp_baselines / ".claude" / "cache" / "code-embeddings.sqlite"
        conn = sqlite3.connect(str(cache))
        conn.execute(
            "INSERT INTO code_chunks VALUES (?, ?, ?)",
            ("mcp/d.py", "delta", "sha-ddd"),
        )
        conn.commit()
        conn.close()
        cb.ratify("second", matches=[_match("z.py", "z", "w.py", "w")])
        lst = cb.list_baselines()
        assert len(lst) == 2
        assert lst[0]["ratified_at"] <= lst[1]["ratified_at"]


# ── diff ─────────────────────────────────────────────────────────────────────
class TestDiff:
    def test_no_baseline_treats_all_as_new(self, tmp_baselines, monkeypatch):
        live = [_match(), _match("x.py", "y", "z.py", "w")]
        monkeypatch.setattr(cb, "_current_matches", lambda threshold=0.7: live)
        result = cb.diff()
        assert result["ok"]
        assert result["baseline_id"] is None
        assert len(result["new_matches"]) == 2

    def test_against_unknown_id_errors(self, tmp_baselines):
        cb.ratify("some", matches=[_match()])
        result = cb.diff(against="no-such-baseline")
        assert not result["ok"]

    def test_surfaces_only_new(self, tmp_baselines, monkeypatch):
        base = _match("a.py", "x", "b.py", "y")
        cb.ratify("base", matches=[base])
        live = [base, _match("a.py", "x", "c.py", "z")]  # 1 same + 1 new
        monkeypatch.setattr(cb, "_current_matches", lambda threshold=0.7: live)
        result = cb.diff()
        assert len(result["new_matches"]) == 1
        assert result["unchanged_count"] == 1

    def test_surfaces_resolved(self, tmp_baselines, monkeypatch):
        m1 = _match("a.py", "f", "b.py", "g")
        m2 = _match("c.py", "h", "d.py", "i")
        cb.ratify("base", matches=[m1, m2])
        # Now only m1 still surfaces.
        monkeypatch.setattr(cb, "_current_matches", lambda threshold=0.7: [m1])
        result = cb.diff()
        assert len(result["resolved_matches"]) == 1
        assert result["unchanged_count"] == 1

    def test_corpus_drift_flagged(self, tmp_baselines, monkeypatch):
        cb.ratify("base", matches=[])
        # Mutate cache → corpus sha changes.
        cache = tmp_baselines / ".claude" / "cache" / "code-embeddings.sqlite"
        conn = sqlite3.connect(str(cache))
        conn.execute(
            "INSERT INTO code_chunks VALUES (?, ?, ?)",
            ("mcp/new.py", "newfn", "sha-new"),
        )
        conn.commit()
        conn.close()
        monkeypatch.setattr(cb, "_current_matches", lambda threshold=0.7: [])
        result = cb.diff()
        assert result["code_corpus_drifted"] is True


# ── Keeper ──────────────────────────────────────────────────────────────────
class TestKeeperIntegration:
    def test_check_silent_without_mcp_dir(self, tmp_path):
        from tools.noctus.dev.compliance import check_code_recurrence_drift
        assert check_code_recurrence_drift(repo_root=tmp_path) == []

    def test_check_suggests_ratify_when_pairs_no_baseline(self, tmp_baselines, monkeypatch):
        monkeypatch.setattr(cb, "_current_matches", lambda threshold=0.7: [_match()])
        from tools.noctus.dev.compliance import check_code_recurrence_drift
        issues = check_code_recurrence_drift(repo_root=tmp_baselines)
        assert any(i["symbol"] == "code-baseline-missing" for i in issues)

    def test_check_fires_on_drift_above_threshold(self, tmp_baselines, monkeypatch):
        cb.ratify("empty baseline", matches=[])
        live = [_match(p1=f"{i}.py") for i in range(10)]
        monkeypatch.setattr(cb, "_current_matches", lambda threshold=0.7: live)
        from tools.noctus.dev.compliance import check_code_recurrence_drift
        issues = check_code_recurrence_drift(repo_root=tmp_baselines)
        assert any(i["symbol"] == "code-recurrence-drift" for i in issues)

    def test_check_silent_below_threshold(self, tmp_baselines, monkeypatch):
        cb.ratify("empty baseline", matches=[])
        # 2 new (below threshold 3).
        live = [_match(p1="a.py"), _match(p1="b.py")]
        monkeypatch.setattr(cb, "_current_matches", lambda threshold=0.7: live)
        from tools.noctus.dev.compliance import check_code_recurrence_drift
        issues = check_code_recurrence_drift(repo_root=tmp_baselines)
        assert not any(i["symbol"] == "code-recurrence-drift" for i in issues)
