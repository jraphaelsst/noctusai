"""Knowledge Extractor — noc product entry point.

Absorbed from the sibling `knowledge-extractor` repo 2026-05-23, then given its
HTTP API + SPA 2026-05-23 (P4 of `container-first-codify-and-absorb-ke`). Wires
onto the seed factory (`create_product_app`) so it inherits logging, DB clients,
auth deps, CORS, credential + LLM resolution, rate limiting, and the standard
health / team / notification surfaces with zero per-product boilerplate.

Domain surface — the CLI pipeline, now exposed over HTTP (`app/routers/`):
  - `catalog`     browse the extracted transcripts/summaries (filesystem);
  - `methodology` the synthesized course manual;
  - `kb`          semantic search over the methodology KB (pgvector);
  - `runs`        trigger + track extraction-pipeline runs (Drive → summary).
The SPA (single container via the seed `serve_spa` seam) lives in `../frontend`.
The CLI (`app/cli.py`) remains for local/batch operation.
"""
from noctusai_seed import create_product_app

from app.config import settings
from app.rate_limit import limiter
from app.routers.catalog_router import router as catalog_router
from app.routers.kb_router import router as kb_router
from app.routers.methodology_router import router as methodology_router
from app.routers.runs_router import router as runs_router

app = create_product_app(
    name="Knowledge Extractor",
    schema="knowledge_extractor",
    settings=settings,
    version="0.1.0",
    limiter=limiter,
    standard_routers=["health", "notificacoes", "team"],
    routers=[catalog_router, methodology_router, kb_router, runs_router],
)
