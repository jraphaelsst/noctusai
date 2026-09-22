"""The active-scope contract (2026-09-22) — asleep products leave every gate.

Pins: (1) the generator derives `active ∩ on-disk + core`; (2) `filter_active`
FAILS TOWARD COVERAGE when the file is missing (never silently turns gates off);
(3) the checked-in files keep `build-scope ⊆ active-scope` — a live product that
the gates skip would ship untested. → KB § PATTERNS/architect/product-working-scope.md
"""
from __future__ import annotations

import logging
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
