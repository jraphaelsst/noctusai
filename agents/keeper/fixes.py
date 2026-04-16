"""
Auto-fix functions for deterministic Guardian issues.

Each fix corresponds to a Guardian check. The fix knows exactly what
to do because the check told it exactly what's wrong.

Only deterministic fixes — no AI, no guessing. If the fix can't be
applied safely, it's skipped and reported as "needs manual fix."
"""
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def fix_issue(issue: dict) -> dict:
    """Attempt to auto-fix a Guardian issue.

    Returns {fixed: bool, action: str} describing what was done.
    """
    issue_text = issue.get("issue", "")
    product = issue.get("product", "")
    file_path = issue.get("file", "")

    # Missing seed/backend/framework in requirements.txt
    if "Missing -e seed/backend/framework" in issue_text:
        return _fix_missing_requirement(issue, "seed/backend/framework")

    # Missing seed/backend/lib in requirements.txt
    if "Missing -e seed/backend/lib" in issue_text:
        return _fix_missing_requirement(issue, "seed/backend/lib")

    # Old shared/backend path
    if "shared/backend" in issue_text and "seed/" in issue_text:
        return _fix_old_path(issue, "shared/backend", "seed/backend/lib")

    # Old shared/frontend path
    if "shared/frontend" in issue_text and "seed/" in issue_text:
        return _fix_old_path(issue, "shared/frontend", "seed/frontend/lib")

    # Product has its own health.py
    if "health.py" in issue_text and "framework provides" in issue_text:
        return _fix_delete_boilerplate(issue, "health.py")

    # Product has its own notificacoes.py
    if "notificacoes.py" in issue_text and "framework provides" in issue_text:
        return _fix_delete_boilerplate(issue, "notificacoes.py")

    # Product has its own team.py
    if "team.py" in issue_text and "framework provides" in issue_text:
        return _fix_delete_boilerplate(issue, "team.py")

    return {"fixed": False, "action": f"Needs manual fix: {issue_text}"}


def _fix_missing_requirement(issue: dict, package_path: str) -> dict:
    """Add a missing -e requirement to requirements.txt."""
    from agents.shared.config import PRODUCTS_DIR
    product_path = PRODUCTS_DIR / issue["product"]
    req_file = product_path / "backend" / "requirements.txt"

    if not req_file.exists():
        return {"fixed": False, "action": f"requirements.txt not found"}

    content = req_file.read_text()
    line = f"-e {package_path}"

    if line in content:
        return {"fixed": True, "action": f"Already present: {line}"}

    # Insert after the first -e line (or at top)
    lines = content.splitlines()
    insert_at = 0
    for i, l in enumerate(lines):
        if l.strip().startswith("-e "):
            insert_at = i + 1

    lines.insert(insert_at, line)
    req_file.write_text("\n".join(lines) + "\n")
    logger.info("Fixed: added '%s' to %s", line, req_file)
    return {"fixed": True, "action": f"Added '{line}' to requirements.txt"}


def _fix_old_path(issue: dict, old: str, new: str) -> dict:
    """Replace old path reference with new one."""
    from agents.shared.config import PRODUCTS_DIR
    product_path = PRODUCTS_DIR / issue["product"]
    target = product_path / issue["file"]

    if not target.exists():
        return {"fixed": False, "action": f"File not found: {target}"}

    content = target.read_text()
    if old not in content:
        return {"fixed": False, "action": f"Pattern '{old}' not found in {target}"}

    new_content = content.replace(old, new)
    target.write_text(new_content)
    logger.info("Fixed: replaced '%s' → '%s' in %s", old, new, target)
    return {"fixed": True, "action": f"Replaced '{old}' → '{new}'"}


def _fix_delete_boilerplate(issue: dict, filename: str) -> dict:
    """Delete a boilerplate router that the framework provides."""
    from agents.shared.config import PRODUCTS_DIR
    product_path = PRODUCTS_DIR / issue["product"]
    target = product_path / "backend" / "app" / "routers" / filename

    if not target.exists():
        return {"fixed": True, "action": f"Already deleted: {filename}"}

    target.unlink()
    logger.info("Fixed: deleted boilerplate %s from %s", filename, product_path.name)
    return {"fixed": True, "action": f"Deleted {filename} (framework provides it)"}
