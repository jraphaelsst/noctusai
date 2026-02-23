"""
Redis caching layer for the ERP API.

Provides optional caching with graceful degradation when Redis is unavailable.
"""
import json
import logging
from typing import Any, Optional, TypeVar, Callable
from functools import wraps

from app.config import settings

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Redis client singleton
_redis_client = None
_redis_available = False


def _get_redis_client():
    """Get or create Redis client singleton."""
    global _redis_client, _redis_available

    if _redis_client is not None:
        return _redis_client if _redis_available else None

    if not settings.redis_url:
        _redis_available = False
        return None

    try:
        import redis
        _redis_client = redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        # Test connection
        _redis_client.ping()
        _redis_available = True
        logger.info("Redis connection established")
        return _redis_client
    except ImportError:
        logger.warning("Redis library not installed. Caching disabled.")
        _redis_available = False
        return None
    except Exception as e:
        logger.warning(f"Redis connection failed: {e}. Caching disabled.")
        _redis_available = False
        return None


class CacheService:
    """
    Redis cache service with graceful degradation.

    All operations return None/False if Redis is unavailable,
    allowing the application to continue without caching.
    """

    DEFAULT_TTL = 300  # 5 minutes

    def __init__(self):
        self._client = _get_redis_client()

    @property
    def available(self) -> bool:
        """Check if caching is available."""
        return self._client is not None

    def get(self, key: str) -> Optional[str]:
        """
        Get a value from cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found/unavailable
        """
        if not self._client:
            return None

        try:
            return self._client.get(key)
        except Exception as e:
            logger.warning(f"Cache get error: {e}")
            return None

    def get_json(self, key: str) -> Optional[Any]:
        """
        Get a JSON value from cache.

        Args:
            key: Cache key

        Returns:
            Parsed JSON value or None if not found/unavailable
        """
        value = self.get(key)
        if value is None:
            return None

        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None

    def set(self, key: str, value: str, ttl: int = DEFAULT_TTL) -> bool:
        """
        Set a value in cache.

        Args:
            key: Cache key
            value: Value to cache
            ttl: Time-to-live in seconds

        Returns:
            True if cached successfully, False otherwise
        """
        if not self._client:
            return False

        try:
            self._client.setex(key, ttl, value)
            return True
        except Exception as e:
            logger.warning(f"Cache set error: {e}")
            return False

    def set_json(self, key: str, value: Any, ttl: int = DEFAULT_TTL) -> bool:
        """
        Set a JSON value in cache.

        Args:
            key: Cache key
            value: Value to serialize and cache
            ttl: Time-to-live in seconds

        Returns:
            True if cached successfully, False otherwise
        """
        try:
            json_value = json.dumps(value, default=str)
            return self.set(key, json_value, ttl)
        except (TypeError, ValueError) as e:
            logger.warning(f"Cache JSON serialization error: {e}")
            return False

    def delete(self, key: str) -> bool:
        """
        Delete a key from cache.

        Args:
            key: Cache key

        Returns:
            True if deleted, False otherwise
        """
        if not self._client:
            return False

        try:
            self._client.delete(key)
            return True
        except Exception as e:
            logger.warning(f"Cache delete error: {e}")
            return False

    def invalidate_pattern(self, pattern: str) -> int:
        """
        Delete all keys matching a pattern.

        Args:
            pattern: Pattern to match (e.g., "clientes:*")

        Returns:
            Number of keys deleted
        """
        if not self._client:
            return 0

        try:
            keys = self._client.keys(pattern)
            if keys:
                return self._client.delete(*keys)
            return 0
        except Exception as e:
            logger.warning(f"Cache invalidate error: {e}")
            return 0


# Global cache instance
cache = CacheService()


def cached(key_prefix: str, ttl: int = CacheService.DEFAULT_TTL):
    """
    Decorator for caching function results.

    Usage:
    ```python
    @cached("condominios:list", ttl=600)
    async def list_condominios():
        # expensive operation
        return data
    ```
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            # Build cache key from prefix and arguments
            key_parts = [key_prefix]
            if args:
                key_parts.extend(str(a) for a in args)
            if kwargs:
                key_parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
            cache_key = ":".join(key_parts)

            # Try to get from cache
            cached_value = cache.get_json(cache_key)
            if cached_value is not None:
                logger.debug(f"Cache hit: {cache_key}")
                return cached_value

            # Execute function and cache result
            result = await func(*args, **kwargs)
            cache.set_json(cache_key, result, ttl)
            logger.debug(f"Cache miss, stored: {cache_key}")

            return result
        return wrapper
    return decorator
