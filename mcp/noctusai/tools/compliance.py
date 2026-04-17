"""Seed compliance checks — migrated from agents/keeper/checks/.

Validates that products follow the seed framework pattern.
All checks are deterministic, fast, zero AI.
"""
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PRODUCTS_DIR = REPO_ROOT / "products"


def check_seed_compliance(product_path: Path) -> list[dict]:
    """Check a product's seed framework compliance."""
    issues = []
    name = product_path.name
    main_py = product_path / "backend" / "app" / "main.py"
    req_txt = product_path / "backend" / "requirements.txt"
    vite_config = product_path / "frontend" / "vite.config.ts"
    app_tsx = product_path / "frontend" / "src" / "App.tsx"

    # Backend checks
    if main_py.exists():
        content = main_py.read_text()
        if "create_product_app" not in content:
            issues.append({"product": name, "file": "backend/app/main.py", "issue": "Does not use create_product_app()", "severity": "critical"})
        if "noctusai_seed" not in content:
            issues.append({"product": name, "file": "backend/app/main.py", "issue": "Does not import from noctusai_seed", "severity": "critical"})

    if req_txt.exists():
        req_content = req_txt.read_text()
        if "seed/backend/framework" not in req_content:
            issues.append({"product": name, "file": "backend/requirements.txt", "issue": "Missing -e seed/backend/framework", "severity": "high"})
        if "seed/backend/lib" not in req_content:
            issues.append({"product": name, "file": "backend/requirements.txt", "issue": "Missing -e seed/backend/lib", "severity": "high"})

    for router_name in ["health.py", "notificacoes.py", "team.py"]:
        if (product_path / "backend" / "app" / "routers" / router_name).exists():
            issues.append({"product": name, "file": f"backend/app/routers/{router_name}", "issue": f"Has own {router_name} — framework provides this", "severity": "warning"})

    # Frontend checks
    if vite_config.exists():
        content = vite_config.read_text()
        if "createViteConfig" not in content:
            issues.append({"product": name, "file": "frontend/vite.config.ts", "issue": "Does not use createViteConfig()", "severity": "critical"})

    if app_tsx.exists():
        app_content = app_tsx.read_text()
        uses_fw = "createProductApp" in app_content or "createProductLayout" in app_content or "@noctusai/seed" in app_content
        if not uses_fw and "QueryClientProvider" in app_content and "BrowserRouter" in app_content:
            issues.append({"product": name, "file": "frontend/src/App.tsx", "issue": "Manual App structure — should use createProductApp()", "severity": "high"})

        src_dir = product_path / "frontend" / "src"
        layout_file = product_path / "frontend" / "src" / "components" / "layout" / "Layout.tsx"
        if layout_file.exists():
            uses_fw_layout = any("createProductLayout" in f.read_text() for f in src_dir.rglob("*.ts") if f.is_file()) or any("createProductLayout" in f.read_text() for f in src_dir.rglob("*.tsx") if f.is_file())
            if not uses_fw_layout:
                issues.append({"product": name, "file": "frontend/src/components/layout/Layout.tsx", "issue": "Has own Layout.tsx — should use createProductLayout()", "severity": "high"})

    return issues


def check_path_references(product_path: Path) -> list[dict]:
    """Check that seed path references are correct."""
    issues = []
    name = product_path.name

    for rel, old, label in [
        ("backend/requirements.txt", "shared/backend", "old shared/backend path"),
        ("frontend/tsconfig.json", "shared/frontend", "old shared/frontend path"),
        ("frontend/tailwind.config.ts", "shared/frontend", "old shared/frontend path"),
    ]:
        target = product_path / rel
        if target.exists():
            content = target.read_text()
            if old in content and "seed/" not in content:
                issues.append({"product": name, "file": rel, "issue": f"References {label} — should be seed/", "severity": "critical"})

    return issues


def check_all_products() -> tuple[int, list]:
    """Run all compliance checks on all products. Returns (score, issues)."""
    all_issues = []
    scores = []

    for d in sorted(PRODUCTS_DIR.iterdir()):
        if not d.is_dir() or d.name.startswith("."):
            continue
        issues = check_seed_compliance(d) + check_path_references(d)
        all_issues.extend(issues)
        penalties = {"critical": 25, "high": 10, "warning": 3}
        penalty = sum(penalties.get(i["severity"], 5) for i in issues)
        scores.append(max(0, 100 - penalty))

    platform_score = round(sum(scores) / len(scores)) if scores else 100
    return platform_score, all_issues
