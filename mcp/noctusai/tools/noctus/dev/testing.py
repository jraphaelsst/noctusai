"""Test runner and coverage tools."""
import logging
import os
import re
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

from settings import REPO_ROOT, PRODUCTS_DIR, resolve_test_python  # noqa: E402  (path constants)
from workspace import resolve_caller_root  # noqa: E402


def _products_dir_for(worktree_path: str | None) -> Path:
    """Resolve the `products/` tree this run is scoped to.

    `None` (the default) preserves the pre-existing module-level
    `PRODUCTS_DIR` — the primary tree, and what tests monkeypatch. An
    explicit `worktree_path` resolves the CALLER's own worktree instead:
    the MCP server is a fixed-CWD process bound to the primary at startup,
    so omitting `worktree_path` from inside an engineer worktree silently
    tests the PRIMARY's copy of the product — the false-green bug this
    closes (`noctus.dev.pytest` reported "689 passed" from the primary
    while the worktree's actual suite was never run). Mirrors the
    `resolve_caller_root` convention used by `noctus.dev.mole` /
    `build_parallel` / `gen_promotions_index`."""
    if worktree_path:
        return resolve_caller_root(worktree_path) / "products"
    return PRODUCTS_DIR


def _worktree_pythonpath(root: Path) -> str:
    """PYTHONPATH entries that make `import noctusai_lib` / the seed
    framework resolve to THIS tree's own copies, not whatever the shared
    PRIMARY venv has editable-installed (the venv has no per-worktree
    variant — `resolve_test_python` always returns the primary's
    interpreter, per the self-branching-mode convention: worktrees carry no
    venv of their own). Prepended so they are found BEFORE the venv's
    editable finder. Per KB § PATTERNS/common/self-branching-mode.md § 5a."""
    entries = [str(root / "seed" / "framework" / "backend"), str(root / "seed" / "lib" / "backend")]
    existing = os.environ.get("PYTHONPATH", "")
    if existing:
        entries.append(existing)
    return os.pathsep.join(entries)


def run_product_tests(slug: str, timeout: int = 120, worktree_path: str | None = None) -> dict:
    """Run pytest for a product and return structured results.

    `worktree_path`: run against the CALLER's worktree copy of the product
    instead of the primary's (see `_products_dir_for`). The interpreter
    always comes from the PRIMARY's shared venv (no per-worktree venv
    exists); `PYTHONPATH` is prepended with the resolved tree's own seed
    dirs so the code under test imports THAT tree's lib/framework, not the
    venv's editable-installed primary copy. The response always includes
    `resolved_root` so the answer is never silently about the wrong tree."""
    products_dir = _products_dir_for(worktree_path)
    root = products_dir.parent
    backend = products_dir / slug / "backend"
    if not (backend / "tests").exists():
        return {"product": slug, "error": "no tests directory", "resolved_root": str(root)}

    env = {**os.environ, "PYTHONPATH": _worktree_pythonpath(root)}
    try:
        result = subprocess.run(
            [resolve_test_python(), "-m", "pytest", "tests/", "-q", "--tb=short"],
            cwd=str(backend),
            capture_output=True, text=True, timeout=timeout, env=env,
        )
        output = result.stdout + result.stderr
        passed = failed = errors = 0
        for line in output.splitlines():
            m = re.search(r"(\d+) passed", line)
            if m: passed = int(m.group(1))
            m = re.search(r"(\d+) failed", line)
            if m: failed = int(m.group(1))
            m = re.search(r"(\d+) error", line)
            if m: errors = int(m.group(1))

        return {
            "product": slug,
            "passed": passed,
            "failed": failed,
            "errors": errors,
            # pytest's exit code is the authority: a crash / missing-module /
            # collection error returns non-zero with NO summary line, which
            # would otherwise parse as 0/0/0 → false green. Gate on returncode.
            "success": result.returncode == 0 and failed == 0 and errors == 0,
            "output": output[-2000:] if len(output) > 2000 else output,
            "resolved_root": str(root),
        }
    except subprocess.TimeoutExpired:
        logger.warning("testing: pytest for %s timed out after %ds", slug, timeout)
        return {"product": slug, "error": "timeout", "resolved_root": str(root)}
    except Exception as e:
        logger.warning("testing: pytest for %s failed unexpectedly: %s", slug, e)
        return {"product": slug, "error": str(e), "resolved_root": str(root)}


def run_all_tests(timeout: int = 300, worktree_path: str | None = None) -> dict:
    """Run tests for all products. See `run_product_tests` for `worktree_path`."""
    products_dir = _products_dir_for(worktree_path)
    results = []
    total_passed = total_failed = 0

    for d in sorted(products_dir.iterdir()):
        if not d.is_dir() or d.name.startswith("."):
            continue
        if not (d / "backend" / "tests").exists():
            continue
        r = run_product_tests(d.name, timeout=timeout, worktree_path=worktree_path)
        results.append(r)
        total_passed += r.get("passed", 0)
        total_failed += r.get("failed", 0)

    return {
        "products": results,
        "total_passed": total_passed,
        "total_failed": total_failed,
        "all_green": total_failed == 0,
        "resolved_root": str(products_dir.parent),
    }


def build_product_frontend(slug: str, timeout: int = 60, worktree_path: str | None = None) -> dict:
    """Build a product's frontend and return result. See `run_product_tests`
    for `worktree_path` — the same primary-default / caller-worktree-explicit
    resolution applies here (no interpreter/PYTHONPATH concern for a FE build;
    only `cwd` scoping matters)."""
    products_dir = _products_dir_for(worktree_path)
    root = products_dir.parent
    frontend = products_dir / slug / "frontend"
    if not frontend.exists():
        return {"product": slug, "error": "no frontend directory", "resolved_root": str(root)}

    try:
        result = subprocess.run(
            ["npx", "vite", "build"],
            cwd=str(frontend),
            capture_output=True, text=True, timeout=timeout,
        )
        success = "built in" in result.stdout.lower() or result.returncode == 0
        return {
            "product": slug,
            "success": success,
            "output": (result.stdout + result.stderr)[-1000:],
            "resolved_root": str(root),
        }
    except subprocess.TimeoutExpired:
        logger.warning("testing: vite build for %s timed out after %ds", slug, timeout)
        return {"product": slug, "error": "timeout", "resolved_root": str(root)}
    except Exception as e:
        logger.warning("testing: vite build for %s failed unexpectedly: %s", slug, e)
        return {"product": slug, "error": str(e), "resolved_root": str(root)}


def build_all_frontends(timeout: int = 120, worktree_path: str | None = None) -> dict:
    """Build all product frontends. See `run_product_tests` for `worktree_path`."""
    products_dir = _products_dir_for(worktree_path)
    results = []
    for d in sorted(products_dir.iterdir()):
        if not d.is_dir() or d.name.startswith("."):
            continue
        if not (d / "frontend" / "vite.config.ts").exists():
            continue
        results.append(build_product_frontend(d.name, timeout=timeout, worktree_path=worktree_path))

    return {
        "products": results,
        "all_success": all(r.get("success", False) for r in results),
        "resolved_root": str(products_dir.parent),
    }


def register(server) -> None:
    @server.tool(
        name="noctus.dev.pytest",
        description=(
            "Run pytest for one product (slug=...) or all products (slug=None). "
            "Pass worktree_path when called from inside a git worktree so the "
            "product tree tested is THAT worktree's, not the primary's — MCP "
            "stdio is fixed-CWD at the primary; omitting worktree_path from a "
            "worktree silently tests the PRIMARY's copy and can report a "
            "false-green (e.g. '689 passed' while the worktree's real suite "
            "never ran). PYTHONPATH is scoped to match, so the worktree's own "
            "lib/framework code is imported, not the shared venv's editable "
            "primary copy. Response always includes resolved_root."
        ),
    )
    def _pytest(slug: str | None = None, worktree_path: str | None = None) -> dict:
        return (run_all_tests(worktree_path=worktree_path) if slug is None
                else run_product_tests(slug, worktree_path=worktree_path))

    @server.tool(
        name="noctus.dev.vite_build",
        description=(
            "Run vite build for one product (slug=...) or all (slug=None). "
            "Pass worktree_path when called from inside a git worktree so the "
            "product frontend built is THAT worktree's, not the primary's — "
            "same tree-resolution as noctus.dev.pytest. Response always "
            "includes resolved_root."
        ),
    )
    def _vite_build(slug: str | None = None, worktree_path: str | None = None) -> dict:
        return (build_all_frontends(worktree_path=worktree_path) if slug is None
                else build_product_frontend(slug, worktree_path=worktree_path))
