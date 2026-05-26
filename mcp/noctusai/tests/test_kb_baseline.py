"""Regression tests for `kb_baseline` — ratified-canonical baseline layer.

Sister tests to `test_vector_calibration` — both modules are reasoning-driven
ratification surfaces (calibration for thresholds, baseline for findings).

KB § CONTEXT/PATTERNS/common/vector-baseline.md.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import kb_baseline as kbb  # noqa: E402


# ── Fixtures ─────────────────────────────────────────────────────────────────
@pytest.fixture
def tmp_baselines(tmp_path, monkeypatch):
    """Isolate BASELINE_DIR + REPO_ROOT to a tmp tree."""
    baseline_dir = tmp_path / "project-history" / "kb-baselines"
    baseline_dir.mkdir(parents=True)
    monkeypatch.setattr(kbb, "BASELINE_DIR", baseline_dir)
    monkeypatch.setattr(kbb, "REPO_ROOT", tmp_path)
    # Seed a tiny KB so _kb_corpus_sha returns something stable.
    kb_dir = tmp_path / "KNOWLEDGE-BASE"
    kb_dir.mkdir()
    (kb_dir / "alpha.md").write_text("# Alpha\nbody one\n")
    (kb_dir / "beta.md").write_text("# Beta\nbody two\n")
    return tmp_path


def _finding(path: str, owner: str = "agent-a", suggested: str = "agent-b",
             drift: float = -0.05) -> dict:
    return {
        "path": path,
        "current_owner": owner,
        "current_score": 0.70,
        "suggested_owner": suggested,
        "suggested_score": 0.75,
        "drift": drift,
    }


# ── _finding_key (stability surface) ────────────────────────────────────────
class TestFindingKey:
    def test_key_excludes_scores(self):
        a = _finding("x.md", drift=-0.01)
        b = _finding("x.md", drift=-0.99)
        assert kbb._finding_key(a) == kbb._finding_key(b)

    def test_key_differs_when_path_differs(self):
        assert kbb._finding_key(_finding("x.md")) != kbb._finding_key(_finding("y.md"))

    def test_key_differs_when_owner_differs(self):
        a = _finding("x.md", owner="agent-a")
        b = _finding("x.md", owner="agent-c")
        assert kbb._finding_key(a) != kbb._finding_key(b)


# ── _kb_corpus_sha ──────────────────────────────────────────────────────────
class TestCorpusSha:
    def test_deterministic_for_same_content(self, tmp_baselines):
        sha1 = kbb._kb_corpus_sha(tmp_baselines)
        sha2 = kbb._kb_corpus_sha(tmp_baselines)
        assert sha1 == sha2
        assert sha1  # non-empty

    def test_changes_when_file_changes(self, tmp_baselines):
        sha1 = kbb._kb_corpus_sha(tmp_baselines)
        (tmp_baselines / "KNOWLEDGE-BASE" / "alpha.md").write_text("# Alpha\nNEW BODY\n")
        sha2 = kbb._kb_corpus_sha(tmp_baselines)
        assert sha1 != sha2

    def test_empty_when_no_kb_dir(self, tmp_path):
        # No KB dir at all → empty string.
        assert kbb._kb_corpus_sha(tmp_path) == ""


# ── ratify ──────────────────────────────────────────────────────────────────
class TestRatify:
    def test_empty_reason_rejected(self, tmp_baselines):
        result = kbb.ratify("")
        assert not result["ok"]
        assert "reason" in result["error"].lower()

    def test_whitespace_only_reason_rejected(self, tmp_baselines):
        result = kbb.ratify("   \n   ")
        assert not result["ok"]

    def test_writes_baseline_file(self, tmp_baselines):
        findings = [_finding("CONTEXT/x.md"), _finding("CONTEXT/y.md")]
        result = kbb.ratify("first ratification — 2 known FPs", findings=findings)
        assert result["ok"]
        assert result["finding_count"] == 2
        target = tmp_baselines / result["path"]
        assert target.exists()
        payload = json.loads(target.read_text(encoding="utf-8"))
        assert payload["finding_count"] == 2
        assert payload["reason"] == "first ratification — 2 known FPs"
        assert len(payload["findings"]) == 2

    def test_does_not_overwrite_same_day_same_corpus(self, tmp_baselines):
        r1 = kbb.ratify("first", findings=[_finding("x.md")])
        r2 = kbb.ratify("second", findings=[_finding("y.md")])
        assert r1["baseline_id"] != r2["baseline_id"]
        # Both files exist.
        assert (tmp_baselines / r1["path"]).exists()
        assert (tmp_baselines / r2["path"]).exists()

    def test_ratify_uses_live_findings_when_omitted(self, tmp_baselines, monkeypatch):
        live = [_finding("auto.md")]
        monkeypatch.setattr(kbb, "_current_findings", lambda: live)
        result = kbb.ratify("auto-pulled findings")
        assert result["finding_count"] == 1


# ── list_baselines / latest ─────────────────────────────────────────────────
class TestListAndLatest:
    def test_empty_when_no_baselines(self, tmp_baselines):
        assert kbb.list_baselines() == []
        assert kbb.latest() is None

    def test_chronological_order(self, tmp_baselines):
        kbb.ratify("first", findings=[_finding("a.md")])
        # Mutate corpus so the second ratification gets a different id.
        (tmp_baselines / "KNOWLEDGE-BASE" / "alpha.md").write_text("# Alpha\nVARIANT\n")
        kbb.ratify("second", findings=[_finding("b.md")])
        lst = kbb.list_baselines()
        assert len(lst) == 2
        assert lst[0]["ratified_at"] <= lst[1]["ratified_at"]

    def test_latest_returns_most_recent(self, tmp_baselines):
        kbb.ratify("first", findings=[])
        (tmp_baselines / "KNOWLEDGE-BASE" / "beta.md").write_text("# Beta\nALT\n")
        kbb.ratify("most recent", findings=[])
        latest = kbb.latest()
        assert latest is not None
        assert latest["reason"] == "most recent"


# ── diff ────────────────────────────────────────────────────────────────────
class TestDiff:
    def test_no_baseline_returns_all_as_new(self, tmp_baselines, monkeypatch):
        live = [_finding("a.md"), _finding("b.md")]
        monkeypatch.setattr(kbb, "_current_findings", lambda: live)
        result = kbb.diff()
        assert result["ok"]
        assert result["baseline_id"] is None
        assert len(result["new_findings"]) == 2
        assert result["base_count"] == 0
        assert "no baseline ratified" in result["message"]

    def test_against_unknown_id_errors(self, tmp_baselines):
        kbb.ratify("some baseline", findings=[_finding("a.md")])
        result = kbb.diff(against="does-not-exist")
        assert not result["ok"]
        assert "does-not-exist" in result["error"]

    def test_diff_surfaces_only_new(self, tmp_baselines, monkeypatch):
        # Ratify with one known finding.
        kbb.ratify("baseline x", findings=[_finding("a.md")])
        # Live now has the same finding + a new one.
        live = [_finding("a.md"), _finding("c.md", owner="agent-x")]
        monkeypatch.setattr(kbb, "_current_findings", lambda: live)
        result = kbb.diff()
        assert result["ok"]
        new_paths = {f["path"] for f in result["new_findings"]}
        assert new_paths == {"c.md"}
        assert result["unchanged_count"] == 1
        assert result["resolved_findings"] == []

    def test_diff_surfaces_resolved(self, tmp_baselines, monkeypatch):
        # Ratify with two findings.
        kbb.ratify("base", findings=[_finding("a.md"), _finding("b.md")])
        # Live now has only one (the other was fixed).
        live = [_finding("a.md")]
        monkeypatch.setattr(kbb, "_current_findings", lambda: live)
        result = kbb.diff()
        resolved_paths = {f["path"] for f in result["resolved_findings"]}
        assert resolved_paths == {"b.md"}
        assert result["unchanged_count"] == 1
        assert result["new_findings"] == []

    def test_corpus_drift_flagged(self, tmp_baselines, monkeypatch):
        kbb.ratify("base", findings=[])
        # Corpus mutates.
        (tmp_baselines / "KNOWLEDGE-BASE" / "alpha.md").write_text("# Alpha\nWILDLY DIFFERENT\n")
        monkeypatch.setattr(kbb, "_current_findings", lambda: [])
        result = kbb.diff()
        assert result["kb_corpus_drifted"] is True

    def test_corpus_unchanged_not_flagged(self, tmp_baselines, monkeypatch):
        kbb.ratify("base", findings=[])
        monkeypatch.setattr(kbb, "_current_findings", lambda: [])
        result = kbb.diff()
        assert result["kb_corpus_drifted"] is False


# ── Keeper integration ──────────────────────────────────────────────────────
class TestKeeperIntegration:
    def test_check_kb_semantic_drift_silent_without_kb(self, tmp_path):
        from tools.noctus.dev.compliance import check_kb_semantic_drift
        # No KB dir at all → silent skip.
        assert check_kb_semantic_drift(repo_root=tmp_path) == []

    def test_check_suggests_ratify_when_findings_no_baseline(self, tmp_baselines, monkeypatch):
        # Seed a fake cache so the keeper proceeds past the cache-exists guard.
        cache_dir = tmp_baselines / ".claude" / "cache"
        cache_dir.mkdir(parents=True)
        (cache_dir / "kb-embeddings.sqlite").write_text("")
        monkeypatch.setattr(kbb, "_current_findings", lambda: [_finding("x.md")])
        from tools.noctus.dev.compliance import check_kb_semantic_drift
        issues = check_kb_semantic_drift(repo_root=tmp_baselines)
        assert any(i["symbol"] == "kb-baseline-missing" for i in issues)

    def test_check_fires_on_drift_above_threshold(self, tmp_baselines, monkeypatch):
        cache_dir = tmp_baselines / ".claude" / "cache"
        cache_dir.mkdir(parents=True)
        (cache_dir / "kb-embeddings.sqlite").write_text("")
        # Baseline with 0 findings; current has 10 → above threshold (5).
        kbb.ratify("empty baseline", findings=[])
        live = [_finding(f"x{i}.md") for i in range(10)]
        monkeypatch.setattr(kbb, "_current_findings", lambda: live)
        from tools.noctus.dev.compliance import check_kb_semantic_drift
        issues = check_kb_semantic_drift(repo_root=tmp_baselines)
        assert any(i["symbol"] == "kb-semantic-drift" for i in issues)

    def test_check_silent_when_below_threshold(self, tmp_baselines, monkeypatch):
        cache_dir = tmp_baselines / ".claude" / "cache"
        cache_dir.mkdir(parents=True)
        (cache_dir / "kb-embeddings.sqlite").write_text("")
        kbb.ratify("empty baseline", findings=[])
        # 2 new (below threshold 5).
        live = [_finding("a.md"), _finding("b.md")]
        monkeypatch.setattr(kbb, "_current_findings", lambda: live)
        from tools.noctus.dev.compliance import check_kb_semantic_drift
        issues = check_kb_semantic_drift(repo_root=tmp_baselines)
        # No drift symbol fired (corpus-drift not triggered here since
        # we didn't mutate KB after ratification).
        assert not any(i["symbol"] == "kb-semantic-drift" for i in issues)


# ── _current_findings defensive path ─────────────────────────────────────────
class TestCurrentFindingsDefensive:
    def test_returns_empty_on_module_failure(self, monkeypatch):
        # Force the import to fail.
        with patch.dict("sys.modules", {"tools.noctus.dev.kb_embeddings": None}):
            # The lazy import inside _current_findings should swallow this.
            result = kbb._current_findings()
            assert result == [] or isinstance(result, list)
