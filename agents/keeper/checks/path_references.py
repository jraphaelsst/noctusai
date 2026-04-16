"""
Path reference validation — ensures all seed paths are correct.

Checks that requirements.txt, tsconfig.json, and tailwind.config.ts
reference seed/lib/ and seed/framework/ correctly.
"""
from pathlib import Path


def check_path_references(product_path: Path) -> list[dict]:
    """Validate that all path references to seed/ are correct."""
    issues = []
    name = product_path.name

    # Backend: requirements.txt should reference seed/backend/lib, not shared/backend
    req_txt = product_path / "backend" / "requirements.txt"
    if req_txt.exists():
        content = req_txt.read_text()
        if "shared/backend" in content and "seed/" not in content:
            issues.append({
                "product": name,
                "file": "backend/requirements.txt",
                "issue": "References old 'shared/backend' path — should be 'seed/backend/lib'",
                "severity": "critical",
            })

    # Frontend: tsconfig.json should reference seed/lib/ and seed/framework/
    tsconfig = product_path / "frontend" / "tsconfig.json"
    if tsconfig.exists():
        content = tsconfig.read_text()
        if "shared/frontend" in content and "seed/" not in content:
            issues.append({
                "product": name,
                "file": "frontend/tsconfig.json",
                "issue": "References old 'shared/frontend' path — should be 'seed/frontend/lib'",
                "severity": "critical",
            })

    # Frontend: tailwind.config.ts should reference seed/lib/
    tailwind = product_path / "frontend" / "tailwind.config.ts"
    if tailwind.exists():
        content = tailwind.read_text()
        if "shared/frontend" in content and "seed/" not in content:
            issues.append({
                "product": name,
                "file": "frontend/tailwind.config.ts",
                "issue": "References old 'shared/frontend' path — should be 'seed/frontend/lib'",
                "severity": "critical",
            })

    return issues
