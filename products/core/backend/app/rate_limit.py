"""
Shared rate limiter instance — framework-delegated.

Flipped from `noctusai_lib.rate_limit.create_limiter` (lib-level) to
`noctusai_seed.rate_limit.create_product_limiter` (framework-level) by
`projects/core-seed-wiring-v2/` Phase 1 (2026-04-23) — matches every
other product, drops a drift divergence. Functional no-op.
"""
from noctusai_seed.rate_limit import create_product_limiter
from app.config import settings

limiter = create_product_limiter(settings)
