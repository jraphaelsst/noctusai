"""
NoctusAI Seed Product — Reference Implementation

The simplest possible product. Just the spine, no domain code.
Proves that the seed framework works end-to-end.

Run with: uvicorn app.main:app --reload --port 8004
"""
from noctusai_seed import create_product_app
from app.config import settings
from app.rate_limit import limiter

app = create_product_app(
    name="Seed Product",
    schema="seed",
    settings=settings,
    version="0.1.0",
    limiter=limiter,
)
