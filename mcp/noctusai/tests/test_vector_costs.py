"""Regression tests for the vector embedding cost tracking module.

Covers:
- log_refresh_batch (append + empty-ledger behaviour)
- estimate_tokens (with tiktoken available, and fallback)
- estimate_cost (table lookup, unknown model)
- report aggregation (day / week / month)
- total aggregation

KB § PATTERNS/common/vector-cost-tracking.md.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import vector_costs as vc  # noqa: E402


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_ledger(tmp_path, monkeypatch):
    """Redirect LEDGER_PATH to a temp file so tests don't touch the real ledger."""
    ledger = tmp_path / "project-history" / "vector-costs.ndjson"
    ledger.parent.mkdir(parents=True)
    monkeypatch.setattr(vc, "LEDGER_PATH", ledger)
    return ledger


# ── estimate_tokens ───────────────────────────────────────────────────────────

class TestEstimateTokens:
    def test_fallback_path(self, monkeypatch):
        """When tiktoken is unavailable the fallback returns len(text) // 4."""
        import builtins
        real_import = builtins.__import__

        def _no_tiktoken(name, *args, **kwargs):
            if name == "tiktoken":
                raise ImportError("tiktoken not available")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _no_tiktoken)
        text = "hello world"
        result = vc.estimate_tokens(text)
        assert result == len(text) // 4

    def test_fallback_for_long_text(self, monkeypatch):
        import builtins
        real_import = builtins.__import__

        def _no_tiktoken(name, *args, **kwargs):
            if name == "tiktoken":
                raise ImportError
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _no_tiktoken)
        text = "a" * 4000
        result = vc.estimate_tokens(text)
        assert result == 1000  # 4000 // 4

    def test_tiktoken_path_when_available(self):
        """When tiktoken IS available the result should be ≥ 1 for non-empty text."""
        try:
            import tiktoken  # noqa: F401
            has_tiktoken = True
        except ImportError:
            has_tiktoken = False

        if not has_tiktoken:
            pytest.skip("tiktoken not installed in this venv")

        result = vc.estimate_tokens("hello world", model="text-embedding-3-small")
        assert result >= 1

    def test_empty_string(self):
        result = vc.estimate_tokens("")
        assert result == 0


# ── estimate_cost ─────────────────────────────────────────────────────────────

class TestEstimateCost:
    def test_known_model_small(self):
        # 1M tokens → $0.02
        cost = vc.estimate_cost(1_000_000, "text-embedding-3-small")
        assert abs(cost - 0.02) < 1e-9

    def test_known_model_large(self):
        # 1M tokens → $0.13
        cost = vc.estimate_cost(1_000_000, "text-embedding-3-large")
        assert abs(cost - 0.13) < 1e-9

    def test_known_model_ada(self):
        cost = vc.estimate_cost(1_000_000, "text-embedding-ada-002")
        assert abs(cost - 0.10) < 1e-9

    def test_half_million(self):
        cost = vc.estimate_cost(500_000, "text-embedding-3-small")
        assert abs(cost - 0.01) < 1e-9

    def test_unknown_model_returns_zero(self):
        cost = vc.estimate_cost(1_000_000, "text-embedding-unknown-v99")
        assert cost == 0.0

    def test_zero_tokens(self):
        cost = vc.estimate_cost(0, "text-embedding-3-small")
        assert cost == 0.0


# ── log_refresh_batch ─────────────────────────────────────────────────────────

class TestLogRefreshBatch:
    def test_appends_row(self, tmp_ledger):
        r = vc.log_refresh_batch(
            namespace="kb-embeddings",
            model="text-embedding-3-small",
            doc_count=5,
            chunk_count=20,
            estimated_tokens=9000,
        )
        assert r["ok"] is True
        lines = tmp_ledger.read_text().strip().splitlines()
        assert len(lines) == 1
        row = json.loads(lines[0])
        assert row["namespace"] == "kb-embeddings"
        assert row["doc_count"] == 5
        assert row["chunk_count"] == 20
        assert row["estimated_tokens"] == 9000
        assert row["model"] == "text-embedding-3-small"
        assert row["provider"] == "openai"
        assert "ts" in row
        assert isinstance(row["estimated_cost_usd"], float)

    def test_cost_computed_from_table_when_none(self, tmp_ledger):
        r = vc.log_refresh_batch(
            namespace="test-ns",
            model="text-embedding-3-small",
            doc_count=1,
            chunk_count=1,
            estimated_tokens=1_000_000,
            cost_estimate_usd=None,
        )
        row = r["row"]
        assert abs(row["estimated_cost_usd"] - 0.02) < 1e-9

    def test_explicit_cost_overrides_table(self, tmp_ledger):
        r = vc.log_refresh_batch(
            namespace="test-ns",
            model="text-embedding-3-small",
            doc_count=1,
            chunk_count=1,
            estimated_tokens=100,
            cost_estimate_usd=99.99,
        )
        assert abs(r["row"]["estimated_cost_usd"] - 99.99) < 1e-6

    def test_multiple_appends_accumulate(self, tmp_ledger):
        for i in range(3):
            vc.log_refresh_batch(
                namespace="kb-embeddings",
                model="text-embedding-3-small",
                doc_count=1,
                chunk_count=i + 1,
                estimated_tokens=100,
            )
        lines = tmp_ledger.read_text().strip().splitlines()
        assert len(lines) == 3

    def test_empty_ledger_creates_file(self, tmp_ledger):
        assert not tmp_ledger.exists()
        vc.log_refresh_batch(
            namespace="ns", model="text-embedding-3-small",
            doc_count=0, chunk_count=0, estimated_tokens=0,
        )
        assert tmp_ledger.exists()

    def test_source_ref_stored(self, tmp_ledger):
        vc.log_refresh_batch(
            namespace="ns", model="text-embedding-3-small",
            doc_count=1, chunk_count=2, estimated_tokens=100,
            source_ref="session:2026-05-26",
        )
        row = json.loads(tmp_ledger.read_text().strip())
        assert row["source_ref"] == "session:2026-05-26"


# ── report ────────────────────────────────────────────────────────────────────

class TestReport:
    def _seed(self, tmp_ledger, rows: list[dict]) -> None:
        with tmp_ledger.open("w") as fh:
            for row in rows:
                fh.write(json.dumps(row) + "\n")

    def test_empty_ledger_returns_empty_list(self, tmp_ledger):
        result = vc.report()
        assert result == []

    def test_aggregates_by_day(self, tmp_ledger):
        self._seed(tmp_ledger, [
            {"ts": "2026-05-01T10:00:00+00:00", "namespace": "kb-embeddings",
             "doc_count": 3, "chunk_count": 10, "estimated_tokens": 4000,
             "estimated_cost_usd": 0.00008},
            {"ts": "2026-05-01T14:00:00+00:00", "namespace": "kb-embeddings",
             "doc_count": 2, "chunk_count": 5, "estimated_tokens": 2000,
             "estimated_cost_usd": 0.00004},
        ])
        result = vc.report(group_by="day")
        assert len(result) == 1
        b = result[0]
        assert b["period"] == "2026-05-01"
        assert b["doc_count"] == 5
        assert b["chunk_count"] == 15
        assert b["estimated_tokens"] == 6000
        assert b["batch_count"] == 2

    def test_aggregates_by_month(self, tmp_ledger):
        self._seed(tmp_ledger, [
            {"ts": "2026-05-01T10:00:00+00:00", "namespace": "kb-embeddings",
             "doc_count": 1, "chunk_count": 3, "estimated_tokens": 1200,
             "estimated_cost_usd": 0.000024},
            {"ts": "2026-06-15T10:00:00+00:00", "namespace": "kb-embeddings",
             "doc_count": 2, "chunk_count": 6, "estimated_tokens": 2400,
             "estimated_cost_usd": 0.000048},
        ])
        result = vc.report(group_by="month")
        assert len(result) == 2
        periods = [r["period"] for r in result]
        assert "2026-05" in periods
        assert "2026-06" in periods

    def test_namespace_filter(self, tmp_ledger):
        self._seed(tmp_ledger, [
            {"ts": "2026-05-01T10:00:00+00:00", "namespace": "kb-embeddings",
             "doc_count": 1, "chunk_count": 1, "estimated_tokens": 400,
             "estimated_cost_usd": 0.000008},
            {"ts": "2026-05-01T10:00:00+00:00", "namespace": "code-embeddings",
             "doc_count": 5, "chunk_count": 20, "estimated_tokens": 8000,
             "estimated_cost_usd": 0.00016},
        ])
        result = vc.report(namespace="kb-embeddings")
        assert len(result) == 1
        assert result[0]["namespace"] == "kb-embeddings"

    def test_since_filter(self, tmp_ledger):
        self._seed(tmp_ledger, [
            {"ts": "2026-04-30T23:59:00+00:00", "namespace": "ns",
             "doc_count": 1, "chunk_count": 1, "estimated_tokens": 400,
             "estimated_cost_usd": 0.0},
            {"ts": "2026-05-01T00:00:00+00:00", "namespace": "ns",
             "doc_count": 2, "chunk_count": 2, "estimated_tokens": 800,
             "estimated_cost_usd": 0.0},
        ])
        result = vc.report(since="2026-05-01")
        assert len(result) == 1
        assert result[0]["doc_count"] == 2

    def test_multiple_namespaces_separate_buckets(self, tmp_ledger):
        self._seed(tmp_ledger, [
            {"ts": "2026-05-01T10:00:00+00:00", "namespace": "ns-a",
             "doc_count": 1, "chunk_count": 1, "estimated_tokens": 100, "estimated_cost_usd": 0.0},
            {"ts": "2026-05-01T10:00:00+00:00", "namespace": "ns-b",
             "doc_count": 2, "chunk_count": 2, "estimated_tokens": 200, "estimated_cost_usd": 0.0},
        ])
        result = vc.report(group_by="day")
        namespaces = {r["namespace"] for r in result}
        assert namespaces == {"ns-a", "ns-b"}


# ── total ─────────────────────────────────────────────────────────────────────

class TestTotal:
    def _seed(self, tmp_ledger, rows: list[dict]) -> None:
        with tmp_ledger.open("w") as fh:
            for row in rows:
                fh.write(json.dumps(row) + "\n")

    def test_empty_ledger(self, tmp_ledger):
        t = vc.total()
        assert t["batch_count"] == 0
        assert t["doc_count"] == 0
        assert t["estimated_tokens"] == 0
        assert t["first_ts"] is None
        assert t["last_ts"] is None

    def test_sums_all_rows(self, tmp_ledger):
        self._seed(tmp_ledger, [
            {"ts": "2026-05-01T10:00:00+00:00", "namespace": "ns",
             "doc_count": 3, "chunk_count": 10, "estimated_tokens": 4000,
             "estimated_cost_usd": 0.00008},
            {"ts": "2026-05-02T10:00:00+00:00", "namespace": "ns",
             "doc_count": 2, "chunk_count": 5, "estimated_tokens": 2000,
             "estimated_cost_usd": 0.00004},
        ])
        t = vc.total()
        assert t["doc_count"] == 5
        assert t["chunk_count"] == 15
        assert t["estimated_tokens"] == 6000
        assert t["batch_count"] == 2
        assert t["first_ts"] < t["last_ts"]

    def test_namespace_filter(self, tmp_ledger):
        self._seed(tmp_ledger, [
            {"ts": "2026-05-01T10:00:00+00:00", "namespace": "kb-embeddings",
             "doc_count": 1, "chunk_count": 1, "estimated_tokens": 100,
             "estimated_cost_usd": 0.000002},
            {"ts": "2026-05-01T10:00:00+00:00", "namespace": "code-embeddings",
             "doc_count": 5, "chunk_count": 20, "estimated_tokens": 8000,
             "estimated_cost_usd": 0.00016},
        ])
        t = vc.total(namespace="kb-embeddings")
        assert t["doc_count"] == 1
        assert t["batch_count"] == 1

    def test_since_filter(self, tmp_ledger):
        self._seed(tmp_ledger, [
            {"ts": "2026-04-01T10:00:00+00:00", "namespace": "ns",
             "doc_count": 10, "chunk_count": 40, "estimated_tokens": 16000,
             "estimated_cost_usd": 0.00032},
            {"ts": "2026-05-01T10:00:00+00:00", "namespace": "ns",
             "doc_count": 1, "chunk_count": 1, "estimated_tokens": 100,
             "estimated_cost_usd": 0.000002},
        ])
        t = vc.total(since="2026-05-01")
        assert t["batch_count"] == 1
        assert t["doc_count"] == 1

    def test_total_returns_correct_first_last_ts(self, tmp_ledger):
        ts_a = "2026-05-01T10:00:00+00:00"
        ts_b = "2026-05-03T10:00:00+00:00"
        self._seed(tmp_ledger, [
            {"ts": ts_b, "namespace": "ns", "doc_count": 1, "chunk_count": 1,
             "estimated_tokens": 100, "estimated_cost_usd": 0.0},
            {"ts": ts_a, "namespace": "ns", "doc_count": 1, "chunk_count": 1,
             "estimated_tokens": 100, "estimated_cost_usd": 0.0},
        ])
        t = vc.total()
        assert t["first_ts"] == ts_a
        assert t["last_ts"] == ts_b
