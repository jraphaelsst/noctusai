"""
Shared rate limiter instance.

Extracted to avoid circular imports between main.py and routers.
"""
from noctusai_seed.rate_limit import create_product_limiter
from app.config import settings

limiter = create_product_limiter(settings)
