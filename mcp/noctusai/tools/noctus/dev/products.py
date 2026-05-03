"""Product structure introspection tools."""
import json
from pathlib import Path

from settings import REPO_ROOT, PRODUCTS_DIR  # noqa: E402  (path constants)


def list_products() -> list[dict]:
    """List all products with their structure summary."""
    products = []
    for d in sorted(PRODUCTS_DIR.iterdir()):
        if not d.is_dir() or d.name.startswith("."):
            continue
        products.append(get_product_summary(d.name))
    return products


def get_product_summary(slug: str) -> dict:
    """Get a quick summary of a product."""
    path = PRODUCTS_DIR / slug
    if not path.exists():
        return {"error": f"Product '{slug}' not found"}

    backend = path / "backend" / "app"
    frontend = path / "frontend" / "src"

    return {
        "name": slug,
        "path": str(path),
        "has_backend": backend.exists(),
        "has_frontend": frontend.exists(),
        "has_readme": (path / "README.md").exists(),
        "has_master_prompt": (path / "MASTER-PROMPT.md").exists(),
        "routers": _list_py_modules(backend / "routers"),
        "services": _list_py_modules(backend / "services"),
        "schemas": _list_py_modules(backend / "schemas"),
        "pages": _list_tsx_modules(frontend / "pages"),
        "hooks": _list_ts_modules(frontend / "hooks"),
    }


def get_product_structure(slug: str) -> dict:
    """Get detailed product structure including file contents summary."""
    path = PRODUCTS_DIR / slug
    if not path.exists():
        return {"error": f"Product '{slug}' not found"}

    backend = path / "backend" / "app"
    frontend = path / "frontend" / "src"

    structure = get_product_summary(slug)

    # Backend details
    if backend.exists():
        structure["backend_config"] = _read_file_preview(backend / "config.py")
        structure["backend_main"] = _read_file_preview(backend / "main.py")
        structure["router_endpoints"] = {}
        for router_file in (backend / "routers").glob("*.py"):
            if router_file.stem != "__init__":
                structure["router_endpoints"][router_file.stem] = _extract_endpoints(router_file)

    # Frontend details
    if frontend.exists():
        structure["app_tsx_preview"] = _read_file_preview(frontend / "App.tsx", lines=30)
        structure["vite_config"] = _read_file_preview(path / "frontend" / "vite.config.ts")

    # Tests
    tests_dir = path / "backend" / "tests"
    if tests_dir.exists():
        structure["test_files"] = []
        for f in sorted(tests_dir.rglob("test_*.py")):
            structure["test_files"].append(str(f.relative_to(path)))

    # Migration
    migrations_dir = path / "backend" / "migrations"
    if migrations_dir.exists():
        structure["migrations"] = [f.name for f in sorted(migrations_dir.glob("*.sql"))]

    return structure


def _list_py_modules(directory: Path) -> list[str]:
    if not directory.exists():
        return []
    return sorted([
        f.stem for f in directory.glob("*.py")
        if f.stem != "__init__" and not f.stem.startswith("__")
    ])


def _list_tsx_modules(directory: Path) -> list[str]:
    if not directory.exists():
        return []
    results = []
    for f in sorted(directory.rglob("*.tsx")):
        rel = str(f.relative_to(directory)).replace(".tsx", "")
        results.append(rel)
    return results


def _list_ts_modules(directory: Path) -> list[str]:
    if not directory.exists():
        return []
    return sorted([
        f.stem for f in directory.glob("*.ts")
        if f.stem != "__init__" and f.stem != "index"
    ])


def _read_file_preview(path: Path, lines: int = 20) -> str:
    if not path.exists():
        return ""
    content = path.read_text()
    return "\n".join(content.splitlines()[:lines])


def _extract_endpoints(router_file: Path) -> list[str]:
    """Extract API endpoint definitions from a router file."""
    content = router_file.read_text()
    endpoints = []
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("@router."):
            # Extract method and path: @router.get("/api/contacts")
            endpoints.append(line)
    return endpoints


def register(server) -> None:
    @server.tool(
        name="noctus.dev.list_products",
        description="List all products with routers, services, pages, hooks counts",
    )
    def _list_products() -> list:
        return list_products()

    @server.tool(
        name="noctus.dev.get_product",
        description="Detailed product structure: endpoints, config, tests, migrations",
    )
    def _get_product(slug: str) -> dict:
        return get_product_structure(slug)
