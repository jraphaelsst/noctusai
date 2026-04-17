"""Proposal management — generate, list, accept, reject."""
import json
import re
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PROPOSALS_DIR = REPO_ROOT / "mcp" / "noctusai" / "proposals"


def _slug(title):
    return title.lower().replace(" ", "-").replace("'", "").replace("/", "-")[:50]


def _extract_key_entity(title):
    match = re.search(r"['\"]?(\w+_\w+)['\"]?", title)
    return match.group(1).lower() if match else _slug(title)[:30]


def _proposal_exists(title):
    if not PROPOSALS_DIR.exists():
        return False
    slug = _slug(title)
    key = _extract_key_entity(title)
    for f in PROPOSALS_DIR.glob("*.md"):
        if f.name == "README.md":
            continue
        fname = f.stem.lower()
        if slug in fname:
            return True
        if key and len(key) > 5 and key in fname:
            return True
    return False


def generate_proposal(title, problem, solution, affected_products, severity="medium", effort="medium", findings=None, agent="keeper"):
    """Generate a proposal. Deduplicates by key entity."""
    if _proposal_exists(title):
        return {"created": False, "reason": "duplicate"}

    PROPOSALS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"{agent}-{timestamp}-{_slug(title)}.md"
    filepath = PROPOSALS_DIR / filename

    findings_section = ""
    if findings:
        findings_section = "\n## Findings\n\n" + "".join(f"- {json.dumps(f, default=str)}\n" for f in findings[:20])

    filepath.write_text(f"""# Proposal: {title}

**Agent:** {agent}
**Generated:** {datetime.now().strftime("%Y-%m-%d %H:%M")}
**Severity:** {severity}
**Effort:** {effort}
**Affected products:** {', '.join(affected_products)}
**Status:** pending

## Problem

{problem}

## Proposed Solution

{solution}
{findings_section}
## Acceptance Criteria

- [ ] All affected products updated
- [ ] All tests pass
- [ ] Keeper validates clean
- [ ] Documentation updated
""")
    return {"created": True, "file": filename}


def list_proposals(agent=None):
    if not PROPOSALS_DIR.exists():
        return []
    results = []
    for f in sorted(PROPOSALS_DIR.glob("*.md")):
        if f.name in (".gitkeep", "README.md"):
            continue
        parts = f.stem.split("-", 1)
        file_agent = parts[0] if len(parts) > 1 and not parts[0].isdigit() else "unknown"
        if agent and file_agent != agent:
            continue
        content = f.read_text()
        status = "pending"
        if "**status:** accepted" in content.lower():
            status = "accepted"
        elif "**status:** rejected" in content.lower():
            status = "rejected"
        title = ""
        for line in content.splitlines():
            if line.startswith("# Proposal:"):
                title = line.replace("# Proposal:", "").strip()
                break
        results.append({"file": f.name, "agent": file_agent, "title": title, "status": status})
    return results


def update_proposal_status(filename, status, reason=""):
    """Update a proposal's status to accepted/rejected."""
    filepath = PROPOSALS_DIR / filename
    if not filepath.exists():
        return {"error": "Proposal not found"}
    content = filepath.read_text()
    content = re.sub(r'\*\*Status:\*\* \w+', f'**Status:** {status}', content)
    if reason and status == "rejected":
        content = content.replace("**Reject** — with reason: ___", f"**Reject** — with reason: {reason}")
    filepath.write_text(content)
    return {"updated": True, "status": status}
