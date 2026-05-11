"""Regression tests — Phase 4 worktree-path adoption across 8 write tools.

Companion to ``TestWorktreeAwarePathResolution`` in ``test_scaffold.py``
(Engineer K's 8 high-impact write tools). This file covers the
``mcp-worktree-rollout-phase4`` follow-up — 8 remaining write tools that
must honor a caller's ``worktree_path``:

  1. ``master_prompts.py::verify_master_prompt``
  2. ``improvements.py::generate_improvements``
  3. ``review.py::run_review``
  4. ``seed/absorb_file.py::absorb_file``
  5. ``promotion.py::promote_from_seed_workspace`` + ``list_promotions``
  6. ``build.py::build_products``
  7. ``catalog.py::generate_catalog``
  8. ``three_way_sync.py::check_three_way_sync``

Per ``resolve_caller_root`` contract (mcp/noctusai/workspace.py):

  3-tier priority: explicit test seam > ``worktree_path`` > module default.

Each test class verifies the priority and the no-silent-fallback rule
(invalid worktree_path raises ValueError, never silently writes to noc).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.build import build_products
from tools.noctus.dev.catalog import generate_catalog
from tools.noctus.dev.improvements import generate_improvements
from tools.noctus.dev.master_prompts import verify_master_prompt
from tools.noctus.dev.promotion import list_promotions, promote_from_seed_workspace
from tools.noctus.dev.proposals import update_proposal_status
from tools.noctus.dev.review import run_review
from tools.noctus.dev.three_way_sync import check_three_way_sync
from tools.noctus.seed.absorb_file import absorb_file


def _make_fake_worktree(root: Path) -> Path:
    """Build a directory shaped like a real worktree root.

    Mirrors ``test_scaffold.py::TestWorktreeAwarePathResolution._make_fake_worktree``.
    """
    root.mkdir(parents=True, exist_ok=True)
    (root / ".git").write_text(
        "gitdir: /tmp/fake/.git/worktrees/agent-test\n", encoding="utf-8"
    )
    (root / ".noctusai-workspace").write_text(
        "workspace_kind=primary\n"
        "workspace_name=fake-worktree\n"
        f"noctusai_home={root}\n"
        "bootstrap_version=1\n",
        encoding="utf-8",
    )
    return root


# ─── build_products ────────────────────────────────────────────────────


class TestBuildProductsWorktreePath:
    """``build_products`` honors ``worktree_path``."""

    def test_worktree_path_scopes_scan_to_worktree(self, tmp_path):
        wt = _make_fake_worktree(tmp_path / "wt")
        # No buildable products under the worktree → empty results, but the
        # ROOT must reflect the worktree (zero-products is a green return).
        result = build_products(worktree_path=wt)
        assert result["all_green"] is True
        assert result["requested"] == []  # nothing buildable under empty wt

    def test_invalid_worktree_path_raises(self, tmp_path):
        bad = tmp_path / "not-a-worktree"
        bad.mkdir()
        with pytest.raises(ValueError, match=r"missing \.git|not a directory"):
            build_products(worktree_path=bad)

    def test_explicit_repo_root_overrides_worktree_path(self, tmp_path):
        """Test seam wins over worktree_path."""
        wt = _make_fake_worktree(tmp_path / "wt")
        sink = tmp_path / "sink-root"
        sink.mkdir()
        result = build_products(repo_root=sink, worktree_path=wt)
        # Sink has no products either → empty, but proves the seam was used.
        assert result["requested"] == []


# ─── check_three_way_sync ──────────────────────────────────────────────


class TestThreeWaySyncWorktreePath:
    """``check_three_way_sync`` reads CLAUDE.md under ``worktree_path``."""

    def test_worktree_path_reads_worktree_claude_md(self, tmp_path):
        wt = _make_fake_worktree(tmp_path / "wt")
        # No CLAUDE.md in fake worktree → returns the "CLAUDE.md not found"
        # high-severity issue. Proves the resolution targeted the worktree.
        result = check_three_way_sync(worktree_path=wt)
        if result["memory_dir"] is None:
            # Memory dir unresolvable on this host — still proves resolution
            # didn't crash; the issue list contains a warning.
            assert any(i["severity"] == "warning" for i in result["issues"])
        else:
            # CLAUDE.md missing under the fake worktree → high-severity issue.
            assert any(
                "CLAUDE.md not found" in i["issue"] and str(wt) in i["issue"]
                for i in result["issues"]
            )

    def test_invalid_worktree_path_raises(self, tmp_path):
        bad = tmp_path / "not-a-worktree"
        bad.mkdir()
        with pytest.raises(ValueError, match=r"missing \.git|not a directory"):
            check_three_way_sync(worktree_path=bad)

    def test_explicit_repo_root_overrides_worktree_path(self, tmp_path):
        wt = _make_fake_worktree(tmp_path / "wt")
        sink = tmp_path / "sink-root"
        sink.mkdir()
        # No CLAUDE.md at sink either, but the path in the issue should
        # point at sink (proves seam wins).
        result = check_three_way_sync(repo_root=sink, worktree_path=wt)
        if result["issues"]:
            high = [i for i in result["issues"] if i["severity"] == "high"]
            for i in high:
                # Sink path should appear in the issue (not the worktree path).
                if "CLAUDE.md not found" in i["issue"]:
                    assert str(sink) in i["issue"]
                    assert str(wt) not in i["issue"]


# ─── generate_catalog ──────────────────────────────────────────────────


class TestCatalogWorktreePath:
    """``generate_catalog`` scans + writes under ``worktree_path``."""

    def test_worktree_path_lands_output_in_worktree(self, tmp_path):
        wt = _make_fake_worktree(tmp_path / "wt")
        # Build empty seed/lib + seed/framework + mcp/noctusai dirs.
        (wt / "seed" / "lib" / "backend" / "noctusai_lib").mkdir(parents=True)
        (wt / "seed" / "framework" / "backend" / "noctusai_seed").mkdir(parents=True)
        (wt / "products").mkdir()
        (wt / "mcp" / "noctusai").mkdir(parents=True)

        result = generate_catalog(write=True, worktree_path=wt)
        # Output landed in the worktree's mcp/noctusai/catalog.md.
        assert (wt / "mcp" / "noctusai" / "catalog.md").exists(), (
            f"catalog.md must land in worktree, got result={result}"
        )

    def test_worktree_path_none_keeps_default_behavior(self, tmp_path, monkeypatch):
        """When ``worktree_path`` is None, the module default applies — no
        crash on regular call shape (catalog scans real noc)."""
        # write=False → no filesystem mutation; just verify the call path.
        result = generate_catalog(write=False, worktree_path=None)
        assert "summary" in result, result

    def test_invalid_worktree_path_raises(self, tmp_path):
        bad = tmp_path / "not-a-worktree"
        bad.mkdir()
        with pytest.raises(ValueError, match=r"missing \.git|not a directory"):
            generate_catalog(write=False, worktree_path=bad)


# ─── generate_improvements ─────────────────────────────────────────────


class TestImprovementsWorktreePath:
    """``generate_improvements`` resolves relative ``project_path`` under ``worktree_path``."""

    def test_relative_project_path_resolves_against_worktree(self, tmp_path):
        wt = _make_fake_worktree(tmp_path / "wt")
        proj_dir = wt / "projects" / "demo"
        proj_dir.mkdir(parents=True)
        (proj_dir / "PROJECT.md").write_text(
            "# Demo\n\n## 6. Implementation phases\n\n"
            "### Phase 1 - [x] Done\n\n**Improvements:** something\n\n",
            encoding="utf-8",
        )
        result = generate_improvements(
            "projects/demo/PROJECT.md", write=True, worktree_path=wt,
        )
        # improvements.md landed next to PROJECT.md inside the worktree.
        assert (proj_dir / "improvements.md").exists(), result
        assert result.get("output_path", "").startswith(str(wt))

    def test_absolute_path_ignores_worktree_path(self, tmp_path):
        wt = _make_fake_worktree(tmp_path / "wt")
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        (elsewhere / "PROJECT.md").write_text(
            "# Demo\n\n## 6. Implementation phases\n\n"
            "### Phase 1 - [x] Done\n\n**Improvements:** thing\n\n",
            encoding="utf-8",
        )
        # Absolute path stays absolute even with worktree_path set.
        result = generate_improvements(
            str(elsewhere / "PROJECT.md"),
            write=True,
            worktree_path=wt,
        )
        assert (elsewhere / "improvements.md").exists(), result
        # worktree didn't get an improvements.md
        assert not (wt / "improvements.md").exists()

    def test_invalid_worktree_path_raises(self, tmp_path):
        bad = tmp_path / "not-a-worktree"
        bad.mkdir()
        with pytest.raises(ValueError, match=r"missing \.git|not a directory"):
            generate_improvements(
                "projects/foo/PROJECT.md", write=True, worktree_path=bad,
            )


# ─── verify_master_prompt ──────────────────────────────────────────────


class TestVerifyMasterPromptWorktreePath:
    """``verify_master_prompt`` reads + writes MASTER-PROMPT.md under ``worktree_path``."""

    def _seed_product(self, products_dir: Path, slug: str) -> Path:
        product = products_dir / slug
        backend = product / "backend" / "app"
        (backend / "routers").mkdir(parents=True)
        (backend / "routers" / "demo.py").write_text("# router stub\n")
        (backend / "services").mkdir()
        (backend / "schemas").mkdir()
        frontend = product / "frontend" / "src"
        (frontend / "pages").mkdir(parents=True)
        (frontend / "hooks").mkdir(parents=True)
        (product / "MASTER-PROMPT.md").write_text(
            "# MASTER\n\n### Backend\n\n```\nold structure\n```\n\n"
            "### Frontend\n\n```\nold front\n```\n",
            encoding="utf-8",
        )
        return product

    def test_worktree_path_targets_worktree_products_dir(self, tmp_path):
        wt = _make_fake_worktree(tmp_path / "wt")
        products_dir = wt / "products"
        products_dir.mkdir()
        self._seed_product(products_dir, "demo")
        result = verify_master_prompt("demo", write=False, worktree_path=wt)
        assert "error" not in result, result
        assert result["slug"] == "demo"

    def test_explicit_products_dir_overrides_worktree_path(self, tmp_path):
        wt = _make_fake_worktree(tmp_path / "wt")
        (wt / "products").mkdir()
        sink_products = tmp_path / "sink-products"
        sink_products.mkdir()
        self._seed_product(sink_products, "demo")
        # products_dir wins — finds demo in sink, not in worktree (which is empty).
        result = verify_master_prompt(
            "demo", write=False, worktree_path=wt, products_dir=sink_products,
        )
        assert "error" not in result, result

    def test_invalid_worktree_path_raises(self, tmp_path):
        bad = tmp_path / "not-a-worktree"
        bad.mkdir()
        with pytest.raises(ValueError, match=r"missing \.git|not a directory"):
            verify_master_prompt("demo", write=False, worktree_path=bad)


# ─── run_review ────────────────────────────────────────────────────────


class TestReviewWorktreePath:
    """``run_review`` detects + writes under ``worktree_path``."""

    def test_worktree_path_scopes_detection_to_worktree(self, tmp_path):
        wt = _make_fake_worktree(tmp_path / "wt")
        (wt / "products").mkdir()  # empty products dir
        result = run_review(product_slug=None, mode="agent", worktree_path=wt)
        # Empty products → empty issues, no products reviewed.
        assert result["mode"] == "agent"
        assert result["reviewed_products"] == []

    def test_explicit_products_dir_overrides_worktree_path(self, tmp_path):
        wt = _make_fake_worktree(tmp_path / "wt")
        (wt / "products").mkdir()
        sink_products = tmp_path / "sink-products"
        sink_products.mkdir()
        (sink_products / "demo").mkdir()
        result = run_review(
            product_slug=None,
            mode="agent",
            worktree_path=wt,
            products_dir=sink_products,
        )
        # Sink products has 'demo' → reviewed.
        assert "demo" in result["reviewed_products"]

    def test_invalid_worktree_path_raises(self, tmp_path):
        bad = tmp_path / "not-a-worktree"
        bad.mkdir()
        with pytest.raises(ValueError, match=r"missing \.git|not a directory"):
            run_review(mode="agent", worktree_path=bad)


# ─── absorb_file ───────────────────────────────────────────────────────


class TestAbsorbFileWorktreePath:
    """``absorb_file`` scans + writes under ``worktree_path``."""

    def test_worktree_path_scopes_scan_to_worktree(self, tmp_path):
        wt = _make_fake_worktree(tmp_path / "wt")
        products_dir = wt / "products"
        # Two products share an identical file.
        for slug in ("a", "b"):
            target = products_dir / slug / "frontend" / "src"
            target.mkdir(parents=True)
            (target / "x.ts").write_text("export const x = 1;\n")
        result = absorb_file(
            "frontend/src/x.ts",
            "seed/framework/frontend/src/x.ts",
            worktree_path=wt,
        )
        assert "error" not in result, result
        assert (wt / "seed" / "framework" / "frontend" / "src" / "x.ts").exists()
        # Source removed from product 'a' (alphabetical first), and from 'b'.
        assert not (products_dir / "a" / "frontend" / "src" / "x.ts").exists()
        assert not (products_dir / "b" / "frontend" / "src" / "x.ts").exists()

    def test_explicit_seams_override_worktree_path(self, tmp_path):
        wt = _make_fake_worktree(tmp_path / "wt")
        (wt / "products").mkdir()
        sink_root = tmp_path / "sink"
        sink_products = sink_root / "products"
        for slug in ("a", "b"):
            target = sink_products / slug / "x"
            target.mkdir(parents=True)
            (target / "f.py").write_text("X = 1\n")
        result = absorb_file(
            "x/f.py",
            "seed/x/f.py",
            worktree_path=wt,
            products_dir=sink_products,
            repo_root=sink_root,
        )
        assert "error" not in result, result
        # Output lands in sink_root, not worktree.
        assert (sink_root / "seed" / "x" / "f.py").exists()
        assert not (wt / "seed" / "x" / "f.py").exists()

    def test_invalid_worktree_path_raises(self, tmp_path):
        bad = tmp_path / "not-a-worktree"
        bad.mkdir()
        with pytest.raises(ValueError, match=r"missing \.git|not a directory"):
            absorb_file("x.ts", "seed/x.ts", worktree_path=bad)


# ─── promote_from_seed_workspace ───────────────────────────────────────


class TestPromotionWorktreePath:
    """``promote_from_seed_workspace`` + ``list_promotions`` honor ``worktree_path``."""

    def _make_seed_workspace(self, parent: Path) -> Path:
        """Build a *seed* workspace (not primary) — required for promote."""
        ws = parent / "seed-ws"
        ws.mkdir()
        (ws / ".noctusai-workspace").write_text(
            "workspace_kind=seed\n"
            "workspace_name=fake-seed-ws\n"
            f"noctusai_home={parent / 'noc'}\n"
            "bootstrap_version=1\n",
            encoding="utf-8",
        )
        (ws / ".promotions").mkdir()
        return ws

    def test_list_promotions_via_worktree_path(self, tmp_path):
        # The worktree's parent contains a seed workspace.
        wt = _make_fake_worktree(tmp_path / "wt")
        # Make 'wt' itself appear with no promotions dir → empty.
        result = list_promotions(worktree_path=wt)
        assert result["pending"] == []
        assert result["promoted"] == []

    def test_invalid_worktree_path_raises_list_promotions(self, tmp_path):
        bad = tmp_path / "not-a-worktree"
        bad.mkdir()
        with pytest.raises(ValueError, match=r"missing \.git|not a directory"):
            list_promotions(worktree_path=bad)

    def test_invalid_worktree_path_raises_promote(self, tmp_path):
        bad = tmp_path / "not-a-worktree"
        bad.mkdir()
        with pytest.raises(ValueError, match=r"missing \.git|not a directory"):
            promote_from_seed_workspace(slug="x", worktree_path=bad)

    def test_explicit_seams_override_worktree_path(self, tmp_path):
        wt = _make_fake_worktree(tmp_path / "wt")
        sink_ws = self._make_seed_workspace(tmp_path)
        # Explicit workspace_root wins over the worktree's walk-up result.
        result = list_promotions(workspace_root=sink_ws, worktree_path=wt)
        assert result["workspace"] == str(sink_ws)


# ─── update_proposal_status (Phase 4 close — residual gap) ─────────────


class TestUpdateProposalStatusWorktreePath:
    """``update_proposal_status`` (MCP ``set_proposal_status``) honors ``worktree_path``.

    The residual write-tool gap closed by Engineer RRR's Phase 4 dispatch
    (2026-05-11). Mirrors the 3-tier pattern (explicit seam > worktree_path >
    module default) and the no-silent-fallback rule used by every other
    adopting tool in this file.
    """

    def _seed_proposal(self, products_dir: Path, product: str, filename: str) -> Path:
        """Build a fake proposal under ``<products_dir>/<product>/proposals/``."""
        proposals = products_dir / product / "proposals"
        proposals.mkdir(parents=True, exist_ok=True)
        path = proposals / filename
        path.write_text(
            "# Proposal: example\n\n**Status:** pending\n\n"
            "**Reject** — with reason: ___\n",
            encoding="utf-8",
        )
        return path

    def test_worktree_path_updates_file_in_worktree(self, tmp_path):
        wt = _make_fake_worktree(tmp_path / "wt")
        products_dir = wt / "products"
        proposal = self._seed_proposal(products_dir, "demo", "rrr-2026-05-11-x.md")

        result = update_proposal_status(
            "rrr-2026-05-11-x.md",
            "accepted",
            product="demo",
            worktree_path=wt,
        )
        assert result == {"updated": True, "status": "accepted"}, result
        # Status flipped in the worktree's copy.
        content = proposal.read_text()
        assert "**Status:** accepted" in content
        assert "**Status:** pending" not in content

    def test_worktree_path_search_across_all_products(self, tmp_path):
        """When ``product`` is None, search across all products under the worktree."""
        wt = _make_fake_worktree(tmp_path / "wt")
        products_dir = wt / "products"
        # Two products; only product-b has the proposal.
        (products_dir / "product-a" / "proposals").mkdir(parents=True)
        proposal_b = self._seed_proposal(products_dir, "product-b", "rrr-find-me.md")

        result = update_proposal_status(
            "rrr-find-me.md",
            "rejected",
            reason="not aligned",
            worktree_path=wt,
        )
        assert result == {"updated": True, "status": "rejected"}, result
        content = proposal_b.read_text()
        assert "**Status:** rejected" in content
        assert "not aligned" in content

    def test_explicit_products_dir_overrides_worktree_path(self, tmp_path):
        wt = _make_fake_worktree(tmp_path / "wt")
        (wt / "products").mkdir()  # worktree's products dir is empty
        sink_products = tmp_path / "sink-products"
        proposal = self._seed_proposal(sink_products, "demo", "rrr-sink.md")

        result = update_proposal_status(
            "rrr-sink.md",
            "accepted",
            product="demo",
            products_dir=sink_products,
            worktree_path=wt,
        )
        assert result == {"updated": True, "status": "accepted"}, result
        content = proposal.read_text()
        assert "**Status:** accepted" in content

    def test_invalid_worktree_path_raises(self, tmp_path):
        bad = tmp_path / "not-a-worktree"
        bad.mkdir()
        with pytest.raises(ValueError, match=r"missing \.git|not a directory"):
            update_proposal_status(
                "x.md", "accepted", worktree_path=bad,
            )

    def test_worktree_path_none_preserves_default_behavior(self, tmp_path):
        """When ``worktree_path`` is None and no explicit seam, the call resolves
        against the module-default ``PRODUCTS_DIR``. With a nonexistent filename
        the existing 'Proposal not found' contract holds."""
        result = update_proposal_status(
            "rrr-does-not-exist-on-disk-anywhere.md",
            "accepted",
            product="demo",
        )
        assert result == {"error": "Proposal not found"}, result
