"""Agent context tools — provide structured platform context."""
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

REPO_ROOT = Path(__file__).resolve().parents[3]


class AgentContextInput(BaseModel):
    """No inputs — the call returns the full bootstrap context unconditionally."""


class AgentContextOutput(BaseModel):
    platform: str
    stack: str
    seed_path: str
    seed_layers: dict[str, str]
    products: list[dict[str, Any]]
    agents: dict[str, str]
    key_files: dict[str, str]
    env: str
    top_rules: list[str]


class ProductContextInput(BaseModel):
    slug: str = Field(description="Product slug, e.g. 'erp-imobiliario'.")


class ProductContextOutput(BaseModel):
    """Product structure + MASTER-PROMPT + README. Shape is dynamic; structure
    fields are merged from `get_product_structure(slug)` and not enumerated here."""

    structure: dict[str, Any] = Field(description="Full product structure dict.")
    master_prompt: str | None
    readme: str | None


def get_agent_context() -> dict:
    """Return the full agent bootstrap context as structured data.

    This is the programmatic equivalent of KNOWLEDGE-BASE/AGENT-CONTEXT.md.
    Agents call this to understand the platform without reading files.
    """
    from tools.products import list_products

    products = list_products()

    return {
        "platform": "NoctusAI",
        "stack": "FastAPI + Supabase backend, React + TypeScript + Vite frontend",
        "seed_path": "seed/",
        "seed_layers": {
            "backend_lib": "seed/backend/lib/ (noctusai_lib)",
            "backend_framework": "seed/backend/framework/ (noctusai_seed)",
            "frontend_lib": "seed/frontend/lib/ (@noctusai/lib)",
            "frontend_framework": "seed/frontend/framework/ (@noctusai/seed)",
        },
        "products": [
            {
                "name": p["name"],
                "routers": len(p["routers"]),
                "services": len(p["services"]),
                "pages": len(p["pages"]),
                "hooks": len(p["hooks"]),
                "has_readme": p["has_readme"],
                "has_master_prompt": p["has_master_prompt"],
            }
            for p in products
        ],
        "agents": {
            "keeper": "mcp/noctusai/ — observation-only reviewer. Detects seed-compliance issues; LLM (OpenAI) authors proposals in products/<product>/proposals/. Never modifies code.",
            "proposals": "products/<product>/proposals/ — product-scoped proposals (pending / accepted / rejected)",
        },
        "key_files": {
            "rules": "CLAUDE.md",
            "agent_bootstrap": "KNOWLEDGE-BASE/AGENT-CONTEXT.md",
            "seed_architecture": "KNOWLEDGE-BASE/CONTEXT/03-SEED-ARCHITECTURE.md",
            "shared_library": "KNOWLEDGE-BASE/CONTEXT/04-SHARED-LIBRARY.md",
            "agents_doc": "KNOWLEDGE-BASE/CONTEXT/06-AGENTS.md",
            "philosophy": "KNOWLEDGE-BASE/CONTEXT/01-PHILOSOPHY.md",
            "landscape": "KNOWLEDGE-BASE/CONTEXT/02-LANDSCAPE.md",
            "kb_index": "KNOWLEDGE-BASE/INDEX.md",
        },
        "env": "Single root .env for everything (backends + frontends via envDir)",
        "top_rules": [
            "Seed first — always use the seed framework",
            "No incomplete commits — backend and frontend at same maturity",
            "Hooks in dedicated files — never inline in pages",
            "MCP toolkit reviews after changes (observation-only) — python mcp/noctusai/cli.py --review",
            "Extend framework, never go custom",
            "Docs stay in sync — every change updates docs in same commit",
        ],
    }


def get_product_context(slug: str) -> dict:
    """Return context for a specific product — everything an agent needs to work on it."""
    from tools.products import get_product_structure

    structure = get_product_structure(slug)
    path = REPO_ROOT / "products" / slug

    # Read MASTER-PROMPT if exists
    mp_file = path / "MASTER-PROMPT.md"
    master_prompt = mp_file.read_text() if mp_file.exists() else None

    # Read README if exists
    readme_file = path / "README.md"
    readme = readme_file.read_text() if readme_file.exists() else None

    structure["master_prompt"] = master_prompt
    structure["readme"] = readme

    return structure
