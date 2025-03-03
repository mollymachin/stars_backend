from fastapi import APIRouter, HTTPException
import logging
import time
import uuid
from datetime import datetime
import datetime as dt

from src.config.settings import settings
from src.db.azure_tables import tables
from src.db.redis_cache import is_cache_initialized
from fastapi_cache import FastAPICache
from src.api.stars import get_stars

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/table-info")
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

@router.get("/active-stars")
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

@router.post("/add-test-star")
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

@router.get("/cache-stats")
async def debug_cache_stats():
    """Debug endpoint to get Redis cache statistics."""
    if not is_cache_initialized():
        return {"status": "not available", "reason": "Redis cache not initialized"}
    
    try:
        redis = FastAPICache.get_backend().client
        info = await redis.info()
        
        return {
            "status": "available",
            "hits": info.get("keyspace_hits", 0),
            "misses": info.get("keyspace_misses", 0),
            "hit_rate": info.get("keyspace_hits", 0) / 
                      (info.get("keyspace_hits", 0) + info.get("keyspace_misses", 1)),
            "keys": len(await redis.keys("*")),
            "memory_used": info.get("used_memory_human", "unknown")
        }
    except Exception as e:
        logger.error(f"Error getting cache stats: {str(e)}")
        return {"status": "error", "reason": str(e)}
