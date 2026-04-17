"""AI reasoning — uses OpenAI to analyze findings and generate proposals."""
import os
import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]

_client = None
_initialized = False


def _get_client():
    global _client, _initialized
    if _initialized:
        return _client
    _initialized = True
    try:
        from dotenv import load_dotenv
        load_dotenv(REPO_ROOT / ".env")
    except ImportError:
        pass
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None
    try:
        from openai import OpenAI
        _client = OpenAI(api_key=api_key)
        return _client
    except ImportError:
        return None


def is_ai_available():
    return _get_client() is not None


def ask_ai(prompt, system="", model="gpt-4o", max_tokens=4096, temperature=0.3):
    client = _get_client()
    if not client:
        return None
    try:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        resp = client.chat.completions.create(model=model, messages=messages, max_tokens=max_tokens, temperature=temperature)
        return resp.choices[0].message.content
    except Exception as e:
        logger.error("OpenAI error: %s", e)
        return None


def analyze_findings(findings):
    """Send analyzer findings to AI for deep reasoning. Returns proposals."""
    if not is_ai_available():
        return [{"type": "info", "message": "AI disabled — set OPENAI_API_KEY"}]

    claude_md = ""
    try:
        claude_md = (REPO_ROOT / "CLAUDE.md").read_text()[:3000]
    except:
        pass

    findings_text = json.dumps(findings, indent=2, default=str)[:8000]

    response = ask_ai(
        prompt=f"Platform rules:\n{claude_md}\n\nFindings:\n{findings_text}\n\nGenerate 1-5 improvement proposals as JSON lines: {{\"title\": ..., \"problem\": ..., \"solution\": ..., \"affected_products\": [...], \"severity\": ..., \"effort\": ...}}",
        system="You are a platform architect. Be specific and practical.",
        temperature=0.4,
    )

    if not response:
        return [{"type": "error", "message": "AI failed to respond"}]

    from tools.proposals import generate_proposal
    proposals = []
    for line in response.strip().splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            data = json.loads(line)
            if data.get("status") == "no_proposals":
                proposals.append({"type": "healthy"})
                continue
            result = generate_proposal(
                title=data.get("title", "Untitled"),
                problem=data.get("problem", ""),
                solution=data.get("solution", ""),
                affected_products=data.get("affected_products", []),
                severity=data.get("severity", "medium"),
                effort=data.get("effort", "medium"),
                agent="keeper-ai",
            )
            proposals.append({"type": "proposal", "title": data["title"], **result})
        except json.JSONDecodeError:
            continue
    return proposals


def ai_advisory(product_path=None):
    """AI reads CLAUDE.md rules and validates code against them."""
    if not is_ai_available():
        return [{"type": "info", "message": "AI disabled"}]

    rules = ""
    try:
        content = (REPO_ROOT / "CLAUDE.md").read_text()
        for line in content.splitlines():
            if line.startswith("## Engineering") or line.startswith("## Frontend") or line.startswith("## Backend") or line.startswith("## Testing"):
                rules += line + "\n"
            elif rules and line.startswith("## "):
                break
            elif rules:
                rules += line + "\n"
    except:
        pass

    from tools.products import list_products, PRODUCTS_DIR
    products = list_products()
    findings = []

    for product in products:
        path = Path(product["path"])
        sample = ""
        for f in ["backend/app/main.py", "backend/app/config.py", "frontend/src/App.tsx", "frontend/vite.config.ts"]:
            fp = path / f
            if fp.exists():
                content = fp.read_text()
                sample += f"\n### {f}\n```\n{content[:500]}\n```\n"

        if not sample:
            continue

        response = ask_ai(
            prompt=f"Rules:\n{rules}\n\nProduct: {product['name']}\n{sample}\n\nReport ONLY actual rule violations as JSON: {{\"product\": ..., \"issue\": ..., \"rule\": ..., \"severity\": \"advisory\"}} or {{\"product\": ..., \"compliant\": true}}",
            system="Strict code auditor. Only real violations.",
            max_tokens=1024,
            temperature=0.1,
        )
        if not response:
            continue

        for line in response.strip().splitlines():
            if line.strip().startswith("{"):
                try:
                    findings.append(json.loads(line.strip()))
                except:
                    pass

    return findings
