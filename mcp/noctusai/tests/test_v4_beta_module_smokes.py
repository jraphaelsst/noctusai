"""Smoke tests for v4.0-beta modules without dedicated test files.

Each module gets minimal coverage: import + at-least-one happy-path call.
Catches: import-time errors, obvious API contract regressions, default
parameter shapes.

Born 2026-05-26 — closing the "untested but shipped" gap before v4.0-beta
declaration. Per the seven-way-sync contract: every shipped module needs
SOME test coverage; smoke is the floor.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


# ── brief_similarity_radar ──────────────────────────────────────────────────
class TestBriefSimilarityRadarSmoke:
    def test_imports(self):
        from tools.noctus.dev import brief_similarity_radar  # noqa: F401

    def test_similarity_check_empty_input_rejected(self):
        from tools.noctus.dev import brief_similarity_radar as bsr
        r = bsr.similarity_check("")
        assert r["ok"] is False

    def test_similarity_check_empty_ledger_returns_empty(self, tmp_path, monkeypatch):
        from tools.noctus.dev import brief_similarity_radar as bsr
        from tools.noctus.dev import brief_ledger as bl
        monkeypatch.setattr(bl, "_ledger_path",
                            lambda: tmp_path / "empty.ndjson")
        r = bsr.similarity_check("some draft")
        assert r["ok"] is True
        assert r["hits"] == []


# ── session_end_sweep ───────────────────────────────────────────────────────
class TestSessionEndSweepSmoke:
    def test_imports(self):
        from tools.noctus.dev import session_end_sweep  # noqa: F401

    def test_sweep_runs_without_error(self):
        from tools.noctus.dev import session_end_sweep as ses
        r = ses.sweep()
        assert r["ok"] is True
        assert "worktrees" in r
        assert "orphan_branches" in r
        assert "sweep_ts" in r


# ── dispatch_warmup ─────────────────────────────────────────────────────────
class TestDispatchWarmupSmoke:
    def test_imports(self):
        from tools.noctus.dev import dispatch_warmup  # noqa: F401

    def test_warmup_returns_markdown(self):
        from tools.noctus.dev import dispatch_warmup as dw
        r = dw.warmup("backend-engineer", description="placeholder probe")
        assert r["ok"] is True
        assert "markdown" in r
        assert r["markdown"].startswith("## Context warmup")
        assert r["agent_name"] == "backend-engineer"


# ── product_centroid_drift ──────────────────────────────────────────────────
class TestProductCentroidDriftSmoke:
    def test_imports(self):
        from tools.noctus.dev import product_centroid_drift  # noqa: F401

    def test_snapshot_runs(self):
        from tools.noctus.dev import product_centroid_drift as pcd
        r = pcd.snapshot(record_to_ledger=False)
        assert r["ok"] is True
        assert "products" in r

    def test_history_with_no_ledger_returns_empty(self, tmp_path, monkeypatch):
        from tools.noctus.dev import product_centroid_drift as pcd
        monkeypatch.setattr(pcd, "_ledger_path",
                            lambda: tmp_path / "empty.ndjson")
        r = pcd.history()
        assert r["ok"] is True
        assert r["history"] == []


# ── auto_author_scaffolds ───────────────────────────────────────────────────
class TestAutoAuthorScaffoldsSmoke:
    def test_imports(self):
        from tools.noctus.dev import auto_author_scaffolds  # noqa: F401

    def test_memory_entry_returns_template(self):
        from tools.noctus.dev import auto_author_scaffolds as aas
        r = aas.memory_entry("test-rule", "test description")
        assert r["ok"] is True
        assert "feedback_test-rule.md" in r["filename_suggestion"]
        assert "<TODO" in r["content"]

    def test_kb_pattern_returns_skeleton(self):
        from tools.noctus.dev import auto_author_scaffolds as aas
        r = aas.kb_pattern("test-pattern", "what it does")
        assert r["ok"] is True
        assert r["filename_suggestion"] == "test-pattern.md"
        assert "Why" in r["content"]
        assert "Anti-patterns" in r["content"]

    def test_keeper_returns_function_skeleton(self):
        from tools.noctus.dev import auto_author_scaffolds as aas
        r = aas.keeper("test_keeper", "enforces something")
        assert r["ok"] is True
        assert "def check_test_keeper" in r["code"]
        assert "next_steps" in r
        assert len(r["next_steps"]) >= 3


# ── doc_to_code_drift ───────────────────────────────────────────────────────
class TestDocToCodeDriftSmoke:
    def test_imports(self):
        from tools.noctus.dev import doc_to_code_drift  # noqa: F401

    def test_extract_referents(self):
        from tools.noctus.dev import doc_to_code_drift as dcd
        text = "Some `check_foo_bar` reference and `noctus.dev.baz` and `qux.py`."
        refs = dcd._extract_referents(text)
        assert "check_foo_bar" in refs
        assert "baz" in refs
        assert "qux" in refs

    def test_scan_runs(self):
        from tools.noctus.dev import doc_to_code_drift as dcd
        r = dcd.scan(limit=5)
        assert r["ok"] is True


# ── orphan_branch_sweeper ───────────────────────────────────────────────────
class TestOrphanBranchSweeperSmoke:
    def test_imports(self):
        from tools.noctus.dev import orphan_branch_sweeper  # noqa: F401

    def test_scan_returns_dict(self):
        from tools.noctus.dev import orphan_branch_sweeper as obs
        r = obs.scan()
        assert r["ok"] is True
        assert "branches" in r
        assert "current_branch" in r

    def test_delete_integrated_dry_run_default(self):
        from tools.noctus.dev import orphan_branch_sweeper as obs
        r = obs.delete_integrated(dry_run=True)
        assert r["ok"] is True
        assert r["dry_run"] is True


# ── scan_repetition_semantic ────────────────────────────────────────────────
class TestScanRepetitionSemanticSmoke:
    def test_imports(self):
        from tools.noctus.dev import scan_repetition_semantic  # noqa: F401

    def test_path_kind_classifier(self):
        from tools.noctus.dev import scan_repetition_semantic as srs
        assert srs._path_kind("products/seed/foo.py") == "seed"
        assert srs._path_kind("seed/lib/bar.py") == "seed"
        assert srs._path_kind("products/erp/services/x.py") == "product:erp"

    def test_absorb_candidate_predicate(self):
        from tools.noctus.dev import scan_repetition_semantic as srs
        assert not srs._is_absorb_candidate("product:erp", "product:erp")
        assert srs._is_absorb_candidate("product:erp", "product:therapy")
        assert srs._is_absorb_candidate("seed", "product:erp")

    def test_scan_runs_on_empty_corpus(self, monkeypatch):
        # Mock the corpus to avoid O(N^2) scan on the live cache.
        from tools.noctus.dev import scan_repetition_semantic as srs
        from tools.noctus.dev import code_embeddings as ce
        monkeypatch.setattr(ce, "_load_all_chunk_vectors", lambda: [])
        r = srs.scan(limit=10)
        assert r["ok"] is True
        assert r["total_candidates"] == 0


# ── cache_telemetry ─────────────────────────────────────────────────────────
class TestCacheTelemetrySmoke:
    def test_imports(self):
        from tools.noctus.dev import cache_telemetry  # noqa: F401

    def test_record_silent_on_failure(self, monkeypatch):
        from tools.noctus.dev import cache_telemetry as ct
        # Point at an unwritable location; ensure record() doesn't raise.
        bad = Path("/this/does/not/exist/cache-telemetry.ndjson")
        monkeypatch.setattr(ct, "_ledger_path", lambda: bad)
        ct.record("test-cache", "test-op")  # should NOT raise

    def test_record_writes_then_summary_reads(self, tmp_path, monkeypatch):
        from tools.noctus.dev import cache_telemetry as ct
        target = tmp_path / "telemetry.ndjson"
        monkeypatch.setattr(ct, "_ledger_path", lambda: target)
        ct.record("test-cache", "search", result_count=5, latency_ms=12.3)
        ct.record("test-cache", "refresh", result_count=100)
        ct.record("other-cache", "search", result_count=1)
        r = ct.summary()
        assert r["ok"] is True
        assert r["total"] == 3
        assert r["by_cache"]["test-cache"] == 2
        assert r["by_cache"]["other-cache"] == 1


# ── unified_query — additional smoke (existing tests cover most) ────────────
class TestUnifiedQueryAdditionalSmoke:
    def test_per_source_filter(self, monkeypatch):
        from tools.noctus.dev import unified_query as uq
        from tools.noctus.dev import kb_embeddings as kbe
        from tools.noctus.dev import code_embeddings as ce
        from tools.noctus.dev import kb_recurrence_radar as krr
        monkeypatch.setattr(kbe, "search", lambda *a, **kw: [])
        monkeypatch.setattr(ce, "search", lambda *a, **kw: [])
        monkeypatch.setattr(krr, "consult", lambda **kw: {"ok": True, "hits": []})
        r = uq.query("test", sources=["kb-embeddings"])
        assert r["ok"] is True
        assert "kb-embeddings" in r["by_source"]
        assert "code-embeddings" not in r["by_source"]
