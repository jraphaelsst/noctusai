"""noctus.dev.canonical_test_audit — discover and audit seed-canonical
inherited tests fleet-wide (static discovery leg).

## Why this tool exists

`products/dev-team` omitted `"team"` from `standard_routers=[...]`, causing the
seed Team-Management organ to be absent. This produced TWO distinct failure
classes:

1. **RED drift** — inherited auth tests asserted `== 401` but got `404` (route
   absent) → tests FAILED. A test-executing runner catches this.
2. **FALSE-GREEN** — tests asserted `in (401, 404)`, passing via 404 without
   exercising auth. See `check_auth_boundary_false_green` + the KB pattern.

This tool handles **class 1** (red drift): it discovers which products carry
inherited seed-canonical test files (the `test_e2e_flows.py` / `TestFrameworkEndpoints`
pattern from `noctusai_lib.testing`), reports their canonical test inventory,
and can run them via the product's own `.venv` to surface red drift.

## Extend-vs-build decision

`noctus.dev.pytest` runs ALL tests per product via subprocess — it has no
concept of "canonical/inherited" test discovery, no classification by inheritance
pattern, and no targeted-subset mode. This tool is genuinely novel: discovery
+ classification is the primary deliverable; execution is a scoped augmentation.

## Execution scope

Actual per-product `.venv` test execution is NOT fully implemented here because
fresh worktrees lack `.venv` (the known gotcha) and each product's venv path and
test invocation is non-trivial to make robust across the fleet.

  NOC-REMEDIATE[canonical-runner-exec]: Full per-product venv execution leg.
  Preconditions: (1) each product's .venv must exist, (2) the product's backend
  must be installable in isolation without the full monorepo. Use `noctus.dev.pytest`
  (which already handles the subprocess / venv / working-dir dance) per slug for
  the execution leg — this tool delivers the DISCOVERY + CLASSIFICATION needed to
  target it. Implement by composing canonical_test_audit (for slug list) with
  pytest (for execution) in an orchestrated sweep.

## What ships today

- `discover_canonical_tests(products_dir)` → per-product inventory (which files,
  which test classes, which suites are inherited from `noctusai_lib.testing`).
- `audit_canonical_tests(products_dir)` → structured report: products with
  canonical tests, suite coverage, venv presence, execution-ready flag.
- MCP tool `noctus.dev.canonical_test_audit` — agent-exposable, per the
  MCP-first-scripts rule.
"""
from __future__ import annotations

import ast
import logging
from pathlib import Path
from typing import Any

from settings import REPO_ROOT, PRODUCTS_DIR

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Known seed-canonical suite names imported from noctusai_lib.testing.
# A product's test file importing and subclassing one of these is a "canonical
# inherited test" — its failure means seed-wiring drift, not product-logic bug.
# ---------------------------------------------------------------------------
CANONICAL_SUITES = frozenset([
    "FrameworkEndpointsSuite",
    "TeamFlowSuite",
    "NotificationFlowSuite",
    "AuthBoundarySuite",
])

# The canonical filename pattern. Products that inline their own copy of the
# framework tests (not importing from noctusai_lib.testing) are also detected
# by class name heuristics (see `_classify_by_class_names`).
CANONICAL_FILENAMES = frozenset([
    "test_e2e_flows.py",
    "test_auth_boundary.py",
    "test_framework_endpoints.py",
])

# Marker classes whose presence in a file indicates inherited framework tests,
# even if they don't import from noctusai_lib.testing (inline copies).
CANONICAL_CLASS_NAMES = frozenset([
    "TestFrameworkEndpoints",
    "TestAuthBoundary",
    "TestTeamFlow",
    "TestNotificationFlow",
])


def _parse_imports(source: str) -> list[tuple[str, str]]:
    """Return (module, name) pairs for all `from <module> import <name>` at
    module level. Used to detect `from noctusai_lib.testing import ...`."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    pairs = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                pairs.append((node.module, alias.name))
    return pairs


def _top_level_class_names(source: str) -> list[str]:
    """Return all top-level class names defined in `source`."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    return [
        node.name
        for node in tree.body
        if isinstance(node, ast.ClassDef)
    ]


def _classify_file(test_file: Path) -> dict[str, Any] | None:
    """Classify a test file as carrying canonical inherited tests or not.

    Returns a dict with classification details, or None if not canonical.
    """
    if not test_file.exists():
        return None
    try:
        source = test_file.read_text(encoding="utf-8")
    except OSError:
        return None

    filename = test_file.name
    is_canonical_filename = filename in CANONICAL_FILENAMES

    imports = _parse_imports(source)
    inherited_suites = [
        name
        for (module, name) in imports
        if "noctusai_lib.testing" in module and name in CANONICAL_SUITES
    ]

    class_names = _top_level_class_names(source)
    canonical_classes = [c for c in class_names if c in CANONICAL_CLASS_NAMES]

    has_canonical_import = bool(inherited_suites)
    has_canonical_class = bool(canonical_classes)

    if not (is_canonical_filename or has_canonical_import or has_canonical_class):
        return None

    return {
        "file": str(test_file),
        "filename": filename,
        "is_canonical_filename": is_canonical_filename,
        "inherited_suites": inherited_suites,
        "canonical_classes": canonical_classes,
        "uses_lib_testing": has_canonical_import,
        "inlined_copy": has_canonical_class and not has_canonical_import,
    }


def discover_canonical_tests(
    products_dir: Path | None = None,
    product_slug: str | None = None,
) -> list[dict[str, Any]]:
    """Discover products that carry seed-canonical inherited tests.

    For each product, inspects `backend/tests/**/*.py` for files that:
    - Have a canonical filename (test_e2e_flows.py, test_auth_boundary.py)
    - Import a suite class from `noctusai_lib.testing`
    - Define a class named `TestFrameworkEndpoints` / `TestAuthBoundary` / etc.

    Returns a list of per-product dicts:
    {
      "product": str,
      "canonical_files": [{"file": str, "inherited_suites": [...], ...}],
      "suite_count": int,
      "uses_lib_testing": bool,   # True if at least one file imports noctusai_lib.testing
      "has_inlined_copy": bool,   # True if at least one file has inline canonical class
    }
    """
    base = products_dir if products_dir is not None else PRODUCTS_DIR
    results = []

    def _scan(product_path: Path) -> dict[str, Any] | None:
        tests_root = product_path / "backend" / "tests"
        if not tests_root.exists():
            return None
        canonical_files = []
        for test_file in sorted(tests_root.rglob("*.py")):
            classification = _classify_file(test_file)
            if classification is not None:
                canonical_files.append(classification)
        if not canonical_files:
            return None
        all_suites = set()
        for cf in canonical_files:
            all_suites.update(cf["inherited_suites"])
            all_suites.update(cf["canonical_classes"])
        return {
            "product": product_path.name,
            "canonical_files": canonical_files,
            "suite_count": len(all_suites),
            "uses_lib_testing": any(cf["uses_lib_testing"] for cf in canonical_files),
            "has_inlined_copy": any(cf["inlined_copy"] for cf in canonical_files),
        }

    if product_slug is not None:
        p = base / product_slug
        if not p.exists():
            logger.warning("canonical_test_audit: product %s not found at %s", product_slug, base)
            return []
        result = _scan(p)
        if result:
            results.append(result)
    else:
        for d in sorted(base.iterdir()):
            if not d.is_dir() or d.name.startswith("."):
                continue
            result = _scan(d)
            if result:
                results.append(result)

    return results


def _venv_python(product_path: Path) -> Path | None:
    """Return the path to the product's .venv Python, or None if absent."""
    candidates = [
        product_path / "backend" / ".venv" / "bin" / "python",
        product_path / "backend" / ".venv" / "Scripts" / "python.exe",
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


def audit_canonical_tests(
    products_dir: Path | None = None,
    product_slug: str | None = None,
) -> dict[str, Any]:
    """Return a structured audit of canonical inherited tests fleet-wide.

    Extends `discover_canonical_tests` with:
    - `venv_present`: whether the product's backend/.venv exists
    - `execution_ready`: venv_present AND uses_lib_testing
    - `red_drift_risk`: products that have canonical tests but lack the
      corresponding standard_routers opt-in (cross-check with the
      check_standard_routers_audit signal, informational only)
    - Summary counters

    NOTE — canonical-runner-exec scope:
    Actual test execution is NOT performed here.
    NOC-REMEDIATE[canonical-runner-exec]: compose this audit's `execution_ready`
    product list with `noctus.dev.pytest(slug=...)` for the execution leg.
    Each product's venv must exist; use `noctus.dev.pytest` which already handles
    subprocess/venv/working-dir. See module docstring for full rationale.
    """
    base = products_dir if products_dir is not None else PRODUCTS_DIR
    inventory = discover_canonical_tests(products_dir=base, product_slug=product_slug)

    enriched = []
    execution_ready = []
    for item in inventory:
        product_path = base / item["product"]
        venv = _venv_python(product_path)
        venv_present = venv is not None
        ready = venv_present and item["uses_lib_testing"]
        enriched.append({
            **item,
            "venv_present": venv_present,
            "venv_path": str(venv) if venv else None,
            "execution_ready": ready,
            "note": (
                "NOC-REMEDIATE[canonical-runner-exec]: run `noctus.dev.pytest(slug='{}')` "
                "to execute the canonical inherited tests and surface RED drift."
            ).format(item["product"]) if ready else (
                "venv absent — install product deps first (see product README or ./start.sh)"
                if not venv_present else
                "canonical tests use inline copies, not noctusai_lib.testing suites — "
                "less reliable as wiring indicators; manual review recommended"
            ),
        })
        if ready:
            execution_ready.append(item["product"])

    total = len(enriched)
    lib_testing_count = sum(1 for p in enriched if p["uses_lib_testing"])
    inlined_count = sum(1 for p in enriched if p["has_inlined_copy"])
    venv_ready_count = len(execution_ready)

    return {
        "ok": True,
        "total_products_with_canonical_tests": total,
        "lib_testing_consumers": lib_testing_count,
        "inlined_copies": inlined_count,
        "execution_ready_count": venv_ready_count,
        "execution_ready_products": execution_ready,
        "products": enriched,
        "execution_note": (
            "NOC-REMEDIATE[canonical-runner-exec]: Full execution leg not implemented. "
            "To run: for each slug in `execution_ready_products`, call "
            "`noctus.dev.pytest(slug=<slug>)` and check for non-zero failed/errors. "
            "RED drift = inherited canonical test FAILS because a standard router is "
            "absent (product omitted it from standard_routers=[...])."
        ),
    }


def register(server) -> None:
    @server.tool(
        name="noctus.dev.canonical_test_audit",
        description=(
            "Discover and audit seed-canonical inherited tests fleet-wide. "
            "Static discovery: which products carry TestFrameworkEndpoints / "
            "TestAuthBoundary / etc. (from noctusai_lib.testing or inlined). "
            "Reports venv_present + execution_ready per product. "
            "Does NOT execute tests (NOC-REMEDIATE[canonical-runner-exec]: "
            "compose execution_ready list with noctus.dev.pytest for the "
            "execution leg). "
            "Pass product_slug to scope to one product. "
            "Paired with check_auth_boundary_false_green (static false-green "
            "detector) for the two-class red-drift / false-green coverage. "
            "KB § PATTERNS/compliance/auth-boundary-false-green.md."
        ),
    )
    def _canonical_test_audit(
        product_slug: str | None = None,
    ) -> dict:
        return audit_canonical_tests(product_slug=product_slug)


__all__ = [
    "discover_canonical_tests",
    "audit_canonical_tests",
    "CANONICAL_SUITES",
    "CANONICAL_CLASS_NAMES",
    "CANONICAL_FILENAMES",
    "register",
]
