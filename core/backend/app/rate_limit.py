"""
Shared rate limiter instance.

Extracted to avoid circular imports between main.py and routers.
"""
from noctusai_lib.rate_limit import create_limiter
from app.config import settings

limiter = create_limiter(redis_url=settings.redis_url)
