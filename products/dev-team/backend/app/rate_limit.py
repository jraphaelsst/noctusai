"""Rate limiter for dev-team — delegates to framework.

The dev-team product proxies the agno multi-agent LLM team via
``POST /api/run``; each call fans out across ~11 specialist agents.
Per-route ``@limiter.limit(...)`` on the LLM-spend perimeter is the
guard against unbounded spend from a misbehaving client.
"""
from noctusai_seed.rate_limit import create_product_limiter
from app.config import settings

limiter = create_product_limiter(settings)

__all__ = ["limiter"]
