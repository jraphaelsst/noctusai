"""AI reasoning — uses OpenAI to analyze findings and author proposals.

`review_compliance_issue()` is the keeper's LLM entry point: it takes a single
deterministic compliance finding, pulls the relevant file snippet for context,
and asks the model for every field the proposal template needs. The keeper
itself never modifies code — its output is always a proposal a human reviews.

Default model is `gpt-4o-mini` (cheap + sufficient for structured JSON). The
caller can override via the `model=` kwarg for evaluation / A-B runs.
"""
import os
import re
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
        logger.info("ai_brain: python-dotenv not installed; relying on already-set env")
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        logger.info("ai_brain: OPENAI_API_KEY not set; AI helpers disabled")
        return None
    try:
        from openai import OpenAI
        _client = OpenAI(api_key=api_key)
        return _client
    except ImportError:
        logger.warning("ai_brain: `openai` SDK not installed; AI helpers disabled")
        return None


def is_ai_available():
    return _get_client() is not None


KEEPER_DEFAULT_MODEL = "gpt-4o-mini"


def ask_ai(prompt, system="", model=KEEPER_DEFAULT_MODEL, max_tokens=4096, temperature=0.3):
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
    except Exception as exc:
        logger.warning("ai_brain: cannot read CLAUDE.md (%s); proceeding without rule context", exc)

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
        except json.JSONDecodeError as exc:
            logger.warning("ai_brain: malformed AI proposal line (%s), skipping: %r", exc, line[:120])
            continue
    return proposals


def review_compliance_issue(issue: dict, product_path: Path, model: str = KEEPER_DEFAULT_MODEL) -> Optional[dict]:
    """Author a structured proposal for one deterministic compliance finding. LLM-backed.

    Reads the flagged file for context and asks the model for every field
    `tools.proposals.fill_proposal_template` needs. Returns that dict, or None
    on any failure (caller must have a skeleton fallback).

    The prompt is explicit that keeper is observation-only: the LLM authors
    advice for a human reviewer, never code-rewriting instructions that assume
    auto-application.
    """
    if not is_ai_available():
        return None

    file_rel = issue.get("file", "")
    file_abs = product_path / file_rel if file_rel else None
    snippet = ""
    if file_abs and file_abs.exists() and file_abs.is_file():
        try:
            snippet = file_abs.read_text()[:2000]
        except Exception as exc:
            logger.warning("ai_brain: cannot read %s for proposal context (%s); proposal will lack code snippet", file_abs, exc)
            snippet = ""

    prompt = f"""You are the NoctusAI **keeper** — an observation-only compliance reviewer for a FastAPI + React + Supabase monorepo built on a central `seed/` framework. You NEVER modify code. You author proposals a human reviews.

Every product inherits backbone from `seed/`: backend uses `create_product_app()` + `noctusai_seed`; frontend uses `createViteConfig()` + `createProductApp()` + `createProductLayout()`. Deviations are violations.

A detector flagged this issue in product `{issue.get('product')}`:

  File: {file_rel}
  Issue: {issue.get('issue')}
  Severity: {issue.get('severity')}

Relevant file content (may be empty if the file is missing):
```
{snippet or '(no content)'}
```

Your proposal is a **context-transfer vehicle** — the agent who will apply the fix must inherit your situational awareness through the text. Respond as strict JSON on ONE line, no prose outside it. Match this shape exactly:

{{
  "title": "short action-oriented string (< 80 chars)",
  "context": "2-4 sentences on what the detector saw and what triggered the flag — the environment this came out of",
  "situation": "3-6 sentences of PURE FACTS about current state — what's there, where, with what shape. No advice, no judgment. Name file paths and symbols.",
  "linkage": "1-2 sentences: why THIS solution fits THIS situation specifically. What about the situation makes this the right move?",
  "application_steps": ["concrete unambiguous step 1", "step 2", "..."],
  "seed_apis": [{{"symbol": "noctusai_seed.something", "why": "what it provides and why it replaces the current code"}}],
  "risks": "specific warnings. If destructive (delete / mass replace), say 'diff against seed first'. If additive, say 'Low risk — additive change, no overwrite.'",
  "alternatives": [{{"approach": "...", "why_not": "one sentence"}}],
  "effects": [{{"dimension": "Behavior|Risk profile|Ergonomics|Coverage", "change": "one-line change"}}],
  "effort": "low|medium|high",
  "related_files": [{{"path": "products/<slug>/...", "note": "what to inspect"}}]
}}

Rules:
- Arrays may be empty (`[]`) when no items apply — DO NOT fabricate filler.
- `situation` is facts only; `linkage` is where your judgment lives.
- Point to exact symbols, files, and seed helpers when possible.
- Do NOT propose changes to `seed/` itself unless the issue clearly indicates a framework gap.
- Return JSON only. No markdown fences, no commentary."""

    response = ask_ai(
        prompt=prompt,
        system="Senior platform engineer. Output one line of valid JSON. No prose outside JSON.",
        model=model,
        max_tokens=2048,
        temperature=0.2,
    )
    if not response:
        return None

    # Strip common wrappers the model sometimes produces despite instructions.
    cleaned = response.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\n?", "", cleaned)
        cleaned = re.sub(r"\n?```\s*$", "", cleaned)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        logger.warning("ai_brain: AI returned non-JSON, attempting JSONL line-by-line fallback (%s)", exc)
        # Try line-by-line as a fallback (some models emit JSONL).
        last_err: Exception | None = None
        for line in cleaned.splitlines():
            line = line.strip()
            if line.startswith("{") and line.endswith("}"):
                try:
                    return json.loads(line)
                except json.JSONDecodeError as line_exc:
                    logger.debug("ai_brain: JSONL line did not parse (%s): %r", line_exc, line[:120])
                    last_err = line_exc
                    continue
        logger.warning(
            "ai_brain: AI response was not valid JSON or JSONL; returning None. "
            "Last parse error: %s. First 200 chars of response: %r",
            last_err, cleaned[:200],
        )
        return None


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
    except Exception as exc:
        logger.warning("ai_brain: cannot read CLAUDE.md for advisory rules (%s); rules will be empty", exc)

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
                except Exception as exc:
                    logger.warning("ai_brain: malformed AI advisory line (%s), skipping: %r", exc, line[:120])

    return findings


def register(server) -> None:
    @server.tool(
        name="noctusai_ai_discover",
        description="AI-powered improvement discovery (requires OPENAI_API_KEY)",
    )
    def _ai_discover() -> dict:
        from tools.analyzers import run_all_analyzers
        return analyze_findings(run_all_analyzers())

    @server.tool(
        name="noctusai_ai_advisory",
        description="AI reads CLAUDE.md rules and validates code (requires OPENAI_API_KEY)",
    )
    def _ai_advisory() -> dict:
        return ai_advisory()
