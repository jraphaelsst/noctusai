"""Regression tests for `code_recurrence_promote` — the active cross-product
recurrence loop closer.

Pipeline this test exercises:
  code_embeddings (mocked rows) → scan() → dedupe + band → promote() →
  auto_improvement.log_entry → codification_radar (downstream, not tested
  here — has its own suite).

KB § CONTEXT/PATTERNS/common/code-embeddings.md § Deferred next-slices.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import code_recurrence_promote as crp  # noqa: E402


# ── Fixtures ─────────────────────────────────────────────────────────────────
@pytest.fixture
def tmp_ledger(tmp_path, monkeypatch):
    """Isolate auto_improvement's LEDGER_PATH to a tmp file."""
    from tools.noctus.dev import auto_improvement as ai
    ledger = tmp_path / "auto-improvement.ndjson"
    ledger.write_text("", encoding="utf-8")
    monkeypatch.setattr(ai, "LEDGER_PATH", ledger)
    cache = tmp_path / "auto-improvement.sqlite"
    monkeypatch.setattr(ai, "CACHE_PATH", cache)
    monkeypatch.setattr(ai, "CACHE_DIR", tmp_path / ".claude" / "cache")
    return ledger


@pytest.fixture
def mock_code_embeddings(monkeypatch):
    """Inject a fake corpus + neighbor function so scan() runs deterministically."""
    from tools.noctus.dev import code_embeddings as ce

    # Two clusters of similar functions across products.
    fake_rows = [
        ("products/a/services/phones.py", 0, "normalize_phone", "function",
         "def normalize_phone(): return '+5511' + '999'", [1.0, 0.0, 0.0]),
        ("products/b/services/numbers.py", 0, "format_phone", "function",
         "def format_phone(): return '+55' + '11999'", [0.95, 0.05, 0.0]),
        ("products/c/util/contacts.py", 0, "clean_phone", "function",
         "def clean_phone(): return '11999999999'", [0.92, 0.08, 0.0]),
        # A totally different surface — should NOT cluster with above.
        ("products/a/util/dates.py", 0, "parse_date", "function",
         "def parse_date(): return '2026-01-01'", [0.0, 1.0, 0.0]),
    ]

    monkeypatch.setattr(ce, "_load_all_chunk_vectors", lambda: fake_rows)

    def _fake_neighbors(path, symbol_name="", top_k=5):
        anchor = next(
            (r for r in fake_rows
             if r[0] == path and (not symbol_name or r[2] == symbol_name)),
            None,
        )
        if anchor is None:
            return []
        _, _, _, _, _, anchor_vec = anchor
        scored = []
        for p, _idx, sym, kind, _txt, vec in fake_rows:
            if p == path and (not symbol_name or sym == symbol_name):
                continue
            score = ce._cosine(anchor_vec, vec)
            scored.append({
                "path": p, "symbol_name": sym, "kind": kind,
                "chunk_idx": 0, "score": score,
            })
        scored.sort(key=lambda d: d["score"], reverse=True)
        return scored[:top_k]

    monkeypatch.setattr(ce, "code_neighbors", _fake_neighbors)
    return fake_rows


# ── Band classifier ──────────────────────────────────────────────────────────
class TestBandClassifier:
    def test_strong_at_threshold(self):
        assert crp._band(0.90) == "strong"
        assert crp._band(0.99) == "strong"

    def test_medium_band(self):
        assert crp._band(0.80) == "medium"
        assert crp._band(0.89) == "medium"

    def test_weak_band(self):
        assert crp._band(0.70) == "weak"
        assert crp._band(0.79) == "weak"

    def test_below_weak_still_classified(self):
        # _band itself doesn't reject — scan's threshold gate does.
        assert crp._band(0.5) == "weak"


# ── Pair canonicalization ────────────────────────────────────────────────────
class TestPairKey:
    def test_symmetric(self):
        a = crp._pair_key("p1", "s1", "p2", "s2")
        b = crp._pair_key("p2", "s2", "p1", "s1")
        assert a == b

    def test_order_by_path_then_symbol(self):
        # Same path, different symbols — symbol lex ordering wins.
        a = crp._pair_key("same.py", "zebra", "same.py", "apple")
        assert a == ("same.py", "apple", "same.py", "zebra")


# ── scan() ──────────────────────────────────────────────────────────────────
class TestScan:
    def test_empty_cache_returns_empty(self, monkeypatch):
        from tools.noctus.dev import code_embeddings as ce
        monkeypatch.setattr(ce, "_load_all_chunk_vectors", lambda: [])
        result = crp.scan()
        assert result["ok"] is True
        assert result["total_pairs"] == 0
        assert result["clusters"] == []
        assert "empty" in result["message"]

    def test_surfaces_high_similarity_pairs(self, mock_code_embeddings):
        result = crp.scan(threshold=0.7)
        assert result["ok"] is True
        # 3 phone-related fns should pair up: C(3,2) = 3 pairs.
        # The date function shouldn't cluster with phone functions.
        assert result["total_pairs"] >= 1
        for cluster in result["clusters"]:
            assert cluster["score"] >= 0.7
            assert "a" in cluster and "b" in cluster

    def test_dedupes_pairs(self, mock_code_embeddings):
        # When A→B and B→A both surface as neighbors, only one entry survives.
        result = crp.scan(threshold=0.7)
        seen_keys = set()
        for c in result["clusters"]:
            key = crp._pair_key(c["a"]["path"], c["a"]["symbol_name"],
                                c["b"]["path"], c["b"]["symbol_name"])
            assert key not in seen_keys, f"duplicate pair: {key}"
            seen_keys.add(key)

    def test_threshold_filters(self, mock_code_embeddings):
        # Very high threshold should drop weak pairs.
        result = crp.scan(threshold=0.99)
        # Phone fns cosine is in ~0.95-0.99 range; date fn is orthogonal (~0).
        # With 0.99 threshold, only the strongest pair(s) survive.
        for c in result["clusters"]:
            assert c["score"] >= 0.99

    def test_band_counts_match_clusters(self, mock_code_embeddings):
        result = crp.scan(threshold=0.7)
        by_band = result["by_band"]
        for band, count in by_band.items():
            actual = sum(1 for c in result["clusters"] if c["band"] == band)
            assert actual == count, f"{band}: counted {actual} but by_band says {count}"

    def test_strong_band_sorts_first(self, mock_code_embeddings):
        result = crp.scan(threshold=0.7)
        # If both strong and weak exist, strong must come first.
        bands = [c["band"] for c in result["clusters"]]
        band_rank = {"strong": 0, "medium": 1, "weak": 2}
        ranks = [band_rank[b] for b in bands]
        assert ranks == sorted(ranks), f"out of band-order: {bands}"

    def test_limit_caps_results(self, mock_code_embeddings):
        result = crp.scan(threshold=0.0, limit=1)  # threshold=0 surfaces everything
        assert len(result["clusters"]) <= 1


# ── promote() ───────────────────────────────────────────────────────────────
class TestPromote:
    def _match(self, p1="p1.py", s1="f", p2="p2.py", s2="g", score=0.85):
        return {
            "score": score,
            "band": crp._band(score),
            "a": {"path": p1, "symbol_name": s1, "kind": "function"},
            "b": {"path": p2, "symbol_name": s2, "kind": "function"},
        }

    def test_writes_to_ledger(self, tmp_ledger):
        result = crp.promote([self._match()])
        assert result["ok"] is True
        assert len(result["promoted"]) == 1
        lines = [ln for ln in tmp_ledger.read_text().splitlines() if ln.strip()]
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["kind"] == "improvement"
        assert entry["status"] == "s1-emergent"
        assert "code-recurrence:" in entry["target"]
        assert "p1.py" in entry["target"]

    def test_target_string_uses_canonical_pair(self, tmp_ledger):
        result = crp.promote([self._match(p1="b.py", s1="x", p2="a.py", s2="y")])
        # Canonical order: a.py::y comes first (lex sort), so target should
        # start with a.py.
        target = result["promoted"][0]["target"]
        assert target.startswith("code-recurrence:a.py::y")

    def test_idempotent_skips_existing(self, tmp_ledger):
        match = self._match()
        first = crp.promote([match])
        assert len(first["promoted"]) == 1
        # Second pass with same match — must skip.
        second = crp.promote([match])
        assert len(second["promoted"]) == 0
        assert len(second["skipped"]) == 1

    def test_skip_existing_can_be_disabled(self, tmp_ledger):
        match = self._match()
        crp.promote([match])
        # With skip_existing=False, the second pass writes again (duplicate ok).
        result = crp.promote([match], skip_existing=False)
        assert len(result["promoted"]) == 1

    def test_invalid_status_rejected(self, tmp_ledger):
        result = crp.promote([self._match()], target_status="not-a-real-status")
        assert result["ok"] is False
        assert "target_status" in result["error"]

    def test_malformed_match_surfaced_as_error(self, tmp_ledger):
        result = crp.promote([{"score": 0.9}])  # missing a/b
        # Errors list non-empty; ok is False.
        assert not result["ok"]
        assert len(result["errors"]) == 1

    def test_score_in_promoted_payload(self, tmp_ledger):
        result = crp.promote([self._match(score=0.88)])
        assert result["promoted"][0]["score"] == pytest.approx(0.88)

    def test_source_ref_threaded_through(self, tmp_ledger):
        crp.promote([self._match()], source_ref="session:test")
        entry = json.loads(tmp_ledger.read_text().splitlines()[0])
        assert entry["source_ref"] == "session:test"


# ── Pipeline end-to-end (scan → promote → re-scan-skips-existing) ──────────
class TestPipeline:
    def test_full_round_trip(self, tmp_ledger, mock_code_embeddings):
        # 1. scan surfaces clusters.
        scan_result = crp.scan(threshold=0.7)
        assert scan_result["total_pairs"] >= 1
        # 2. promote writes them to the ledger.
        promo = crp.promote(scan_result["clusters"], source_ref="test-pipeline")
        assert promo["ok"] is True
        assert len(promo["promoted"]) == scan_result["total_pairs"]
        # 3. Promote again — every match should now skip.
        promo2 = crp.promote(scan_result["clusters"])
        assert len(promo2["promoted"]) == 0
        assert len(promo2["skipped"]) == scan_result["total_pairs"]
