"""The active-scope contract (2026-09-22) — asleep products leave every gate.

Pins: (1) the generator derives `active ∩ on-disk + core`; (2) `filter_active`
FAILS TOWARD COVERAGE when the file is missing (never silently turns gates off);
(3) the checked-in files keep `build-scope ⊆ active-scope` — a live product that
the gates skip would ship untested. → KB § PATTERNS/architect/product-working-scope.md
"""
from __future__ import annotations

import logging
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import build_scope as bs  # noqa: E402
from tools.noctus.dev import product_scope as ps  # noqa: E402

REPO = Path(__file__).resolve().parents[3]


def _repo(tmp_path: Path, products: list[str]) -> Path:
    for slug in products:
        (tmp_path / "products" / slug).mkdir(parents=True)
    return tmp_path


def test_generator_intersects_catalog_with_disk_and_adds_core(tmp_path):
    root = _repo(tmp_path, ["core", "seed", "igig", "therapy-platform"])
    r = ps.refresh_active_scope(_active=["seed", "igig", "pilates"], root=root)
    assert r["ok"] and r["status"] == "written"
    assert r["slugs"] == ["core", "igig", "seed"]
    assert r["dormant"] == ["therapy-platform"]
    assert r["catalog_only"] == ["pilates"]
    assert ps.read_active_scope(root) == ["core", "igig", "seed"]


def test_regenerate_same_set_is_in_sync(tmp_path):
    root = _repo(tmp_path, ["core", "seed"])
    ps.refresh_active_scope(_active=["seed"], root=root)
    assert ps.refresh_active_scope(_active=["seed"], root=root)["status"] == "in-sync"


def test_filter_and_dormant(tmp_path):
    root = _repo(tmp_path, ["core", "seed", "therapy-platform"])
    ps.refresh_active_scope(_active=["seed"], root=root)
    assert ps.filter_active(["seed", "therapy-platform", "core"], root) == ["seed", "core"]
    assert ps.is_active("seed", root) and not ps.is_active("therapy-platform", root)
    assert ps.dormant_slugs(root) == ["therapy-platform"]


def test_missing_file_fails_toward_coverage_loudly(tmp_path, caplog):
    root = _repo(tmp_path, ["core", "therapy-platform"])
    with caplog.at_level(logging.WARNING):
        assert ps.filter_active(["core", "therapy-platform"], root) == ["core", "therapy-platform"]
    assert "missing" in caplog.text
    assert ps.dormant_slugs(root) == []


def test_catalog_unreachable_is_an_error_not_a_guess(tmp_path, monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    r = ps.refresh_active_scope(root=_repo(tmp_path, ["core"]))
    assert r["ok"] is False and r["status"] == "error"


def test_checked_in_build_scope_is_subset_of_active_scope():
    active = ps.read_active_scope(REPO)
    assert active is not None, "deploy/fleet/active-scope.txt is missing"
    missing = sorted(set(bs.read_build_scope()) - set(active))
    assert not missing, (
        f"{missing} are built+deployed (build-scope.txt) but asleep (active-scope.txt) — "
        "they would ship with no gate checking them. Run --refresh-build-scope."
    )


def test_checked_in_active_scope_names_real_products():
    active = ps.read_active_scope(REPO) or []
    ghosts = [s for s in active if not (REPO / "products" / s).is_dir()]
    assert not ghosts, f"active-scope.txt lists {ghosts} with no products/<slug>/ dir"


def test_every_gate_surface_agrees_with_active_scope():
    """The guarantee: no gate surface checks an asleep product or skips an awake one.

    A new gate that walks `products/*` without `filter_active` turns its product
    `MIXED` here and fails CI — the scope cannot leak silently.
    """
    rep = ps.product_scope_report(root=REPO, catalog=False)
    mixed = {s: r["surfaces"] for s, r in rep["products"].items() if r["verdict"] == "MIXED"}
    assert not mixed, f"gate surfaces disagree with active-scope.txt: {mixed}"
    active = set(ps.read_active_scope(REPO) or [])
    for slug, row in rep["products"].items():
        assert row["verdict"] == ("awake" if slug in active else "asleep"), (slug, row)


_WALK = re.compile(
    r"(PRODUCTS_DIR|products_root|products_dir|base_products_dir|eff_products_dir|"
    r"/ \"products\"\))[^#\n]*\.(iterdir|r?glob)\(|r?glob\([\"']products/\*"
)


def test_every_products_walk_declares_its_scope():
    """Compliance by construction: a walk over `products/` in the toolkit must say
    whether it skips asleep products (`# product-scope: active`) or deliberately
    sees all of them (`# product-scope: all — <reason>`), on the line or up to 2
    lines above. A new unmarked walk is exactly how therapy-platform leaked into
    the pre-push ledger check after the first sweep — this fails CI instead.
    """
    toolkit = REPO / "mcp" / "noctusai"
    unmarked = []
    # Tools AND the toolkit's own real-repo tests: the TS-corpus test walked asleep
    # products too, and only surfaced when p-studio's wake-up ran the full suite.
    for path in sorted([*(toolkit / "tools" / "noctus" / "dev").glob("*.py"), *(toolkit / "tests").glob("*.py")]):
        if path.name in ("product_scope.py", "test_product_scope.py"):
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        for i, line in enumerate(lines):
            if line.lstrip().startswith("#") or not _WALK.search(line):
                continue
            window = "\n".join(lines[max(0, i - 2): i + 1])
            if "product-scope:" not in window:
                unmarked.append(f"{path.name}:{i + 1}: {line.strip()}")
    assert not unmarked, "products/ walks without a `# product-scope:` marker:\n" + "\n".join(unmarked)
