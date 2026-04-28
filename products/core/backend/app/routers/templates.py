"""
Templates Router — List available project templates.

GET /api/admin/templates         — List all templates
GET /api/admin/templates/{name}  — Get template details (files, placeholders, README)
"""
import os
import logging
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Header, HTTPException

from app.dependencies import get_current_admin

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin/templates", tags=["Admin Templates"])

# Templates live at repo root /templates/
TEMPLATES_DIR = Path(__file__).resolve().parents[4] / "templates"


def _scan_template(template_path: Path) -> dict:
    """Scan a template directory and return its metadata."""
    readme_path = template_path / "README.md"
    readme = readme_path.read_text(encoding="utf-8") if readme_path.exists() else None

    # Collect all files
    files = []
    for root, _, filenames in os.walk(template_path):
        for f in filenames:
            full = Path(root) / f
            rel = full.relative_to(template_path)
            try:
                content = full.read_text(encoding="utf-8")
            except (UnicodeDecodeError, PermissionError):
                content = None
            files.append({
                "path": str(rel),
                "size": full.stat().st_size,
                "content": content,
            })
    files.sort(key=lambda f: f["path"])

    # Extract placeholders from all text files
    placeholders = set()
    for f in files:
        if f["content"]:
            import re
            placeholders.update(re.findall(r"\{\{(\w+)\}\}", f["content"]))

    # Count by layer
    backend_files = [f for f in files if f["path"].startswith("backend/")]
    frontend_files = [f for f in files if f["path"].startswith("frontend/")]

    return {
        "name": template_path.name,
        "readme": readme,
        "total_files": len(files),
        "backend_files": len(backend_files),
        "frontend_files": len(frontend_files),
        "placeholders": sorted(placeholders),
        "files": files,
    }


@router.get("")
async def list_templates(authorization: Optional[str] = Header(None)):
    """List all available templates."""
    await get_current_admin(authorization)

    if not TEMPLATES_DIR.exists():
        return {"data": []}

    templates = []
    for item in sorted(TEMPLATES_DIR.iterdir()):
        if item.is_dir() and not item.name.startswith("."):
            info = _scan_template(item)
            # Summary only — no file contents in list
            templates.append({
                "name": info["name"],
                "total_files": info["total_files"],
                "backend_files": info["backend_files"],
                "frontend_files": info["frontend_files"],
                "placeholders": info["placeholders"],
                "has_readme": info["readme"] is not None,
            })

    return {"data": templates}


@router.get("/{template_name}")
async def get_template(template_name: str, authorization: Optional[str] = Header(None)):
    """Get full template details including file contents."""
    await get_current_admin(authorization)

    template_path = TEMPLATES_DIR / template_name
    if not template_path.exists() or not template_path.is_dir():
        raise HTTPException(status_code=404, detail="Template não encontrado")

    return {"data": _scan_template(template_path)}
