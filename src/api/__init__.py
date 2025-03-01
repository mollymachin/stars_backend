"""
API routes for the Star Map API.
"""

from src.api.stars import router as stars_router
from src.api.users import router as users_router
from src.api.health import router as health_router
from src.api.debug import router as debug_router
from src.api.admin import router as admin_router
from src.api.sse import router as sse_router

__all__ = [
    "stars_router",
    "users_router",
    "health_router",
    "debug_router",
    "admin_router",
    "sse_router"
]
