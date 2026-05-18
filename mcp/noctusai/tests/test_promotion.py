"""Tests for `mcp/noctusai/tools/promotion.py` — seed-workspace→noc absorption.

Round-trip:
- create a tmp workspace with a template marker + .promotions/<slug>.md
- create a tmp noc dir
- run promote_from_seed_workspace(slug, dry_run=True) → returns plan
- run promote_from_seed_workspace(slug) → file lands in noc, manifest updated
- adversarial: refuse from primary; refuse `..` escape; refuse missing origin
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from tools.noctus.dev.promotion import (
    PROMOTIONS_DIRNAME,
    list_promotions,
    parse_manifest,
    promote_from_seed_workspace,
)
from workspace import MARKER_FILENAME


def _bootstrap_seed_workspace(ws: Path, noc: Path) -> None:
    """Plant the marker + dirs to make `ws` look like a seed workspace."""
    (ws / "products").mkdir(parents=True, exist_ok=True)
    (ws / "projects").mkdir(parents=True, exist_ok=True)
    (ws / "sandbox").mkdir(parents=True, exist_ok=True)
    (ws / PROMOTIONS_DIRNAME).mkdir(parents=True, exist_ok=True)
    (ws / MARKER_FILENAME).write_text(
        "workspace_kind=seed\n"
        f"workspace_name={ws.name}\n"
        f"noctusai_home={noc}\n"
        "bootstrap_version=1\n",
        encoding="utf-8",
    )


def _write_manifest(ws: Path, slug: str, origin: str, dest: str, promoted: str = "not-yet") -> Path:
    p = ws / PROMOTIONS_DIRNAME / f"{slug}.md"
    p.write_text(
        f"""---
slug: {slug}
origin: {origin}
intended_noc_destination: {dest}
layer_rationale: |
  Test addition; no rationale needed.
seed_first_analysis: |
  Q1 yes. Q2 no. Q3 no. Q4 yes. Q5 yes. Q6 default-on.
dependencies_on_other_additions: []
promoted_on: {promoted}
---

## Why this addition exists
Test fixture.

## Integration notes
Drop into noc as-is.
""",
        encoding="utf-8",
    )
    return p


class TestParseManifest:
    def test_parses_minimal_manifest(self, tmp_path: Path) -> None:
        ws = tmp_path / "ws"; noc = tmp_path / "noc"; noc.mkdir(); ws.mkdir()
        _bootstrap_seed_workspace(ws, noc)
        (ws / "products" / "foo").mkdir(parents=True)
        (ws / "products" / "foo" / "bar.txt").write_text("hi", encoding="utf-8")
        manifest_path = _write_manifest(ws, "foo", "products/foo", "products/foo")
        m = parse_manifest(manifest_path)
        assert m.slug == "foo"
        assert m.origin == ["products/foo"]
        assert m.intended_noc_destination == "products/foo"
        assert m.promoted_on == "not-yet"
        assert "Q1 yes" in m.seed_first_analysis

    def test_refuses_missing_frontmatter(self, tmp_path: Path) -> None:
        p = tmp_path / "no-frontmatter.md"
        p.write_text("just prose, no frontmatter\n", encoding="utf-8")
        with pytest.raises(ValueError, match="frontmatter"):
            parse_manifest(p)

    def test_refuses_missing_required_fields(self, tmp_path: Path) -> None:
        p = tmp_path / "incomplete.md"
        p.write_text("---\nslug: x\n---\n\nbody\n", encoding="utf-8")
        with pytest.raises(ValueError, match="origin"):
            parse_manifest(p)


class TestPromoteRoundTrip:
    def test_dry_run_returns_plan_without_copying(self, tmp_path: Path) -> None:
        ws = tmp_path / "ws"; noc = tmp_path / "noc"; ws.mkdir(); noc.mkdir()
        _bootstrap_seed_workspace(ws, noc)
        (ws / "products" / "foo").mkdir(parents=True)
        (ws / "products" / "foo" / "bar.txt").write_text("payload", encoding="utf-8")
        _write_manifest(ws, "foo", "products/foo", "products/foo")

        result = promote_from_seed_workspace("foo", dry_run=True, workspace_root=ws, noctusai_home=noc)
        assert result["dry_run"] is True
        assert result["promoted_on"] == "dry-run"
        # Destination MUST NOT exist after dry run.
        assert not (noc / "products" / "foo").exists()

    def test_real_promotion_copies_and_marks_promoted(self, tmp_path: Path) -> None:
        ws = tmp_path / "ws"; noc = tmp_path / "noc"; ws.mkdir(); noc.mkdir()
        _bootstrap_seed_workspace(ws, noc)
        (ws / "products" / "foo").mkdir(parents=True)
        (ws / "products" / "foo" / "bar.txt").write_text("payload", encoding="utf-8")
        manifest_path = _write_manifest(ws, "foo", "products/foo", "products/foo")

        result = promote_from_seed_workspace("foo", workspace_root=ws, noctusai_home=noc)
        assert result["dry_run"] is False
        assert result["promoted_on"] == date.today().isoformat()
        # File landed.
        assert (noc / "products" / "foo" / "bar.txt").read_text(encoding="utf-8") == "payload"
        # Manifest updated.
        m = parse_manifest(manifest_path)
        assert m.promoted_on == date.today().isoformat()

    def test_single_file_origin(self, tmp_path: Path) -> None:
        ws = tmp_path / "ws"; noc = tmp_path / "noc"; ws.mkdir(); noc.mkdir()
        _bootstrap_seed_workspace(ws, noc)
        (ws / "noctusai_lib_local").mkdir()
        (ws / "noctusai_lib_local" / "helper.py").write_text("def hi(): pass\n", encoding="utf-8")
        _write_manifest(
            ws,
            "helper",
            "noctusai_lib_local/helper.py",
            "noctusai_lib/integrations/helper.py",
        )

        result = promote_from_seed_workspace("helper", workspace_root=ws, noctusai_home=noc)
        assert result["files_copied"] == ["noctusai_lib/integrations/helper.py"]
        assert (noc / "noctusai_lib" / "integrations" / "helper.py").read_text(encoding="utf-8") == "def hi(): pass\n"


class TestRefusalCases:
    def test_refuses_from_primary_workspace(self, tmp_path: Path) -> None:
        ws = tmp_path / "ws"; ws.mkdir()
        # Plant primary marker — refuses promotion.
        (ws / MARKER_FILENAME).write_text(
            "workspace_kind=primary\nworkspace_name=ws\n", encoding="utf-8"
        )
        (ws / PROMOTIONS_DIRNAME).mkdir()
        (ws / "x.txt").write_text("y", encoding="utf-8")
        _write_manifest(ws, "x", "x.txt", "x.txt")
        with pytest.raises(ValueError, match="primary"):
            promote_from_seed_workspace("x", workspace_root=ws, noctusai_home=ws)

    def test_refuses_origin_outside_workspace(self, tmp_path: Path) -> None:
        ws = tmp_path / "ws"; noc = tmp_path / "noc"; ws.mkdir(); noc.mkdir()
        _bootstrap_seed_workspace(ws, noc)
        # Manifest with `..` escape.
        _write_manifest(ws, "escape", "../outside.txt", "outside.txt")
        with pytest.raises(ValueError, match="outside workspace"):
            promote_from_seed_workspace("escape", workspace_root=ws, noctusai_home=noc)

    def test_refuses_destination_outside_noc(self, tmp_path: Path) -> None:
        ws = tmp_path / "ws"; noc = tmp_path / "noc"; ws.mkdir(); noc.mkdir()
        _bootstrap_seed_workspace(ws, noc)
        (ws / "x.txt").write_text("y", encoding="utf-8")
        _write_manifest(ws, "x", "x.txt", "../outside-noc.txt")
        with pytest.raises(ValueError, match="outside noc_home"):
            promote_from_seed_workspace("x", workspace_root=ws, noctusai_home=noc)

    def test_refuses_already_promoted(self, tmp_path: Path) -> None:
        ws = tmp_path / "ws"; noc = tmp_path / "noc"; ws.mkdir(); noc.mkdir()
        _bootstrap_seed_workspace(ws, noc)
        (ws / "x.txt").write_text("y", encoding="utf-8")
        _write_manifest(ws, "x", "x.txt", "x.txt", promoted="2026-01-01")
        with pytest.raises(ValueError, match="already promoted"):
            promote_from_seed_workspace("x", workspace_root=ws, noctusai_home=noc)

    def test_refuses_missing_origin(self, tmp_path: Path) -> None:
        ws = tmp_path / "ws"; noc = tmp_path / "noc"; ws.mkdir(); noc.mkdir()
        _bootstrap_seed_workspace(ws, noc)
        _write_manifest(ws, "ghost", "does-not-exist.txt", "ghost.txt")
        with pytest.raises(FileNotFoundError, match="does not exist"):
            promote_from_seed_workspace("ghost", workspace_root=ws, noctusai_home=noc)

    def test_refuses_destination_already_exists(self, tmp_path: Path) -> None:
        ws = tmp_path / "ws"; noc = tmp_path / "noc"; ws.mkdir(); noc.mkdir()
        _bootstrap_seed_workspace(ws, noc)
        (ws / "x.txt").write_text("y", encoding="utf-8")
        (noc / "x.txt").write_text("conflict", encoding="utf-8")
        _write_manifest(ws, "x", "x.txt", "x.txt")
        with pytest.raises(FileExistsError, match="already exists"):
            promote_from_seed_workspace("x", workspace_root=ws, noctusai_home=noc)


class TestParseManifestBlockList:
    """Regression: parse_manifest accepts the YAML block-list form of
    `origin:` / `intended_noc_destination:` (not only the inline form).

    Bug: `partition(":")` treated a key whose value is newline-prefixed
    `- item` children as an empty inline scalar → empty destination,
    empty origin. Observed on ~5 of 14 real manifests 2026-05-16.
    """

    _BLOCK_LIST_MANIFEST = """---
slug: google-integrations
origin:
  - products/youtube-crawler/backend/app/services/calendar/
  - products/youtube-crawler/backend/app/routers/calendar_router.py
intended_noc_destination:
  - noctusai_lib/integrations/google/calendar/
  - noctusai_lib/api/calendar_router.py
layer_rationale: |
  Block-scalar still works alongside the new block-list branch.
seed_first_analysis: |
  Q1 yes. Q2 no.
dependencies_on_other_additions:
  - whatsapp-chatbot-service
  - platform-chat-agent
promoted_on: not-yet
---

prose body
"""

    def test_block_list_origin_and_destination_parsed(self, tmp_path: Path) -> None:
        p = tmp_path / "google-integrations.md"
        p.write_text(self._BLOCK_LIST_MANIFEST, encoding="utf-8")
        m = parse_manifest(p)
        assert m.slug == "google-integrations"
        assert m.origin == [
            "products/youtube-crawler/backend/app/services/calendar/",
            "products/youtube-crawler/backend/app/routers/calendar_router.py",
        ]
        # Multi-element block-list destination joined, NON-EMPTY (the bug
        # produced "").
        assert m.intended_noc_destination != ""
        assert m.intended_noc_destination == (
            "noctusai_lib/integrations/google/calendar/; "
            "noctusai_lib/api/calendar_router.py"
        )
        # Block-list also applies to other multi-value keys.
        assert m.dependencies == ["whatsapp-chatbot-service", "platform-chat-agent"]
        # Block-scalar (`|`) keys still parse alongside the new branch.
        assert "Q1 yes" in m.seed_first_analysis
        assert m.promoted_on == "not-yet"

    def test_single_element_block_list_destination_collapses_to_bare_path(
        self, tmp_path: Path
    ) -> None:
        p = tmp_path / "single.md"
        p.write_text(
            "---\n"
            "slug: single\n"
            "origin:\n"
            "  - products/foo/svc.py\n"
            "intended_noc_destination:\n"
            "  - noctusai_lib/integrations/foo.py\n"
            "layer_rationale: |\n"
            "  x\n"
            "seed_first_analysis: |\n"
            "  y\n"
            "dependencies_on_other_additions: []\n"
            "promoted_on: not-yet\n"
            "---\n\nbody\n",
            encoding="utf-8",
        )
        m = parse_manifest(p)
        assert m.origin == ["products/foo/svc.py"]
        # Single-element list collapses → promote pipeline keeps working.
        assert m.intended_noc_destination == "noctusai_lib/integrations/foo.py"

    def test_inline_forms_still_parse_identically(self, tmp_path: Path) -> None:
        """Backward-compat: existing inline-scalar / inline-list manifests
        yield identical results after the block-list extension."""
        p = tmp_path / "inline.md"
        p.write_text(
            "---\n"
            "slug: inline\n"
            "origin: products/foo\n"
            "intended_noc_destination: products/foo\n"
            "layer_rationale: |\n"
            "  inline scalar form unchanged.\n"
            "seed_first_analysis: |\n"
            "  Q1 yes.\n"
            "dependencies_on_other_additions: [a, b]\n"
            "promoted_on: not-yet\n"
            "---\n\nbody\n",
            encoding="utf-8",
        )
        m = parse_manifest(p)
        assert m.origin == ["products/foo"]
        assert m.intended_noc_destination == "products/foo"
        assert m.dependencies == ["a", "b"]
        assert m.promoted_on == "not-yet"


class TestListPromotions:
    def test_lists_pending_and_promoted(self, tmp_path: Path) -> None:
        ws = tmp_path / "ws"; noc = tmp_path / "noc"; ws.mkdir(); noc.mkdir()
        _bootstrap_seed_workspace(ws, noc)
        (ws / "a.txt").write_text("a", encoding="utf-8")
        (ws / "b.txt").write_text("b", encoding="utf-8")
        _write_manifest(ws, "a", "a.txt", "a.txt", promoted="not-yet")
        _write_manifest(ws, "b", "b.txt", "b.txt", promoted="2026-04-01")
        result = list_promotions(ws)
        assert len(result["pending"]) == 1
        assert result["pending"][0]["slug"] == "a"
        assert len(result["promoted"]) == 1
        assert result["promoted"][0]["slug"] == "b"
