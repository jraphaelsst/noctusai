"""`noctusai_build` — parallel cross-product `vite build` sweep.

Replaces the manual `for p in seed core erp ... ; do (cd $p/frontend && npx
vite build); done` loop run 5+ times during the 2026-04-28 session.
Spawns one subprocess per product, collects exit codes + last-line build
summary, prints a green/red table.

**Modes:**
- `build_products()` — every product's frontend.
- `build_products(slugs=[...])` — just the specified products.
- `build_products(changed_only=True)` — uses `git diff --name-only HEAD`
  to detect which products had changes since last commit and only builds
  those (perf — skips the 5-7 unchanged products).

**Why subprocess instead of importing vite:** vite's CLI is the
authoritative builder; replicating its config-discovery would diverge.
Subprocess + `cwd=<product>/frontend` matches what every dev runs locally.
"""
from __future__ import annotations

import logging
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]
PRODUCTS_DIR = REPO_ROOT / "products"

# Products that don't have a frontend (backend-only). Skip in build sweeps
# to avoid noisy "no package.json" errors. Empty today; populate if a
# backend-only product is added.
_BACKEND_ONLY_PRODUCTS: set[str] = set()


@dataclass
class BuildResult:
    product: str
    exit_code: int
    duration_seconds: float
    summary: str  # last meaningful line of stdout/stderr (typically "✓ built in 8.97s" or the error)
    success: bool

    def to_dict(self) -> dict:
        return {
            "product": self.product,
            "exit_code": self.exit_code,
            "duration_seconds": round(self.duration_seconds, 2),
            "summary": self.summary,
            "success": self.success,
        }


def _list_all_product_slugs(repo_root: Path) -> list[str]:
    products = repo_root / "products"
    if not products.exists():
        return []
    out: list[str] = []
    for d in sorted(products.iterdir()):
        if not d.is_dir() or d.name.startswith("."):
            continue
        if d.name in _BACKEND_ONLY_PRODUCTS:
            continue
        if not (d / "frontend" / "package.json").exists():
            # Skip products without a buildable frontend.
            continue
        out.append(d.name)
    return out


def _detect_changed_products(repo_root: Path) -> list[str]:
    """Return product slugs whose `frontend/` or `backend/` had changes
    since `HEAD`. Falls back to all products if `git diff` fails (e.g.
    not in a git repo, or git not installed).
    """
    try:
        proc = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        logger.warning(
            "build: `git diff` failed (%s); cannot detect changed products, "
            "falling back to ALL products (safe superset)", exc,
        )
        return _list_all_product_slugs(repo_root)
    if proc.returncode != 0:
        return _list_all_product_slugs(repo_root)
    changed_files = proc.stdout.strip().splitlines()
    affected: set[str] = set()
    for f in changed_files:
        if f.startswith("products/"):
            parts = f.split("/", 2)
            if len(parts) >= 2:
                affected.add(parts[1])
        # Seed changes affect every product (they consume from `seed/`).
        if f.startswith("seed/"):
            return _list_all_product_slugs(repo_root)
    # Filter against actual buildable products to skip backend-only / removed.
    all_slugs = set(_list_all_product_slugs(repo_root))
    return sorted(affected & all_slugs)


def _last_meaningful_line(output: str) -> str:
    """Extract the most informative line from vite's output — typically
    the `✓ built in 8.97s` line or the first error message. Strips ANSI
    color codes (vite uses them) for clean text output.
    """
    import re
    ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
    cleaned = ansi_escape.sub("", output)
    lines = [ln.strip() for ln in cleaned.splitlines() if ln.strip()]
    if not lines:
        return "(no output)"
    # Prefer "✓ built" lines (success path).
    for line in reversed(lines):
        if "built in" in line.lower() or "✓" in line:
            return line
    # Else surface the first "error" line.
    for line in lines:
        if "error" in line.lower():
            return line
    # Fallback: last non-empty line.
    return lines[-1]


def _build_one(slug: str, repo_root: Path, timeout: int = 300) -> BuildResult:
    """Build a single product's frontend. Returns a BuildResult; never raises."""
    import time
    frontend_dir = repo_root / "products" / slug / "frontend"
    if not frontend_dir.exists():
        return BuildResult(
            product=slug,
            exit_code=-1,
            duration_seconds=0.0,
            summary=f"frontend directory not found: {frontend_dir}",
            success=False,
        )
    start = time.time()
    try:
        proc = subprocess.run(
            ["npx", "vite", "build"],
            cwd=frontend_dir,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        duration = time.time() - start
        combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
        return BuildResult(
            product=slug,
            exit_code=proc.returncode,
            duration_seconds=duration,
            summary=_last_meaningful_line(combined),
            success=proc.returncode == 0,
        )
    except subprocess.TimeoutExpired:
        logger.warning("build: %s timed out after %ds", slug, timeout)
        return BuildResult(
            product=slug,
            exit_code=-2,
            duration_seconds=timeout,
            summary=f"timeout after {timeout}s",
            success=False,
        )
    except FileNotFoundError as e:
        logger.warning("build: %s missing executable (npx?): %s", slug, e)
        return BuildResult(
            product=slug,
            exit_code=-3,
            duration_seconds=time.time() - start,
            summary=f"npx not found: {e}",
            success=False,
        )


def build_products(
    slugs: list[str] | None = None,
    *,
    changed_only: bool = False,
    repo_root: Path | None = None,
    parallel: int = 4,
    timeout: int = 300,
) -> dict:
    """Build N product frontends in parallel.

    Args:
        slugs: explicit product slugs to build. If None, builds all (or
            uses `changed_only` filter).
        changed_only: when True + `slugs` is None, scope to products with
            changes since HEAD.
        repo_root: repo root; defaults to the package's resolved root.
        parallel: max concurrent subprocess workers (default 4 — keeps
            CPU + npm cache contention reasonable).
        timeout: per-product timeout in seconds (default 300 = 5min).

    Returns:
        `{"requested": [slug, ...], "results": [{...BuildResult.to_dict()},
          ...], "total_duration_seconds": ..., "all_green": bool}`.
    """
    root = repo_root or REPO_ROOT
    if slugs is None:
        targets = _detect_changed_products(root) if changed_only else _list_all_product_slugs(root)
    else:
        targets = list(slugs)

    if not targets:
        return {
            "requested": [],
            "results": [],
            "total_duration_seconds": 0.0,
            "all_green": True,
            "note": (
                "No products to build (changed_only filter returned empty, or "
                "no buildable frontends found)."
            ),
        }

    import time
    overall_start = time.time()
    results: list[BuildResult] = []
    with ThreadPoolExecutor(max_workers=parallel) as pool:
        futures = {pool.submit(_build_one, slug, root, timeout): slug for slug in targets}
        for fut in as_completed(futures):
            results.append(fut.result())
    overall_duration = time.time() - overall_start

    # Sort results to match the input order for stable output.
    order_index = {s: i for i, s in enumerate(targets)}
    results.sort(key=lambda r: order_index.get(r.product, len(targets)))

    return {
        "requested": targets,
        "results": [r.to_dict() for r in results],
        "total_duration_seconds": round(overall_duration, 2),
        "all_green": all(r.success for r in results),
    }
