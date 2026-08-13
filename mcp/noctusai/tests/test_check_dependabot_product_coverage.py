"""`check_dependabot_product_coverage` — the keeper (backstop) half of the
dependabot-coverage gate.

WHY (2026-08-13). `igig` (live in prod since 2026-08-09), `orbity` (live), and
`products/seed` (in `deploy/fleet/build-scope.txt`) had NO npm block in
`.github/dependabot.yml` — zero Dependabot coverage, silently, for the whole
time they were in production. `a40814b9` fixed the data by hand; this keeper
is the backstop so it can never silently regress. `CLAUDE.md` §1
gate↔methodology-sync: the companion generator is
`noctus.dev.refresh_dependabot_coverage` (`dependabot_sync.py`,
`test_dependabot_sync.py`).

Three legs, pinned in three test classes below:
  1. every products/<slug>/frontend/package.json has a matching npm block
  2. no block points at a directory whose package.json no longer exists
  3. every npm block carries the full 8-entry fleet-major `ignore:` guard

→ KB § PATTERNS/devops/product-lockfile-and-slug-drift.md
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.compliance import check_dependabot_product_coverage  # noqa: E402
from tools.noctus.dev.dependabot_sync import MAJOR_GUARD_DEPS  # noqa: E402

REPO = Path(__file__).resolve().parents[3]

_HEADER = "version: 2\n\nupdates:\n"

_FULLY_GUARDED = """\
  - package-ecosystem: "npm"
    directory: "/products/{slug}/frontend"
    schedule:
      interval: "weekly"
    open-pull-requests-limit: 2
    groups:
      all:
        patterns:
          - "*"
    ignore:
      - dependency-name: "react-router-dom"
        update-types: ["version-update:semver-major"]
      - dependency-name: "react-router"
        update-types: ["version-update:semver-major"]
      - dependency-name: "react"
        update-types: ["version-update:semver-major"]
      - dependency-name: "react-dom"
        update-types: ["version-update:semver-major"]
      - dependency-name: "@types/react"
        update-types: ["version-update:semver-major"]
      - dependency-name: "@types/react-dom"
        update-types: ["version-update:semver-major"]
      - dependency-name: "typescript"
        update-types: ["version-update:semver-major"]
      - dependency-name: "vite"
        update-types: ["version-update:semver-major"]
    labels:
      - "dependencies"
      - "javascript"

"""

_NO_GUARD_AT_ALL = """\
  - package-ecosystem: "npm"
    directory: "/products/{slug}/frontend"
    schedule:
      interval: "weekly"
    open-pull-requests-limit: 2
    groups:
      all:
        patterns:
          - "*"
    labels:
      - "dependencies"
      - "javascript"

"""

_PARTIAL_GUARD = """\
  - package-ecosystem: "npm"
    directory: "/products/{slug}/frontend"
    schedule:
      interval: "weekly"
    open-pull-requests-limit: 2
    groups:
      all:
        patterns:
          - "*"
    ignore:
      - dependency-name: "react-router-dom"
        update-types: ["version-update:semver-major"]
    labels:
      - "dependencies"
      - "javascript"

"""


def _write_dependabot(root: Path, body: str) -> Path:
    p = root / ".github" / "dependabot.yml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(_HEADER + body)
    return p


def _write_product(root: Path, slug: str) -> None:
    pdir = root / "products" / slug / "frontend"
    pdir.mkdir(parents=True)
    (pdir / "package.json").write_text('{"name": "%s-frontend"}' % slug)


class TestLeg1MissingProductBlock:
    """A products/<slug>/frontend with a package.json but no npm block."""

    def test_flags_a_product_with_no_block_at_all(self, tmp_path):
        _write_dependabot(tmp_path, _FULLY_GUARDED.format(slug="core"))
        _write_product(tmp_path, "core")
        _write_product(tmp_path, "igig")  # on disk, uncovered — the real incident shape

        issues = check_dependabot_product_coverage(tmp_path)
        missing = [i for i in issues if i["product"] == "igig"]
        assert len(missing) == 1, issues
        assert missing[0]["severity"] == "high"
        assert "NO npm block" in missing[0]["issue"]

    def test_all_products_covered_no_missing_finding(self, tmp_path):
        _write_dependabot(tmp_path, _FULLY_GUARDED.format(slug="core"))
        _write_product(tmp_path, "core")
        issues = check_dependabot_product_coverage(tmp_path)
        assert issues == [], issues

    def test_product_with_no_frontend_package_json_is_not_required(self, tmp_path):
        # A backend-only product (no frontend/package.json) must NOT be
        # flagged — it was never a Dependabot-npm candidate.
        _write_dependabot(tmp_path, _FULLY_GUARDED.format(slug="core"))
        _write_product(tmp_path, "core")
        (tmp_path / "products" / "headless" / "backend").mkdir(parents=True)
        issues = check_dependabot_product_coverage(tmp_path)
        assert issues == [], issues


class TestLeg2StaleBlock:
    """A block whose directory no longer has a package.json."""

    def test_flags_a_stale_block(self, tmp_path):
        _write_dependabot(tmp_path, _FULLY_GUARDED.format(slug="ghost"))
        # note: no products/ghost on disk at all
        issues = check_dependabot_product_coverage(tmp_path)
        assert len(issues) == 1, issues
        assert issues[0]["product"] == "ghost"
        assert issues[0]["severity"] == "high"
        assert "no package.json any more" in issues[0]["issue"]

    def test_does_not_flag_a_live_block(self, tmp_path):
        _write_dependabot(tmp_path, _FULLY_GUARDED.format(slug="core"))
        _write_product(tmp_path, "core")
        issues = check_dependabot_product_coverage(tmp_path)
        assert issues == [], issues


class TestLeg3GuardCoverage:
    """Every npm block must carry the full 8-entry fleet-major guard."""

    def test_flags_a_fully_unguarded_block(self, tmp_path):
        _write_dependabot(tmp_path, _NO_GUARD_AT_ALL.format(slug="acme"))
        _write_product(tmp_path, "acme")
        issues = check_dependabot_product_coverage(tmp_path)
        guard_issues = [i for i in issues if "guard" in i["issue"]]
        assert len(guard_issues) == 1, issues
        assert guard_issues[0]["severity"] == "high"
        assert "unguarded" in guard_issues[0]["issue"]
        for dep in MAJOR_GUARD_DEPS:
            assert dep in guard_issues[0]["issue"]

    def test_flags_a_partially_guarded_block(self, tmp_path):
        _write_dependabot(tmp_path, _PARTIAL_GUARD.format(slug="core"))
        _write_product(tmp_path, "core")
        issues = check_dependabot_product_coverage(tmp_path)
        guard_issues = [i for i in issues if "guard" in i["issue"]]
        assert len(guard_issues) == 1, issues
        assert "partially guarded" in guard_issues[0]["issue"]
        # already-present entry must not be reported as missing
        assert "react-router-dom" not in guard_issues[0]["issue"]

    def test_fully_guarded_block_is_clean(self, tmp_path):
        _write_dependabot(tmp_path, _FULLY_GUARDED.format(slug="core"))
        _write_product(tmp_path, "core")
        issues = check_dependabot_product_coverage(tmp_path)
        assert issues == [], issues

    def test_non_product_npm_block_is_also_guard_checked(self, tmp_path):
        # seed/lib/frontend is not a /products/<slug>/frontend shape — leg 3
        # (the guard) must still apply to it (the "14 npm blocks" incident).
        body = _NO_GUARD_AT_ALL.format(slug="core").replace(
            '"/products/core/frontend"', '"/seed/lib/frontend"'
        )
        _write_dependabot(tmp_path, body)
        seed_fe = tmp_path / "seed" / "lib" / "frontend"
        seed_fe.mkdir(parents=True)
        (seed_fe / "package.json").write_text('{"name": "@noctusai/lib"}')  # not stale
        issues = check_dependabot_product_coverage(tmp_path)
        assert len(issues) == 1, issues
        assert issues[0]["product"] == "<seed>"


class TestAllClean:
    def test_all_clean_case_zero_issues(self, tmp_path):
        _write_dependabot(
            tmp_path,
            _FULLY_GUARDED.format(slug="core") + _FULLY_GUARDED.format(slug="acme"),
        )
        _write_product(tmp_path, "core")
        _write_product(tmp_path, "acme")
        assert check_dependabot_product_coverage(tmp_path) == []

    def test_no_dependabot_file_no_crash_no_flag(self, tmp_path):
        _write_product(tmp_path, "core")
        assert check_dependabot_product_coverage(tmp_path) == []

    def test_no_products_dir_no_crash_missing_leg_is_silent(self, tmp_path):
        # No `products/` dir at all ⇒ leg 1 (missing-block) has nothing to
        # require — must not crash. A block that still names a directory with
        # no products/ tree behind it is correctly leg-2 stale, so use a
        # dependabot.yml with no npm block at all to isolate leg 1's no-op.
        (tmp_path / ".github").mkdir()
        (tmp_path / ".github" / "dependabot.yml").write_text(_HEADER)
        assert check_dependabot_product_coverage(tmp_path) == []


class TestCheckDependabotProductCoverage:
    """Named for `check_detector_has_regression_test`'s `Test<CamelCase>`
    heuristic — a real true-positive/false-positive pair, not a rubber stamp
    (the finer-grained per-leg classes above are the detailed pins)."""

    def test_true_positive_missing_product_block(self, tmp_path):
        _write_dependabot(tmp_path, _FULLY_GUARDED.format(slug="core"))
        _write_product(tmp_path, "core")
        _write_product(tmp_path, "igig")
        issues = check_dependabot_product_coverage(tmp_path)
        assert any(i["product"] == "igig" for i in issues)

    def test_false_positive_fully_covered_and_guarded_is_clean(self, tmp_path):
        _write_dependabot(tmp_path, _FULLY_GUARDED.format(slug="core"))
        _write_product(tmp_path, "core")
        assert check_dependabot_product_coverage(tmp_path) == []


class TestRealRepoIsGreen:
    def test_real_repo_has_zero_dependabot_coverage_drift(self):
        """The historical bug, proven caught: as of a40814b9 the live repo has
        12/12 product coverage and an 8-entry guard on every npm block. This
        pins that state AND proves the detector would have caught the
        pre-fix tree (see TestCatchesTheHistoricalBug below, which replays
        the exact igig/orbity/seed shape against a synthetic fixture)."""
        issues = check_dependabot_product_coverage(REPO)
        assert issues == [], issues


class TestCatchesTheHistoricalBug:
    """Reconstructs the pre-a40814b9 state (dependabot.yml missing igig,
    orbity, products/seed) against synthetic products, and proves the
    detector fires on it — not just "the current tree is clean"."""

    def test_pre_fix_state_is_flagged_post_fix_state_is_not(self, tmp_path):
        covered = ("core", "erp-imobiliario", "social-wiring", "adconnect")
        uncovered = ("igig", "orbity", "seed")

        body = "".join(_FULLY_GUARDED.format(slug=s) for s in covered)
        _write_dependabot(tmp_path, body)
        for s in covered + uncovered:
            _write_product(tmp_path, s)

        pre_fix_issues = check_dependabot_product_coverage(tmp_path)
        pre_fix_missing = {i["product"] for i in pre_fix_issues}
        assert pre_fix_missing == set(uncovered), pre_fix_issues

        # Now the fixed state: every product covered + guarded.
        body_fixed = "".join(_FULLY_GUARDED.format(slug=s) for s in covered + uncovered)
        _write_dependabot(tmp_path, body_fixed)
        assert check_dependabot_product_coverage(tmp_path) == []
