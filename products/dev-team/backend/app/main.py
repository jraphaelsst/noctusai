"""
NoctusAI dev-team — FastAPI Backend (seed framework).

Wraps the agno multi-agent dev team engine at `dev_team/` (repo root) with
auth + multi-tenant + RLS + a REST API. The engine itself is shared with
the CLI and the MCP tools; this product is its multi-tenant face.

Run with: uvicorn app.main:app --reload --port 8009
"""
from noctusai_seed import create_product_app

from app.config import settings
from app.api import agents, metrics, run, configs

app = create_product_app(
    name="dev-team",
    schema="dev_team",
    settings=settings,
    routers=[
        agents.router,
        metrics.router,
        run.router,
        configs.router,
    ],
    version="0.1.0",
    standard_routers=["health"],
)
