import logging
from redis import asyncio as aioredis
from fastapi_cache import FastAPICache
from fastapi_cache.backends.redis import RedisBackend
from fastapi_limiter import FastAPILimiter

from src.config.settings import settings

logger = logging.getLogger(__name__)

# Cache status
redis_initialized = False

async def init_redis():
    """Initialize Redis connection and setup caching/rate limiting"""
    global redis_initialized
    
    redis_host = settings.REDIS.HOST
    redis_password = settings.REDIS.PASSWORD
    redis_ssl = settings.REDIS.SSL
    redis_port = settings.REDIS.PORT
    
    # Construct Redis URL with proper SSL handling
    redis_scheme = "rediss" if redis_ssl else "redis"
    redis_url = f"{redis_scheme}://{redis_host}:{redis_port}"
    
    # Configure connection pool
    try:
        redis = aioredis.from_url(
            redis_url,
            password=redis_password,
            encoding="utf8",
            decode_responses=True,
            max_connections=10,  # Configure pool size based on container resources
            retry_on_timeout=True,
            socket_connect_timeout=10.0,  # Add timeout to prevent hanging
            socket_keepalive=True  # Keep connection alive
        )
        await redis.ping()  # Test connection
        logger.info("Successfully connected to Redis cache")
        
        # Initialize FastAPI Cache
        FastAPICache.init(
            backend=RedisBackend(redis),
            prefix="starmap-cache"
        )
        logger.info("FastAPI Cache initialized")
        
        # Initialize rate limiter if not in test environment
        if settings.ENVIRONMENT != "test":
            await FastAPILimiter.init(redis)
            logger.info("Rate limiter initialized")
        
        redis_initialized = True
        return redis
    except Exception as e:
        logger.warning(f"Failed to connect to Redis: {str(e)}")
        logger.warning("Application will function without caching and rate limiting")
        redis_initialized = False
        return None

def is_cache_initialized():
    """Check if the cache is properly initialized"""
    try:
        return FastAPICache._backend is not None
    except Exception:
        return False
