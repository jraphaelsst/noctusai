"""Knowledge Extractor — noc product entry point.

Absorbed from the sibling `knowledge-extractor` repo 2026-05-23. This wires the
product onto the seed factory (`create_product_app`) so it inherits logging,
DB clients, auth deps, CORS, credential + LLM resolution, and the standard
health endpoint with zero per-product boilerplate.

Backend-only (no SPA): the pipeline (Drive → transcribe → summarize → extract
methodology → pgvector KB) is currently CLI-driven (`app/cli.py`). Turning the
CLI into product routers + a `noctus.*` MCP tool is the next gate; until then
this app exposes the standard health surface only.

ABSORPTION FOLLOW-UPS (Gate 6/7, in flight — `container-first-codify-and-absorb-ke`):
  - make `app.config.Settings` subclass `noctusai_lib` ProductSettings;
  - swap the local seams (`app/integrations/{google_drive,llm,media,vectors}`)
    for their `noctusai_lib` counterparts (callers unchanged — see MASTER-PROMPT.md §3);
  - add domain routers as the CLI pipeline is exposed over HTTP.
"""
from noctusai_seed import create_product_app

from app.config import settings

app = create_product_app(
    name="Knowledge Extractor",
    schema="knowledge_extractor",
    settings=settings,
    version="0.1.0",
    standard_routers=["health"],
    routers=[],
)
