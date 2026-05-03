"""Diff and comparison tools — compare products against seed patterns."""
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

from settings import REPO_ROOT, PRODUCTS_DIR  # noqa: E402  (path constants)


def diff_product_against_seed(slug: str) -> dict:
    """Compare a product's structural files against the seed product.

    Shows which files deviate from the seed pattern and how.
    Useful for finding products that drifted from the standard.
    """
    product = PRODUCTS_DIR / slug
    seed = PRODUCTS_DIR / "seed"

    if not product.exists():
        return {"error": f"Product '{slug}' not found"}
    if not seed.exists():
        return {"error": "Seed product not found"}

    structural_files = [
        "frontend/vite.config.ts",
        "frontend/tailwind.config.ts",
        "frontend/tsconfig.json",
    ]

    diffs = {}
    for f in structural_files:
        product_file = product / f
        seed_file = seed / f
        if not product_file.exists() or not seed_file.exists():
            diffs[f] = "missing in one side"
            continue

        try:
            result = subprocess.run(
                ["diff", str(seed_file), str(product_file)],
                capture_output=True, text=True,
            )
            if result.returncode == 0:
                diffs[f] = "identical"
            else:
                diffs[f] = result.stdout[:500] if result.stdout else "different"
        except Exception as exc:
            logger.warning("diff: comparing %s failed (%s)", f, exc)
            diffs[f] = f"error comparing: {exc}"

    return {"product": slug, "diffs": diffs}


def find_orphaned_files(slug: str) -> dict:
    """Find files in a product that might be orphaned (not imported anywhere).

    Checks frontend components and hooks that aren't imported by any page or App.tsx.
    """
    product = PRODUCTS_DIR / slug
    frontend = product / "frontend" / "src"
    if not frontend.exists():
        return {"product": slug, "orphans": []}

    # Collect all .tsx/.ts files that could be orphaned
    candidates = []
    for subdir in ["components", "hooks", "lib"]:
        d = frontend / subdir
        if d.exists():
            for f in d.rglob("*.tsx"):
                if "node_modules" not in str(f):
                    candidates.append(f)
            for f in d.rglob("*.ts"):
                if "node_modules" not in str(f) and f.stem != "index":
                    candidates.append(f)

    # Check if each candidate is imported somewhere
    all_sources = list((frontend / "pages").rglob("*.tsx")) + [frontend / "App.tsx"]
    all_content = ""
    for src in all_sources:
        if src.exists():
            try:
                all_content += src.read_text()
            except Exception as exc:
                logger.warning("diff: cannot read %s for orphan scan (%s), skipping", src, exc)

    orphans = []
    for candidate in candidates:
        name = candidate.stem
        # Check if the filename appears in any import
        if name not in all_content and f"/{name}" not in all_content:
            orphans.append(str(candidate.relative_to(product)))

    return {"product": slug, "orphans": orphans, "count": len(orphans)}


def check_api_consistency(slug: str) -> dict:
    """Check if a product's API endpoints follow consistent patterns.

    Validates: response shapes, status codes, error handling.
    """
    backend = PRODUCTS_DIR / slug / "backend" / "app" / "routers"
    if not backend.exists():
        return {"product": slug, "issues": []}

    issues = []
    for router_file in sorted(backend.glob("*.py")):
        if router_file.stem == "__init__":
            continue
        try:
            content = router_file.read_text()
        except Exception as exc:
            logger.warning("diff: cannot read router %s (%s), skipping", router_file, exc)
            continue

        name = router_file.stem

        # Check response consistency
        uses_success_response = "success_response" in content
        uses_paginated = "paginated_response" in content
        uses_raw_dict = 'return {"' in content or "return {'" in content

        if uses_raw_dict and (uses_success_response or uses_paginated):
            issues.append({
                "router": name,
                "issue": "Mixes raw dict returns with response helpers — use helpers consistently",
            })

        # Check error handling
        has_try_except = "try:" in content
        has_http_exception = "HTTPException" in content
        if not has_http_exception and "async def" in content:
            issues.append({
                "router": name,
                "issue": "No HTTPException usage — endpoints may not handle errors properly",
            })

    return {"product": slug, "issues": issues}


def register(server) -> None:
    @server.tool(
        name="noctus.dev.diff_against_seed",
        description="Compare a product's structural files against the seed product",
    )
    def _diff(slug: str) -> dict:
        return diff_product_against_seed(slug)

    @server.tool(
        name="noctus.dev.find_orphans",
        description="Find orphaned files not imported anywhere",
    )
    def _orphans(slug: str) -> dict:
        return find_orphaned_files(slug)

    @server.tool(
        name="noctus.dev.check_api_consistency",
        description="Check API response pattern consistency",
    )
    def _api_consistency(slug: str) -> dict:
        return check_api_consistency(slug)
