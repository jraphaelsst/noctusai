"""Tests for ``scripts/gen-promotions-index.py`` — the derived PROMOTIONS.md.

Coverage:
- Empty .promotions/ → "(none)" pending+promoted, exit 0.
- One pending manifest → row in Pending table.
- One promoted manifest (promoted_on=date) → row in Promoted table.
- MANIFEST-TEMPLATE.md is NOT counted as an index row.
- Idempotent: regenerate twice → byte-identical, --check exits 0.
- DRIFT: add a manifest after generating → --check exits 1.
- Stale hand-written index with markers → marker region swapped, header
  preserved (directly reproduces the W0.2 stale-PROMOTIONS.md slip class:
  7-of-14 → all rows derived).
- Unparseable manifest → "Needs attention" section, no silent drop, exit 0.
- No .promotions/ dir → exit 0 with a stderr note (not an error).

The generator is a plain script (dashed filename, lives outside tools/),
so it's imported via spec_from_file_location — same convention as
test_render_history.py.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[3]
_SCRIPT = _REPO / "scripts" / "gen-promotions-index.py"

PENDING_MANIFEST = """\
---
slug: my-adapter
origin: products/x/backend/app/services/foo.py
intended_noc_destination: noctusai_lib/integrations/foo/
layer_rationale: |
  Six-layer model: integration adapter.
seed_first_analysis: |
  Q1 cross-product? YES. readiness: N=2
dependencies_on_other_additions: []
promoted_on: not-yet
---

## Why this addition exists
Because.
"""

PROMOTED_MANIFEST = """\
---
slug: done-thing
origin: products/x/backend/app/services/bar.py
intended_noc_destination: noctusai_lib/domain/bar/
layer_rationale: |
  domain primitive.
seed_first_analysis: |
  Q1 cross-product? YES.
dependencies_on_other_additions: []
promoted_on: 2026-05-10
---

## Why
done.
"""

BROKEN_MANIFEST = "no frontmatter at all, just prose\n"


def _load():
    spec = importlib.util.spec_from_file_location("gen_promotions_index", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def gen():
    return _load()


def _mk_ws(tmp_path: Path) -> Path:
    (tmp_path / ".promotions").mkdir()
    return tmp_path


def test_empty_promotions_dir(gen, tmp_path):
    ws = _mk_ws(tmp_path)
    rc = gen.main(["--workspace", str(ws)])
    assert rc == 0
    out = (ws / "PROMOTIONS.md").read_text()
    assert "## Pending" in out and "## Promoted" in out
    assert out.count("_(none)_") == 2
    assert gen.START_MARKER in out and gen.END_MARKER in out


def test_pending_manifest_row(gen, tmp_path):
    ws = _mk_ws(tmp_path)
    (ws / ".promotions" / "my-adapter.md").write_text(PENDING_MANIFEST)
    rc = gen.main(["--workspace", str(ws)])
    assert rc == 0
    out = (ws / "PROMOTIONS.md").read_text()
    assert "| `my-adapter` | `noctusai_lib/integrations/foo/` | N=2 |" in out
    # not in Promoted
    promoted_section = out.split("## Promoted", 1)[1]
    assert "my-adapter" not in promoted_section


def test_promoted_manifest_row(gen, tmp_path):
    ws = _mk_ws(tmp_path)
    (ws / ".promotions" / "done-thing.md").write_text(PROMOTED_MANIFEST)
    gen.main(["--workspace", str(ws)])
    out = (ws / "PROMOTIONS.md").read_text()
    assert "2026-05-10" in out
    promoted_section = out.split("## Promoted", 1)[1]
    assert "`done-thing`" in promoted_section


def test_manifest_template_not_an_index_row(gen, tmp_path):
    ws = _mk_ws(tmp_path)
    (ws / ".promotions" / gen.MANIFEST_TEMPLATE_NAME).write_text(PENDING_MANIFEST)
    gen.main(["--workspace", str(ws)])
    out = (ws / "PROMOTIONS.md").read_text()
    assert "my-adapter" not in out
    assert out.count("_(none)_") == 2


def test_idempotent_and_check_clean(gen, tmp_path):
    ws = _mk_ws(tmp_path)
    (ws / ".promotions" / "my-adapter.md").write_text(PENDING_MANIFEST)
    gen.main(["--workspace", str(ws)])
    first = (ws / "PROMOTIONS.md").read_text()
    gen.main(["--workspace", str(ws)])
    second = (ws / "PROMOTIONS.md").read_text()
    assert first == second
    assert gen.main(["--workspace", str(ws), "--check"]) == 0


def test_check_detects_drift(gen, tmp_path):
    ws = _mk_ws(tmp_path)
    (ws / ".promotions" / "my-adapter.md").write_text(PENDING_MANIFEST)
    gen.main(["--workspace", str(ws)])
    # Add a second manifest WITHOUT regenerating → drift.
    (ws / ".promotions" / "done-thing.md").write_text(PROMOTED_MANIFEST)
    assert gen.main(["--workspace", str(ws), "--check"]) == 1


def test_stale_handwritten_index_marker_region_swapped(gen, tmp_path):
    """Reproduces the W0.2 slip: a hand-written index lists 1, dir has 2."""
    ws = _mk_ws(tmp_path)
    (ws / ".promotions" / "my-adapter.md").write_text(PENDING_MANIFEST)
    (ws / ".promotions" / "done-thing.md").write_text(PROMOTED_MANIFEST)
    stale = (
        "# Promotion Manifest Index — handcrafted\n\n"
        "CUSTOM PROSE THE AUTHOR WANTS KEPT\n\n"
        f"{gen.START_MARKER}\n## Pending\n- only-one-stale-entry\n{gen.END_MARKER}\n"
    )
    (ws / "PROMOTIONS.md").write_text(stale)
    gen.main(["--workspace", str(ws)])
    out = (ws / "PROMOTIONS.md").read_text()
    assert "CUSTOM PROSE THE AUTHOR WANTS KEPT" in out  # header preserved
    assert "only-one-stale-entry" not in out  # stale region replaced
    assert "`my-adapter`" in out and "`done-thing`" in out  # both derived


def test_unparseable_manifest_surfaced_not_dropped(gen, tmp_path):
    ws = _mk_ws(tmp_path)
    (ws / ".promotions" / "broken.md").write_text(BROKEN_MANIFEST)
    rc = gen.main(["--workspace", str(ws)])
    assert rc == 0
    out = (ws / "PROMOTIONS.md").read_text()
    assert "Needs attention" in out
    assert "`.promotions/broken.md`" in out


def test_no_promotions_dir_is_noop_not_error(gen, tmp_path):
    rc = gen.main(["--workspace", str(tmp_path)])
    assert rc == 0
    assert not (tmp_path / "PROMOTIONS.md").exists()
