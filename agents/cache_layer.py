"""
Query caching layer using Redis.
Caches frequently asked questions and agent outputs for 5-10 minute TTL.
"""
import json
import hashlib
import logging
from typing import Optional, Any
from datetime import datetime, timedelta
import redis
from config import settings

logger = logging.getLogger(__name__)

# Redis connection pool (singleton)
_redis_client: Optional[redis.Redis] = None


def get_redis_client() -> Optional[redis.Redis]:
    """Get or create Redis client."""
    global _redis_client
    if _redis_client is not None:
        return _redis_client

    try:
        _redis_client = redis.Redis(
            host=getattr(settings, "redis_host", "localhost"),
            port=getattr(settings, "redis_port", 6379),
            db=0,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_keepalive=True,
            health_check_interval=30,
        )
        # Test connection
        _redis_client.ping()
        logger.info("✅ Redis cache layer connected")
        return _redis_client
    except Exception as e:
        logger.warning(f"Redis connection failed: {e} - Caching disabled")
        return None


def _hash_query(student_id: str, message: str, agent: str = "") -> str:
    """Generate cache key from student_id, message, and optional agent."""
    key_parts = f"{student_id}:{agent}:{message.lower().strip()}"
    return f"cache:{hashlib.md5(key_parts.encode()).hexdigest()}"


async def get_cached_response(
    student_id: str,
    message: str,
    agent: str = ""
) -> Optional[dict]:
    """
    Retrieve cached response if exists and not expired.

    Args:
        student_id: Student's college ID
        message: Chat message
        agent: Optional agent name for granular caching

    Returns:
        Cached response dict or None
    """
    redis_client = get_redis_client()
    if not redis_client:
        return None

    try:
        cache_key = _hash_query(student_id, message, agent)
        cached = redis_client.get(cache_key)

        if cached:
            data = json.loads(cached)
            logger.info(f"✅ Cache hit for {student_id} | TTL: {data.get('ttl_remaining', 'unknown')}")
            return data

        return None
    except Exception as e:
        logger.warning(f"Cache retrieval error: {e}")
        return None


async def cache_response(
    student_id: str,
    message: str,
    response_data: dict,
    agent: str = "",
    ttl_minutes: int = 5
) -> bool:
    """
    Cache a response with TTL.

    Args:
        student_id: Student's college ID
        message: Chat message
        response_data: Response to cache
        agent: Optional agent name
        ttl_minutes: Time-to-live in minutes (default 5)

    Returns:
        True if cached successfully, False otherwise
    """
    redis_client = get_redis_client()
    if not redis_client:
        return False

    try:
        cache_key = _hash_query(student_id, message, agent)

        # Add metadata to cached data
        cached_data = {
            **response_data,
            "cached_at": datetime.now().isoformat(),
            "ttl_remaining": ttl_minutes * 60,
        }

        redis_client.setex(
            cache_key,
            timedelta(minutes=ttl_minutes),
            json.dumps(cached_data)
        )

        logger.info(f"✅ Cached response for {student_id} | TTL: {ttl_minutes} min")
        return True
    except Exception as e:
        logger.warning(f"Cache storage error: {e}")
        return False


async def invalidate_cache(student_id: str, message: str = "", agent: str = "") -> bool:
    """
    Invalidate cache entry or all entries for a student.

    Args:
        student_id: Student's college ID
        message: Specific message to invalidate (optional - invalidates all if empty)
        agent: Optional agent name

    Returns:
        True if invalidated successfully
    """
    redis_client = get_redis_client()
    if not redis_client:
        return False

    try:
        if message:
            # Invalidate specific cache entry
            cache_key = _hash_query(student_id, message, agent)
            redis_client.delete(cache_key)
            logger.info(f"✅ Invalidated cache for {student_id}")
        else:
            # Invalidate all cache entries for student
            pattern = f"cache:*{student_id}*"
            keys = redis_client.keys(pattern)
            if keys:
                redis_client.delete(*keys)
            logger.info(f"✅ Invalidated all cache for {student_id}")

        return True
    except Exception as e:
        logger.warning(f"Cache invalidation error: {e}")
        return False


async def get_cache_stats() -> dict:
    """Get caching statistics."""
    redis_client = get_redis_client()
    if not redis_client:
        return {"status": "disabled"}

    try:
        info = redis_client.info()
        keys = redis_client.keys("cache:*")

        return {
            "status": "connected",
            "total_cache_keys": len(keys),
            "memory_used": info.get("used_memory_human", "unknown"),
            "hit_rate": info.get("keyspace_hits", 0) / max(info.get("keyspace_hits", 0) + info.get("keyspace_misses", 1), 1),
        }
    except Exception as e:
        logger.warning(f"Cache stats error: {e}")
        return {"status": "error", "error": str(e)}


async def clear_all_cache() -> bool:
    """Clear all cache entries (admin only)."""
    redis_client = get_redis_client()
    if not redis_client:
        return False

    try:
        keys = redis_client.keys("cache:*")
        if keys:
            redis_client.delete(*keys)
        logger.info(f"🧹 Cleared {len(keys)} cache entries")
        return True
    except Exception as e:
        logger.warning(f"Cache clear error: {e}")
        return False
