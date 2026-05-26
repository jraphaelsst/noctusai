"""Regression tests for `kb_recurrence_radar` — semantic consult-before-editing
over auto-improvement.ndjson.

KB § CONTEXT/PATTERNS/common/kb-recurrence-radar.md.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import kb_recurrence_radar as krr  # noqa: E402


# ── Fixtures ─────────────────────────────────────────────────────────────────
@pytest.fixture(autouse=True)
def clear_embedding_cache():
    """In-session embedding cache is module-global; reset between tests."""
    krr._DESCRIPTION_EMBEDDING_CACHE.clear()
    yield
    krr._DESCRIPTION_EMBEDDING_CACHE.clear()


@pytest.fixture
def fake_embed(monkeypatch):
    """Deterministic embedding: sha-derived vector. Identical text → same vec."""
    import hashlib

    def _fake(text: str) -> list[float] | None:
        if not text or not text.strip():
            return None
        seed = int.from_bytes(hashlib.sha256(text.encode()).digest()[:4], "big")
        return [((seed * (i + 1)) % 1000) / 1000.0 - 0.5 for i in range(8)]

    monkeypatch.setattr(krr, "_embed", _fake)
    return _fake


@pytest.fixture
def stub_query(monkeypatch):
    """Stub auto_improvement.query so tests don't depend on a real ledger."""
    entries = []

    def _q(open_only=True, limit=500):
        return list(entries)

    from tools.noctus.dev import auto_improvement as ai
    monkeypatch.setattr(ai, "query", _q)
    return entries  # mutate this list per test


# ── _entry_sha (cache key stability) ────────────────────────────────────────
class TestEntrySha:
    def test_stable_for_same_description(self):
        a = {"description": "foo bar baz", "target": "ignored"}
        b = {"description": "foo bar baz", "target": "different"}
        assert krr._entry_sha(a) == krr._entry_sha(b)

    def test_changes_when_description_changes(self):
        a = {"description": "foo bar baz"}
        b = {"description": "foo bar baz!"}
        assert krr._entry_sha(a) != krr._entry_sha(b)


# ── _cosine ──────────────────────────────────────────────────────────────────
class TestCosine:
    def test_identical_vectors_score_one(self):
        v = [1.0, 0.0, 0.0]
        assert krr._cosine(v, v) == pytest.approx(1.0)

    def test_orthogonal_vectors_score_zero(self):
        assert krr._cosine([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)

    def test_zero_vector_returns_zero(self):
        assert krr._cosine([0.0, 0.0], [1.0, 1.0]) == 0.0


# ── consult — validation ─────────────────────────────────────────────────────
class TestConsultValidation:
    def test_requires_text_or_path(self):
        result = krr.consult()
        assert not result["ok"]
        assert "text" in result["error"] or "path" in result["error"]


# ── consult — empty paths ───────────────────────────────────────────────────
class TestConsultEmpty:
    def test_empty_entries_returns_empty(self, stub_query, fake_embed):
        result = krr.consult(text="anything")
        assert result["ok"]
        assert result["hits"] == []

    def test_provider_failure_returns_empty(self, stub_query, monkeypatch):
        # Provider returns None for everything.
        monkeypatch.setattr(krr, "_embed", lambda text: None)
        stub_query.append({"description": "some entry", "target": "x"})
        result = krr.consult(text="query")
        assert result["ok"]
        assert result["hits"] == []


# ── consult — ranking ───────────────────────────────────────────────────────
class TestConsultRanking:
    def test_identical_description_scores_highest(self, stub_query, fake_embed):
        stub_query.extend([
            {"description": "exact match text", "target": "a", "status": "s1-emergent"},
            {"description": "completely different content", "target": "b", "status": "s1-emergent"},
        ])
        result = krr.consult(text="exact match text", top_k=5)
        assert result["ok"]
        assert len(result["hits"]) == 2
        # Identical text → cosine 1.0 → first hit.
        top = result["hits"][0]
        assert top["entry"]["target"] == "a"
        assert top["score"] == pytest.approx(1.0)

    def test_top_k_limit(self, stub_query, fake_embed):
        for i in range(10):
            stub_query.append({
                "description": f"description number {i}",
                "target": f"target-{i}",
                "status": "s1-emergent",
            })
        result = krr.consult(text="probe", top_k=3)
        assert len(result["hits"]) == 3

    def test_min_score_filter(self, stub_query, fake_embed):
        stub_query.append({
            "description": "irrelevant content",
            "target": "x",
            "status": "s1-emergent",
        })
        # Very high min_score: nothing should pass.
        result = krr.consult(text="probe", min_score=0.99)
        # We don't enforce hits=0 strictly (deterministic embed could
        # happen to collide), but we verify the filter is applied.
        for h in result["hits"]:
            assert h["score"] >= 0.99


# ── consult — key_overlap ───────────────────────────────────────────────────
class TestKeyOverlap:
    def test_key_overlap_true_when_path_in_target(self, stub_query, fake_embed):
        stub_query.append({
            "description": "abstract decision about that file",
            "target": "products/erp/services/contacts.py",
            "status": "s1-emergent",
        })
        # min_score=-1.0 to keep all scores (fake-embed cosines can be negative).
        result = krr.consult(path="products/erp/services/contacts.py", top_k=5, min_score=-1.0)
        assert any(h["key_overlap"] for h in result["hits"])

    def test_key_overlap_false_when_path_unrelated(self, stub_query, fake_embed):
        stub_query.append({
            "description": "unrelated abstract content",
            "target": "products/erp/util/dates.py",
            "status": "s1-emergent",
        })
        result = krr.consult(path="products/social/templates.py", top_k=5, min_score=-1.0)
        for h in result["hits"]:
            assert h["key_overlap"] is False


# ── consult — caching ────────────────────────────────────────────────────────
class TestEmbeddingCache:
    def test_descriptions_embedded_once(self, stub_query, monkeypatch):
        call_count = {"n": 0}

        def _counting_embed(text: str) -> list[float] | None:
            call_count["n"] += 1
            return [1.0] * 4

        monkeypatch.setattr(krr, "_embed", _counting_embed)
        stub_query.extend([
            {"description": "A", "target": "a", "status": "s1-emergent"},
            {"description": "B", "target": "b", "status": "s1-emergent"},
        ])
        # First call: 1 query embed + 2 description embeds = 3.
        krr.consult(text="probe")
        first_n = call_count["n"]
        # Second call: only the query embed (descriptions cached). +1 = first_n + 1.
        krr.consult(text="different probe")
        assert call_count["n"] == first_n + 1

    def test_cache_invalidates_on_description_change(self, stub_query, monkeypatch):
        call_count = {"n": 0}

        def _counting_embed(text: str) -> list[float] | None:
            call_count["n"] += 1
            return [1.0] * 4

        monkeypatch.setattr(krr, "_embed", _counting_embed)
        stub_query.append({"description": "original", "target": "x", "status": "s1-emergent"})
        krr.consult(text="probe")
        before = call_count["n"]
        # Mutate the description in-place.
        stub_query[0]["description"] = "MUTATED"
        krr.consult(text="probe")
        # The mutated entry's sha is different → it gets re-embedded.
        assert call_count["n"] > before


# ── consult — path with markdown H1 ─────────────────────────────────────────
class TestPathQueryConstruction:
    def test_md_h1_used_when_present(self, stub_query, fake_embed, tmp_path, monkeypatch):
        # Plant a markdown file with an H1.
        md = tmp_path / "test.md"
        md.write_text("# The Awesome Pattern\n\nSome body content.\n")
        # Patch REPO_ROOT inside settings (lazy import in kb_recurrence_radar).
        from settings import REPO_ROOT as RR_ORIG  # noqa: F401
        import settings
        monkeypatch.setattr(settings, "REPO_ROOT", tmp_path)
        stub_query.append({"description": "Awesome Pattern decision", "target": "test.md", "status": "s1-emergent"})
        result = krr.consult(path="test.md", top_k=5)
        assert result["ok"]
        # Query should contain the H1 title (prefix).
        assert "Awesome Pattern" in result["query"]


# ── Pipeline integration ────────────────────────────────────────────────────
class TestPipeline:
    def test_full_consult_returns_ranked_hits(self, stub_query, fake_embed):
        stub_query.extend([
            {"description": "branching off origin/dev avoids stale-base", "target": "task_branch", "status": "s1-emergent"},
            {"description": "completely orthogonal: gmail oauth pin", "target": "gmail", "status": "s1-emergent"},
            {"description": "branching off origin/dev avoids stale-base", "target": "task_branch (duplicate desc)", "status": "s2-memory"},
        ])
        result = krr.consult(text="branching off origin/dev avoids stale-base", top_k=5)
        assert result["ok"]
        # Both entries with the exact description should rank perfectly (1.0).
        top_two_scores = [h["score"] for h in result["hits"][:2]]
        assert all(s == pytest.approx(1.0) for s in top_two_scores)
