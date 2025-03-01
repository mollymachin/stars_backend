import os
import logging
from fastapi import APIRouter, HTTPException, Header, Depends, Security
from fastapi.security.api_key import APIKeyHeader, APIKey
from typing import Optional

from src.db.azure_tables import tables
from src.api.sse import star_event_queue
from src.config.settings import settings

router = APIRouter()
logger = logging.getLogger(__name__)

API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

# Load admin API key from environment variables
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "")
if not ADMIN_API_KEY and settings.ENVIRONMENT != "development":
    logger.warning("ADMIN_API_KEY not set. Admin endpoints will be inaccessible!")

async def get_api_key(api_key: str = Security(api_key_header)):
    """Validate the API key and return it if valid"""
    if not ADMIN_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="API key authentication is not configured"
        )
    
    if api_key == ADMIN_API_KEY:
        return api_key
    
    raise HTTPException(
        status_code=401,
        detail="Invalid API Key"
    )

@router.delete("/stars", dependencies=[Depends(get_api_key)])
async def remove_all_stars():
    """
    Remove all stars and push an SSE event
    """
    logger.warning("Admin endpoint called: remove_all_stars")
    
    # Count stars before deletion
    stars_list = list(tables["Stars"].list_entities())
    count = len(stars_list)
    
    # Delete each star
    for star in stars_list:
        try:
            tables["Stars"].delete_entity(star["PartitionKey"], star["RowKey"])
        except Exception as e:
            logger.error(f"Error deleting star {star.get('RowKey')}: {str(e)}")
    
    # Push SSE event
    try:
        await star_event_queue.put({
            "event": "remove_all"
        })
    except Exception as e:
        logger.error(f"Error pushing SSE event for remove_all_stars: {str(e)}")

    return {
        "message": f"All stars removed ({count} total)",
        "count": count
    }

@router.get("/status", dependencies=[Depends(get_api_key)])
async def admin_status():
    """Get admin status and environment information"""
    return {
        "admin_configured": bool(ADMIN_API_KEY),
        "environment": settings.ENVIRONMENT,
        "host": settings.HOST_NAME
    }
