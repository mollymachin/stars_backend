import time
import logging
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

async def request_timing_middleware(request: Request, call_next):
    """Middleware to log request timing information"""
    start_time = time.time()
    
    try:
        response = await call_next(request)
        
        # Calculate request duration
        duration = time.time() - start_time
        response.headers["X-Process-Time"] = str(duration)
        
        # Log request details
        logger.info(f"{request.method} {request.url.path} completed in {duration:.3f}s with status {response.status_code}")
        
        return response
    except Exception as e:
        logger.error(f"Error processing request: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"}
        )

async def error_handling_middleware(request: Request, call_next):
    """Global error handling middleware"""
    try:
        return await call_next(request)
    except Exception as e:
        logger.exception(f"Unhandled exception: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"}
        )

def register_middleware(app: FastAPI):
    """Register all middleware with the FastAPI application"""
    # Add middleware in reverse order (last added = first executed)
    app.middleware("http")(error_handling_middleware)
    app.middleware("http")(request_timing_middleware)
