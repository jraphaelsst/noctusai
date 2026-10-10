"""`settle_scope_artifacts` — a product sleep/wake leaves ZERO derived-list drift.

WHY (2026-10-10). The scope bot flipped `active-scope.txt` / `build-scope.txt`
but not the lists derived from them, so every owner deactivation (community,
store, orbity, p-studio) turned dev CI red. This pins the composed fix: after a
simulated sleep AND wake, every scope-fed keeper reports nothing.
→ KB § PATTERNS/devops/product-lockfile-and-slug-drift.md
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import compliance  # noqa: E402
from tools.noctus.dev.dependabot_sync import _render_missing_block  # noqa: E402
from tools.noctus.dev.propagate import propagate_composes, propagate_dockerfiles  # noqa: E402
from tools.noctus.dev.scope_settle import SETTLED_FILES, settle_scope_artifacts  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
PRODUCTS = ["core", "igig", "orbity"]  # all registered in the real start.sh

_WORKFLOW = """\
jobs:
  product-backend-tests:
    strategy:
      matrix:
        product:
{items}

  product-frontend-tests:
    strategy:
      matrix:
        product:
{items}

  trivy:
    runs-on: ubuntu-latest
"""


def _tree(tmp_path: Path) -> Path:
    for rel in ("start.sh", "products/seed/docker-compose.yml", "products/seed/backend/Dockerfile"):
        dst = tmp_path / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(REPO / rel, dst)
    for slug in PRODUCTS:
        (tmp_path / "products" / slug / "frontend" / "src").mkdir(parents=True)
        (tmp_path / "products" / slug / "frontend" / "package.json").write_text("{}")
        (tmp_path / "products" / slug / "frontend" / "src" / "a.test.ts").write_text("x")
        (tmp_path / "products" / slug / "backend" / "tests").mkdir(parents=True)
        (tmp_path / "products" / slug / "backend" / "tests" / "test_a.py").write_text("x")
    (tmp_path / "deploy" / "fleet").mkdir(parents=True)
    (tmp_path / "deploy" / "fleet" / "docker-compose.prod.yml").write_text(
        "services:\n" + "".join(f"  {s}:\n    image: x\n" for s in PRODUCTS)
    )
    blocks = "".join("".join(_render_missing_block(s, "2026-10-10")) + "\n" for s in PRODUCTS)
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    (tmp_path / ".github" / "dependabot.yml").write_text(
        "version: 2\nupdates:\n" + blocks + "  # ── GitHub Actions ──\n  - package-ecosystem: \"github-actions\"\n    directory: \"/\"\n"
    )
    (wf / "test.yml").write_text(_WORKFLOW.format(items="\n".join(f"          - {s}" for s in PRODUCTS)))
    return tmp_path


def _all_keepers_clean(root: Path) -> None:
    assert compliance.check_dependabot_product_coverage(repo_root=root) == []
    assert compliance.check_ci_test_matrix_coverage(repo_root=root) == []
    assert propagate_composes(check=True, repo_root=str(root))["stale"] == []
    assert propagate_dockerfiles(check=True, repo_root=str(root))["stale"] == []


def test_sleep_then_wake_leaves_no_derived_drift(tmp_path):
    root = _tree(tmp_path)

    # SLEEP orbity: the catalog payload now lists only core + igig.
    r = settle_scope_artifacts(root=root, live=["igig"], active=["igig"])
    assert r["ok"], r
    assert r["steps"]["dependabot"]["pruned"] == ["orbity"]
    dep = (root / ".github" / "dependabot.yml").read_text()
    assert "/products/orbity/frontend" not in dep and "/products/igig/frontend" in dep
    assert "GitHub Actions" in dep  # the section marker survives the prune
    _all_keepers_clean(root)

    # WAKE orbity again: block returns, still clean.
    r = settle_scope_artifacts(root=root, live=["igig"], active=["igig", "orbity"])
    assert r["ok"] and r["woke"] == ["orbity"]
    assert "/products/orbity/frontend" in (root / ".github" / "dependabot.yml").read_text()
    _all_keepers_clean(root)

    # Idempotent: a second identical run changes nothing.
    snap = {f: (root / f).read_text() for f in SETTLED_FILES if (root / f).exists()}
    settle_scope_artifacts(root=root, live=["igig"], active=["igig", "orbity"])
    assert snap == {f: (root / f).read_text() for f in snap}


def test_real_repo_derived_artifacts_match_scope():
    """The checked-in tree itself: no scope-fed keeper reports drift."""
    assert compliance.check_dependabot_product_coverage(repo_root=REPO) == []
    assert compliance.check_ci_test_matrix_coverage(repo_root=REPO) == []
