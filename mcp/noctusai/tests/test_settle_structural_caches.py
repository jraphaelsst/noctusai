"""Tests for settle_structural_caches — heal-on-contact for the zero-OpenAI
STRUCTURAL keeper-mirror caches.

The durable guarantee: structural caches (keeper-patterns / agent-context /
auto-improvement / noc-graph) self-heal whenever freshness is OBSERVED, closing
the staleness gaps that event-hooks structurally cannot catch (git skips
post-merge on fast-forward merges; out-of-commit ndjson appends never fire
pre-commit; the Tier-1 shared cache sees cross-tree integrate transients).
Embedding caches (OpenAI cost) are NEVER healed here — they stay warn-only.

KB § PATTERNS/common/cache-auto-freshness.md § Heal-on-contact.
"""
from tools.noctus.dev import refresh_all_caches as rac


class TestSettleStructuralCaches:
    def test_structural_set_excludes_embedding_caches(self):
        """The healed set must be ONLY zero-OpenAI caches — never an embedding cache."""
        for embedding in ("kb-embeddings", "code-embeddings", "corpus-embeddings", "memory-embeddings"):
            assert embedding not in rac._STRUCTURAL_CACHES
        assert set(rac._STRUCTURAL_CACHES) == {
            "keeper-patterns", "agent-context", "auto-improvement", "noc-graph"
        }

    def test_noop_when_nothing_stale(self, monkeypatch):
        """Nothing stale → no refresh call, healed empty, ok True."""
        calls = []
        monkeypatch.setattr(rac, "detect_stale_caches", lambda root=None: [])
        monkeypatch.setattr(rac, "refresh_all", lambda **kw: calls.append(kw) or {"ok": True})
        r = rac.settle_structural_caches()
        assert r["ok"] is True
        assert r["healed"] == []
        assert r["stale_embedding"] == []
        assert calls == []  # refresh NEVER invoked when nothing is stale

    def test_heals_structural_only_leaves_embedding(self, monkeypatch):
        """Mixed staleness: refresh ONLY the structural subset; embedding reported, not touched."""
        calls = []
        monkeypatch.setattr(
            rac, "detect_stale_caches",
            lambda root=None: ["noc-graph", "auto-improvement", "code-embeddings"],
        )
        monkeypatch.setattr(
            rac, "refresh_all",
            lambda **kw: calls.append(kw) or {"ok": True, "failures": []},
        )
        r = rac.settle_structural_caches()
        assert calls == [{"only": ["noc-graph", "auto-improvement"]}]  # embedding excluded
        assert r["healed"] == ["noc-graph", "auto-improvement"]
        assert r["stale_embedding"] == ["code-embeddings"]
        assert r["ok"] is True

    def test_embedding_only_stale_is_structural_noop(self, monkeypatch):
        """Only an embedding cache stale → no refresh (OpenAI stays human-in-the-loop)."""
        calls = []
        monkeypatch.setattr(rac, "detect_stale_caches", lambda root=None: ["kb-embeddings"])
        monkeypatch.setattr(rac, "refresh_all", lambda **kw: calls.append(kw) or {"ok": True})
        r = rac.settle_structural_caches()
        assert calls == []  # embedding never auto-refreshed here
        assert r["healed"] == []
        assert r["stale_embedding"] == ["kb-embeddings"]

    def test_refresh_failure_reported_not_raised(self, monkeypatch):
        """A failed structural refresh is reported (ok False, name dropped from healed), never raised."""
        monkeypatch.setattr(rac, "detect_stale_caches", lambda root=None: ["noc-graph"])
        monkeypatch.setattr(
            rac, "refresh_all",
            lambda **kw: {"ok": False, "failures": ["noc-graph"]},
        )
        r = rac.settle_structural_caches()
        assert r["ok"] is False
        assert r["healed"] == []  # failed cache is NOT claimed as healed

    def test_preserves_structural_order(self, monkeypatch):
        """Healed list follows detect order, filtered to the structural set."""
        monkeypatch.setattr(
            rac, "detect_stale_caches",
            lambda root=None: ["keeper-patterns", "code-embeddings", "noc-graph"],
        )
        monkeypatch.setattr(rac, "refresh_all", lambda **kw: {"ok": True, "failures": []})
        r = rac.settle_structural_caches()
        assert r["healed"] == ["keeper-patterns", "noc-graph"]
