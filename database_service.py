import redis
import json
import time
import asyncio
import uuid
import os
import math
import logging

from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi_cache import FastAPICache
from fastapi_cache.backends.redis import RedisBackend
from fastapi_cache.decorator import cache
from fastapi.openapi.docs import get_swagger_ui_html
from redis import asyncio as aioredis
from pydantic import BaseModel, validator
from azure.data.tables import TableServiceClient
from azure.core.exceptions import ResourceExistsError, ResourceNotFoundError
from azure.core.pipeline.policies import RetryPolicy, RetryMode
try:
    from opencensus.ext.azure import metrics_exporter
    from opencensus.stats import stats as stats_module
    AZURE_MONITORING = True
except ImportError:
    AZURE_MONITORING = False
    print("Azure monitoring disabled - opencensus not installed")
from sqlalchemy import create_engine, Column, Integer, Float, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import NoResultFound
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from dotenv import load_dotenv
from datetime import datetime, UTC
from typing import Optional
from fastapi.responses import JSONResponse
from fastapi_limiter import FastAPILimiter
from fastapi_limiter.depends import RateLimiter
from fastapi.openapi.utils import get_openapi

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Comment out legacy SQLite + SQLAlchemy code for local development

##############################################################################
# 2) Azure Table Storage Setup with Connection Pooling & Retry Logic
##############################################################################

# Configure retry policy for resilience
retry_policy = RetryPolicy(
    retry_mode=RetryMode.Exponential,
    backoff_factor=2,
    backoff_max=60,
    total_retries=5
)

# Use managed identity if available, otherwise connection string
connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
managed_identity_enabled = os.getenv("USE_MANAGED_IDENTITY", "false").lower() == "true"

if managed_identity_enabled:
    from azure.identity import DefaultAzureCredential
    credential = DefaultAzureCredential()
    account_url = os.getenv("AZURE_STORAGE_ACCOUNT_URL")
    table_service_client = TableServiceClient(
        endpoint=account_url,
        credential=credential,
        retry_policy=retry_policy
    )
    logger.info("Using managed identity for Azure Table Storage authentication")
else:
    table_service_client = TableServiceClient.from_connection_string(
        connection_string,
        retry_policy=retry_policy
    )
    logger.info("Using connection string for Azure Table Storage authentication")

# Initialise tables with retry logic
tables = {}
for table_name in ["Users", "Stars", "UserStars"]:
    max_attempts = 3
    for attempt in range(max_attempts):
        try:
            table_service_client.create_table_if_not_exists(table_name)
            tables[table_name] = table_service_client.get_table_client(table_name)
            logger.info(f"Successfully initialized table: {table_name}")
            break
        except Exception as e:
            if attempt == max_attempts - 1:
                logger.error(f"Failed to initialize table {table_name} after {max_attempts} attempts: {str(e)}")
                raise
            logger.warning(f"Failed to initialize table {table_name}, attempt {attempt+1}/{max_attempts}: {str(e)}")
            time.sleep(2 ** attempt)  # Exponential backoff

##############################################################################
# 3) Pydantic Models
##############################################################################

class Star(BaseModel):
    id: Optional[str] = None
    x: float
    y: float
    message: str
    brightness: Optional[float] = 100.0
    last_liked: Optional[float] = None

    @validator('x', 'y')
    def validate_coordinates(cls, v):
        if not -1 <= v <= 1:
            raise ValueError('Coordinates must be between -1 and 1')
        return v

    @validator('message')
    def validate_message(cls, v):
        if len(v) > 280:  # Twitter-style limit
            raise ValueError('Message too long')
        return v

class User(BaseModel):
    id: Optional[str] = None
    name: str
    email: str
    created_at: Optional[datetime] = None

##############################################################################
# 4) SSE Event Queue
##############################################################################

star_event_queue = asyncio.Queue()
user_event_queue = asyncio.Queue()

##############################################################################
# 5) FastAPI App with Azure Table Storage
##############################################################################

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Update this for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/users")
async def create_user(user: User):
    user_id = str(uuid.uuid4())
    user_entity = {
        "PartitionKey": "USER",
        "RowKey": user_id,
        "Username": user.name,
        "Email": user.email,
        "CreatedAt": datetime.now(UTC).isoformat()
    }
    tables["Users"].create_entity(user_entity)
    return {"user_id": user_id, **user.dict()}

@app.post("/stars")
async def add_star(star: Star):
    current_time = datetime.now(UTC).timestamp()
    star_entity = {
        "PartitionKey": f"STAR_{datetime.now(UTC).strftime('%Y%m')}",
        "RowKey": str(uuid.uuid4()),
        "X": star.x,
        "Y": star.y,
        "Message": star.message,
        "Brightness": 100.0, # Default brightness
        "LastLiked": current_time,
        "CreatedAt": current_time
    }
    tables["Stars"].create_entity(star_entity)

    # Push SSE event 
    await star_event_queue.put({
        "event": "add",
        "star": {
            "id": star_entity["RowKey"],
            "x": star.x,
            "y": star.y,
            "message": star.message,
            "brightness": star.brightness,
            "last_liked": current_time
        }
    })
    return star_entity

##############################################################################
# 6) Redis Cache Configuration with Connection Pooling
##############################################################################

CACHE_TTL_SECONDS = 300 # Regular cache TTL
POPULAR_CACHE_TTL_SECONDS = 3600 # Longer TTL for popular items
POPULARITY_THRESHOLD = 50 # Minimum likes to be considered "popular"
POPULARITY_WINDOW_SECONDS = 3600 # Time window for popularity calculation

@app.on_event("startup")
async def startup():
    redis_host = os.getenv("REDIS_HOST")
    redis_password = os.getenv("REDIS_PASSWORD")
    redis_ssl = os.getenv("REDIS_SSL", "false").lower() == "true"
    redis_port = int(os.getenv("REDIS_PORT", "6379"))
    
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
        
        FastAPICache.init(
            backend=RedisBackend(redis),
            prefix="starmap-cache"
        )
        
        # Initialize rate limiter
        await FastAPILimiter.init(redis)
        logger.info("Rate limiter initialized")
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {str(e)}")
        # Continue without Redis - the app will function without caching
        logger.warning("Application continuing without Redis cache")

##############################################################################
# 7) CRUD + SSE Endpoints
##############################################################################

@app.get("/stars")
async def get_stars():
    """Return all stars with their current brightness."""
    stars = tables["Stars"].query_entities(query_filter="PartitionKey eq 'STAR'")
    current_time = datetime.now(UTC).timestamp()
    
    return [{
        "id": star["RowKey"],
        "x": star["X"],
        "y": star["Y"],
        "message": star["Message"],
        "brightness": calculate_current_brightness(star["Brightness"], star["LastLiked"]),
        "last_liked": star["LastLiked"]
    } for star in stars]

@app.get("/stars/{star_id}")
@cache(expire=CACHE_TTL_SECONDS)
async def get_star(star_id: str):
    """Get a specific star with automatic caching."""
    try:
        # Check if it's in Redis first
        redis = FastAPICache.get_backend().client
        popularity_key = f"star_popularity:{star_id}"
        recent_likes = await redis.get(popularity_key)
        
        star = tables["Stars"].get_entity(partition_key="STAR", row_key=star_id)
        current_brightness = calculate_current_brightness(
            star["Brightness"],
            star["LastLiked"]
        )
        
        response = {
            "id": star["RowKey"],
            "x": star["X"],
            "y": star["Y"],
            "message": star["Message"],
            "brightness": current_brightness,
            "last_liked": star["LastLiked"],
            "is_popular": recent_likes is not None and int(recent_likes) >= POPULARITY_THRESHOLD
        }

        # If star is popular, update cache with longer TTL
        if response["is_popular"]:
            await FastAPICache.get_backend().set(
                f"star:{star_id}",
                json.dumps(response),
                expire=POPULAR_CACHE_TTL_SECONDS
            )
            
        return response
    except:
        raise HTTPException(status_code=404, detail="Star not found")

@app.post("/stars/{star_id}/like")
# Comment out for testing: async def like_star(star_id: str, _=Depends(RateLimiter(times=5, seconds=60))):
async def like_star(star_id: str):
    """Like a star and update popularity metrics."""
    try:
        star = tables["Stars"].get_entity(partition_key="STAR", row_key=star_id)
        current_time = datetime.now(UTC).timestamp()
        
        # Update the star's brightness and last_liked time
        star["Brightness"] = min(100.0, star["Brightness"] + 20.0)
        star["LastLiked"] = current_time
        
        # Update popularity counter in Redis
        redis = FastAPICache.get_backend().client
        popularity_key = f"star_popularity:{star_id}"
        
        # Increment likes counter with expiry
        await redis.incr(popularity_key)
        await redis.expire(popularity_key, POPULARITY_WINDOW_SECONDS)
        
        # Invalidate the star's cache to force refresh
        await FastAPICache.get_backend().delete(f"star:{star_id}")

        tables["Stars"].update_entity(star)
        
        # Push SSE event
        await star_event_queue.put({
            "event": "update",
            "star": {
                "id": star_id,
                "brightness": star["Brightness"],
                "last_liked": current_time
            }
        })
        
        return star
    except:
        raise HTTPException(status_code=404, detail="Star not found")

def calculate_current_brightness(base_brightness: float, last_liked: float) -> float:
    time_since_liked = datetime.now(UTC).timestamp() - last_liked
    decay_factor = max(0.01, 1.0 - 0.01 * time_since_liked)
    return max(20.0, base_brightness * math.exp(-decay_factor * time_since_liked))

@app.get("/stars/popular")
@cache(expire=30)
async def get_popular_stars():
    """Get currently popular stars."""
    redis = FastAPICache.get_backend().client
    
    # Get all popularity counters
    keys = await redis.keys("star_popularity:*")
    popular_stars = []
    
    for key in keys:
        star_id = key.split(":")[1]
        likes = int(await redis.get(key) or 0)
        
        if likes >= POPULARITY_THRESHOLD:
            try:
                star = await get_star(star_id)
                popular_stars.append(star)
            except HTTPException:
                continue
            
    return sorted(popular_stars, key=lambda x: x["brightness"], reverse=True)

@app.get("/stars/batch/{star_ids}")
async def get_stars_batch(star_ids: str):
    """Get multiple stars in a single request."""
    ids = star_ids.split(",")
    stars = []
    
    for star_id in ids:
        try:
            star = await get_star(star_id.strip())
            stars.append(star)
        except HTTPException:
            continue
    
    return stars

@app.get("/stats/cache")
async def get_cache_stats():
    """Get cache statistics."""
    redis = FastAPICache.get_backend().client
    
    # Get cache stats
    info = await redis.info()
    
    return {
        "hits": info["keyspace_hits"],
        "misses": info["keyspace_misses"],
        "hit_rate": info["keyspace_hits"] / (info["keyspace_hits"] + info["keyspace_misses"]),
        "popular_stars": len([k for k in await redis.keys("star_popularity:*")]),
        "memory_used": info["used_memory_human"]
    }

@app.delete("/stars/{star_id}")
async def remove_star(star_id: str):
    "Remove a star by ID and push an SSE event"
    try:
        star = tables["Stars"].get_entity(partition_key="STAR", row_key=star_id)
        tables["Stars"].delete_entity(partition_key="STAR", row_key=star_id)

        # Push SSE event
        await star_event_queue.put({
            "event": "remove",
            "star": {
                "id": star_id,
                "x": star["X"],
                "y": star["Y"],
                "message": star["Message"]
            }
        })

        return {"message": f"Star {star_id} successfully removed"}
    except ResourceNotFoundError:
        raise HTTPException(status_code=404, detail=f"Star with ID {star_id} not found")
    
@app.delete("/stars")
async def remove_all_stars():
    "Remove all stars and push an SSE event (NB!!! Dangerous! Only for admins)"
    # TODO: Add admin authentication
    stars = tables["Stars"].query_entities(query_filter="PartitionKey eq 'STAR'")
    for star in tables["Stars"].query_entities(query_filter="PartitionKey eq 'STAR'"):
        tables["Stars"].delete_entity(partition_key="STAR", row_key=star["RowKey"])

    # Push SSE event
    await star_event_queue.put({
        "event": "remove_all"        
    })

    return {"message": "All stars removed"}

@app.get("/stars/stream")
async def stream_stars(request: Request):
    """
    SSE endpoint that emits star add/remove events.
    If no event occurs within 15 seconds, send a keep-alive comment.
    """
    async def event_generator():
        while True:
            if await request.is_disconnected():
                break
            try:
                event = await asyncio.wait_for(star_event_queue.get(), timeout=15.0)
                yield f"data: {event}\n\n"
            except asyncio.TimeoutError:
                yield ": keep-alive\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.get("/stars/active")
@cache(expire=300)
async def get_active_stars():
    """Get all stars that have been liked recently."""
    current_time = datetime.now(UTC).timestamp()
    cutoff_time = current_time - POPULARITY_WINDOW_SECONDS  # Only include stars liked in the last hour

    # Query Azure Table Storage for stars
    query_filter = f"LastLiked ge {cutoff_time}"
    stars = tables["Stars"].query_entities(query_filter=query_filter)

    return [
        {
            "id": star["RowKey"],
            "x": star["X"],
            "y": star["Y"],
            "message": star["Message"],
            "brightness": calculate_current_brightness(star["Brightness"], star["LastLiked"]),
            "last_liked": star["LastLiked"]
        }
        for star in stars
    ]

##############################################################################
# 8) Azure Monitor Metrics
##############################################################################

if AZURE_MONITORING:
    exporter = metrics_exporter.new_metrics_exporter()
    stats_recorder = stats_module.StatsRecorder()
else:
    exporter = None
    stats_recorder = None

# Add performance monitoring
@app.middleware("http")
async def add_monitoring(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time
    
    # Log request duration (without opencensus)
    print(f"Request to {request.url.path} took {duration:.2f} seconds")
    return response

# Add health checks
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "version": "1.1",
        "timestamp": datetime.now(UTC).timestamp()
    }

##############################################################################
# 9) Error Handling
##############################################################################

@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )

@app.middleware("http")
async def add_error_handling(request: Request, call_next):
    try:
        response = await call_next(request)
        return response
    except Exception as e:
        logger.error(f"Error processing request: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"}
        )
    

##############################################################################
# 10) Logging
##############################################################################

@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info(f"Request: {request.method} {request.url}")
    response = await call_next(request)
    logger.info(f"Response: {response.status_code}")
    return response


##############################################################################
# 11) Container Readiness and Health Probes
##############################################################################

@app.get("/health/readiness")
async def readiness_check():
    """
    Readiness probe for container orchestrators.
    Verifies database connections are operational.
    """
    health_status = {"status": "ready", "services": {}}
    
    # Check Azure Table Storage
    try:
        # Test Azure Table Storage connection
        tables["Users"].list_entities(select="RowKey", top=1)
        health_status["services"]["azure_tables"] = "healthy"
    except Exception as e:
        logger.warning(f"Azure Tables check failed: {str(e)}")
        health_status["status"] = "not_ready"
        health_status["services"]["azure_tables"] = f"unhealthy: {str(e)}"
    
    # Check Redis connection - don't fail readiness if Redis is down
    try:
        if 'FastAPICache' in globals() and FastAPICache._backend is not None:
            redis = FastAPICache.get_backend().client
            await redis.ping()
            health_status["services"]["redis"] = "healthy"
        else:
            health_status["services"]["redis"] = "not configured"
    except Exception as e:
        logger.warning(f"Redis check failed: {str(e)}")
        health_status["services"]["redis"] = f"unhealthy: {str(e)}"
        # Don't fail readiness just because Redis is down - app can function without it
    
    status_code = 200 if health_status["status"] == "ready" else 503
    return JSONResponse(status_code=status_code, content=health_status)

@app.get("/health/liveness")
async def liveness_check():
    """
    Liveness probe for container orchestrators.
    Simple check to verify the application is running.
    """
    return {"status": "alive", "timestamp": datetime.now(UTC).timestamp()}

##############################################################################
# 12) Logging
##############################################################################

@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info(f"Request: {request.method} {request.url}")
    response = await call_next(request)
    logger.info(f"Response: {response.status_code}")
    return response


##############################################################################
# 13) Azure Container App Configuration
##############################################################################

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8080"))
    uvicorn.run(app, host="0.0.0.0", port=port)

##############################################################################
# 14) Documentation
##############################################################################

@app.get("/docs")
async def get_documentation():
    return get_swagger_ui_html(
        openapi_url="/openapi.json",
        title="Astro App Backend API Documentation"
    )

##############################################################################
# 15) OpenAPI
##############################################################################

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title="Star Map API",
        version="1.0.0",
        description="API for managing stars in the star map application",
        routes=app.routes,
    )
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi

##############################################################################
# 16) Settings
##############################################################################

class Settings:
    def __init__(self):
        self.ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
        self.REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
        self.REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
        self.CACHE_TTL = int(os.getenv("CACHE_TTL", 300))

settings = Settings()