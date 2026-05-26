"""Regression tests for `codification_radar` — the s1/s2 → s3/s4 sensor.

Wave-2 follow-up that ports the original E4 work (incompatible APIs) to
the real `auto_improvement.query()` + `vectorize.embed_text()` shapes.

KB § PATTERNS/common/scoped-auto-improvement.md § Codification radar.
"""
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import codification_radar as cr  # noqa: E402


@pytest.fixture
def tmp_ledger(tmp_path, monkeypatch):
    """Bind auto_improvement's LEDGER_PATH to a tmp file."""
    from tools.noctus.dev import auto_improvement as ai
    ledger = tmp_path / "auto-improvement.ndjson"
    ledger.write_text("", encoding="utf-8")
    monkeypatch.setattr(ai, "LEDGER_PATH", ledger)
    # Also disable the real cache for the query() lazy refresh path.
    cache = tmp_path / "auto-improvement.sqlite"
    monkeypatch.setattr(ai, "CACHE_PATH", cache)
    monkeypatch.setattr(ai, "CACHE_DIR", tmp_path / ".claude" / "cache")
    return ledger


def _entry(ts: str, target: str, description: str, status: str = "s1-emergent") -> dict:
    return {
        "ts": ts, "agent": "tech-lead", "scope": "broad", "kind": "improvement",
        "target": target, "description": description, "status": status,
        "source_ref": None,
    }


class TestCosineHelper:
    def test_identical_vectors_score_one(self):
        v = [1.0, 0.0, 0.0]
        assert cr._cosine(v, v) == pytest.approx(1.0)

    def test_orthogonal_vectors_score_zero(self):
        assert cr._cosine([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)

    def test_opposite_vectors_score_minus_one(self):
        assert cr._cosine([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0)

    def test_empty_inputs_return_zero(self):
        assert cr._cosine([], [1.0]) == 0.0
        assert cr._cosine([1.0], []) == 0.0

    def test_zero_vector_returns_zero(self):
        assert cr._cosine([0.0, 0.0], [1.0, 1.0]) == 0.0


class TestSuggestedNext:
    def test_s1_pair_suggests_s2(self):
        entries = [{"status": "s1-emergent"}, {"status": "s1-emergent"}]
        assert cr._suggested_next(entries, 2) == "s2-memory"

    def test_s1_triple_suggests_s3(self):
        entries = [{"status": "s1-emergent"}] * 3
        assert cr._suggested_next(entries, 3) == "s3-kb"

    def test_s2_triple_suggests_s4(self):
        entries = [{"status": "s2-memory"}] * 3
        assert cr._suggested_next(entries, 3) == "s4-keeper"

    def test_mixed_takes_lowest(self):
        # cluster of s1 + s2 + s1 → lowest is s1; size=3 → s3
        entries = [
            {"status": "s1-emergent"},
            {"status": "s2-memory"},
            {"status": "s1-emergent"},
        ]
        assert cr._suggested_next(entries, 3) == "s3-kb"

    def test_closed_in_cluster_flags_review(self):
        entries = [{"status": "s1-emergent"}, {"status": "closed"}]
        assert cr._suggested_next(entries, 2) == "review-needed"


class TestClusterEmptyAndDegradedPaths:
    def test_empty_ledger_returns_empty_clusters(self, tmp_ledger):
        result = cr.cluster()
        assert result["ok"] is True
        assert result["clusters"] == []
        assert result["total_entries"] == 0

    def test_embedding_unreachable_returns_error(self, tmp_ledger):
        # Append one entry; mock embed_text to fail.
        tmp_ledger.write_text(
            json.dumps(_entry("2026-05-26", "X", "test")) + "\n",
            encoding="utf-8",
        )
        with patch("tools.noctus.dev.vectorize.embed_text") as m:
            m.return_value = {"ok": False, "error": "provider not configured"}
            result = cr.cluster()
        assert result["ok"] is False
        assert "embedding" in result["error"].lower() or "provider" in result["error"].lower()
        assert result["clusters"] == []

    def test_auto_improvement_query_failure_returns_error(self, tmp_ledger):
        from tools.noctus.dev import auto_improvement as ai
        with patch.object(ai, "query", side_effect=RuntimeError("boom")):
            result = cr.cluster()
        assert result["ok"] is False
        assert "query failed" in result["error"]


class TestClusterHappyPath:
    def test_two_similar_entries_form_a_cluster(self, tmp_ledger):
        # Two entries about the same concept; one entry unrelated.
        tmp_ledger.write_text(
            "\n".join([
                json.dumps(_entry("2026-05-26T10", "fileA.py", "Pydantic strict-http enforcement")),
                json.dumps(_entry("2026-05-26T11", "fileB.py", "Pydantic StrictHttpModel adoption")),
                json.dumps(_entry("2026-05-26T12", "unrelated.md", "totally different topic")),
            ]) + "\n",
            encoding="utf-8",
        )
        # Mock embed_text to return high-similarity vectors for the first
        # two (about Pydantic) and a different vector for the third.
        def fake_embed(text):
            if "pydantic" in text.lower() or "strict" in text.lower():
                return {"ok": True, "vector": [1.0, 0.0, 0.0]}
            return {"ok": True, "vector": [0.0, 1.0, 0.0]}
        with patch("tools.noctus.dev.vectorize.embed_text", side_effect=fake_embed):
            result = cr.cluster(threshold=0.5)
        assert result["ok"] is True
        # Expect exactly one cluster (size 2) — the third entry is unrelated.
        clusters_with_size_ge_2 = [c for c in result["clusters"] if c["size"] >= 2]
        assert len(clusters_with_size_ge_2) == 1
        c = clusters_with_size_ge_2[0]
        assert c["size"] == 2
        assert c["suggested_status_next"] == "s2-memory"
        assert c["avg_score"] > 0.9

    def test_three_similar_entries_suggest_s3(self, tmp_ledger):
        tmp_ledger.write_text(
            "\n".join([
                json.dumps(_entry("2026-05-26T01", "A", "concept X happens here")),
                json.dumps(_entry("2026-05-26T02", "B", "concept X recurs again")),
                json.dumps(_entry("2026-05-26T03", "C", "concept X surfaces a third time")),
            ]) + "\n",
            encoding="utf-8",
        )
        with patch("tools.noctus.dev.vectorize.embed_text") as m:
            m.return_value = {"ok": True, "vector": [1.0, 0.0]}  # all identical
            result = cr.cluster(threshold=0.5)
        assert result["ok"] is True
        # All 3 should cluster; suggested_status_next = s3-kb
        assert len(result["clusters"]) == 1
        c = result["clusters"][0]
        assert c["size"] == 3
        assert c["suggested_status_next"] == "s3-kb"


class TestPromote:
    def test_promote_validates_target_status(self, tmp_ledger):
        result = cr.promote([], "invalid-status")
        assert result["ok"] is False
        assert "status must be one of" in result["error"]

    def test_promote_rewrites_matching_entries(self, tmp_ledger):
        tmp_ledger.write_text(
            "\n".join([
                json.dumps(_entry("ts1", "target1", "desc1", status="s1-emergent")),
                json.dumps(_entry("ts2", "target2", "desc2", status="s1-emergent")),
            ]) + "\n",
            encoding="utf-8",
        )
        matches = [{"ts": "ts1", "target": "target1", "description": "desc1"}]
        result = cr.promote(matches, "s2-memory")
        assert result["ok"] is True
        assert result["updated"] == 1
        # Verify the ndjson was rewritten correctly.
        lines = tmp_ledger.read_text(encoding="utf-8").strip().splitlines()
        e1 = json.loads(lines[0])
        e2 = json.loads(lines[1])
        assert e1["status"] == "s2-memory"
        assert e2["status"] == "s1-emergent"  # unchanged

    def test_promote_idempotent(self, tmp_ledger):
        tmp_ledger.write_text(
            json.dumps(_entry("ts1", "target1", "desc1", status="s2-memory")) + "\n",
            encoding="utf-8",
        )
        matches = [{"ts": "ts1", "target": "target1", "description": "desc1"}]
        result = cr.promote(matches, "s2-memory")
        assert result["ok"] is True
        assert result["updated"] == 0
        assert result["no_match"] == 1  # already at target_status

    def test_promote_preserves_malformed_lines(self, tmp_ledger):
        tmp_ledger.write_text(
            "not valid json at all\n"
            + json.dumps(_entry("ts1", "target1", "desc1", status="s1-emergent")) + "\n"
            + "another bad line\n",
            encoding="utf-8",
        )
        matches = [{"ts": "ts1", "target": "target1", "description": "desc1"}]
        result = cr.promote(matches, "s2-memory")
        assert result["ok"] is True
        assert result["updated"] == 1
        lines = tmp_ledger.read_text(encoding="utf-8").strip().splitlines()
        assert lines[0] == "not valid json at all"  # preserved
        assert lines[2] == "another bad line"  # preserved

    def test_promote_missing_ledger_errors(self, tmp_path, monkeypatch):
        from tools.noctus.dev import auto_improvement as ai
        monkeypatch.setattr(ai, "LEDGER_PATH", tmp_path / "nonexistent.ndjson")
        result = cr.promote([{"ts": "x", "target": "y", "description": "z"}], "s2-memory")
        assert result["ok"] is False
        assert "ledger not found" in result["error"]
