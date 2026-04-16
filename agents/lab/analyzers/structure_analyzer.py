"""
Structure Analyzer — compares product structures against the seed standard.

Identifies structural gaps: missing files, missing directories,
products that deviate from the expected structure.
"""
from pathlib import Path

from agents.shared.config import list_products
from agents.shared.repo import get_product_structure, read_file, count_lines


# Expected files in a framework-compliant product
EXPECTED_BACKEND = [
    "app/__init__.py",
    "app/main.py",
    "app/config.py",
    "app/database.py",
    "app/dependencies.py",
    "app/rate_limit.py",
    "requirements.txt",
]

EXPECTED_FRONTEND = [
    "src/App.tsx",
    "src/main.tsx",
    "src/index.css",
    "src/store/authStore.ts",
    "src/integrations/supabase/client.ts",
    "src/lib/api-client.ts",
    "src/hooks/useNotificacoes.ts",
    "src/components/NotificationBell.tsx",
    "vite.config.ts",
    "tsconfig.json",
    "tailwind.config.ts",
    "package.json",
    ".env.example",
]

EXPECTED_ROOT = [
    "README.md",
    "MASTER-PROMPT.md",
]


def analyze_product_structure(product_path: Path) -> list[dict]:
    """Check a product against the expected file structure."""
    issues = []
    name = product_path.name

    # Root files
    for f in EXPECTED_ROOT:
        if not (product_path / f).exists():
            issues.append({
                "product": name,
                "file": f,
                "issue": f"Missing required file: {f}",
                "severity": "high",
            })

    # Backend files
    if (product_path / "backend").exists():
        for f in EXPECTED_BACKEND:
            if not (product_path / "backend" / f).exists():
                issues.append({
                    "product": name,
                    "file": f"backend/{f}",
                    "issue": f"Missing backend file: {f}",
                    "severity": "warning",
                })

        # Check main.py uses framework
        main_content = read_file(product_path / "backend" / "app" / "main.py")
        if main_content and "create_product_app" not in main_content:
            issues.append({
                "product": name,
                "file": "backend/app/main.py",
                "issue": "Does not use create_product_app() from seed framework",
                "severity": "critical",
            })

    # Frontend files
    if (product_path / "frontend").exists():
        for f in EXPECTED_FRONTEND:
            if not (product_path / "frontend" / f).exists():
                issues.append({
                    "product": name,
                    "file": f"frontend/{f}",
                    "issue": f"Missing frontend file: {f}",
                    "severity": "warning",
                })

    return issues


def analyze_code_metrics() -> list[dict]:
    """Collect code metrics per product: line counts, file counts, test counts."""
    products = list_products()
    metrics = []

    for product in products:
        structure = get_product_structure(product["path"])
        backend_lines = 0
        frontend_lines = 0

        if (product["path"] / "backend" / "app").exists():
            for f in (product["path"] / "backend" / "app").rglob("*.py"):
                if "__pycache__" not in str(f):
                    backend_lines += count_lines(f)

        if (product["path"] / "frontend" / "src").exists():
            for ext in ["*.tsx", "*.ts"]:
                for f in (product["path"] / "frontend" / "src").rglob(ext):
                    if "node_modules" not in str(f):
                        frontend_lines += count_lines(f)

        metrics.append({
            "product": product["name"],
            "backend_lines": backend_lines,
            "frontend_lines": frontend_lines,
            "routers": len(structure["backend"].get("routers", [])),
            "services": len(structure["backend"].get("services", [])),
            "pages": len(structure["frontend"].get("pages", [])),
            "hooks": len(structure["frontend"].get("hooks", [])),
        })

    return metrics


def run_all() -> dict:
    products = list_products()
    all_issues = []
    for product in products:
        all_issues.extend(analyze_product_structure(product["path"]))

    return {
        "structure_issues": all_issues,
        "code_metrics": analyze_code_metrics(),
    }
