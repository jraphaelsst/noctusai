"""
Proposal Generator — creates structured improvement proposals.

Proposals live in agents/proposals/, organized by agent:
  agents/proposals/keeper-20260416-153635-extract-criar-meta.md
  agents/proposals/reviewer-20260417-091200-missing-error-handling.md

The agent name prefix scopes proposals so you can filter by agent
while keeping everything in one folder.
"""
import json
from datetime import datetime
from pathlib import Path

from agents.shared.config import REPO_ROOT

PROPOSALS_DIR = REPO_ROOT / "agents" / "proposals"


def _slug(title: str) -> str:
    """Generate a filename slug from a title."""
    return title.lower().replace(" ", "-").replace("'", "").replace("/", "-")[:50]


def _extract_key_entity(title: str) -> str:
    """Extract the key entity from a proposal title for fuzzy matching."""
    import re
    match = re.search(r"['\"]?(\w+_\w+)['\"]?", title)
    if match:
        return match.group(1).lower()
    return _slug(title)[:30]


def _proposal_exists(title: str, agent: str) -> bool:
    """Check if a proposal with this title (or similar entity) already exists for any agent."""
    if not PROPOSALS_DIR.exists():
        return False

    slug = _slug(title)
    key_entity = _extract_key_entity(title)

    for f in PROPOSALS_DIR.glob("*.md"):
        if f.name == "README.md":
            continue
        fname = f.stem.lower()
        if slug in fname:
            return True
        if key_entity and len(key_entity) > 5 and key_entity in fname:
            return True
    return False


def generate_proposal(
    title: str,
    problem: str,
    solution: str,
    affected_products: list[str],
    severity: str = "medium",
    effort: str = "medium",
    findings: list[dict] = None,
    agent: str = "keeper",
) -> Path:
    """Generate a structured improvement proposal.

    Args:
        agent: Name of the agent creating this proposal (e.g. "keeper", "reviewer").
               Used as filename prefix for scoping.

    Returns the path to the saved proposal file, or existing one if deduplicated.
    """
    if _proposal_exists(title, agent):
        slug = _slug(title)
        for f in PROPOSALS_DIR.glob("*.md"):
            if slug in f.stem:
                return f
        return PROPOSALS_DIR / "deduplicated"

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    slug = _slug(title)
    filename = f"{agent}-{timestamp}-{slug}.md"
    filepath = PROPOSALS_DIR / filename

    findings_section = ""
    if findings:
        findings_section = "\n## Findings\n\n"
        for f in findings[:20]:
            findings_section += f"- {json.dumps(f, default=str)}\n"

    content = f"""# Proposal: {title}

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
## Trade-offs & Risks

_To be assessed during review._

## Acceptance Criteria

- [ ] All affected products updated
- [ ] All tests pass
- [ ] Keeper validates clean (100/100)
- [ ] Documentation updated

## Decision

- [ ] **Accept** — implement this proposal
- [ ] **Reject** — with reason: ___
- [ ] **Defer** — revisit on: ___
"""

    PROPOSALS_DIR.mkdir(parents=True, exist_ok=True)
    filepath.write_text(content)
    return filepath


def list_proposals(agent: str = None) -> list[dict]:
    """List proposals. Optionally filter by agent name."""
    proposals = []
    if not PROPOSALS_DIR.exists():
        return proposals

    for f in sorted(PROPOSALS_DIR.glob("*.md")):
        if f.name in (".gitkeep", "README.md"):
            continue

        # Extract agent from filename (agent-timestamp-slug.md)
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

        proposals.append({
            "file": f.name,
            "path": str(f),
            "agent": file_agent,
            "status": status,
        })

    return proposals
