"""
Seed compliance check — validates that products use the seed framework.

Checks:
  - Backend main.py imports create_product_app from noctusai_seed
  - Backend requirements.txt includes -e seed/framework/backend
  - Frontend vite.config.ts imports createViteConfig from seed framework
  - Frontend App.tsx imports from @noctusai/seed
"""
import re
from pathlib import Path


def check_backend_compliance(product_path: Path) -> list[dict]:
    """Check backend seed compliance. Returns list of issues."""
    issues = []
    name = product_path.name
    main_py = product_path / "backend" / "app" / "main.py"
    req_txt = product_path / "backend" / "requirements.txt"

    if not main_py.exists():
        return issues  # no backend, skip

    # Check main.py imports create_product_app
    content = main_py.read_text()
    if "create_product_app" not in content:
        issues.append({
            "product": name,
            "file": "backend/app/main.py",
            "issue": "Does not use create_product_app() from noctusai_seed",
            "severity": "critical",
        })
    if "noctusai_seed" not in content and "from noctusai_seed" not in content:
        issues.append({
            "product": name,
            "file": "backend/app/main.py",
            "issue": "Does not import from noctusai_seed framework",
            "severity": "critical",
        })

    # Check requirements.txt includes framework
    if req_txt.exists():
        req_content = req_txt.read_text()
        if "seed/framework/backend" not in req_content:
            issues.append({
                "product": name,
                "file": "backend/requirements.txt",
                "issue": "Missing -e seed/framework/backend dependency",
                "severity": "high",
            })
        if "seed/lib/backend" not in req_content:
            issues.append({
                "product": name,
                "file": "backend/requirements.txt",
                "issue": "Missing -e seed/lib/backend dependency",
                "severity": "high",
            })

    # Check for boilerplate that should NOT exist (framework provides these)
    for router_name in ["health.py", "notificacoes.py", "team.py"]:
        router_file = product_path / "backend" / "app" / "routers" / router_name
        if router_file.exists():
            issues.append({
                "product": name,
                "file": f"backend/app/routers/{router_name}",
                "issue": f"Product has its own {router_name} — framework provides this",
                "severity": "warning",
            })

    return issues


def check_frontend_compliance(product_path: Path) -> list[dict]:
    """Check frontend seed compliance. Returns list of issues."""
    issues = []
    name = product_path.name
    vite_config = product_path / "frontend" / "vite.config.ts"
    app_tsx = product_path / "frontend" / "src" / "App.tsx"

    if not vite_config.exists():
        return issues  # no frontend, skip

    # Check vite.config.ts uses createViteConfig
    content = vite_config.read_text()
    if "createViteConfig" not in content:
        issues.append({
            "product": name,
            "file": "frontend/vite.config.ts",
            "issue": "Does not use createViteConfig() from seed framework",
            "severity": "critical",
        })

    # Check for manual alias definitions (should not exist with the factory)
    if content.count("path.resolve") > 1:  # more than the import path
        issues.append({
            "product": name,
            "file": "frontend/vite.config.ts",
            "issue": "Has manual path.resolve aliases — should use createViteConfig() factory exclusively",
            "severity": "warning",
        })

    # Check App.tsx uses framework (if it exists)
    if app_tsx.exists():
        app_content = app_tsx.read_text()
        uses_framework = (
            "createProductApp" in app_content
            or "createProductLayout" in app_content
            or "@noctusai/seed" in app_content
        )
        if uses_framework:
            pass  # compliant — uses framework (may have custom routing on top)
        elif "QueryClientProvider" in app_content and "BrowserRouter" in app_content:
            issues.append({
                "product": name,
                "file": "frontend/src/App.tsx",
                "issue": "Manual App structure — should use createProductApp() from @noctusai/seed",
                "severity": "high",
            })

    # Check for Layout.tsx that should not exist (framework provides it)
    # Exception: if the product uses createProductLayout elsewhere (e.g. layouts.ts for role-based routing)
    layout_file = product_path / "frontend" / "src" / "components" / "layout" / "Layout.tsx"
    if layout_file.exists():
        layout_content = layout_file.read_text()
        # Check if createProductLayout is used anywhere in the frontend src
        src_dir = product_path / "frontend" / "src"
        uses_framework_layout = any(
            "createProductLayout" in f.read_text()
            for f in src_dir.rglob("*.ts")
            if f.is_file()
        ) or any(
            "createProductLayout" in f.read_text()
            for f in src_dir.rglob("*.tsx")
            if f.is_file()
        )
        if "createProductLayout" not in layout_content and not uses_framework_layout:
            issues.append({
                "product": name,
                "file": "frontend/src/components/layout/Layout.tsx",
                "issue": "Product has its own Layout.tsx — should use createProductLayout() from @noctusai/seed",
                "severity": "high",
            })

    return issues


def check_product(product_path: Path) -> list[dict]:
    """Run all compliance checks on a product."""
    issues = []
    issues.extend(check_backend_compliance(product_path))
    issues.extend(check_frontend_compliance(product_path))
    return issues
