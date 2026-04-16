"""
Shared rate limiter instance — seed framework.
"""
from noctusai_seed.rate_limit import create_product_limiter
from app.config import settings

limiter = create_product_limiter(settings)
