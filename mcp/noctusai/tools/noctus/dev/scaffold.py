"""Product scaffolding — create new products from the seed framework.

Migrations emitted by the scaffolded product MUST keep the canonical SQL
DDL conventions used elsewhere in the platform. Helpers live at
`noctusai_lib.domain.sql_templates` (`set_search_path`, `updated_at_function`,
`updated_at_trigger`, `rls_subquery_policy`). The bundled `001_seed.sql`
template uses placeholders that resolve to schema-correct SQL on scaffold;
the regression tests at `tests/test_scaffold.py` (TestSqlTemplatesIntegration)
assert the scaffolded migration's `SET search_path` line + RLS policy line
match the helpers' output, so future drift is caught at CI rather than
discovered via a broken migration.
"""
import logging
import shutil
from pathlib import Path

from workspace import get_noctusai_home, get_workspace_root

logger = logging.getLogger(__name__)

# Workspace-aware: products/ created under the workspace's own root (so
# scaffold_product from a template lands in template's products/, not
# noc's). The seed template lives only in noc — fetched via get_noctusai_home().
# See mcp/noctusai/workspace.py + KB § PATTERNS/seed-workspace.md.
REPO_ROOT = get_workspace_root()
PRODUCTS_DIR = REPO_ROOT / "products"
TEMPLATE_DIR = get_noctusai_home() / "templates" / "product-seed"


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
            except Exception as exc:
                logger.warning("scaffold: cannot write %s (%s), skipping", f, exc)

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


def register(server) -> None:
    @server.tool(
        name="noctus.dev.scaffold_product",
        description="Create a new product from the seed template",
    )
    def _scaffold(
        name: str,
        slug: str,
        schema: str,
        backend_port: int,
        frontend_port: int,
        icon: str = "Box",
    ) -> dict:
        return scaffold_product(name, slug, schema, backend_port, frontend_port, icon)

    @server.tool(
        name="noctus.dev.available_ports",
        description="Find next available backend and frontend ports",
    )
    def _available_ports() -> dict:
        return list_available_ports()
