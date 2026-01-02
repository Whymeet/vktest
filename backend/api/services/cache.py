"""
Redis caching service for VK Ads Manager
Per-user cache isolation with pattern-based invalidation
"""
import os
import json
import hashlib
from typing import Optional, Any, Callable, List
from functools import wraps

import redis
from loguru import logger

# Redis connection
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Singleton Redis client
_redis_client: Optional[redis.Redis] = None


def get_redis() -> redis.Redis:
    """Get or create Redis connection"""
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(
            REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True,
        )
    return _redis_client


def is_redis_available() -> bool:
    """Check if Redis is available"""
    try:
        client = get_redis()
        client.ping()
        return True
    except (redis.ConnectionError, redis.TimeoutError):
        return False


class CacheKey:
    """Cache key builder with user isolation"""
    PREFIX = "vkads"

    @staticmethod
    def build(user_id: int, endpoint: str, params: Optional[dict] = None) -> str:
        """
        Build cache key: vkads:cache:{user_id}:{endpoint}:{params_hash}

        Example: vkads:cache:1:disable-rules:abc123
        """
        key_parts = [CacheKey.PREFIX, "cache", str(user_id), endpoint]

        if params:
            # Sort params for consistent hashing
            sorted_params = json.dumps(params, sort_keys=True)
            params_hash = hashlib.md5(sorted_params.encode()).hexdigest()[:8]
            key_parts.append(params_hash)

        return ":".join(key_parts)

    @staticmethod
    def pattern(user_id: int, endpoint: Optional[str] = None) -> str:
        """
        Build pattern for cache invalidation

        Examples:
        - vkads:cache:1:* (all user cache)
        - vkads:cache:1:disable-rules:* (specific endpoint)
        """
        if endpoint:
            return f"{CacheKey.PREFIX}:cache:{user_id}:{endpoint}:*"
        return f"{CacheKey.PREFIX}:cache:{user_id}:*"


class CacheTTL:
    """Cache TTL values for different endpoints (in seconds)"""

    # High priority - rarely change
    DISABLE_RULES = 300           # 5 min
    DISABLE_RULES_METRICS = 1800  # 30 min (static data)
    SCALING_CONFIGS = 300         # 5 min
    WHITELIST = 300               # 5 min
    ACCOUNTS = 300                # 5 min
    SETTINGS = 600                # 10 min
    LEADSTECH_CABINETS = 600      # 10 min
    LEADSTECH_CONFIG = 600        # 10 min
    LEADSTECH_RESULTS = 600       # 10 min (profitable ads page)
    LEADSTECH_ANALYSIS_CABINETS = 600  # 10 min

    # Medium priority
    DASHBOARD = 30                # 30 sec
    CONTROL_STATUS = 10           # 10 sec
    SCALING_LOGS = 60             # 1 min
    BANNER_HISTORY = 60           # 1 min


# Endpoints that should NEVER be cached
NO_CACHE_ENDPOINTS = {
    "banners-disabled",
    "banners-disabled-accounts",
    "stats",
    "scaling-tasks",
    "scaling-active-tasks",
    "leadstech-analysis-status",  # Status должен быть всегда свежим
}


def should_cache(endpoint: str) -> bool:
    """Check if endpoint should be cached"""
    return endpoint not in NO_CACHE_ENDPOINTS


async def get_cached(user_id: int, endpoint: str, params: Optional[dict] = None) -> Optional[Any]:
    """
    Get cached value for user endpoint

    Returns None if not cached or Redis unavailable
    """
    if not should_cache(endpoint):
        return None

    try:
        client = get_redis()
        key = CacheKey.build(user_id, endpoint, params)
        cached = client.get(key)

        if cached:
            logger.debug(f"Cache hit: {key}")
            return json.loads(cached)
        logger.debug(f"Cache miss: {key}")
        return None
    except (redis.ConnectionError, redis.TimeoutError, json.JSONDecodeError) as e:
        logger.warning(f"Cache get error: {e}")
        return None


async def set_cached(
    user_id: int,
    endpoint: str,
    data: Any,
    ttl: int,
    params: Optional[dict] = None
) -> bool:
    """
    Set cached value for user endpoint

    Returns True if cached successfully
    """
    if not should_cache(endpoint):
        return False

    try:
        client = get_redis()
        key = CacheKey.build(user_id, endpoint, params)
        serialized = json.dumps(data, default=str)
        client.setex(key, ttl, serialized)
        logger.debug(f"Cache set: {key} (TTL: {ttl}s)")
        return True
    except (redis.ConnectionError, redis.TimeoutError, TypeError) as e:
        logger.warning(f"Cache set error: {e}")
        return False


async def invalidate_cache(user_id: int, endpoint: Optional[str] = None) -> int:
    """
    Invalidate cache for user

    Args:
        user_id: User ID
        endpoint: Optional endpoint name (e.g., "disable-rules")
                  If None, invalidates ALL user cache

    Returns number of keys deleted
    """
    try:
        client = get_redis()
        key_pattern = CacheKey.pattern(user_id, endpoint)

        # Use SCAN for large keysets (safer than KEYS)
        deleted = 0
        cursor = 0
        while True:
            cursor, keys = client.scan(cursor, match=key_pattern, count=100)
            if keys:
                deleted += client.delete(*keys)
            if cursor == 0:
                break

        if deleted > 0:
            logger.debug(f"Cache invalidated: {key_pattern} ({deleted} keys)")
        return deleted
    except (redis.ConnectionError, redis.TimeoutError) as e:
        logger.warning(f"Cache invalidation error: {e}")
        return 0


async def invalidate_related_cache(user_id: int, endpoints: List[str]) -> int:
    """
    Invalidate cache for multiple related endpoints

    Used after CRUD operations that affect multiple views
    """
    deleted = 0
    for endpoint in endpoints:
        deleted += await invalidate_cache(user_id, endpoint)
    return deleted


def cached(ttl: int, endpoint_name: str):
    """
    Decorator for caching FastAPI endpoint responses

    Usage:
        @router.get("/configs")
        @cached(ttl=CacheTTL.SCALING_CONFIGS, endpoint_name="scaling-configs")
        async def get_configs(current_user: User = Depends(get_current_user)):
            ...

    The decorator:
    1. Checks cache first
    2. If miss, calls endpoint and caches result
    3. Gracefully falls back to uncached if Redis unavailable
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract user from kwargs (set by Depends(get_current_user))
            current_user = kwargs.get("current_user")
            if not current_user:
                # No user context, skip caching
                return await func(*args, **kwargs)

            user_id = current_user.id

            # Build params from relevant kwargs (exclude db, current_user)
            cache_params = {
                k: v for k, v in kwargs.items()
                if k not in ("db", "current_user", "background_tasks") and v is not None
            }

            # Try cache first
            cached_data = await get_cached(user_id, endpoint_name, cache_params or None)
            if cached_data is not None:
                return cached_data

            # Cache miss - call actual endpoint
            result = await func(*args, **kwargs)

            # Cache the result (convert pydantic models to dict if needed)
            cache_data = result
            if hasattr(result, "model_dump"):
                cache_data = result.model_dump()
            elif hasattr(result, "dict"):
                cache_data = result.dict()

            await set_cached(user_id, endpoint_name, cache_data, ttl, cache_params or None)

            return result

        return wrapper
    return decorator


class CacheInvalidation:
    """
    Helper class for invalidating related caches after CRUD operations
    """

    # Mapping of entity types to affected endpoints
    INVALIDATION_MAP = {
        "disable_rule": ["disable-rules"],
        "scaling_config": ["scaling-configs"],
        "whitelist": ["whitelist"],
        "account": ["accounts", "dashboard"],
        "settings": ["settings", "dashboard"],
        "leadstech_config": ["leadstech-config", "leadstech-cabinets"],
        "leadstech_cabinet": ["leadstech-cabinets"],
        "leadstech_results": ["leadstech-results", "leadstech-analysis-cabinets"],
    }

    @classmethod
    async def after_create(cls, user_id: int, entity_type: str) -> int:
        """Invalidate cache after creating entity"""
        endpoints = cls.INVALIDATION_MAP.get(entity_type, [])
        return await invalidate_related_cache(user_id, endpoints)

    @classmethod
    async def after_update(cls, user_id: int, entity_type: str) -> int:
        """Invalidate cache after updating entity"""
        endpoints = cls.INVALIDATION_MAP.get(entity_type, [])
        return await invalidate_related_cache(user_id, endpoints)

    @classmethod
    async def after_delete(cls, user_id: int, entity_type: str) -> int:
        """Invalidate cache after deleting entity"""
        endpoints = cls.INVALIDATION_MAP.get(entity_type, [])
        return await invalidate_related_cache(user_id, endpoints)

    @classmethod
    async def clear_all(cls, user_id: int) -> int:
        """Clear all cache for user"""
        return await invalidate_cache(user_id)
