"""Test runner and coverage tools."""
import logging
import re
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

from settings import REPO_ROOT, PRODUCTS_DIR  # noqa: E402  (path constants)


def run_product_tests(slug: str, timeout: int = 120) -> dict:
    """Run pytest for a product and return structured results."""
    backend = PRODUCTS_DIR / slug / "backend"
    if not (backend / "tests").exists():
        return {"product": slug, "error": "no tests directory"}

    try:
        result = subprocess.run(
            ["python", "-m", "pytest", "tests/", "-q", "--tb=short"],
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
            "success": failed == 0 and errors == 0,
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
        name="noctusai_run_tests",
        description="Run pytest for a product",
    )
    def _run_tests(slug: str) -> dict:
        return run_product_tests(slug)

    @server.tool(
        name="noctusai_run_all_tests",
        description="Run tests for all products",
    )
    def _run_all_tests() -> dict:
        return run_all_tests()

    @server.tool(
        name="noctusai_build_frontend",
        description="Build a product's frontend (vite build)",
    )
    def _build_fe(slug: str) -> dict:
        return build_product_frontend(slug)

    @server.tool(
        name="noctusai_build_all_frontends",
        description="Build all product frontends",
    )
    def _build_all_fe() -> dict:
        return build_all_frontends()
