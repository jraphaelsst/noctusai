"""Test runner and coverage tools."""
import logging
import re
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

from settings import REPO_ROOT, PRODUCTS_DIR, resolve_test_python  # noqa: E402  (path constants)


def run_product_tests(slug: str, timeout: int = 120) -> dict:
    """Run pytest for a product and return structured results."""
    backend = PRODUCTS_DIR / slug / "backend"
    if not (backend / "tests").exists():
        return {"product": slug, "error": "no tests directory"}

    try:
        result = subprocess.run(
            [resolve_test_python(), "-m", "pytest", "tests/", "-q", "--tb=short"],
            cwd=str(backend),
            capture_output=True, text=True, timeout=timeout,
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
        }
    except subprocess.TimeoutExpired:
        logger.warning("testing: pytest for %s timed out after %ds", slug, timeout)
        return {"product": slug, "error": "timeout"}
    except Exception as e:
        logger.warning("testing: pytest for %s failed unexpectedly: %s", slug, e)
        return {"product": slug, "error": str(e)}


def run_all_tests(timeout: int = 300) -> dict:
    """Run tests for all products."""
    results = []
    total_passed = total_failed = 0

    for d in sorted(PRODUCTS_DIR.iterdir()):
        if not d.is_dir() or d.name.startswith("."):
            continue
        if not (d / "backend" / "tests").exists():
            continue
        r = run_product_tests(d.name, timeout=timeout)
        results.append(r)
        total_passed += r.get("passed", 0)
        total_failed += r.get("failed", 0)

    return {
        "products": results,
        "total_passed": total_passed,
        "total_failed": total_failed,
        "all_green": total_failed == 0,
    }


def build_product_frontend(slug: str, timeout: int = 60) -> dict:
    """Build a product's frontend and return result."""
    frontend = PRODUCTS_DIR / slug / "frontend"
    if not frontend.exists():
        return {"product": slug, "error": "no frontend directory"}

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
        }
    except subprocess.TimeoutExpired:
        logger.warning("testing: vite build for %s timed out after %ds", slug, timeout)
        return {"product": slug, "error": "timeout"}
    except Exception as e:
        logger.warning("testing: vite build for %s failed unexpectedly: %s", slug, e)
        return {"product": slug, "error": str(e)}


def build_all_frontends(timeout: int = 120) -> dict:
    """Build all product frontends."""
    results = []
    for d in sorted(PRODUCTS_DIR.iterdir()):
        if not d.is_dir() or d.name.startswith("."):
            continue
        if not (d / "frontend" / "vite.config.ts").exists():
            continue
        results.append(build_product_frontend(d.name, timeout=timeout))

    return {
        "products": results,
        "all_success": all(r.get("success", False) for r in results),
    }


def register(server) -> None:
    @server.tool(
        name="noctus.dev.pytest",
        description="Run pytest for one product (slug=...) or all products (slug=None).",
    )
    def _pytest(slug: str | None = None) -> dict:
        return run_all_tests() if slug is None else run_product_tests(slug)

    @server.tool(
        name="noctus.dev.vite_build",
        description="Run vite build for one product (slug=...) or all (slug=None).",
    )
    def _vite_build(slug: str | None = None) -> dict:
        return build_all_frontends() if slug is None else build_product_frontend(slug)
