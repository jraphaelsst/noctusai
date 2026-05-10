"""Master prompt sync tools — regenerate structural sections from filesystem."""
import re
from pathlib import Path
from tools.noctus.dev.products import get_product_summary, REPO_ROOT, PRODUCTS_DIR


def sync_master_prompt(slug: str) -> dict:
    """Regenerate the structural sections of a product's MASTER-PROMPT.md.

    Reads the filesystem to get current routers, services, schemas, pages, hooks.
    Updates the MASTER-PROMPT while preserving descriptive sections.
    Returns {updated: bool, changes: list[str]}.
    """
    path = PRODUCTS_DIR / slug
    mp_file = path / "MASTER-PROMPT.md"

    if not mp_file.exists():
        return {"error": f"No MASTER-PROMPT.md for '{slug}'", "updated": False}

    structure = get_product_summary(slug)
    current = mp_file.read_text()
    changes = []

    # Update backend structure section
    if structure["has_backend"]:
        new_backend = _generate_backend_section(structure)
        current, changed = _replace_section(current, "Backend", new_backend)
        if changed:
            changes.append("Backend structure updated")

    # Update frontend structure section
    if structure["has_frontend"]:
        new_frontend = _generate_frontend_section(structure)
        current, changed = _replace_section(current, "Frontend", new_frontend)
        if changed:
            changes.append("Frontend structure updated")

    if changes:
        mp_file.write_text(current)

    return {
        "updated": len(changes) > 0,
        "changes": changes,
        "product": slug,
        "routers": structure["routers"],
        "services": structure["services"],
        "pages": structure["pages"],
        "hooks": structure["hooks"],
    }


def check_master_prompt_staleness(slug: str) -> dict:
    """Check if a MASTER-PROMPT is out of sync with the filesystem."""
    path = PRODUCTS_DIR / slug
    mp_file = path / "MASTER-PROMPT.md"

    if not mp_file.exists():
        return {"slug": slug, "stale": True, "reason": "No MASTER-PROMPT.md"}

    content = mp_file.read_text()
    structure = get_product_summary(slug)
    issues = []

    # Check if routers mentioned in MASTER-PROMPT match filesystem
    for router in structure["routers"]:
        if router not in content:
            issues.append(f"Router '{router}' exists but not in MASTER-PROMPT")

    # Check for files mentioned in MASTER-PROMPT that no longer exist
    for match in re.finditer(r'(\w+)\.py', content):
        name = match.group(1)
        if name.startswith("test_"):
            continue
        if name in ("__init__", "conftest"):
            continue
        # Check if it's a router, service, or schema reference
        backend = path / "backend" / "app"
        if any(name in content_section for content_section in [
            "routers/", "services/", "schemas/"
        ]):
            found = False
            for subdir in ["routers", "services", "schemas"]:
                if (backend / subdir / f"{name}.py").exists():
                    found = True
                    break
            if not found and name not in structure["routers"] + structure["services"] + structure["schemas"]:
                issues.append(f"'{name}.py' referenced in MASTER-PROMPT but doesn't exist")

    return {
        "slug": slug,
        "stale": len(issues) > 0,
        "issues": issues,
    }


def _generate_backend_section(structure: dict) -> str:
    """Generate backend structure documentation."""
    lines = ["```"]
    lines.append("products/{}/backend/app/".format(structure["name"]))
    lines.append("  main.py              → create_product_app() with domain routers")
    lines.append("  config.py            → ProductSettings extension")
    lines.append("  database.py          → create_database_module()")
    lines.append("  dependencies.py      → create_dependencies()")
    lines.append("  routers/")
    for r in structure["routers"]:
        lines.append(f"    {r}.py")
    lines.append("  services/")
    for s in structure["services"]:
        lines.append(f"    {s}.py")
    if structure["schemas"]:
        lines.append("  schemas/")
        for s in structure["schemas"]:
            lines.append(f"    {s}.py")
    lines.append("```")
    return "\n".join(lines)


def _generate_frontend_section(structure: dict) -> str:
    """Generate frontend structure documentation."""
    lines = ["```"]
    lines.append("products/{}/frontend/src/".format(structure["name"]))
    lines.append("  App.tsx              → createProductApp() from seed framework")
    lines.append("  vite.config.ts       → createViteConfig()")
    lines.append("  pages/")
    for p in structure["pages"]:
        lines.append(f"    {p}.tsx")
    if structure["hooks"]:
        lines.append("  hooks/")
        for h in structure["hooks"]:
            lines.append(f"    {h}.ts")
    lines.append("```")
    return "\n".join(lines)


def _replace_section(content: str, section_name: str, new_content: str) -> tuple[str, bool]:
    """Replace a code block section in the MASTER-PROMPT. Returns (new_content, changed)."""
    # Look for ### Backend or ### Frontend followed by a code block
    pattern = rf'(### {section_name}.*?\n\n)```[\s\S]*?```'
    match = re.search(pattern, content)
    if match:
        old = match.group(0)
        new = match.group(1) + new_content
        if old.strip() != new.strip():
            return content.replace(old, new), True
    return content, False


def verify_master_prompt(
    slug: str | None = None,
    *,
    write: bool = False,
    all_products: bool = False,
) -> dict:
    """Staleness check + optional regenerate. all_products=True iterates."""
    if all_products:
        products: list[dict] = []
        for d in sorted(PRODUCTS_DIR.iterdir()):
            if not d.is_dir() or d.name.startswith("."):
                continue
            if (d / "MASTER-PROMPT.md").exists():
                products.append(
                    verify_master_prompt(d.name, write=write, all_products=False)
                )
        return {
            "products": products,
            "total": len(products),
            "stale_count": sum(1 for p in products if p.get("stale")),
            "synced_count": sum(1 for p in products if p.get("synced")),
            "write_attempted": write,
        }

    if slug is None:
        return {"error": "slug is required when all_products=False"}

    check = check_master_prompt_staleness(slug)
    out = {
        "slug": slug,
        "stale": check.get("stale", False),
        "issues": check.get("issues", []),
        "reason": check.get("reason"),
        "synced": False,
        "changes": [],
        "write_attempted": write,
    }
    if write and out["stale"]:
        sync = sync_master_prompt(slug)
        out["synced"] = sync.get("updated", False)
        out["changes"] = sync.get("changes", [])
        if "error" in sync:
            out["error"] = sync["error"]
    return out


def register(server) -> None:
    @server.tool(
        name="noctus.dev.verify_master_prompt",
        description=(
            "MASTER-PROMPT.md staleness check (write=False) or "
            "regenerate-if-stale (write=True). all_products=True iterates."
        ),
    )
    def _verify(
        slug: str | None = None,
        write: bool = False,
        all_products: bool = False,
    ) -> dict:
        return verify_master_prompt(slug, write=write, all_products=all_products)
