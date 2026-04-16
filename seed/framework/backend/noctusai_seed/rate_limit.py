"""
Rate limiter factory for the seed framework.

Products can create a limiter by just importing from the framework::

    from noctusai_seed.rate_limit import create_product_limiter
    limiter = create_product_limiter(settings)

Or use the lib's create_limiter directly if they need more control.
"""
from noctusai_shared.rate_limit import create_limiter


def create_product_limiter(settings):
    """Create a rate limiter using the product's settings.

    Uses Redis if available (settings.redis_url), otherwise in-memory.
    """
    redis_url = getattr(settings, "redis_url", None)
    return create_limiter(redis_url=redis_url)
