"""
Scientist AI Brain — reasons over analyzer findings to generate intelligent proposals.

The file analyzers are the Scientist's eyes (data collection).
This module is the Scientist's brain (reasoning).

Flow: file analyzers → findings → AI brain → proposals

Capabilities:
1. Semantic duplication detection — finds functions that do the same thing with different names
2. Cross-product reasoning — identifies shared patterns across products
3. Improvement synthesis — turns raw findings into actionable proposals with code
4. Ecosystem awareness — suggests patterns from FastAPI/React ecosystem
"""
import json
import logging
from typing import Optional

from agents.shared.models import ask_claude, is_ai_available
from agents.shared.config import REPO_ROOT
from agents.shared.repo import read_file
from agents.scientist.proposer import generate_proposal

logger = logging.getLogger(__name__)


def _load_platform_context() -> str:
    """Load key platform docs for AI context."""
    claude_md = read_file(REPO_ROOT / "CLAUDE.md") or ""
    seed_readme = read_file(REPO_ROOT / "seed" / "README.md") or ""
    # Truncate to avoid token overload
    return f"## CLAUDE.md (rules)\n{claude_md[:3000]}\n\n## Seed README\n{seed_readme[:2000]}"


def analyze_findings(findings: dict) -> list[dict]:
    """Send analyzer findings to Claude for deep reasoning.

    Takes the raw output from all analyzers and asks the AI to:
    1. Identify patterns humans would miss
    2. Prioritize findings by real impact
    3. Generate concrete improvement proposals
    """
    if not is_ai_available():
        return [{"type": "info", "message": "AI brain skipped — ANTHROPIC_API_KEY not set"}]

    context = _load_platform_context()

    # Prepare findings summary for the AI
    findings_text = json.dumps(findings, indent=2, default=str)
    if len(findings_text) > 8000:
        findings_text = findings_text[:8000] + "\n... (truncated)"

    prompt = f"""You are the NoctusAI Scientist — an AI that analyzes a multi-product SaaS platform and proposes improvements.

## Platform Context

{context}

## Analyzer Findings

These are the raw findings from automated file analysis:

{findings_text}

## Your Task

Analyze these findings and generate 1-5 improvement proposals. Focus on:

1. **Highest impact, lowest effort first** — what gives the most value for the least work?
2. **Cross-product patterns** — are multiple products doing the same thing differently?
3. **Seed extraction candidates** — what should be moved to the seed lib/framework?
4. **Architecture improvements** — structural changes that reduce maintenance burden
5. **Security concerns** — anything that could be a vulnerability

For each proposal, output a JSON object:
{{"title": "short title", "problem": "what's wrong and why it matters", "solution": "concrete steps to fix it", "affected_products": ["product1", "product2"], "severity": "high|medium|low", "effort": "low|medium|high"}}

Output one JSON object per line. Only output real, actionable proposals. No vague suggestions.
If the platform is in good shape with no significant improvements needed, output:
{{"title": "Platform healthy", "status": "no_proposals"}}"""

    response = ask_claude(
        prompt=prompt,
        system="You are a senior platform architect. Be specific, concrete, and practical. Every proposal must include actual steps, not just descriptions.",
        model="claude-sonnet-4-6",
        max_tokens=4096,
        temperature=0.4,
    )

    if not response:
        return [{"type": "error", "message": "AI brain failed to respond"}]

    proposals = []
    for line in response.strip().splitlines():
        line = line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            data = json.loads(line)
            if data.get("status") == "no_proposals":
                proposals.append({"type": "healthy", "message": "Platform is in good shape"})
                continue

            # Generate a real proposal file
            filepath = generate_proposal(
                title=data.get("title", "Untitled"),
                problem=data.get("problem", ""),
                solution=data.get("solution", ""),
                affected_products=data.get("affected_products", []),
                severity=data.get("severity", "medium"),
                effort=data.get("effort", "medium"),
            )
            proposals.append({
                "type": "proposal",
                "title": data["title"],
                "severity": data.get("severity", "medium"),
                "effort": data.get("effort", "medium"),
                "file": str(filepath),
            })
        except json.JSONDecodeError:
            continue

    return proposals


def deep_analyze_duplication(duplicated_functions: list[dict]) -> Optional[str]:
    """Use AI to determine if duplicated functions are truly the same or just named similarly."""
    if not is_ai_available() or not duplicated_functions:
        return None

    funcs_text = json.dumps(duplicated_functions[:10], indent=2, default=str)

    prompt = f"""These functions appear in multiple NoctusAI products with the same name:

{funcs_text}

For each function, determine:
1. Are these likely the SAME logic (should be extracted to seed lib)?
2. Or are they just similarly NAMED but different logic (keep separate)?

Consider: functions like "log_action" are likely the same across products. Functions like "criar_meta" (create goal) may have different domain logic per product even though the name is the same.

Output your assessment as JSON lines:
{{"function": "name", "same_logic": true/false, "confidence": "high/medium/low", "recommendation": "extract to seed lib" or "keep separate — different domain logic"}}"""

    return ask_claude(
        prompt=prompt,
        system="You are a code architect evaluating whether functions should be shared or kept separate.",
        max_tokens=2048,
        temperature=0.2,
    )
