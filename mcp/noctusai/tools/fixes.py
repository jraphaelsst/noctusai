"""Auto-fix functions for deterministic compliance issues."""
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PRODUCTS_DIR = REPO_ROOT / "products"


def fix_issue(issue: dict) -> dict:
    """Attempt to auto-fix a compliance issue. Returns {fixed, action}."""
    text = issue.get("issue", "")
    product = issue.get("product", "")

    if "Missing -e seed/backend/framework" in text:
        return _fix_missing_req(product, "seed/backend/framework")
    if "Missing -e seed/backend/lib" in text:
        return _fix_missing_req(product, "seed/backend/lib")
    if "shared/backend" in text and "seed/" in text:
        return _fix_old_path(issue, "shared/backend", "seed/backend/lib")
    if "shared/frontend" in text and "seed/" in text:
        return _fix_old_path(issue, "shared/frontend", "seed/frontend/lib")
    for name in ["health.py", "notificacoes.py", "team.py"]:
        if name in text and "framework provides" in text:
            return _fix_delete_boilerplate(product, name)

    return {"fixed": False, "action": f"Needs manual fix: {text}"}


def _fix_missing_req(product, package_path):
    req = PRODUCTS_DIR / product / "backend" / "requirements.txt"
    if not req.exists():
        return {"fixed": False, "action": "requirements.txt not found"}
    content = req.read_text()
    line = f"-e {package_path}"
    if line in content:
        return {"fixed": True, "action": f"Already present: {line}"}
    lines = content.splitlines()
    insert_at = 0
    for i, l in enumerate(lines):
        if l.strip().startswith("-e "):
            insert_at = i + 1
    lines.insert(insert_at, line)
    req.write_text("\n".join(lines) + "\n")
    return {"fixed": True, "action": f"Added '{line}'"}


def _fix_old_path(issue, old, new):
    target = PRODUCTS_DIR / issue["product"] / issue["file"]
    if not target.exists():
        return {"fixed": False, "action": f"File not found"}
    content = target.read_text()
    if old not in content:
        return {"fixed": False, "action": f"Pattern not found"}
    target.write_text(content.replace(old, new))
    return {"fixed": True, "action": f"Replaced '{old}' → '{new}'"}


def _fix_delete_boilerplate(product, filename):
    target = PRODUCTS_DIR / product / "backend" / "app" / "routers" / filename
    if not target.exists():
        return {"fixed": True, "action": f"Already deleted"}
    target.unlink()
    return {"fixed": True, "action": f"Deleted {filename}"}


def heal_product(product_slug: str = None, max_iterations: int = 10) -> dict:
    """Heal loop: detect → fix → verify → repeat until clean."""
    from tools.compliance import check_seed_compliance, check_path_references
    from tools.proposals import generate_proposal

    products = []
    if product_slug:
        p = PRODUCTS_DIR / product_slug
        if p.exists():
            products = [p]
    else:
        products = sorted([d for d in PRODUCTS_DIR.iterdir() if d.is_dir() and not d.name.startswith(".")])

    total_fixed = 0
    total_proposals = 0

    for iteration in range(max_iterations):
        all_issues = []
        for p in products:
            all_issues.extend(check_seed_compliance(p))
            all_issues.extend(check_path_references(p))

        if not all_issues:
            break

        fixed_this_round = 0
        for issue in all_issues:
            result = fix_issue(issue)
            if result["fixed"]:
                fixed_this_round += 1
                total_fixed += 1
            else:
                generate_proposal(
                    title=f"Fix: {issue.get('issue', '')[:60]}",
                    problem=issue.get("issue", ""),
                    solution="Requires manual review.",
                    affected_products=[issue.get("product", "unknown")],
                    severity=issue.get("severity", "medium"),
                    agent="keeper",
                )
                total_proposals += 1

        if fixed_this_round == 0:
            break

    # Final score
    from tools.compliance import check_all_products
    final_score, final_issues = check_all_products()

    return {
        "iterations": iteration + 1,
        "auto_fixed": total_fixed,
        "proposals_created": total_proposals,
        "final_score": final_score,
        "remaining_issues": len(final_issues),
    }
