"""
Proposal Generator — creates structured improvement proposals from analyzer findings.

Each proposal is saved as a markdown file in agents/scientist/proposals/.
"""
import json
from datetime import datetime
from pathlib import Path

from agents.shared.config import REPO_ROOT

PROPOSALS_DIR = REPO_ROOT / "agents" / "scientist" / "proposals"


def generate_proposal(
    title: str,
    problem: str,
    solution: str,
    affected_products: list[str],
    severity: str = "medium",
    effort: str = "medium",
    findings: list[dict] = None,
) -> Path:
    """Generate a structured improvement proposal.

    Returns the path to the saved proposal file.
    """
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    slug = title.lower().replace(" ", "-").replace("/", "-")[:50]
    filename = f"{timestamp}-{slug}.md"
    filepath = PROPOSALS_DIR / filename

    findings_section = ""
    if findings:
        findings_section = "\n## Findings\n\n"
        for f in findings[:20]:
            findings_section += f"- {json.dumps(f, default=str)}\n"

    content = f"""# Proposal: {title}

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
## Trade-offs & Risks

_To be assessed during review._

## Acceptance Criteria

- [ ] All affected products updated
- [ ] All tests pass
- [ ] Guardian score remains 100/100
- [ ] Documentation updated

## Decision

- [ ] **Accept** — implement this proposal
- [ ] **Reject** — with reason: ___
- [ ] **Defer** — revisit on: ___
"""

    PROPOSALS_DIR.mkdir(parents=True, exist_ok=True)
    filepath.write_text(content)
    return filepath


def list_proposals() -> list[dict]:
    """List all existing proposals."""
    proposals = []
    if not PROPOSALS_DIR.exists():
        return proposals

    for f in sorted(PROPOSALS_DIR.glob("*.md")):
        if f.name == ".gitkeep":
            continue
        content = f.read_text()
        status = "pending"
        if "**Status:** accepted" in content.lower():
            status = "accepted"
        elif "**Status:** rejected" in content.lower():
            status = "rejected"

        proposals.append({
            "file": f.name,
            "path": str(f),
            "status": status,
        })

    return proposals
