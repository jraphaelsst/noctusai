"""Rate limiter for Social Wiring — delegates to framework."""
from noctusai_seed.rate_limit import create_product_limiter
from app.config import settings

limiter = create_product_limiter(settings)
