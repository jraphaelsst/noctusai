"""
AI Advisory Layer — reads CLAUDE.md rules and validates code against them.

This is the Guardian's AI-powered extension. It doesn't block CI — it warns.
When a new rule is added to CLAUDE.md, the advisory layer automatically
enforces it without anyone writing a new check.

Requires ANTHROPIC_API_KEY in .env.
"""
import logging
from pathlib import Path

from agents.shared.config import REPO_ROOT, list_products
from agents.shared.repo import read_file, find_files
from agents.shared.models import ask_claude, is_ai_available

logger = logging.getLogger(__name__)


def _load_rules() -> str:
    """Load CLAUDE.md engineering rules."""
    content = read_file(REPO_ROOT / "CLAUDE.md")
    if not content:
        return ""
    # Extract just the Engineering Philosophy and key pattern sections
    lines = content.splitlines()
    rules = []
    in_section = False
    for line in lines:
        if line.startswith("## Engineering Philosophy") or line.startswith("## Frontend Patterns") or line.startswith("## Backend Patterns") or line.startswith("## Testing Standards"):
            in_section = True
        elif line.startswith("## ") and in_section:
            in_section = False
        if in_section:
            rules.append(line)
    return "\n".join(rules)


def _get_product_sample(product_path: Path) -> str:
    """Get a representative code sample from a product for AI analysis."""
    samples = []

    # main.py
    main = read_file(product_path / "backend" / "app" / "main.py")
    if main:
        samples.append(f"### backend/app/main.py\n```python\n{main}\n```")

    # config.py
    config = read_file(product_path / "backend" / "app" / "config.py")
    if config:
        samples.append(f"### backend/app/config.py\n```python\n{config}\n```")

    # dependencies.py
    deps = read_file(product_path / "backend" / "app" / "dependencies.py")
    if deps:
        samples.append(f"### backend/app/dependencies.py\n```python\n{deps}\n```")

    # App.tsx (first 80 lines)
    app_tsx = read_file(product_path / "frontend" / "src" / "App.tsx")
    if app_tsx:
        lines = app_tsx.splitlines()[:80]
        samples.append(f"### frontend/src/App.tsx\n```tsx\n{chr(10).join(lines)}\n```")

    # vite.config.ts
    vite = read_file(product_path / "frontend" / "vite.config.ts")
    if vite:
        samples.append(f"### frontend/vite.config.ts\n```ts\n{vite}\n```")

    return "\n\n".join(samples)


def run_advisory(product_path: Path = None) -> list[dict]:
    """Run AI advisory checks on one or all products.

    Returns list of advisory findings (warnings, not blockers).
    """
    if not is_ai_available():
        return [{"type": "info", "message": "AI advisory skipped — ANTHROPIC_API_KEY not set"}]

    rules = _load_rules()
    if not rules:
        return [{"type": "error", "message": "Could not load CLAUDE.md rules"}]

    products = list_products()
    if product_path:
        products = [p for p in products if p["path"] == product_path]

    findings = []

    for product in products:
        sample = _get_product_sample(product["path"])
        if not sample:
            continue

        prompt = f"""You are the NoctusAI Guardian — an AI that validates code against the platform's engineering rules.

## Rules (from CLAUDE.md)

{rules}

## Product: {product['name']}

{sample}

## Task

Analyze this product's code against the rules above. Report ONLY actual violations — not style preferences, not suggestions, not "could be better." Only report things that BREAK a rule.

For each violation, output a JSON line:
{{"product": "{product['name']}", "file": "path/to/file", "rule": "rule that's broken", "issue": "what's wrong", "severity": "warning"}}

If the code is fully compliant, output:
{{"product": "{product['name']}", "compliant": true}}

Output ONLY JSON lines, nothing else."""

        response = ask_claude(
            prompt=prompt,
            system="You are a strict code auditor. Only report real rule violations. No false positives.",
            max_tokens=2048,
            temperature=0.1,
        )

        if not response:
            continue

        # Parse response lines
        import json
        for line in response.strip().splitlines():
            line = line.strip()
            if not line or not line.startswith("{"):
                continue
            try:
                finding = json.loads(line)
                if finding.get("compliant"):
                    findings.append({
                        "product": product["name"],
                        "type": "compliant",
                        "message": f"{product['name']} is fully compliant with CLAUDE.md rules",
                    })
                else:
                    findings.append({
                        "product": finding.get("product", product["name"]),
                        "file": finding.get("file", ""),
                        "rule": finding.get("rule", ""),
                        "issue": finding.get("issue", ""),
                        "severity": "advisory",
                        "type": "advisory",
                    })
            except json.JSONDecodeError:
                continue

    return findings
