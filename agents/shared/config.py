"""Agent configuration — repo paths, product discovery."""
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PRODUCTS_DIR = REPO_ROOT / "products"
SEED_DIR = REPO_ROOT / "seed"
SEED_LIB = SEED_DIR / "lib"
SEED_FRAMEWORK = SEED_DIR / "framework"


def list_products() -> list[dict]:
    """Discover all products in the repo. Returns list of {name, path, has_backend, has_frontend}."""
    products = []
    if not PRODUCTS_DIR.exists():
        return products
    for d in sorted(PRODUCTS_DIR.iterdir()):
        if not d.is_dir() or d.name.startswith("."):
            continue
        products.append({
            "name": d.name,
            "path": d,
            "has_backend": (d / "backend" / "app" / "main.py").exists(),
            "has_frontend": (d / "frontend" / "src").exists(),
        })
    return products
