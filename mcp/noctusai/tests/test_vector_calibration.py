"""Regression tests for `vector_calibration` — reasoning-driven calibration.

KB § PATTERNS/common/vector-calibration.md. W2-E7 (2026-05-26).
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import vector_calibration as vc  # noqa: E402


@pytest.fixture
def tmp_ledgers(tmp_path, monkeypatch):
    """Bind the ledger paths to tmp."""
    signals = tmp_path / "vector-signals.ndjson"
    decisions = tmp_path / "vector-calibration.ndjson"
    monkeypatch.setattr(vc, "SIGNALS_PATH", signals)
    monkeypatch.setattr(vc, "DECISIONS_PATH", decisions)
    return signals, decisions


class TestLogSignal:
    def test_appends_valid_entry(self, tmp_ledgers):
        signals, _ = tmp_ledgers
        r = vc.log_signal(
            signal_type="kb_search",
            params={"top_k": 5, "threshold": 0.75},
            result={"hits": [{"path": "x.md", "score": 0.82}]},
        )
        assert r["ok"] is True
        line = signals.read_text(encoding="utf-8").strip()
        entry = json.loads(line)
        assert entry["signal_type"] == "kb_search"
        assert entry["params"]["top_k"] == 5

    def test_unknown_signal_type_rejected(self, tmp_ledgers):
        r = vc.log_signal(signal_type="invalid-type", params={}, result={})
        assert r["ok"] is False
        assert "signal_type must be one of" in r["error"]

    def test_appends_optional_context(self, tmp_ledgers):
        signals, _ = tmp_ledgers
        vc.log_signal(
            signal_type="codification_radar",
            params={"threshold": 0.75},
            result={"clusters": []},
            context={"session": "test", "user_action": "review"},
        )
        entry = json.loads(signals.read_text(encoding="utf-8").strip())
        assert entry["context"]["session"] == "test"


class TestLogDecision:
    def test_appends_valid_decision(self, tmp_ledgers):
        _, decisions = tmp_ledgers
        r = vc.log_decision(
            signal_type="kb_search",
            parameter="similarity_threshold",
            old_value=0.75,
            new_value=0.80,
            reasoning="Q25 of observed scores was 0.78; threshold was below the discriminating range.",
        )
        assert r["ok"] is True
        entry = json.loads(decisions.read_text(encoding="utf-8").strip())
        assert entry["parameter"] == "similarity_threshold"
        assert entry["new_value"] == 0.80
        assert "Q25" in entry["reasoning"]

    def test_reasoning_required(self, tmp_ledgers):
        r = vc.log_decision(
            signal_type="kb_search",
            parameter="similarity_threshold",
            old_value=0.75,
            new_value=0.80,
            reasoning="",
        )
        assert r["ok"] is False
        assert "reasoning is required" in r["error"]

    def test_unknown_parameter_rejected(self, tmp_ledgers):
        r = vc.log_decision(
            signal_type="kb_search",
            parameter="fake_param",
            old_value=1,
            new_value=2,
            reasoning="...",
        )
        assert r["ok"] is False
        assert "unknown parameter" in r["error"]


class TestDecisionsLog:
    def test_empty_when_no_ledger(self, tmp_ledgers):
        assert vc.decisions_log() == []

    def test_filter_by_signal_type(self, tmp_ledgers):
        vc.log_decision("kb_search", "similarity_threshold", 0.7, 0.8, "ok")
        vc.log_decision("codification_radar", "min_cluster_size", 2, 3, "ok")
        assert len(vc.decisions_log()) == 2
        assert len(vc.decisions_log(signal_type="kb_search")) == 1
        assert len(vc.decisions_log(signal_type="codification_radar")) == 1


class TestAnalyze:
    def test_empty_ledger_returns_no_analyses(self, tmp_ledgers):
        result = vc.analyze()
        assert result["ok"] is True
        assert result["analyses"] == []

    def test_few_signals_surfaces_too_few_warning(self, tmp_ledgers):
        # Log 3 signals — under the 10-observation threshold.
        for i in range(3):
            vc.log_signal(
                signal_type="kb_search",
                params={"threshold": 0.75},
                result={"hits": [{"score": 0.80 + i * 0.01}]},
            )
        result = vc.analyze(signal_type="kb_search")
        assert result["ok"] is True
        analyses = result["analyses"]
        assert len(analyses) == 1
        reasoning = " ".join(analyses[0]["reasoning"])
        assert "too few" in reasoning.lower() or "observations" in reasoning.lower()

    def test_many_signals_threshold_below_q25(self, tmp_ledgers):
        # Threshold = 0.5, scores are all 0.8-0.9 ⇒ threshold below Q25
        for i in range(30):
            vc.log_signal(
                signal_type="kb_search",
                params={"threshold": 0.5},
                result={"hits": [{"score": 0.80 + (i % 10) * 0.01}]},
            )
        result = vc.analyze(signal_type="kb_search")
        reasoning = " ".join(result["analyses"][0]["reasoning"])
        assert "below" in reasoning.lower()

    def test_many_signals_threshold_above_q75(self, tmp_ledgers):
        # Threshold = 0.95, scores are 0.5-0.7 ⇒ threshold above Q75
        for i in range(30):
            vc.log_signal(
                signal_type="kb_search",
                params={"threshold": 0.95},
                result={"hits": [{"score": 0.50 + (i % 20) * 0.01}]},
            )
        result = vc.analyze(signal_type="kb_search")
        reasoning = " ".join(result["analyses"][0]["reasoning"])
        assert "above" in reasoning.lower()

    def test_distribution_stats_populated(self, tmp_ledgers):
        for i in range(20):
            vc.log_signal(
                signal_type="kb_search",
                params={"threshold": 0.75},
                result={"hits": [{"score": 0.5 + (i / 40)}]},
            )
        result = vc.analyze(signal_type="kb_search")
        dist = result["analyses"][0]["score_distribution"]
        assert dist["count"] == 20
        assert "mean" in dist
        assert "median" in dist
        assert "q25" in dist
        assert "q75" in dist
        assert "histogram_0_to_1_in_5_bins" in dist

    def test_since_filter_excludes_old_signals(self, tmp_ledgers):
        # Direct ndjson write so we can control ts.
        signals, _ = tmp_ledgers
        signals.write_text(
            "\n".join([
                json.dumps({"ts": "2026-01-01", "signal_type": "kb_search",
                            "params": {"threshold": 0.75}, "result": {"hits": [{"score": 0.8}]}, "context": {}}),
                json.dumps({"ts": "2026-06-01", "signal_type": "kb_search",
                            "params": {"threshold": 0.75}, "result": {"hits": [{"score": 0.9}]}, "context": {}}),
            ]) + "\n",
            encoding="utf-8",
        )
        # since 2026-05-26 excludes the 2026-01-01 entry
        result = vc.analyze(signal_type="kb_search", since="2026-05-26")
        assert result["analyses"][0]["observation_count"] == 1


class TestReasoningOutputs:
    """Spot-check that the reasoning lines INCLUDE the WHY clauses
    (architects should see hypotheses, not just numbers)."""

    def test_threshold_below_q25_includes_why(self, tmp_ledgers):
        for i in range(30):
            vc.log_signal(
                signal_type="kb_search",
                params={"threshold": 0.5},
                result={"hits": [{"score": 0.80 + (i % 10) * 0.01}]},
            )
        result = vc.analyze(signal_type="kb_search")
        reasoning = " ".join(result["analyses"][0]["reasoning"])
        # Must contain a WHY clause — the reasoning template demands it.
        assert "why" in reasoning.lower()

    def test_recommended_next_step_is_advisory(self, tmp_ledgers):
        for i in range(15):
            vc.log_signal(
                signal_type="kb_search", params={"threshold": 0.75},
                result={"hits": [{"score": 0.75 + i * 0.005}]},
            )
        result = vc.analyze(signal_type="kb_search")
        # The recommended_next_step must explicitly NOT auto-apply.
        next_step = result["analyses"][0]["recommended_next_step"]
        assert "advisory" in next_step.lower() or "review" in next_step.lower()
