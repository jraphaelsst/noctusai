"""Regression tests for `check_product_lockfile_dep_sync`.

The 2026-07-22 devops escalation: a product's `package.json` can declare a
required dep (FRAMEWORK_DEPS, or a live seed-organ transitive import per
`check_framework_deps._required_deps`) while its `package-lock.json`
snapshot — what a clean `npm ci` actually materializes into `node_modules`
— never caught up. N=3 in one session: `@dnd-kit/*` (commit `acfef9bb`),
`recharts` + `@radix-ui/react-tabs` (chart-organ promotion, broke SEVEN
products), and the sibling shape in `check_hardcoded_product_slug_set`
(`scripts/infra/build-and-push.sh`'s `ALL_SLUGS`).

This detector guards the OTHER half of the drift `check_framework_deps`
already guards: that check audits the DECLARATION (package.json); this one
audits the RESOLVED SNAPSHOT (package-lock.json). A product can pass
`check_framework_deps` and still fail here — that's the actual gap this
test pins.

See `KB § PATTERNS/devops/product-lockfile-and-slug-drift.md`.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.compliance import check_product_lockfile_dep_sync  # noqa: E402


def _write_product(
    root: Path,
    slug: str,
    deps: dict[str, str],
    lockfile_packages: dict[str, dict] | None,
) -> None:
    """Write `products/<slug>/frontend/{package.json,package-lock.json}`.

    `lockfile_packages` is the `packages` dict of a lockfileVersion-3
    package-lock.json (keyed `node_modules/<dep>`, plus the root `""` entry).
    Pass `None` to omit the lockfile entirely (detector must skip, not crash).
    """
    pdir = root / "products" / slug / "frontend"
    pdir.mkdir(parents=True)
    (pdir / "package.json").write_text(
        json.dumps({"name": f"{slug}-frontend", "dependencies": deps}, indent=2)
    )
    if lockfile_packages is not None:
        lock = {
            "name": f"{slug}-frontend",
            "lockfileVersion": 3,
            "packages": {
                "": {"name": f"{slug}-frontend", "dependencies": deps},
                **lockfile_packages,
            },
        }
        (pdir / "package-lock.json").write_text(json.dumps(lock, indent=2))


class TestProductLockfileDepSync:
    """`check_product_lockfile_dep_sync` — package.json declares a required
    dep; package-lock.json's resolved snapshot must actually carry it.
    """

    def test_flags_dep_declared_but_missing_from_lockfile(self, tmp_path: Path):
        # `react` is a FRAMEWORK_DEP; declared in package.json but the
        # lockfile's `packages` dict has no `node_modules/react` entry — the
        # exact @dnd-kit/recharts shape: npm ci silently won't install it.
        _write_product(
            tmp_path, "acme",
            deps={"react": "^18.3.1"},
            lockfile_packages={},  # no node_modules/react entry at all
        )
        issues = check_product_lockfile_dep_sync(tmp_path)
        assert len(issues) == 1, issues
        assert issues[0]["product"] == "acme"
        assert issues[0]["severity"] == "high"
        assert "react" in issues[0]["issue"]
        assert "npm ci" in issues[0]["issue"]

    def test_does_not_flag_when_lockfile_has_the_entry(self, tmp_path: Path):
        _write_product(
            tmp_path, "acme",
            deps={"react": "^18.3.1"},
            lockfile_packages={
                "node_modules/react": {"version": "18.3.1", "license": "MIT"},
            },
        )
        issues = check_product_lockfile_dep_sync(tmp_path)
        assert issues == [], issues

    def test_no_lockfile_no_crash_no_flag(self, tmp_path: Path):
        # A product mid-scaffold with no lockfile yet — skip, don't crash.
        _write_product(tmp_path, "acme", deps={"react": "^18.3.1"}, lockfile_packages=None)
        issues = check_product_lockfile_dep_sync(tmp_path)
        assert issues == [], issues

    def test_dep_not_declared_is_not_this_detectors_problem(self, tmp_path: Path):
        # A required dep absent from package.json entirely is
        # `check_framework_deps`'s finding, not this detector's — this
        # detector only flags a dep that IS declared but whose lockfile
        # snapshot is stale.
        _write_product(
            tmp_path, "acme",
            deps={},  # react not declared at all
            lockfile_packages={},
        )
        issues = check_product_lockfile_dep_sync(tmp_path)
        assert issues == [], issues

    def test_no_products_dir_no_error(self, tmp_path: Path):
        issues = check_product_lockfile_dep_sync(tmp_path)
        assert issues == []

    def test_multiple_products_each_reported_independently(self, tmp_path: Path):
        _write_product(tmp_path, "acme", deps={"react": "^18.3.1"}, lockfile_packages={})
        _write_product(
            tmp_path, "beta",
            deps={"react": "^18.3.1"},
            lockfile_packages={"node_modules/react": {"version": "18.3.1"}},
        )
        issues = check_product_lockfile_dep_sync(tmp_path)
        assert len(issues) == 1, issues
        assert issues[0]["product"] == "acme"

    def test_real_repo_is_green(self):
        """The live repo (as of this commit) must have zero drift — the
        2026-07-22 knowledge-extractor @dnd-kit gap this session found was
        fixed via a scoped lockfile splice (not a bare `npm install`, which
        would have re-resolved the whole tree)."""
        repo_root = Path(__file__).resolve().parents[3]
        issues = check_product_lockfile_dep_sync(repo_root)
        assert issues == [], issues
