"""Tests for noc-graph PER-BUCKET INCREMENTAL rebuild.

The graph derives from 7 disjoint input buckets (code / kb / harness /
landscape / memory / cli / history). The ``code`` bucket is the only expensive
one (the AST walk). The incremental path reuses the cached ``code:*`` nodes when
the code sub-sha is unchanged and re-runs only the cheap knowledge tier + the
global finalization.

These tests lock in the three correctness guarantees:

  (i)   an unchanged bucket is SKIPPED — code unchanged ⇒ the AST walk does not
        re-run (status == "incremental", build_graph not re-invoked for code);
  (ii)  a CHANGED bucket re-extracts WITHOUT orphaning other buckets' nodes —
        editing a kb file updates its node yet every code node survives;
  (iii) FULL vs INCREMENTAL produce the SAME final graph for the same tree —
        the parity oracle that locks the extractor order + reuse equivalence.

All tests run against a throwaway tmp cache + a synthetic mini-repo — they
never touch the live ``.claude/cache/noc-graph.sqlite``.

KB § PATTERNS/architect/noc-graph.md.
KB § PATTERNS/common/cache-auto-freshness.md.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import noc_graph_cache as ngc  # noqa: E402


# ── Synthetic mini-repo ──────────────────────────────────────────────────────


def _write(p: Path, body: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")


def _make_repo(tmp_path: Path) -> Path:
    """A minimal repo exercising every bucket the incremental path touches."""
    repo = tmp_path / "repo"

    # code bucket — seed + mcp + a product, with a cross-file import edge.
    _write(
        repo / "seed" / "lib" / "backend" / "noctusai_lib" / "alpha.py",
        '"""Alpha module."""\n\n\ndef alpha_fn():\n    return 1\n',
    )
    _write(
        repo / "seed" / "lib" / "backend" / "noctusai_lib" / "beta.py",
        '"""Beta module."""\nfrom noctusai_lib import alpha\n\n\nclass Beta:\n    def run(self):\n        return alpha.alpha_fn()\n',
    )
    _write(
        repo / "mcp" / "noctusai" / "cli.py",
        '"""CLI surface."""\n\nif "--demo-flag" in []:\n    pass\n',
    )
    _write(
        repo / "products" / "demo" / "backend" / "service.py",
        '"""Demo service."""\n\n\ndef serve():\n    return "ok"\n',
    )

    # kb bucket — a chapter + a pattern that DOCUMENTS a code file.
    _write(
        repo / "KNOWLEDGE-BASE" / "02-LANDSCAPE.md",
        "# Landscape\n\n## Products\n\n- **demo** — a demo product.\n",
    )
    _write(
        repo / "KNOWLEDGE-BASE" / "PATTERNS" / "backend" / "alpha-pattern.md",
        "# Alpha Pattern\n\nDocuments `seed/lib/backend/noctusai_lib/alpha.py`.\n",
    )

    # harness bucket — an agent pointing at a KB pattern.
    _write(
        repo / ".claude" / "agents" / "demo-agent.md",
        "---\nname: demo-agent\nowns_kb:\n  - PATTERNS/backend/alpha-pattern.md\n---\n\n# Demo agent\n",
    )

    # landscape bucket — CLAUDE.md routing.
    _write(repo / "CLAUDE.md", "# CLAUDE\n\nRouter. KB § PATTERNS/backend/alpha-pattern.md\n")
    _write(repo / "VERSION", "0.1.0\n")

    # history bucket — an auto-improvement event decorating a code node.
    _write(
        repo / "project-history" / "auto-improvement.ndjson",
        '{"target": "seed/lib/backend/noctusai_lib/alpha.py", "stage": "s1", "ts": "2026-01-01T00:00:00Z"}\n',
    )
    return repo


@pytest.fixture()
def repo(tmp_path):
    return _make_repo(tmp_path)


@pytest.fixture()
def tmp_cache(tmp_path, monkeypatch):
    """Redirect cache_path() to a throwaway file — never the live cache."""
    cache_file = tmp_path / "cache" / "noc-graph.sqlite"
    monkeypatch.setattr(ngc, "cache_path", lambda repo_root=None: cache_file)
    # Memory lives outside the repo — force the memory bucket empty + deterministic.
    monkeypatch.setattr(
        "noctusai_lib.graph.build._discover_memory_root", lambda repo_root: None
    )
    # R3 edge injection (SEMANTIC_NEIGHBOR / GUARDED_BY) reaches into the LIVE
    # embeddings + keeper-pattern caches — slow + non-hermetic. It is purely
    # additive and IDENTICAL across the full + incremental paths, so stub it to
    # a no-op: these tests isolate the EXTRACTOR-parity guarantee, not R3.
    # (Accepts the ``reuse_semantic`` kwarg the real signature now carries.)
    monkeypatch.setattr(
        ngc, "_inject_r3_edges", lambda graph, root, reuse_semantic=None: None
    )
    # The semantic-reuse gate also reads the live embeddings caches — stub it to
    # "no fingerprint, no reuse" so the EXTRACTOR-parity tests stay hermetic.
    monkeypatch.setattr(ngc, "_maybe_reuse_semantic", lambda graph, root, force: (None, None))
    return cache_file


# ── Graph snapshot helpers (parity oracle) ───────────────────────────────────


def _snapshot(cache_file: Path) -> dict:
    """Read the persisted graph back as comparable, order-independent sets.

    Node meta excludes the volatile ``cluster`` (recomputed) only if it ever
    diverged — but clustering IS part of correctness, so we keep it: parity must
    hold INCLUDING cluster ids. Edges are full tuples.
    """
    import json
    import sqlite3

    conn = sqlite3.connect(str(cache_file))
    conn.row_factory = sqlite3.Row
    try:
        nodes = {}
        for r in conn.execute(
            "SELECT id, label, kind, path, line, end_line, product, cluster, "
            "confidence, meta_json FROM noc_graph_nodes"
        ):
            nodes[r["id"]] = (
                r["label"], r["kind"], r["path"], r["line"], r["end_line"],
                r["product"], r["cluster"], r["confidence"],
                r["meta_json"],
            )
        edges = set()
        for r in conn.execute(
            "SELECT source, target, kind, confidence, weight, meta_json FROM noc_graph_edges"
        ):
            edges.add((
                r["source"], r["target"], r["kind"], r["confidence"],
                r["weight"], r["meta_json"],
            ))
        return {"nodes": nodes, "edges": edges}
    finally:
        conn.close()


def _full_refresh(repo: Path) -> dict:
    return ngc.refresh(force=True, repo_root=repo)


# ── (i) unchanged bucket is skipped ──────────────────────────────────────────


class TestUnchangedBucketSkipsAstWalk:
    def test_in_sync_short_circuits_when_nothing_changed(self, repo, tmp_cache):
        _full_refresh(repo)
        # No file changed → aggregate sha matches → in-sync no-op.
        res = ngc.refresh(force=False, repo_root=repo)
        assert res["status"] == "in-sync"
        assert res["rows_written"] == 0

    def test_code_unchanged_uses_incremental_and_skips_build_graph(self, repo, tmp_cache):
        _full_refresh(repo)
        # Change ONLY a kb file → aggregate sha differs, but code bucket sha
        # is unchanged → incremental path, AST walk skipped.
        _write(
            repo / "KNOWLEDGE-BASE" / "PATTERNS" / "backend" / "alpha-pattern.md",
            "# Alpha Pattern (edited)\n\nDocuments `seed/lib/backend/noctusai_lib/alpha.py`.\n",
        )
        import noctusai_lib.graph as gmod
        with patch.object(gmod, "build_graph", wraps=gmod.build_graph) as spy:
            res = ngc.refresh(force=False, repo_root=repo)
        assert res["status"] == "incremental"
        # build_graph (the full extractor incl. AST walk) must NOT be invoked.
        spy.assert_not_called()

    def test_code_change_falls_back_to_full(self, repo, tmp_cache):
        _full_refresh(repo)
        # Edit a CODE file → code bucket sha changes → full rebuild.
        _write(
            repo / "seed" / "lib" / "backend" / "noctusai_lib" / "alpha.py",
            '"""Alpha module edited."""\n\n\ndef alpha_fn():\n    return 2\n',
        )
        import noctusai_lib.graph as gmod
        with patch.object(gmod, "build_graph", wraps=gmod.build_graph) as spy:
            res = ngc.refresh(force=False, repo_root=repo)
        assert res["status"] == "refreshed"
        spy.assert_called_once()


# ── (ii) changed bucket re-extracts without orphaning other buckets ──────────


class TestChangedBucketNoOrphans:
    def test_kb_edit_updates_kb_node_and_preserves_all_code_nodes(self, repo, tmp_cache):
        _full_refresh(repo)
        before = _snapshot(tmp_cache)
        code_ids_before = {nid for nid in before["nodes"] if nid.startswith("code:")}
        assert code_ids_before, "fixture must produce code nodes"

        _write(
            repo / "KNOWLEDGE-BASE" / "PATTERNS" / "backend" / "alpha-pattern.md",
            "# Alpha Pattern RENAMED\n\nDocuments `seed/lib/backend/noctusai_lib/alpha.py`.\n",
        )
        res = ngc.refresh(force=False, repo_root=repo)
        assert res["status"] == "incremental"

        after = _snapshot(tmp_cache)
        code_ids_after = {nid for nid in after["nodes"] if nid.startswith("code:")}
        # No code node orphaned or dropped.
        assert code_ids_after == code_ids_before
        # The kb node's label reflects the edit (bucket re-extracted).
        kb_node = next(
            v for k, v in after["nodes"].items()
            if k.endswith("PATTERNS/backend/alpha-pattern.md")
        )
        assert kb_node[0] == "Alpha Pattern RENAMED"

    def test_history_decoration_recomputed_not_stale_on_incremental(self, repo, tmp_cache):
        _full_refresh(repo)
        # Drop the auto-improvement event (history bucket changes). Code is
        # unchanged → incremental. The reused code node must LOSE its stale
        # ai_* decoration (history re-runs from scratch).
        _write(repo / "project-history" / "auto-improvement.ndjson", "")
        res = ngc.refresh(force=False, repo_root=repo)
        assert res["status"] == "incremental"
        after = _snapshot(tmp_cache)
        import json as _json
        alpha = after["nodes"]["code:seed/lib/backend/noctusai_lib/alpha.py"]
        meta = _json.loads(alpha[8]) if alpha[8] else {}
        assert "ai_events" not in meta, "stale history decoration leaked into reused code node"


# ── (iii) full vs incremental parity ─────────────────────────────────────────


class TestFullVsIncrementalParity:
    def _assert_parity(self, incremental_snapshot, repo, tmp_path):
        # Re-create an IDENTICAL tree in a clean repo + clean cache, full-build it.
        ref_repo = repo  # same tree; full-rebuild it from scratch into a fresh cache
        ref_cache = tmp_path / "ref-cache" / "noc-graph.sqlite"
        with patch.object(ngc, "cache_path", lambda repo_root=None: ref_cache):
            ngc.refresh(force=True, repo_root=ref_repo)
            full_snapshot = _snapshot(ref_cache)
        assert incremental_snapshot["nodes"] == full_snapshot["nodes"], (
            "node sets diverge between incremental and full rebuild"
        )
        assert incremental_snapshot["edges"] == full_snapshot["edges"], (
            "edge sets diverge between incremental and full rebuild"
        )

    def test_kb_edit_incremental_equals_full(self, repo, tmp_cache, tmp_path):
        _full_refresh(repo)
        _write(
            repo / "KNOWLEDGE-BASE" / "PATTERNS" / "backend" / "alpha-pattern.md",
            "# Alpha Pattern v2\n\nDocuments `seed/lib/backend/noctusai_lib/alpha.py`.\n",
        )
        res = ngc.refresh(force=False, repo_root=repo)
        assert res["status"] == "incremental"
        incremental = _snapshot(tmp_cache)
        self._assert_parity(incremental, repo, tmp_path)

    def test_harness_edit_incremental_equals_full(self, repo, tmp_cache, tmp_path):
        _full_refresh(repo)
        _write(
            repo / ".claude" / "agents" / "demo-agent.md",
            "---\nname: demo-agent\nowns_kb:\n  - PATTERNS/backend/alpha-pattern.md\n---\n\n# Demo agent v2\n",
        )
        res = ngc.refresh(force=False, repo_root=repo)
        assert res["status"] == "incremental"
        incremental = _snapshot(tmp_cache)
        self._assert_parity(incremental, repo, tmp_path)

    def test_history_edit_incremental_equals_full(self, repo, tmp_cache, tmp_path):
        _full_refresh(repo)
        _write(
            repo / "project-history" / "auto-improvement.ndjson",
            '{"target": "seed/lib/backend/noctusai_lib/alpha.py", "stage": "s1", "ts": "2026-01-01T00:00:00Z"}\n'
            '{"target": "seed/lib/backend/noctusai_lib/beta.py", "stage": "s2", "ts": "2026-02-01T00:00:00Z"}\n',
        )
        res = ngc.refresh(force=False, repo_root=repo)
        assert res["status"] == "incremental"
        incremental = _snapshot(tmp_cache)
        self._assert_parity(incremental, repo, tmp_path)


# ── per-bucket sub-sha plumbing ──────────────────────────────────────────────


class TestBucketShaPlumbing:
    def test_all_buckets_get_a_sha(self, repo, tmp_cache):
        shas = ngc.compute_bucket_shas(repo)
        assert set(shas) == set(ngc._BUCKETS)
        # Each in-tree bucket present in the fixture is non-empty-distinct.
        assert shas["code"] != shas["kb"]

    def test_only_edited_bucket_sha_changes(self, repo, tmp_cache):
        before = ngc.compute_bucket_shas(repo)
        _write(
            repo / "KNOWLEDGE-BASE" / "PATTERNS" / "backend" / "alpha-pattern.md",
            "# edited\n",
        )
        after = ngc.compute_bucket_shas(repo)
        assert after["kb"] != before["kb"]
        for b in ngc._BUCKETS:
            if b != "kb":
                assert after[b] == before[b], f"bucket {b} sha changed unexpectedly"

    def test_cached_bucket_shas_persisted(self, repo, tmp_cache):
        ngc.refresh(force=True, repo_root=repo)
        cached = ngc.get_cached_bucket_shas(repo)
        assert set(cached) == set(ngc._BUCKETS)
        assert cached == ngc.compute_bucket_shas(repo)


# ── SEMANTIC_NEIGHBOR cross-bucket-edge reuse gate (the dominant-cost win) ────
#
# SEMANTIC_NEIGHBOR is the ~60s O(N²) cosine — the practical 1-2 min cost. The
# pairs are a PURE FUNCTION of (embeddings, node-id-set), captured by
# ``semantic_neighbor_fingerprint``. These tests lock the reuse equivalence
# invariant: when the fingerprint is unchanged the persisted semantic edges are
# reused VERBATIM and the cosine is skipped, producing a graph IDENTICAL to a
# from-scratch recompute. When any input changes, the fingerprint busts and the
# cosine recomputes (correctness over speed).
#
# These run WITHOUT the tmp_cache fixture's R3 stub so the REAL
# ``_inject_r3_edges`` + ``_maybe_reuse_semantic`` execute — but the cosine +
# embeddings + keeper reads are stubbed deterministically here (hermetic, fast).


@pytest.fixture()
def tmp_cache_real_r3(tmp_path, monkeypatch):
    """Like ``tmp_cache`` but leaves the REAL R3 + reuse-gate code in place.

    The expensive / non-hermetic leaves (cosine, embeddings load, keeper read)
    are stubbed deterministically so the reuse LOGIC runs end-to-end fast.
    """
    cache_file = tmp_path / "cache" / "noc-graph.sqlite"
    monkeypatch.setattr(ngc, "cache_path", lambda repo_root=None: cache_file)
    monkeypatch.setattr(
        "noctusai_lib.graph.build._discover_memory_root", lambda repo_root: None
    )
    return cache_file


def _stub_semantic(monkeypatch, *, fingerprint, pairs, recompute_counter):
    """Stub the seed-side R3 leaves used by the real ``_inject_r3_edges``.

    ``fingerprint`` — value returned by ``semantic_neighbor_fingerprint``.
    ``pairs``       — (id_a, id_b, score) tuples the cosine "computes".
    ``recompute_counter`` — a list; appended to each time the cosine runs (so a
                            test can assert it was SKIPPED on the reuse path).
    """
    import tools.noctus.graph.build as B

    def _fake_cosine(graph, root):
        recompute_counter.append(1)
        node_ids = {n.id for n in graph.nodes}
        return [(a, b, s) for (a, b, s) in pairs if a in node_ids and b in node_ids]

    monkeypatch.setattr(B, "_compute_semantic_neighbors", _fake_cosine)
    monkeypatch.setattr(B, "_compute_guarded_by_edges", lambda graph, root: [])
    monkeypatch.setattr(
        B, "semantic_neighbor_fingerprint", lambda graph, root: fingerprint
    )


def _semantic_edges(cache_file: Path) -> set:
    snap = _snapshot(cache_file)
    return {e for e in snap["edges"] if e[2] == "semantic_neighbor"}


class TestSemanticReuseEquivalence:
    def test_unchanged_fingerprint_reuses_and_skips_cosine(self, repo, tmp_cache_real_r3, monkeypatch):
        counter: list = []
        # A pair between two real code nodes the fixture produces.
        pairs = [(
            "code:seed/lib/backend/noctusai_lib/alpha.py",
            "code:seed/lib/backend/noctusai_lib/beta.py",
            0.93,
        )]
        _stub_semantic(monkeypatch, fingerprint="fp-stable", pairs=pairs, recompute_counter=counter)

        # First (forced) build → cosine runs once, edges persisted.
        ngc.refresh(force=True, repo_root=repo)
        assert len(counter) == 1, "first build must run the cosine"
        full_sem = _semantic_edges(tmp_cache_real_r3)
        assert full_sem, "fixture must yield at least one semantic edge"

        # Edit ONLY a kb file → aggregate sha differs (rebuild triggers), code
        # bucket unchanged (incremental assembly), fingerprint UNCHANGED → reuse.
        _write(
            repo / "KNOWLEDGE-BASE" / "PATTERNS" / "backend" / "alpha-pattern.md",
            "# Alpha Pattern edited\n\nDocuments `seed/lib/backend/noctusai_lib/alpha.py`.\n",
        )
        res = ngc.refresh(force=False, repo_root=repo)
        assert res["status"] == "incremental"
        # Cosine must NOT have re-run.
        assert len(counter) == 1, "cosine re-ran despite unchanged fingerprint"
        # Semantic edges identical (reused verbatim).
        assert _semantic_edges(tmp_cache_real_r3) == full_sem

    def test_changed_fingerprint_recomputes(self, repo, tmp_cache_real_r3, monkeypatch):
        counter: list = []
        pairs = [(
            "code:seed/lib/backend/noctusai_lib/alpha.py",
            "code:seed/lib/backend/noctusai_lib/beta.py",
            0.91,
        )]
        # First build with one fingerprint.
        _stub_semantic(monkeypatch, fingerprint="fp-v1", pairs=pairs, recompute_counter=counter)
        ngc.refresh(force=True, repo_root=repo)
        assert len(counter) == 1

        # Bump the fingerprint (simulating an embeddings-cache change) → recompute.
        _stub_semantic(monkeypatch, fingerprint="fp-v2", pairs=pairs, recompute_counter=counter)
        _write(
            repo / "KNOWLEDGE-BASE" / "PATTERNS" / "backend" / "alpha-pattern.md",
            "# Alpha Pattern v3\n",
        )
        res = ngc.refresh(force=False, repo_root=repo)
        assert res["status"] == "incremental"
        assert len(counter) == 2, "cosine must re-run when the fingerprint busts"

    def test_reuse_path_equals_full_recompute(self, repo, tmp_cache_real_r3, tmp_path, monkeypatch):
        """The equivalence ORACLE: reuse-path graph == a from-scratch full build.

        Builds once (recompute), mutates a non-semantic bucket (kb), rebuilds
        incrementally with the SAME fingerprint (reuse). Then full-rebuilds the
        mutated tree from a clean cache. The two semantic-edge sets MUST match.
        """
        counter: list = []
        pairs = [(
            "code:seed/lib/backend/noctusai_lib/alpha.py",
            "code:seed/lib/backend/noctusai_lib/beta.py",
            0.88,
        )]
        _stub_semantic(monkeypatch, fingerprint="fp-eq", pairs=pairs, recompute_counter=counter)

        ngc.refresh(force=True, repo_root=repo)
        _write(
            repo / "KNOWLEDGE-BASE" / "PATTERNS" / "backend" / "alpha-pattern.md",
            "# Alpha Pattern eq\n\nDocuments `seed/lib/backend/noctusai_lib/alpha.py`.\n",
        )
        res = ngc.refresh(force=False, repo_root=repo)
        assert res["status"] == "incremental"
        reuse_snapshot = _snapshot(tmp_cache_real_r3)

        # From-scratch full rebuild of the mutated tree into a clean cache.
        ref_cache = tmp_path / "ref-cache" / "noc-graph.sqlite"
        with patch.object(ngc, "cache_path", lambda repo_root=None: ref_cache):
            ngc.refresh(force=True, repo_root=repo)
            full_snapshot = _snapshot(ref_cache)

        # FULL equivalence — node set AND edge set (incl. semantic) must match.
        assert reuse_snapshot["nodes"] == full_snapshot["nodes"]
        assert reuse_snapshot["edges"] == full_snapshot["edges"]


class TestSemanticFingerprintDeterminism:
    """The fingerprint itself — stable for equal inputs, sensitive to changes."""

    def test_fingerprint_stable_and_node_sensitive(self, repo, tmp_cache_real_r3):
        from noctusai_lib.graph import build_graph
        from tools.noctus.graph.build import semantic_neighbor_fingerprint

        g1 = build_graph(repo, scope="repo")
        fp1 = semantic_neighbor_fingerprint(g1, repo)
        fp1_again = semantic_neighbor_fingerprint(g1, repo)
        assert fp1 == fp1_again, "fingerprint must be deterministic for equal inputs"
        assert isinstance(fp1, str) and fp1

        # Drop a node → fingerprint must change (node-id-set is an input).
        g1.nodes = g1.nodes[:-1]
        assert semantic_neighbor_fingerprint(g1, repo) != fp1
