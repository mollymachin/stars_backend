from fastapi import APIRouter, Response
from fastapi.responses import JSONResponse
import logging
from datetime import datetime
import datetime as dt

from src.config.settings import settings
from src.db.azure_tables import tables
from src.db.redis_cache import is_cache_initialized
from fastapi_cache import FastAPICache

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/")
async def health_check():
    """Basic health check endpoint"""
    return {
        "status": "healthy",
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "timestamp": datetime.now(dt.timezone.utc).timestamp()
    }

@router.get("/readiness")
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
        if is_cache_initialized():
            health_status["services"]["redis"] = "healthy"
        else:
            health_status["services"]["redis"] = "not configured"
    except Exception as e:
        logger.warning(f"Redis check failed: {str(e)}")
        health_status["services"]["redis"] = f"unhealthy: {str(e)}"
        # Don't fail readiness just because Redis is down - app can function without it
    
    status_code = 200 if health_status["status"] == "ready" else 503
    return JSONResponse(status_code=status_code, content=health_status)

@router.get("/liveness")
async def liveness_check():
    """
    Liveness probe for container orchestrators.
    Simple check to verify the application is running.
    """
    return {
        "status": "alive", 
        "timestamp": datetime.now(dt.timezone.utc).timestamp()
    }
