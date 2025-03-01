from typing import Optional, Protocol
from fastapi import Depends
from fastapi_cache import FastAPICache

from src.config.settings import settings
from src.db.redis_cache import is_cache_initialized

# Database provider interface
class DatabaseProvider(Protocol):
    async def get_star(self, star_id: str):
        ...
    
    async def create_star(self, star_data):
        ...
    
    # Define other operations

# Dependency injection
def get_redis():
    """Dependency to get Redis client if available"""
    if is_cache_initialized():
        return FastAPICache.get_backend().client
    return None

def get_table_storage():
    """Dependency to get Table Storage client"""
    from src.db.azure_tables import tables
    return tables
