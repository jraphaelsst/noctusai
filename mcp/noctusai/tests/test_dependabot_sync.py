"""`sync_dependabot_coverage` — the generator half of the dependabot-coverage
gate (`noctus.dev.refresh_dependabot_coverage`).

WHY (2026-08-13). `.github/dependabot.yml` is a hand-maintained per-product list
— the same drift class `check_hardcoded_product_slug_set` (frozen slug literals)
and `check_product_lockfile_dep_sync` (stale lockfile snapshots) already gate.
`igig` (live in prod since 2026-08-09), `orbity` (live), and `products/seed`
(in `deploy/fleet/build-scope.txt`) had NO npm block at all — zero Dependabot
coverage, silently, because nothing was watching those directories. Fixed by
hand in `a40814b9`; this module is the DERIVE-IT mechanism.

`CLAUDE.md` §1 gate↔methodology-sync: the keeper (`check_dependabot_product_
coverage`, pinned in `test_check_dependabot_product_coverage.py`) is the
backstop; this generator is the compliance-by-construction mechanism — a
targeted repair that preserves every existing comment/entry byte-for-byte.

→ KB § PATTERNS/devops/product-lockfile-and-slug-drift.md
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.dependabot_sync import (  # noqa: E402
    MAJOR_GUARD_DEPS,
    sync_dependabot_coverage,
)

REPO = Path(__file__).resolve().parents[3]

_HEADER = """\
version: 2

# A load-bearing rationale comment that MUST survive every repair verbatim —
# the whole point of a targeted repair over a full-file regeneration.

updates:
"""

_CORE_BLOCK = """\
  - package-ecosystem: "npm"
    directory: "/products/core/frontend"
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

_ACME_BLOCK_NO_GUARD = """\
  - package-ecosystem: "npm"
    directory: "/products/acme/frontend"
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

_GHOST_BLOCK = """\
  - package-ecosystem: "npm"
    directory: "/products/ghost/frontend"
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

_GH_ACTIONS = """\
  # ── GitHub Actions ────────────────────────────────────────────────────────

  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
"""


def _write_dependabot(root: Path, body: str) -> Path:
    p = root / ".github" / "dependabot.yml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(_HEADER + body + _GH_ACTIONS)
    return p


def _write_product(root: Path, slug: str) -> None:
    pdir = root / "products" / slug / "frontend"
    pdir.mkdir(parents=True)
    (pdir / "package.json").write_text('{"name": "%s-frontend"}' % slug)


class TestMissingProductBlock:
    def test_adds_a_block_for_an_uncovered_product(self, tmp_path):
        _write_dependabot(tmp_path, _CORE_BLOCK)
        _write_product(tmp_path, "core")
        _write_product(tmp_path, "beta")  # on disk, no block yet

        r = sync_dependabot_coverage(root=tmp_path)
        assert r["ok"] and r["status"] == "written"
        assert r["added"] == ["beta"]

        text = (tmp_path / ".github" / "dependabot.yml").read_text()
        assert '"/products/beta/frontend"' in text
        for dep in MAJOR_GUARD_DEPS:
            assert f'"{dep}"' in text

    def test_new_block_lands_before_the_github_actions_section(self, tmp_path):
        _write_dependabot(tmp_path, _CORE_BLOCK)
        _write_product(tmp_path, "core")
        _write_product(tmp_path, "beta")
        sync_dependabot_coverage(root=tmp_path)
        text = (tmp_path / ".github" / "dependabot.yml").read_text()
        assert text.index('"/products/beta/frontend"') < text.index("GitHub Actions")

    def test_existing_comments_survive_byte_for_byte(self, tmp_path):
        _write_dependabot(tmp_path, _CORE_BLOCK)
        _write_product(tmp_path, "core")
        _write_product(tmp_path, "beta")
        sync_dependabot_coverage(root=tmp_path)
        text = (tmp_path / ".github" / "dependabot.yml").read_text()
        assert "A load-bearing rationale comment that MUST survive" in text

    def test_two_missing_products_both_added(self, tmp_path):
        _write_dependabot(tmp_path, _CORE_BLOCK)
        _write_product(tmp_path, "core")
        _write_product(tmp_path, "beta")
        _write_product(tmp_path, "alpha")
        r = sync_dependabot_coverage(root=tmp_path)
        assert r["added"] == ["alpha", "beta"]


class TestStaleBlockIsReportedNeverRemoved:
    def test_stale_block_reported(self, tmp_path):
        # /products/ghost/frontend has a block but no product on disk.
        _write_dependabot(tmp_path, _CORE_BLOCK + _GHOST_BLOCK)
        _write_product(tmp_path, "core")
        r = sync_dependabot_coverage(root=tmp_path)
        assert r["stale"] == ["products/ghost/frontend"]

    def test_stale_block_is_never_deleted(self, tmp_path):
        _write_dependabot(tmp_path, _CORE_BLOCK + _GHOST_BLOCK)
        _write_product(tmp_path, "core")
        sync_dependabot_coverage(root=tmp_path)
        text = (tmp_path / ".github" / "dependabot.yml").read_text()
        assert '"/products/ghost/frontend"' in text

    def test_stale_only_is_in_sync_not_written(self, tmp_path):
        """core is fully guarded and ghost is stale-but-untouched — nothing to
        WRITE (stale is report-only), so status must be in-sync, not written."""
        _write_dependabot(tmp_path, _GHOST_BLOCK)
        r = sync_dependabot_coverage(root=tmp_path)
        assert r["status"] == "in-sync"
        assert r["stale"] == ["products/ghost/frontend"]


class TestGuardRepair:
    def test_unguarded_block_gets_the_full_guard(self, tmp_path):
        _write_dependabot(tmp_path, _ACME_BLOCK_NO_GUARD)
        _write_product(tmp_path, "acme")
        r = sync_dependabot_coverage(root=tmp_path)
        assert r["ok"] and r["status"] == "written"
        assert set(r["guard_fixed"]["/products/acme/frontend"]) == set(MAJOR_GUARD_DEPS)
        text = (tmp_path / ".github" / "dependabot.yml").read_text()
        for dep in MAJOR_GUARD_DEPS:
            assert f'"{dep}"' in text

    def test_partially_guarded_block_gets_only_the_missing_entries(self, tmp_path):
        # _CORE_BLOCK carries only react-router-dom.
        _write_dependabot(tmp_path, _CORE_BLOCK)
        _write_product(tmp_path, "core")
        r = sync_dependabot_coverage(root=tmp_path)
        assert r["status"] == "written"
        gap = set(r["guard_fixed"]["/products/core/frontend"])
        assert gap == set(MAJOR_GUARD_DEPS) - {"react-router-dom"}
        text = (tmp_path / ".github" / "dependabot.yml").read_text()
        # the pre-existing entry is not duplicated
        assert text.count('"react-router-dom"') == 1
        for dep in MAJOR_GUARD_DEPS:
            assert f'"{dep}"' in text

    def test_fully_guarded_block_is_untouched(self, tmp_path):
        _write_dependabot(tmp_path, _GHOST_BLOCK.replace("ghost", "core"))
        _write_product(tmp_path, "core")
        before = (tmp_path / ".github" / "dependabot.yml").read_text()
        r = sync_dependabot_coverage(root=tmp_path)
        assert r["status"] == "in-sync"
        assert (tmp_path / ".github" / "dependabot.yml").read_text() == before


class TestAllCleanIsIdempotent:
    def test_second_run_is_a_true_no_op(self, tmp_path):
        _write_dependabot(tmp_path, _CORE_BLOCK + _ACME_BLOCK_NO_GUARD)
        _write_product(tmp_path, "core")
        _write_product(tmp_path, "acme")
        _write_product(tmp_path, "beta")

        first = sync_dependabot_coverage(root=tmp_path)
        assert first["status"] == "written"
        after_first = (tmp_path / ".github" / "dependabot.yml").read_text()

        second = sync_dependabot_coverage(root=tmp_path)
        assert second["status"] == "in-sync"
        assert second["added"] == [] and second["guard_fixed"] == {}
        assert (tmp_path / ".github" / "dependabot.yml").read_text() == after_first

    def test_all_clean_from_the_start_is_in_sync(self, tmp_path):
        _write_dependabot(tmp_path, _GHOST_BLOCK.replace("ghost", "core"))
        _write_product(tmp_path, "core")
        r = sync_dependabot_coverage(root=tmp_path)
        assert r["ok"] and r["status"] == "in-sync" and r["changed"] is False


class TestDryRun:
    def test_dry_run_writes_nothing(self, tmp_path):
        _write_dependabot(tmp_path, _CORE_BLOCK)
        _write_product(tmp_path, "core")
        _write_product(tmp_path, "beta")
        before = (tmp_path / ".github" / "dependabot.yml").read_text()

        r = sync_dependabot_coverage(root=tmp_path, write=False)
        assert r["status"] == "would-write"
        assert r["added"] == ["beta"]
        assert (tmp_path / ".github" / "dependabot.yml").read_text() == before


class TestMissingFileIsAnHonestError:
    def test_no_dependabot_yml_is_error_not_crash(self, tmp_path):
        (tmp_path / "products").mkdir()
        r = sync_dependabot_coverage(root=tmp_path)
        assert r["ok"] is False and r["status"] == "error"


class TestRealRepoIsGreen:
    def test_real_repo_needs_no_write(self):
        """The live repo (as of this commit) is already fully covered + guarded
        — the 2026-08-13 fix (a40814b9) plus this session's own additions. A
        second run must report in-sync, proving the generator is idempotent
        against the real file, not just synthetic fixtures."""
        r = sync_dependabot_coverage(root=REPO, write=False)
        assert r["ok"], r
        assert r["added"] == [], r["added"]
        assert r["guard_fixed"] == {}, r["guard_fixed"]
