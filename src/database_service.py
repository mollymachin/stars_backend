import redis
import json
import time
import asyncio
import uuid
import os
import math
import logging
import socket

from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi_cache import FastAPICache
from fastapi_cache.backends.redis import RedisBackend
from fastapi_cache.decorator import cache
from fastapi.openapi.docs import get_swagger_ui_html
from redis import asyncio as aioredis
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
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
from datetime import datetime
import datetime as dt
from typing import Optional, List
from fastapi.responses import JSONResponse
from fastapi_limiter import FastAPILimiter
from fastapi_limiter.depends import RateLimiter
from fastapi.openapi.utils import get_openapi

load_dotenv()

##############################################################################
# 1) Settings
##############################################################################

class LoggingSettings(BaseSettings):
    LEVEL: str = Field("INFO", description="Logging level")
    FORMAT: str = Field(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        description="Log format string"
    )
    
    class Config:
        env_prefix = "LOG_"

class AzureStorageSettings(BaseSettings):
    CONNECTION_STRING: Optional[str] = Field(
        None, 
        description="Azure Storage connection string"
    )
    ACCOUNT_URL: Optional[str] = Field(
        None, 
        description="Azure Storage account URL for managed identity"
    )
    USE_MANAGED_IDENTITY: bool = Field(
        False, 
        description="Whether to use Azure Managed Identity"
    )
    
    @field_validator("ACCOUNT_URL")
    def validate_account_url(cls, v, info):
        values = info.data
        if values.get("USE_MANAGED_IDENTITY") and not v:
            raise ValueError("AZURE_STORAGE_ACCOUNT_URL must be provided when USE_MANAGED_IDENTITY is enabled")
        return v
        
    class Config:
        env_prefix = "AZURE_STORAGE_"

class RedisSettings(BaseSettings):
    HOST: str = Field(..., description="Redis host")
    PORT: int = Field(6379, description="Redis port")
    PASSWORD: Optional[str] = Field(None, description="Redis password")
    SSL: bool = Field(False, description="Whether to use SSL for Redis connection")
    CACHE_TTL: int = Field(300, description="Default cache TTL in seconds")
    POPULAR_CACHE_TTL: int = Field(3600, description="Cache TTL for popular items")
    POPULARITY_THRESHOLD: int = Field(50, description="Threshold for considering an item popular")
    POPULARITY_WINDOW: int = Field(3600, description="Time window for popularity calculation in seconds")
    
    class Config:
        env_prefix = "REDIS_"

class APISettings(BaseSettings):
    CORS_ORIGINS: List[str] = Field(
        ["http://localhost:3000"], # Default for development
        description="List of allowed CORS origins"
    )
    RATE_LIMIT_TIMES: int = Field(5, description="Number of requests allowed in the time window")
    RATE_LIMIT_SECONDS: int = Field(60, description="Time window for rate limiting in seconds")
    
    @validator('CORS_ORIGINS')
    def validate_cors_origins(cls, v, values):
        env = os.getenv('ENVIRONMENT', 'development')
        if env == 'production' and '*' in v:
            raise ValueError("Wildcard CORS origin '*' is not allowed in production")
        return v
    
    class Config:
        env_prefix = "API_"

class AppSettings(BaseSettings):
    ENVIRONMENT: str = Field("development", description="Application environment")
    PORT: int = Field(8080, description="Application port")
    DEBUG: bool = Field(False, description="Debug mode")
    PROJECT_NAME: str = Field("Star Map API", description="Project name")
    VERSION: str = Field("1.1.0", description="API version")
    
    # Sub-settings
    AZURE: AzureStorageSettings = Field(default_factory=AzureStorageSettings)
    REDIS: RedisSettings = Field(default_factory=RedisSettings)
    LOGGING: LoggingSettings = Field(default_factory=LoggingSettings)
    API: APISettings = Field(default_factory=APISettings)
    
    # Host information for diagnostics
    HOST_NAME: str = Field(default_factory=socket.gethostname)
    
    @field_validator("ENVIRONMENT")
    def validate_environment(cls, v):
        allowed_environments = ["development", "staging", "production", "test"]
        if v not in allowed_environments:
            raise ValueError(f"Environment must be one of {allowed_environments}")
        return v
        
    model_config = SettingsConfigDict(
        env_file=(".env", f".env.{os.getenv('ENVIRONMENT', 'development').lower()}"),
        env_file_encoding="utf-8",
        case_sensitive=True
    )

# Initialize settings once
settings = AppSettings()

# Configure logging based on settings
logging.basicConfig(
    level=getattr(logging, settings.LOGGING.LEVEL),
    format=settings.LOGGING.FORMAT
)
logger = logging.getLogger(__name__)

# Log important configuration details
logger.info(f"Starting application in {settings.ENVIRONMENT} environment")
logger.info(f"Host: {settings.HOST_NAME}, Port: {settings.PORT}")

# Verify critical settings
def verify_required_settings():
    """Verify that all required settings are present and valid at startup"""
    critical_errors = []
    warnings = []
    
    # Check Azure Storage settings
    if not settings.AZURE.USE_MANAGED_IDENTITY and not settings.AZURE.CONNECTION_STRING:
        critical_errors.append(
            "Either AZURE_STORAGE_CONNECTION_STRING must be provided or AZURE_STORAGE_USE_MANAGED_IDENTITY must be enabled"
        )
        
    # Check Redis settings - warn but don't fail if Redis is not configured
    if not settings.REDIS.HOST:
        warnings.append("REDIS_HOST not configured. Caching and rate limiting will be disabled.")
        
    # Check API settings
    if settings.ENVIRONMENT == "production" and "*" in settings.API.CORS_ORIGINS:
        warnings.append("CORS is configured to allow all origins (*) in production environment")
            
    # Log warnings
    for warning in warnings:
        logger.warning(f"Configuration warning: {warning}")
        
    # Exit on critical errors
    if critical_errors:
        for error in critical_errors:
            logger.error(f"Configuration error: {error}")
        logger.error("Application startup failed due to configuration errors")
        import sys
        sys.exit(1)
        
# Run verification
verify_required_settings()

# Make the configuration values available throughout the application
# Replace all direct os.getenv() calls with settings

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
connection_string = settings.AZURE.CONNECTION_STRING
managed_identity_enabled = settings.AZURE.USE_MANAGED_IDENTITY

if managed_identity_enabled:
    from azure.identity import DefaultAzureCredential
    credential = DefaultAzureCredential()
    account_url = settings.AZURE.ACCOUNT_URL
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

    @field_validator('x', 'y')
    def validate_coordinates(cls, v):
        if not -1 <= v <= 1:
            raise ValueError('Coordinates must be between -1 and 1')
        return v

    @field_validator('message')
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
    allow_origins=settings.API.CORS_ORIGINS,
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
        "CreatedAt": datetime.now(dt.timezone.utc).isoformat()
    }
    tables["Users"].create_entity(user_entity)
    return {"user_id": user_id, **user.dict()}

@app.post("/stars")
async def add_star(star: Star):
    current_time = datetime.now(dt.timezone.utc).timestamp()
    star_entity = {
        "PartitionKey": f"STAR_{datetime.now(dt.timezone.utc).strftime('%Y%m')}",
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

@app.on_event("startup")
async def startup():
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
    # Query for all stars with PartitionKey that starts with STAR_
    stars = []
    
    # Log to help debug
    logger.info("Fetching stars from Azure Table Storage")
    
    # Try direct query with no filter first to see what's actually in the table
    all_stars = list(tables["Stars"].list_entities())
    logger.info(f"Found {len(all_stars)} total entities in the Stars table")
    
    for star in all_stars:
        logger.info(f"Found star with PartitionKey: {star.get('PartitionKey')}, RowKey: {star.get('RowKey')}")
    
    # Use the direct results since we've already fetched them
    return [{
        "id": star["RowKey"],
        "x": star["X"],
        "y": star["Y"],
        "message": star["Message"],
        "brightness": calculate_current_brightness(star["Brightness"], star["LastLiked"]),
        "last_liked": star["LastLiked"]
    } for star in all_stars]

# Custom active stars endpoint - specify this BEFORE the star_id endpoint to prevent route conflicts
@app.get("/stars/active", include_in_schema=True)
async def get_active_stars():
    """Get all stars that have been liked recently."""
    logger.info("Fetching active stars")
    
    try:
        # Get the current time and calculate cutoff
        current_time = datetime.now(dt.timezone.utc).timestamp()
        cutoff_time = current_time - settings.REDIS.POPULARITY_WINDOW
        logger.info(f"Current time: {current_time}, Cutoff time: {cutoff_time}")
        
        # Get all stars first, then filter
        try:
            all_stars = list(tables["Stars"].list_entities())
            logger.info(f"Retrieved {len(all_stars)} total stars")
        except Exception as e:
            logger.error(f"Error retrieving stars from table: {str(e)}")
            # Return empty list instead of error
            return []
        
        # Filter stars manually
        active_stars = []
        for star in all_stars:
            # Debug log to see what's in the star record
            logger.debug(f"Star: {star.get('RowKey')}, LastLiked: {star.get('LastLiked')}")
            
            # Check if LastLiked exists and is recent
            if "LastLiked" in star and star["LastLiked"] >= cutoff_time:
                try:
                    active_stars.append({
                        "id": star["RowKey"],
                        "x": star["X"],
                        "y": star["Y"],
                        "message": star["Message"],
                        "brightness": calculate_current_brightness(star["Brightness"], star["LastLiked"]),
                        "last_liked": star["LastLiked"]
                    })
                except Exception as star_error:
                    logger.warning(f"Error processing star {star.get('RowKey')}: {str(star_error)}")
                    continue
        
        logger.info(f"Found {len(active_stars)} active stars")
        
        # Try to cache the result if Redis is available
        if is_cache_initialized():
            try:
                await FastAPICache.get_backend().set(
                    "active_stars",
                    json.dumps(active_stars),
                    expire=300
                )
                logger.info("Cached active stars in Redis")
            except Exception as e:
                logger.warning(f"Failed to cache active stars: {str(e)}")
        
        # Return empty list if no active stars found
        return active_stars
        
    except Exception as e:
        logger.error(f"Unexpected error in get_active_stars: {str(e)}")
        # Return empty list instead of error for robustness
        return []

# Create a function to check if FastAPICache is properly initialized
def is_cache_initialized():
    try:
        return FastAPICache._backend is not None
    except Exception:
        return False

# Define get_star without the decorator
async def _get_star_impl(star_id: str):
    """Implementation of get_star without the cache decorator."""
    try:
        # Check if Redis is initialized and available
        redis = None
        recent_likes = None
        try:
            if is_cache_initialized():
                redis = FastAPICache.get_backend().client
                popularity_key = f"star_popularity:{star_id}"
                recent_likes = await redis.get(popularity_key)
        except Exception as redis_error:
            logger.warning(f"Redis error when getting star {star_id}: {str(redis_error)}")
            # Continue without Redis
        
        logger.info(f"Looking up star with id: {star_id}")
        
        # Try to find the star across all partition keys
        star = None
        all_entities = list(tables["Stars"].list_entities())
        
        for entity in all_entities:
            if entity.get("RowKey") == star_id:
                star = entity
                logger.info(f"Found star with PartitionKey: {star.get('PartitionKey')}")
                break
                
        if not star:
            logger.warning(f"Star with id {star_id} not found in any partition")
            raise HTTPException(status_code=404, detail="Star not found")
            
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
            "is_popular": recent_likes is not None and int(recent_likes) >= settings.REDIS.POPULARITY_THRESHOLD
        }

        # If star is popular and Redis is available, update cache with longer TTL
        if response["is_popular"] and redis is not None:
            try:
                await FastAPICache.get_backend().set(
                    f"star:{star_id}",
                    json.dumps(response),
                    expire=settings.REDIS.POPULAR_CACHE_TTL
                )
            except Exception as cache_error:
                logger.warning(f"Could not cache popular star {star_id}: {str(cache_error)}")
            
        return response
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving star {star_id}: {str(e)}")
        raise HTTPException(status_code=404, detail="Star not found")

# Define the endpoint with conditional caching
@app.get("/stars/{star_id}")
async def get_star(star_id: str):
    """Get a specific star with automatic caching if available."""
    if star_id == "active":
        logger.warning("get_star was called with 'active' as the star_id, which might indicate a routing issue")
        # This should not happen if routes are defined in the correct order
        # Return empty list to match the expected output of get_active_stars
        return []
        
    # Call the implementation directly without caching if Redis is not available
    return await _get_star_impl(star_id)

@app.post("/stars/{star_id}/like")
async def like_star(
    star_id: str, 
    _=Depends(
        RateLimiter(
            times=settings.API.RATE_LIMIT_TIMES, 
            seconds=settings.API.RATE_LIMIT_SECONDS
        ) if settings.ENVIRONMENT != "test" else None
    )
):
    """Like a star and update popularity metrics."""
    try:
        logger.info(f"Liking star with id: {star_id}")
        
        # Try to find the star across all partition keys
        star = None
        all_entities = list(tables["Stars"].list_entities())
        
        for entity in all_entities:
            if entity.get("RowKey") == star_id:
                star = entity
                logger.info(f"Found star to like with PartitionKey: {star.get('PartitionKey')}")
                break
                
        if not star:
            logger.warning(f"Star with id {star_id} not found in any partition")
            raise HTTPException(status_code=404, detail="Star not found")
            
        current_time = datetime.now(dt.timezone.utc).timestamp()
        
        # Update the star's brightness and last_liked time
        star["Brightness"] = min(100.0, star["Brightness"] + 20.0)
        star["LastLiked"] = current_time
        
        # Try to update popularity counter in Redis if available
        try:
            if is_cache_initialized():
                redis = FastAPICache.get_backend().client
                popularity_key = f"star_popularity:{star_id}"
                
                # Increment likes counter with expiry
                await redis.incr(popularity_key)
                await redis.expire(popularity_key, settings.REDIS.POPULARITY_WINDOW)
                
                # Try to invalidate the star's cache to force refresh
                try:
                    await FastAPICache.get_backend().delete(f"star:{star_id}")
                except Exception as cache_error:
                    logger.warning(f"Failed to invalidate cache for star {star_id}: {str(cache_error)}")
        except Exception as redis_error:
            logger.warning(f"Redis error during like operation for star {star_id}: {str(redis_error)}")
            # Continue without Redis functionality

        tables["Stars"].update_entity(star)
        
        # Push SSE event
        try:
            await star_event_queue.put({
                "event": "update",
                "star": {
                    "id": star_id,
                    "brightness": star["Brightness"],
                    "last_liked": current_time
                }
            })
        except Exception as sse_error:
            logger.warning(f"Failed to push SSE event for star {star_id}: {str(sse_error)}")
        
        return star
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error liking star {star_id}: {str(e)}")
        raise HTTPException(status_code=404, detail="Star not found")

def calculate_current_brightness(base_brightness: float, last_liked: float) -> float:
    time_since_liked = datetime.now(dt.timezone.utc).timestamp() - last_liked
    decay_factor = max(0.01, 1.0 - 0.01 * time_since_liked)
    return max(20.0, base_brightness * math.exp(-decay_factor * time_since_liked))

@app.get("/stars/popular")
async def get_popular_stars():
    """Get currently popular stars."""
    popular_stars = []
    
    # Check if Redis is available
    if not is_cache_initialized():
        logger.warning("Redis cache not initialized, cannot get popular stars")
        return popular_stars
        
    try:
        redis = FastAPICache.get_backend().client
        
        # Get all popularity counters
        keys = await redis.keys("star_popularity:*")
        
        for key in keys:
            star_id = key.split(":")[1]
            likes = int(await redis.get(key) or 0)
            
            if likes >= settings.REDIS.POPULARITY_THRESHOLD:
                try:
                    star = await _get_star_impl(star_id)
                    popular_stars.append(star)
                except HTTPException:
                    continue
                
        return sorted(popular_stars, key=lambda x: x["brightness"], reverse=True)
    except Exception as e:
        logger.error(f"Error getting popular stars: {str(e)}")
        return popular_stars

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
    # Check if Redis is available
    if not is_cache_initialized():
        logger.warning("Redis cache not initialized, cannot get cache stats")
        return {"status": "not available", "reason": "Redis cache not initialized"}
        
    try:
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
    except Exception as e:
        logger.error(f"Error getting cache stats: {str(e)}")
        return {"status": "error", "reason": str(e)}

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

##############################################################################
# 8) Azure Monitor Metrics
##############################################################################

if AZURE_MONITORING:
    try:
        # Only try to initialize if we have an instrumentation key
        exporter = metrics_exporter.new_metrics_exporter()
        stats_recorder = stats_module.StatsRecorder()
        logger.info("Azure Monitor metrics exporter initialized")
    except ValueError as e:
        logger.warning(f"Failed to initialize Azure Monitor: {str(e)}")
        logger.warning("Azure monitoring disabled - missing instrumentation key")
        AZURE_MONITORING = False
        exporter = None
        stats_recorder = None
else:
    exporter = None
    stats_recorder = None
    logger.info("Azure monitoring is disabled")

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
        "timestamp": datetime.now(dt.timezone.utc).timestamp()
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
    return {"status": "alive", "timestamp": datetime.now(dt.timezone.utc).timestamp()}

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
    uvicorn.run(app, host="0.0.0.0", port=settings.PORT)

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
# 16) Debug Endpoints
##############################################################################

@app.get("/debug/table-info")
async def debug_table_info():
    """Debug endpoint to get information about the tables."""
    result = {
        "tables": list(tables.keys()),
        "stars_count": 0,
        "connection_info": {
            "using_managed_identity": settings.AZURE.USE_MANAGED_IDENTITY,
            "account_url": settings.AZURE.ACCOUNT_URL,
            "has_connection_string": bool(settings.AZURE.CONNECTION_STRING)
        }
    }
    
    # Try to count stars
    try:
        all_stars = list(tables["Stars"].list_entities())
        result["stars_count"] = len(all_stars)
        result["stars_details"] = []
        
        for star in all_stars:
            result["stars_details"].append({
                "partition_key": star.get("PartitionKey"),
                "row_key": star.get("RowKey"),
                "properties": list(star.keys())
            })
    except Exception as e:
        result["error"] = str(e)
    
    return result

@app.get("/debug/active-stars")
async def debug_active_stars():
    """Debug endpoint to diagnose issues with active stars."""
    result = {
        "status": "running",
        "cutoff_info": {},
        "stars_raw": [],
        "stars_count": 0,
        "errors": []
    }
    
    try:
        # Get current time and calculate cutoff
        current_time = datetime.now(dt.timezone.utc).timestamp()
        cutoff_time = current_time - settings.REDIS.POPULARITY_WINDOW
        result["cutoff_info"] = {
            "current_time": current_time,
            "cutoff_time": cutoff_time,
            "window_seconds": settings.REDIS.POPULARITY_WINDOW
        }
        
        # Get stars without filtering
        try:
            all_stars = list(tables["Stars"].list_entities())
            result["stars_count"] = len(all_stars)
            
            # Include basic info about each star
            for star in all_stars:
                star_info = {
                    "id": star.get("RowKey"),
                    "partition_key": star.get("PartitionKey"),
                    "has_lastliked": "LastLiked" in star,
                    "lastliked_value": star.get("LastLiked"),
                    "would_be_active": "LastLiked" in star and star["LastLiked"] >= cutoff_time
                }
                result["stars_raw"].append(star_info)
                
        except Exception as e:
            result["errors"].append(f"Error listing stars: {str(e)}")
        
        return result
        
    except Exception as e:
        result["errors"].append(f"Unexpected error: {str(e)}")
        result["status"] = "error"
        return result

@app.post("/debug/add-test-star")
async def debug_add_test_star():
    """Debug endpoint to add a test star and immediately try to retrieve it."""
    # Generate a unique ID for tracing
    debug_id = str(uuid.uuid4())[:8]
    
    # Step 1: Add a star with a debug message
    current_time = datetime.now(dt.timezone.utc).timestamp()
    star_entity = {
        "PartitionKey": f"STAR_{datetime.now(dt.timezone.utc).strftime('%Y%m')}",
        "RowKey": f"debug-{debug_id}",
        "X": 0.1,
        "Y": 0.2,
        "Message": f"Debug star created at {datetime.now(dt.timezone.utc).isoformat()}",
        "Brightness": 100.0,
        "LastLiked": current_time,
        "CreatedAt": current_time
    }
    
    result = {
        "debug_id": debug_id,
        "created": None,
        "retrieved_direct": None,
        "retrieved_api": None,
        "all_stars_count": 0,
        "errors": []
    }
    
    # Step 2: Create the star
    try:
        tables["Stars"].create_entity(star_entity)
        result["created"] = {
            "partition_key": star_entity["PartitionKey"],
            "row_key": star_entity["RowKey"]
        }
    except Exception as e:
        result["errors"].append(f"Creation error: {str(e)}")
    
    # Step 3: Try to retrieve directly
    try:
        time.sleep(1)  # Wait a moment for the entity to be available
        all_stars = list(tables["Stars"].list_entities())
        result["all_stars_count"] = len(all_stars)
        
        for star in all_stars:
            if star.get("RowKey") == f"debug-{debug_id}":
                result["retrieved_direct"] = {
                    "partition_key": star.get("PartitionKey"),
                    "row_key": star.get("RowKey"),
                    "message": star.get("Message")
                }
                break
    except Exception as e:
        result["errors"].append(f"Direct retrieval error: {str(e)}")
    
    # Step 4: Try to retrieve via API
    try:
        stars_response = await get_stars()
        result["stars_api_response_length"] = len(stars_response)
        
        for star in stars_response:
            if star.get("id") == f"debug-{debug_id}":
                result["retrieved_api"] = {
                    "id": star.get("id"),
                    "message": star.get("message")
                }
                break
    except Exception as e:
        result["errors"].append(f"API retrieval error: {str(e)}")
    
    return result