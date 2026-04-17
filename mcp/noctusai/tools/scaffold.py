"""Product scaffolding — create new products from the seed framework."""
import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PRODUCTS_DIR = REPO_ROOT / "products"
TEMPLATE_DIR = REPO_ROOT / "templates" / "product-seed"


def scaffold_product(name: str, slug: str, schema: str, backend_port: int, frontend_port: int, icon: str = "Box") -> dict:
    """Create a new product from the seed template.

    Replaces {{PLACEHOLDERS}} with actual values.
    Returns {created: bool, path: str, files: int}.
    """
    target = PRODUCTS_DIR / slug
    if target.exists():
        return {"error": f"Product '{slug}' already exists at {target}"}

    if not TEMPLATE_DIR.exists():
        return {"error": "Template not found at templates/product-seed/"}

    # Copy template
    shutil.copytree(TEMPLATE_DIR, target, ignore=shutil.ignore_patterns("node_modules", "__pycache__", ".backup", "*.egg-info"))

    # Replace placeholders
    replacements = {
        "{{PRODUCT_NAME}}": name,
        "{{SCHEMA_NAME}}": schema,
        "{{BACKEND_PORT}}": str(backend_port),
        "{{FRONTEND_PORT}}": str(frontend_port),
        "{{PRODUCT_ICON}}": icon,
    }

    file_count = 0
    for f in target.rglob("*"):
        if f.is_file() and f.suffix in (".py", ".ts", ".tsx", ".json", ".md", ".sql", ".html", ".css", ".txt"):
            try:
                content = f.read_text()
                for placeholder, value in replacements.items():
                    content = content.replace(placeholder, value)
                f.write_text(content)
                file_count += 1
            except:
                pass

    return {
        "created": True,
        "path": str(target),
        "files_processed": file_count,
        "next_steps": [
            f"Add to start.sh (backend {backend_port}, frontend {frontend_port})",
            f"Add to CLAUDE.md product table",
            f"Run migration: mcp/noctusai tools → noctusai_apply_migration",
            f"Insert into public.products table",
            f"Add to PRODUCT_MAP in vite.config.factory.ts",
        ],
    }


def list_available_ports() -> dict:
    """Find the next available backend and frontend ports."""
    used_backend = {8000, 8001, 8002, 8003, 8004, 8005, 8006}
    used_frontend = {5173, 8080, 8090, 8095, 8100, 8110, 8120}

    # Scan start.sh for any additional ports
    start_sh = REPO_ROOT / "start.sh"
    if start_sh.exists():
        content = start_sh.read_text()
        import re
        for match in re.finditer(r'--port (\d+)', content):
            port = int(match.group(1))
            if port < 8100:
                used_backend.add(port)
            else:
                used_frontend.add(port)

    next_backend = max(used_backend) + 1
    next_frontend = max(used_frontend) + 10

    return {
        "next_backend_port": next_backend,
        "next_frontend_port": next_frontend,
        "used_backend": sorted(used_backend),
        "used_frontend": sorted(used_frontend),
    }
